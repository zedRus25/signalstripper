from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from signalstripper.schema.registry import SchemaProfile


@dataclass
class SizeAttribution:
    thread_id: int
    recipient_display: str
    total_bytes: int
    attachment_bytes: int
    message_count: int
    oldest_message_ts: int
    newest_message_ts: int
    breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class GlobalSummary:
    db_path: str
    db_size_bytes: int
    schema_version: int
    page_size: int
    page_count: int
    freelist_count: int
    threads: list[SizeAttribution]
    table_sizes: dict[str, int]
    total_attachment_bytes: int


def analyze(db_path: Path, profile: SchemaProfile) -> GlobalSummary:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist_count = conn.execute("PRAGMA freelist_count").fetchone()[0]
        db_size_bytes = page_size * page_count

        # Per-table page estimates via sqlite_master + dbstat if available
        table_sizes = _table_sizes(conn, page_size)

        threads = _thread_attributions(conn, profile)
        total_attachment_bytes = sum(t.attachment_bytes for t in threads)

        return GlobalSummary(
            db_path=str(db_path),
            db_size_bytes=db_size_bytes,
            schema_version=profile.version,
            page_size=page_size,
            page_count=page_count,
            freelist_count=freelist_count,
            threads=threads,
            table_sizes=table_sizes,
            total_attachment_bytes=total_attachment_bytes,
        )
    finally:
        conn.close()


def _table_sizes(conn: sqlite3.Connection, page_size: int) -> dict[str, int]:
    try:
        rows = conn.execute(
            "SELECT name, sum(pageno) as pages FROM dbstat GROUP BY name"
        ).fetchall()
        # dbstat.pageno is 1-based page number; what we want is page count per table
        rows = conn.execute(
            "SELECT name, count(*) as pages FROM dbstat GROUP BY name"
        ).fetchall()
        return {row[0]: row[1] * page_size for row in rows}
    except sqlite3.OperationalError:
        # dbstat not available in this SQLite build
        return {}


def _thread_attributions(conn: sqlite3.Connection, profile: SchemaProfile) -> list[SizeAttribution]:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # Collect threads
    thread_rows = conn.execute(
        "SELECT t._id, r.phone, r.profile_joined_name, r.group_id "
        "FROM thread t LEFT JOIN recipient r ON t.recipient_id = r._id"
    ).fetchall()

    attributions = []
    for row in thread_rows:
        thread_id = row[0]
        display = _recipient_display(row[1], row[2], row[3])

        msg_count, oldest, newest = _message_stats(conn, thread_id, tables)
        attachment_bytes, breakdown = _attachment_stats(conn, thread_id, profile)

        total = attachment_bytes  # future: add body bytes if needed

        attributions.append(SizeAttribution(
            thread_id=thread_id,
            recipient_display=display,
            total_bytes=total,
            attachment_bytes=attachment_bytes,
            message_count=msg_count,
            oldest_message_ts=oldest,
            newest_message_ts=newest,
            breakdown=breakdown,
        ))

    attributions.sort(key=lambda a: a.total_bytes, reverse=True)
    return attributions


def _recipient_display(phone: str | None, name: str | None, group_id: str | None) -> str:
    if name:
        return name
    if phone:
        return phone
    if group_id:
        return f"Group:{group_id[:8]}"
    return "Unknown"


def _message_stats(
    conn: sqlite3.Connection, thread_id: int, tables: set[str]
) -> tuple[int, int, int]:
    count = 0
    oldest = 0
    newest = 0

    for tbl in ("sms", "mms"):
        if tbl not in tables:
            continue
        row = conn.execute(
            f"SELECT count(*), min(date), max(date) FROM {tbl} WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row and row[0]:
            count += row[0]
            if row[1]:
                oldest = row[1] if oldest == 0 else min(oldest, row[1])
            if row[2]:
                newest = max(newest, row[2])

    return count, oldest, newest


def _attachment_stats(
    conn: sqlite3.Connection, thread_id: int, profile: SchemaProfile
) -> tuple[int, dict[str, int]]:
    query = profile.size_queries.get("attachments_by_thread")
    if not query:
        return 0, {}

    try:
        rows = conn.execute(query, (thread_id,)).fetchall()
    except sqlite3.OperationalError:
        return 0, {}

    total = 0
    breakdown: dict[str, int] = {}
    for row in rows:
        size = row[1] or 0
        ct = row[2] or "application/octet-stream"
        bucket = ct.split("/")[0] if "/" in ct else ct
        total += size
        breakdown[bucket] = breakdown.get(bucket, 0) + size

    return total, breakdown
