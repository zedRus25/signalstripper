from __future__ import annotations

# Mock data calibrated to actual user profile:
#   120 k total messages · max 3 MB per attachment · ~5 GB total OS-reported storage
#
# Signal Android stores full-size attachments as external encrypted files;
# the SQLite DB (via PRAGMA page_count) is ~1.5 GB.  The parts/attachment
# table records data_size for each file.  total_attachment_bytes below is
# the sum of those data_size values (~2.8 GB), which is what the reclaim
# tally is based on.  OS total (DB + attachment files + app overhead) ≈ 5 GB.

import time
from signalstripper.analyze import GlobalSummary, SizeAttribution
from signalstripper.browse import MessagePage, ThreadSummary
from signalstripper.schema.registry import SchemaProfile

_NOW_MS = int(time.time() * 1000)
_DAY = 86_400_000
_MB = 1_000_000


def mock_profile() -> SchemaProfile:
    return SchemaProfile(
        version=166,
        description="Mock (no DB required)",
        required_tables={},
        size_queries={},
    )


def mock_summary() -> GlobalSummary:
    # 9 threads totalling 120 k messages, 4 150 attachments, 2.81 GB attachments
    # max individual attachment = 3 MB  (Signal-compressed images / voice notes)
    threads = [
        SizeAttribution(
            thread_id=1,
            recipient_display="Alice Chen",
            total_bytes=998 * _MB,
            attachment_bytes=998 * _MB,
            message_count=32_000,
            oldest_message_ts=_NOW_MS - 4 * 365 * _DAY,
            newest_message_ts=_NOW_MS - _DAY,
            # 1 100 imgs avg 870 KB + 100 voice avg 130 KB
            breakdown={"image": 957 * _MB, "audio": 13 * _MB},
        ),
        SizeAttribution(
            thread_id=2,
            recipient_display="Family 👨‍👩‍👧‍👦",
            total_bytes=838 * _MB,
            attachment_bytes=838 * _MB,
            message_count=38_000,
            oldest_message_ts=_NOW_MS - 5 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 2 * _DAY,
            # 1 200 imgs avg 620 KB + 80 short vids avg 1.9 MB (under 3 MB cap)
            breakdown={"image": 686 * _MB, "video": 152 * _MB},
        ),
        SizeAttribution(
            thread_id=3,
            recipient_display="Hiking Club 🏔",
            total_bytes=441 * _MB,
            attachment_bytes=441 * _MB,
            message_count=9_500,
            oldest_message_ts=_NOW_MS - 3 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 3 * _DAY,
            # 350 imgs avg 1.26 MB (outdoor full-res, Signal max ~3 MB)
            breakdown={"image": 441 * _MB},
        ),
        SizeAttribution(
            thread_id=4,
            recipient_display="Work Team",
            total_bytes=188 * _MB,
            attachment_bytes=188 * _MB,
            message_count=18_000,
            oldest_message_ts=_NOW_MS - 4 * 365 * _DAY,
            newest_message_ts=_NOW_MS,
            # 600 docs avg 230 KB + 80 screenshots avg 550 KB
            breakdown={"application": 138 * _MB, "image": 44 * _MB},
        ),
        SizeAttribution(
            thread_id=5,
            recipient_display="Bob Müller",
            total_bytes=167 * _MB,
            attachment_bytes=167 * _MB,
            message_count=11_500,
            oldest_message_ts=_NOW_MS - 6 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 90 * _DAY,
            # 250 imgs avg 580 KB + 40 short clips avg 800 KB
            breakdown={"image": 145 * _MB, "video": 32 * _MB},
        ),
        SizeAttribution(
            thread_id=6,
            recipient_display="Priya Sharma",
            total_bytes=82 * _MB,
            attachment_bytes=82 * _MB,
            message_count=5_500,
            oldest_message_ts=_NOW_MS - 3 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 45 * _DAY,
            breakdown={"image": 55 * _MB, "application": 27 * _MB},
        ),
        SizeAttribution(
            thread_id=7,
            recipient_display="Carlos Rivera",
            total_bytes=18 * _MB,
            attachment_bytes=18 * _MB,
            message_count=3_000,
            oldest_message_ts=_NOW_MS - 2 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 10 * _DAY,
            # 150 voice notes avg 120 KB
            breakdown={"audio": 18 * _MB},
        ),
        SizeAttribution(
            thread_id=8,
            recipient_display="Signal News",
            total_bytes=22 * _MB,
            attachment_bytes=22 * _MB,
            message_count=1_500,
            oldest_message_ts=_NOW_MS - 2 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 14 * _DAY,
            breakdown={"image": 22 * _MB},
        ),
        SizeAttribution(
            thread_id=9,
            recipient_display="Old Friends",
            total_bytes=57 * _MB,
            attachment_bytes=57 * _MB,
            message_count=1_000,
            oldest_message_ts=_NOW_MS - 7 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 365 * _DAY,
            breakdown={"image": 42 * _MB, "application": 15 * _MB},
        ),
    ]
    # Verify: sum(message_count) = 120 000
    # 32k + 38k + 9.5k + 18k + 11.5k + 5.5k + 3k + 1.5k + 1k = 120 000 ✓
    # Verify: total_attachment_bytes ≈ 2.81 GB (Signal files, not counting SQLite)

    total_attach = sum(t.attachment_bytes for t in threads)  # 2 811 MB

    # SQLite DB file (page_count × page_size):
    #   sms + mms text, FTS search index, thumbnail blobs, metadata ≈ 1.5 GB
    db_sqlite_bytes = 1_520 * _MB
    page_size = 4096
    page_count = db_sqlite_bytes // page_size        # 390 625

    return GlobalSummary(
        db_path="/data/user/0/org.thoughtcrime.securesms/databases/signal.db",
        db_size_bytes=db_sqlite_bytes,
        schema_version=166,
        page_size=page_size,
        page_count=page_count,
        freelist_count=48_000,          # ~187 MB free / reclaimed by VACUUM
        threads=threads,
        table_sizes={
            # Approximate page counts × page_size per table
            "sms":                  148 * _MB,
            "mms":                  198 * _MB,
            "fts_message_content":  392 * _MB,   # full-text search index
            "fts_message_segments": 74 * _MB,
            "fts_message_docsize":  14 * _MB,
            "part":                 48 * _MB,    # metadata rows; actual files external
            "thread":               1 * _MB,
            "recipient":            1 * _MB,
        },
        total_attachment_bytes=total_attach,
    )


