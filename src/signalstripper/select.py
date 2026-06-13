from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from signalstripper.analyze import GlobalSummary


@dataclass
class ThreadSelection:
    thread_id: int
    intent: Literal["strip_attachments", "remove_thread"]
    date_after: int | None = None
    date_before: int | None = None
    min_size_bytes: int | None = None
    content_types: list[str] = field(default_factory=list)


@dataclass
class SelectionSet:
    selections: list[ThreadSelection] = field(default_factory=list)


def estimate_reclaim(selection: SelectionSet, summary: GlobalSummary) -> int:
    thread_index = {t.thread_id: t for t in summary.threads}
    total = 0
    for sel in selection.selections:
        attr = thread_index.get(sel.thread_id)
        if attr is None:
            continue
        if sel.intent == "remove_thread":
            total += attr.total_bytes
        elif sel.intent == "strip_attachments":
            if not sel.content_types:
                total += attr.attachment_bytes
            else:
                for ct_prefix in sel.content_types:
                    bucket = ct_prefix.rstrip("/*").split("/")[0]
                    total += attr.breakdown.get(bucket, 0)
    return total


def to_cli_args(selection: SelectionSet) -> list[str]:
    args: list[str] = []
    for sel in selection.selections:
        if sel.intent == "strip_attachments":
            args.append(f"--remove-attachments-from-thread")
            args.append(str(sel.thread_id))
            if sel.date_before is not None:
                args.append("--before-date")
                args.append(str(sel.date_before))
            if sel.date_after is not None:
                args.append("--after-date")
                args.append(str(sel.date_after))
            if sel.min_size_bytes is not None:
                args.append("--onlylargerthan")
                args.append(str(sel.min_size_bytes))
        elif sel.intent == "remove_thread":
            args.append("--remove-thread")
            args.append(str(sel.thread_id))
    return args
