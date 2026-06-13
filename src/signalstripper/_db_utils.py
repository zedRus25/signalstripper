from __future__ import annotations

import sqlite3


def recipient_display(phone: str | None, name: str | None, group_id: str | None) -> str:
    if name:
        return name
    if phone:
        return phone
    if group_id:
        return f"Group:{group_id[:8]}"
    return "Unknown"


def message_stats(
    conn: sqlite3.Connection, thread_id: int, tables: set[str]
) -> tuple[int, int, int, int]:
    """Return (message_count, oldest_ts, newest_ts, body_bytes) for a thread.

    body_bytes is the summed byte length of message text across the sms/mms
    tables, used to attribute a thread's non-attachment footprint.
    """
    count, oldest, newest, body_bytes = 0, 0, 0, 0
    for tbl in ("sms", "mms"):
        if tbl not in tables:
            continue
        row = conn.execute(
            f"SELECT count(*), min(date), max(date), sum(length(body)) "
            f"FROM {tbl} WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row and row[0]:
            count += row[0]
            if row[1]:
                oldest = row[1] if oldest == 0 else min(oldest, row[1])
            if row[2]:
                newest = max(newest, row[2])
            body_bytes += row[3] or 0
    return count, oldest, newest, body_bytes
