import os
import sqlite3
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze, _table_sizes

# Named constants matching tests/fixtures/build_fixture_db.py
THREAD_10_BYTES = 1_500_000 + 8_000_000   # image/jpeg + video/mp4
THREAD_20_BYTES = 200_000                   # application/pdf
THREAD_30_BYTES = 3_000_000 + 12_000_000   # image/png + video/mp4
TOTAL_ATTACHMENT_BYTES = THREAD_10_BYTES + THREAD_20_BYTES + THREAD_30_BYTES


@pytest.fixture
def summary(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    return analyze(db_v166, result.profile), db_v166


def test_global_summary(summary):
    s, _ = summary
    assert s.total_attachment_bytes == TOTAL_ATTACHMENT_BYTES
    assert len(s.threads) == 3
    assert s.schema_version == 166


def test_no_writes_to_db(summary):
    s, db_path = summary
    mtime_before = os.path.getmtime(db_path)
    profiles = load_profiles()
    from signalstripper.schema.introspect import introspect as intr
    analyze(db_path, intr(db_path, profiles).profile)
    assert os.path.getmtime(db_path) == mtime_before, "analyze() must not modify the DB file"


def test_threads_sorted_by_size_descending(summary):
    s, _ = summary
    sizes = [t.total_bytes for t in s.threads]
    assert sizes == sorted(sizes, reverse=True)


def test_breakdown_keys_are_mime_prefixes(summary):
    s, _ = summary
    for thread in s.threads:
        for key in thread.breakdown:
            assert "/" not in key, f"breakdown key should be MIME prefix only, got {key!r}"


@pytest.mark.parametrize("thread_id,expected_bytes,expected_breakdown", [
    (10, THREAD_10_BYTES, {"image": 1_500_000, "video": 8_000_000}),
    (20, THREAD_20_BYTES, {"application": 200_000}),
    (30, THREAD_30_BYTES, {"image": 3_000_000, "video": 12_000_000}),
])
def test_per_thread_attribution(summary, thread_id, expected_bytes, expected_breakdown):
    s, _ = summary
    thread = next(t for t in s.threads if t.thread_id == thread_id)
    assert thread.attachment_bytes == expected_bytes
    assert thread.breakdown == expected_breakdown


def test_table_sizes_fallback_when_dbstat_unavailable():
    """When dbstat raises OperationalError, _table_sizes returns {} without crashing."""
    class NoDbstatConn:
        def execute(self, sql, *args, **kwargs):
            if "dbstat" in sql:
                raise sqlite3.OperationalError("no such table: dbstat")
            raise AssertionError(f"Unexpected query: {sql}")

    assert _table_sizes(NoDbstatConn(), page_size=4096) == {}
