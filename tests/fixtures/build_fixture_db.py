#!/usr/bin/env python3
"""
Script to generate synthetic Signal SQLite fixture databases for testing.
Run: python tests/fixtures/build_fixture_db.py
Outputs: tests/fixtures/signal_v166.db
"""
import sqlite3
import time
from pathlib import Path

OUT_DIR = Path(__file__).parent
NOW_MS = int(time.time() * 1000)
DAY_MS = 86_400_000


def build_v166(path: Path) -> None:
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 166")

    conn.executescript("""
        CREATE TABLE recipient (
            _id                INTEGER PRIMARY KEY,
            phone              TEXT,
            profile_joined_name TEXT,
            group_id           TEXT
        );
        CREATE TABLE thread (
            _id          INTEGER PRIMARY KEY,
            recipient_id INTEGER NOT NULL,
            date         INTEGER,
            snippet      TEXT
        );
        CREATE TABLE sms (
            _id       INTEGER PRIMARY KEY,
            thread_id INTEGER NOT NULL,
            date      INTEGER,
            body      TEXT,
            type      INTEGER
        );
        CREATE TABLE mms (
            _id       INTEGER PRIMARY KEY,
            thread_id INTEGER NOT NULL,
            date      INTEGER,
            body      TEXT,
            m_type    INTEGER
        );
        CREATE TABLE part (
            _id       INTEGER PRIMARY KEY,
            mid       INTEGER NOT NULL,
            ct        TEXT,
            data_size INTEGER,
            unique_id INTEGER
        );
    """)

    # Recipients
    conn.executemany(
        "INSERT INTO recipient (_id, phone, profile_joined_name, group_id) VALUES (?,?,?,?)",
        [
            (1, "+15550001111", "Alice", None),
            (2, "+15550002222", "Bob", None),
            (3, None, None, "group_abc123"),
        ],
    )

    # Threads
    conn.executemany(
        "INSERT INTO thread (_id, recipient_id, date, snippet) VALUES (?,?,?,?)",
        [
            (10, 1, NOW_MS - DAY_MS,    "Hey!"),
            (20, 2, NOW_MS - 2*DAY_MS,  "See you tomorrow"),
            (30, 3, NOW_MS - 7*DAY_MS,  "Group chat"),
        ],
    )

    # SMS messages
    sms_rows = []
    for i in range(10):
        sms_rows.append((i+1, 10, NOW_MS - i*DAY_MS, f"sms body {i}", 1))
    for i in range(10):
        sms_rows.append((i+11, 20, NOW_MS - (i+1)*DAY_MS, f"sms body {i}", 2))
    conn.executemany(
        "INSERT INTO sms (_id, thread_id, date, body, type) VALUES (?,?,?,?,?)", sms_rows
    )

    # MMS messages
    mms_rows = [
        (1, 10, NOW_MS - DAY_MS,     "image msg",  128),
        (2, 10, NOW_MS - 2*DAY_MS,   "video msg",  128),
        (3, 20, NOW_MS - 3*DAY_MS,   "doc msg",    128),
        (4, 30, NOW_MS - 4*DAY_MS,   "group img",  128),
        (5, 30, NOW_MS - 5*DAY_MS,   "group vid",  128),
    ]
    conn.executemany(
        "INSERT INTO mms (_id, thread_id, date, body, m_type) VALUES (?,?,?,?,?)", mms_rows
    )

    # Attachments (part rows linked to mms)
    part_rows = [
        (1, 1, "image/jpeg",  1_500_000,  1001),
        (2, 2, "video/mp4",   8_000_000,  1002),
        (3, 3, "application/pdf", 200_000, 1003),
        (4, 4, "image/png",   3_000_000,  1004),
        (5, 5, "video/mp4",  12_000_000,  1005),
    ]
    conn.executemany(
        "INSERT INTO part (_id, mid, ct, data_size, unique_id) VALUES (?,?,?,?,?)", part_rows
    )

    conn.commit()
    conn.close()
    print(f"Written: {path}")


if __name__ == "__main__":
    build_v166(OUT_DIR / "signal_v166.db")
