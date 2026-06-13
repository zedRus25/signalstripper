from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from signalstripper._db_utils import message_stats, recipient_display
from signalstripper.schema.registry import SchemaProfile


def _decode_cursor(cursor: str | None) -> int:
    """Decode an opaque pagination cursor into a row offset.

    Raises ValueError on any malformed cursor so callers can surface a 4xx
    rather than an uncaught 500.
    """
    if not cursor:
        return 0
    try:
        offset = json.loads(base64.b64decode(cursor).decode())["offset"]
    except (ValueError, KeyError, TypeError) as exc:
        # binascii.Error and json.JSONDecodeError both subclass ValueError.
        raise ValueError("invalid cursor") from exc
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("invalid cursor")
    return offset


@dataclass
class ThreadSummary:
    thread_id: int
    recipient_display: str
    message_count: int
    attachment_count: int
    date_range: tuple[int, int]


@dataclass
class MessagePage:
    thread_id: int
    messages: list[dict]
    cursor: str | None


def list_threads(db_path: Path, profile: SchemaProfile) -> list[ThreadSummary]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT t._id, r.phone, r.profile_joined_name, r.group_id "
            "FROM thread t LEFT JOIN recipient r ON t.recipient_id = r._id "
            "ORDER BY t.date DESC"
        ).fetchall()

        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        summaries = []
        for row in rows:
            thread_id = row[0]
            display = recipient_display(row[1], row[2], row[3])
            msg_count, oldest, newest, _ = message_stats(conn, thread_id, tables)
            att_count = _attachment_count(conn, thread_id)
            summaries.append(ThreadSummary(
                thread_id=thread_id,
                recipient_display=display,
                message_count=msg_count,
                attachment_count=att_count,
                date_range=(oldest, newest),
            ))
        return summaries
    finally:
        conn.close()


def get_messages(
    db_path: Path,
    profile: SchemaProfile,
    thread_id: int,
    before: int | None = None,
    after: int | None = None,
    cursor: str | None = None,
    page_size: int = 50,
) -> MessagePage:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        offset = _decode_cursor(cursor)
        messages, has_more = _fetch_messages(conn, thread_id, before, after, offset, page_size)

        next_cursor = None
        if has_more:
            next_cursor = base64.b64encode(
                json.dumps({"offset": offset + len(messages)}).encode()
            ).decode()

        return MessagePage(thread_id=thread_id, messages=messages, cursor=next_cursor)
    finally:
        conn.close()


def _fetch_messages(
    conn: sqlite3.Connection,
    thread_id: int,
    before: int | None,
    after: int | None,
    offset: int,
    page_size: int,
) -> tuple[list[dict], bool]:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    parts: list[str] = []
    params: list = []
    for source in ("sms", "mms"):
        if source not in tables:
            continue
        type_col = "type" if source == "sms" else "m_type"
        clauses = ["thread_id = ?"]
        p: list = [thread_id]
        if before is not None:
            clauses.append("date < ?")
            p.append(before)
        if after is not None:
            clauses.append("date > ?")
            p.append(after)
        where = " AND ".join(clauses)
        parts.append(
            f"SELECT _id, date, body, {type_col} AS msg_type, '{source}' AS src "
            f"FROM {source} WHERE {where}"
        )
        params.extend(p)

    if not parts:
        return [], False

    union = " UNION ALL ".join(parts)
    # Deterministic total order: date DESC, src DESC ('sms' > 'mms'), _id DESC
    rows = conn.execute(
        f"SELECT _id, date, body, msg_type, src FROM ({union}) "
        f"ORDER BY date DESC, src DESC, _id DESC "
        f"LIMIT ? OFFSET ?",
        params + [page_size + 1, offset],
    ).fetchall()

    has_more = len(rows) > page_size
    rows = rows[:page_size]
    return [
        {"_id": r[0], "date": r[1], "body": r[2], "type": r[3], "source": r[4]}
        for r in rows
    ], has_more


def _attachment_count(conn: sqlite3.Connection, thread_id: int) -> int:
    try:
        row = conn.execute(
            "SELECT count(*) FROM part p JOIN mms m ON p.mid = m._id WHERE m.thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0
