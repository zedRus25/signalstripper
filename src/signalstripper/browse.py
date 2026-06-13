from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from signalstripper.schema.registry import SchemaProfile


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
            display = _recipient_display(row[1], row[2], row[3])
            msg_count, oldest, newest = _message_stats(conn, thread_id, tables)
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
        # Decode cursor: {"last_date": int, "last_id": int, "source": "sms"|"mms"}
        cursor_state = json.loads(base64.b64decode(cursor).decode()) if cursor else None

        messages = _fetch_messages(conn, thread_id, before, after, cursor_state, page_size)

        next_cursor = None
        if len(messages) == page_size:
            last = messages[-1]
            next_cursor = base64.b64encode(
                json.dumps({"last_date": last["date"], "last_id": last["_id"], "source": last["source"]}).encode()
            ).decode()

        return MessagePage(thread_id=thread_id, messages=messages, cursor=next_cursor)
    finally:
        conn.close()


def _fetch_messages(
    conn: sqlite3.Connection,
    thread_id: int,
    before: int | None,
    after: int | None,
    cursor_state: dict | None,
    page_size: int,
) -> list[dict]:
    results = []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    type_col = {"sms": "type", "mms": "m_type"}
    for source in ("sms", "mms"):
        if source not in tables:
            continue
        clauses = ["thread_id = ?"]
        params: list = [thread_id]
        if before is not None:
            clauses.append("date < ?")
            params.append(before)
        if after is not None:
            clauses.append("date > ?")
            params.append(after)
        if cursor_state:
            clauses.append("(date < ? OR (date = ? AND _id < ?))")
            params += [cursor_state["last_date"], cursor_state["last_date"], cursor_state["last_id"]]

        where = " AND ".join(clauses)
        col = type_col[source]
        rows = conn.execute(
            f"SELECT _id, date, body, {col} AS msg_type FROM {source} WHERE {where} ORDER BY date DESC LIMIT ?",
            params + [page_size],
        ).fetchall()

        for r in rows:
            results.append({"_id": r[0], "date": r[1], "body": r[2], "type": r[3], "source": source})

    results.sort(key=lambda m: (m["date"], m["_id"]), reverse=True)
    return results[:page_size]


def _message_stats(
    conn: sqlite3.Connection, thread_id: int, tables: set[str]
) -> tuple[int, int, int]:
    count, oldest, newest = 0, 0, 0
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


def _attachment_count(conn: sqlite3.Connection, thread_id: int) -> int:
    try:
        row = conn.execute(
            "SELECT count(*) FROM part p JOIN mms m ON p.mid = m._id WHERE m.thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def _recipient_display(phone: str | None, name: str | None, group_id: str | None) -> str:
    if name:
        return name
    if phone:
        return phone
    if group_id:
        return f"Group:{group_id[:8]}"
    return "Unknown"
