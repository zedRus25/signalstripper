from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from signalstripper._db_utils import message_stats, recipient_display
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
            "SELECT name, count(*) AS pages FROM dbstat GROUP BY name"
        ).fetchall()
        return {row[0]: row[1] * page_size for row in rows}
    except sqlite3.OperationalError:
        # dbstat virtual table not compiled into this SQLite build
        return {}


def _thread_attributions(conn: sqlite3.Connection, profile: SchemaProfile) -> list[SizeAttribution]:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    thread_rows = conn.execute(
        "SELECT t._id, r.phone, r.profile_joined_name, r.group_id "
        "FROM thread t LEFT JOIN recipient r ON t.recipient_id = r._id"
    ).fetchall()

    attributions = []
    for row in thread_rows:
        thread_id = row[0]
        display = recipient_display(row[1], row[2], row[3])
        msg_count, oldest, newest, body_bytes = message_stats(conn, thread_id, tables)
        attachment_bytes, breakdown = _attachment_stats(conn, thread_id, profile)

        attributions.append(SizeAttribution(
            thread_id=thread_id,
            recipient_display=display,
            total_bytes=attachment_bytes + body_bytes,
            attachment_bytes=attachment_bytes,
            message_count=msg_count,
            oldest_message_ts=oldest,
            newest_message_ts=newest,
            breakdown=breakdown,
        ))

    attributions.sort(key=lambda a: a.total_bytes, reverse=True)
    return attributions


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