# ── Browse helpers for mock mode ──────────────────────────────────────────────

def _mock_thread_summaries(summary: GlobalSummary) -> list[ThreadSummary]:
    # avg attachment size: 2.81 GB / ~4 150 total ≈ 680 KB
    _AVG_ATTACH = 680_000
    return [
        ThreadSummary(
            thread_id=t.thread_id,
            recipient_display=t.recipient_display,
            message_count=t.message_count,
            attachment_count=max(1, round(t.attachment_bytes / _AVG_ATTACH)),
            date_range=(t.oldest_message_ts, t.newest_message_ts),
        )
        for t in summary.threads
    ]


_SAMPLE_BODIES = [
    "Hey, how's it going?",
    "Did you see that photo I sent?",
    "Can we meet tomorrow?",
    "LOL 😂",
    "On my way!",
    "Check this out",
    "Sounds good to me",
    "Sorry, busy right now",
    "Let me know when you're free",
    "👍",
    "Miss you! 🙂",
    "That's hilarious",
    "Are you around later?",
    "Just got back",
    "Perfect, see you then",
]


def mock_messages(thread_id: int) -> MessagePage:
    import random
    rng = random.Random(thread_id)
    messages = []
    for i in range(20):
        ts = _NOW_MS - i * rng.randint(1, 6) * 3_600_000
        messages.append({
            "_id": i + 1,
            "date": ts,
            "body": rng.choice(_SAMPLE_BODIES),
            "type": 1 if i % 3 else 2,
            "source": "sms" if i % 5 else "mms",
        })
    return MessagePage(thread_id=thread_id, messages=messages, cursor=None)
