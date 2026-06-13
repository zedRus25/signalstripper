from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
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


_VALID_INTENTS = frozenset({"strip_attachments", "remove_thread"})


def validate_selection(sel: ThreadSelection) -> None:
    if sel.intent not in _VALID_INTENTS:
        raise ValueError(f"Unknown intent {sel.intent!r}; expected one of {sorted(_VALID_INTENTS)}")


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


def to_cli_args(selection: SelectionSet, summary: GlobalSummary | None = None) -> list[str]:
    """Translate a SelectionSet into signalbackup-tools CLI arguments.

    Strip-attachment selections are batched by modifier fingerprint so that
    threads sharing the same date/size/type filters map to a single
    --replaceattachments invocation.

    Remove-thread selections produce --croptothreads with the complement
    set (all threads not being removed).  Requires summary to enumerate
    all thread IDs.
    """
    for sel in selection.selections:
        validate_selection(sel)

    args: list[str] = []

    # ── Strip-attachment selections ──────────────────────────────────────────
    strip_sels = [s for s in selection.selections if s.intent == "strip_attachments"]

    def _modifier_key(s: ThreadSelection) -> tuple:
        return (s.date_after, s.date_before, s.min_size_bytes, tuple(sorted(s.content_types)))

    for key, group_iter in groupby(sorted(strip_sels, key=_modifier_key), key=_modifier_key):
        group = list(group_iter)
        date_after, date_before, min_size_bytes, content_types = key

        thread_ids = ",".join(str(s.thread_id) for s in group)
        args += ["--replaceattachments", "--onlyinthreads", thread_ids]
        if date_before is not None:
            args += ["--onlyolderthan", str(date_before)]
        if date_after is not None:
            args += ["--onlynewerthan", str(date_after)]
        if min_size_bytes is not None:
            args += ["--onlylargerthan", str(min_size_bytes)]
        for ct in content_types:
            args += ["--onlytype", ct]

    # ── Remove-thread selections ─────────────────────────────────────────────
    remove_sels = [s for s in selection.selections if s.intent == "remove_thread"]
    if remove_sels:
        remove_ids = {s.thread_id for s in remove_sels}
        if summary is not None:
            keep_ids = [t.thread_id for t in summary.threads if t.thread_id not in remove_ids]
            if not keep_ids:
                raise ValueError("Selection would remove all threads — refusing to emit.")
            args += ["--croptothreads", ",".join(str(i) for i in keep_ids)]
        else:
            # No summary available: emit a placeholder the user must fill in
            args += [
                "--croptothreads",
                "<ALL_THREAD_IDS_EXCEPT_" + ",".join(str(i) for i in sorted(remove_ids)) + ">",
            ]

    return args
