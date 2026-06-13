from __future__ import annotations

import time
from signalstripper.analyze import GlobalSummary, SizeAttribution
from signalstripper.browse import MessagePage, ThreadSummary
from signalstripper.schema.registry import SchemaProfile

_NOW_MS = int(time.time() * 1000)
_DAY = 86_400_000


def mock_profile() -> SchemaProfile:
    return SchemaProfile(
        version=166,
        description="Mock (no DB required)",
        required_tables={},
        size_queries={},
    )


def mock_summary() -> GlobalSummary:
    threads = [
        SizeAttribution(
            thread_id=1,
            recipient_display="Alice Chen",
            total_bytes=892_000_000,
            attachment_bytes=892_000_000,
            message_count=14_320,
            oldest_message_ts=_NOW_MS - 4 * 365 * _DAY,
            newest_message_ts=_NOW_MS - _DAY,
            breakdown={"image": 480_000_000, "video": 380_000_000, "audio": 32_000_000},
        ),
        SizeAttribution(
            thread_id=2,
            recipient_display="Family 👨‍👩‍👧‍👦",
            total_bytes=654_000_000,
            attachment_bytes=654_000_000,
            message_count=32_100,
            oldest_message_ts=_NOW_MS - 5 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 2 * _DAY,
            breakdown={"image": 420_000_000, "video": 180_000_000, "application": 54_000_000},
        ),
        SizeAttribution(
            thread_id=3,
            recipient_display="Work Team",
            total_bytes=411_000_000,
            attachment_bytes=411_000_000,
            message_count=8_760,
            oldest_message_ts=_NOW_MS - 3 * 365 * _DAY,
            newest_message_ts=_NOW_MS,
            breakdown={"application": 310_000_000, "image": 101_000_000},
        ),
        SizeAttribution(
            thread_id=4,
            recipient_display="Bob Müller",
            total_bytes=198_000_000,
            attachment_bytes=198_000_000,
            message_count=5_430,
            oldest_message_ts=_NOW_MS - 6 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 180 * _DAY,
            breakdown={"video": 140_000_000, "image": 58_000_000},
        ),
        SizeAttribution(
            thread_id=5,
            recipient_display="Signal News",
            total_bytes=88_000_000,
            attachment_bytes=88_000_000,
            message_count=1_200,
            oldest_message_ts=_NOW_MS - 2 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 30 * _DAY,
            breakdown={"image": 88_000_000},
        ),
        SizeAttribution(
            thread_id=6,
            recipient_display="Carlos Rivera",
            total_bytes=43_000_000,
            attachment_bytes=43_000_000,
            message_count=920,
            oldest_message_ts=_NOW_MS - 365 * _DAY,
            newest_message_ts=_NOW_MS - 10 * _DAY,
            breakdown={"audio": 43_000_000},
        ),
        SizeAttribution(
            thread_id=7,
            recipient_display="Hiking Club 🏔",
            total_bytes=310_000_000,
            attachment_bytes=310_000_000,
            message_count=6_800,
            oldest_message_ts=_NOW_MS - 2 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 5 * _DAY,
            breakdown={"image": 240_000_000, "video": 70_000_000},
        ),
        SizeAttribution(
            thread_id=8,
            recipient_display="Priya Sharma",
            total_bytes=120_000_000,
            attachment_bytes=120_000_000,
            message_count=3_100,
            oldest_message_ts=_NOW_MS - 3 * 365 * _DAY,
            newest_message_ts=_NOW_MS - 60 * _DAY,
            breakdown={"image": 75_000_000, "application": 45_000_000},
        ),
    ]
    total_attachment_bytes = sum(t.attachment_bytes for t in threads)
    return GlobalSummary(
        db_path="/mock/signal.db",
        db_size_bytes=7_370_000_000,
        schema_version=166,
        page_size=4096,
        page_count=1_799_316,
        freelist_count=95_000,
        threads=threads,
        table_sizes={
            "sms": 180_000_000,
            "mms": 320_000_000,
            "part": total_attachment_bytes,
            "thread": 512_000,
            "recipient": 128_000,
            "fts_message_content": 340_000_000,
            "fts_message_docsize": 12_000_000,
        },
        total_attachment_bytes=total_attachment_bytes,
    )


def _mock_thread_summaries(summary: GlobalSummary) -> list[ThreadSummary]:
    return [
        ThreadSummary(
            thread_id=t.thread_id,
            recipient_display=t.recipient_display,
            message_count=t.message_count,
            attachment_count=max(1, t.attachment_bytes // 500_000),
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
    "Sound good to me",
    "Sorry, busy right now",
    "Let me know when you're free",
    "👍",
]


def mock_messages(thread_id: int) -> MessagePage:
    import random
    rng = random.Random(thread_id)
    now = _NOW_MS
    messages = []
    for i in range(20):
        ts = now - i * 3 * 3600 * 1000
        messages.append({
            "_id": i + 1,
            "date": ts,
            "body": rng.choice(_SAMPLE_BODIES),
            "type": 1 if i % 3 else 2,
            "source": "sms" if i % 5 else "mms",
        })
    return MessagePage(thread_id=thread_id, messages=messages, cursor=None)
