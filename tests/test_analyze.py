import os
import sqlite3
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze, _table_sizes

# Named constants derived from tests/fixtures/build_fixture_db.py
# Thread 10: image/jpeg 1.5 MB + video/mp4 8 MB
# Thread 20: application/pdf 200 KB
# Thread 30: image/png 3 MB + video/mp4 12 MB
THREAD_10_BYTES = 1_500_000 + 8_000_000
THREAD_20_BYTES = 200_000
THREAD_30_BYTES = 3_000_000 + 12_000_000
TOTAL_ATTACHMENT_BYTES = THREAD_10_BYTES + THREAD_20_BYTES + THREAD_30_BYTES


@pytest.fixture
def summary(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    return analyze(db_v166, result.profile), db_v166


def test_total_attachment_bytes(summary):
    s, _ = summary
    assert s.total_attachment_bytes == TOTAL_ATTACHMENT_BYTES


def test_thread_count(summary):
    s, _ = summary
    assert len(s.threads) == 3


def test_schema_version(summary):
    s, _ = summary
    assert s.schema_version == 166


def test_no_writes_to_db(summary):
    s, db_path = summary
    mtime_before = os.path.getmtime(db_path)
    profiles = load_profiles()
    from signalstripper.schema.introspect import introspect as intr
    result = intr(db_path, profiles)
    analyze(db_path, result.profile)
    mtime_after = os.path.getmtime(db_path)
    assert mtime_before == mtime_after, "analyze() must not modify the DB file"


def test_threads_sorted_by_size_descending(summary):
    s, _ = summary
    sizes = [t.total_bytes for t in s.threads]
    assert sizes == sorted(sizes, reverse=True)


def test_breakdown_keys_are_mime_prefixes(summary):
    s, _ = summary
    for thread in s.threads:
        for key in thread.breakdown:
            assert "/" not in key, f"breakdown key should be MIME prefix only, got {key!r}"


def test_per_thread_attachment_bytes(summary):
    s, _ = summary
    by_id = {t.thread_id: t for t in s.threads}
    assert by_id[10].attachment_bytes == THREAD_10_BYTES
    assert by_id[20].attachment_bytes == THREAD_20_BYTES
    assert by_id[30].attachment_bytes == THREAD_30_BYTES


def test_per_thread_breakdown(summary):
    s, _ = summary
    by_id = {t.thread_id: t for t in s.threads}
    assert by_id[10].breakdown == {"image": 1_500_000, "video": 8_000_000}
    assert by_id[20].breakdown == {"application": 200_000}
    assert by_id[30].breakdown == {"image": 3_000_000, "video": 12_000_000}


def test_table_sizes_fallback_when_dbstat_unavailable():
    """When dbstat raises OperationalError, _table_sizes returns {} without crashing."""
    class NoDbstatConn:
        def execute(self, sql, *args, **kwargs):
            if "dbstat" in sql:
                raise sqlite3.OperationalError("no such table: dbstat")
            raise AssertionError(f"Unexpected query: {sql}")

    result = _table_sizes(NoDbstatConn(), page_size=4096)
    assert result == {}
