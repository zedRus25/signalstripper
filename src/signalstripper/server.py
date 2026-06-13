from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from signalstripper.analyze import GlobalSummary
from signalstripper.emit import emit_reclaim_command
from signalstripper.schema.registry import SchemaProfile
from signalstripper.select import SelectionSet, ThreadSelection, validate_selection

_STATIC_DIR = Path(__file__).parent / "static"

ALLOWED_HOST = "127.0.0.1"


class NonLoopbackBindError(ValueError):
    pass


def create_app(db_path: Path, profile: SchemaProfile, summary: GlobalSummary, mock: bool = False) -> Starlette:
    state: dict[str, Any] = {"db_path": db_path, "profile": profile, "summary": summary, "mock": mock}

    async def analyze_endpoint(request: Request) -> Response:
        return JSONResponse(dataclasses.asdict(state["summary"]))

    async def threads_endpoint(request: Request) -> Response:
        if state.get("mock"):
            from signalstripper.mock import _mock_thread_summaries
            return JSONResponse([dataclasses.asdict(t) for t in _mock_thread_summaries(state["summary"])])
        from signalstripper.browse import list_threads
        threads = list_threads(state["db_path"], state["profile"])
        return JSONResponse([dataclasses.asdict(t) for t in threads])

    async def messages_endpoint(request: Request) -> Response:
        thread_id = int(request.path_params["thread_id"])
        if state.get("mock"):
            from signalstripper.mock import mock_messages
            page = mock_messages(thread_id)
            return JSONResponse(dataclasses.asdict(page))
        from signalstripper.browse import get_messages
        params = request.query_params
        page = get_messages(
            state["db_path"],
            state["profile"],
            thread_id,
            before=int(params["before"]) if "before" in params else None,
            after=int(params["after"]) if "after" in params else None,
            cursor=params.get("cursor"),
        )
        return JSONResponse(dataclasses.asdict(page))

    async def emit_endpoint(request: Request) -> Response:
        body = await request.json()
        raw_selections = body.get("selections", [])
        selections = []
        for sel in raw_selections:
            try:
                ts = ThreadSelection(
                    thread_id=int(sel["thread_id"]),
                    intent=sel["intent"],
                    date_after=sel.get("date_after"),
                    date_before=sel.get("date_before"),
                    min_size_bytes=sel.get("min_size_bytes"),
                    content_types=list(sel.get("content_types") or []),
                )
                validate_selection(ts)
            except (ValueError, KeyError, TypeError) as exc:
                return JSONResponse({"error": str(exc)}, status_code=422)
            selections.append(ts)
        sel_set = SelectionSet(selections=selections)
        output_path = Path(body.get("output_path", str(state["db_path"].with_suffix(".stripped.db"))))
        cmd = emit_reclaim_command(state["db_path"], output_path, sel_set, state["summary"])
        return Response(cmd, media_type="text/plain")

    routes = [
        Route("/api/analyze", analyze_endpoint),
        Route("/api/threads", threads_endpoint),
        Route("/api/threads/{thread_id:int}/messages", messages_endpoint),
        Route("/api/emit", emit_endpoint, methods=["POST"]),
        Mount("/", app=StaticFiles(directory=str(_STATIC_DIR), html=True)),
    ]

    return Starlette(routes=routes)


def serve(app: Starlette, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host != ALLOWED_HOST:
        raise NonLoopbackBindError(
            f"signalstripper refuses to bind to {host!r}. "
            f"Only {ALLOWED_HOST!r} is permitted."
        )
    import uvicorn
    uvicorn.run(app, host=host, port=port)
