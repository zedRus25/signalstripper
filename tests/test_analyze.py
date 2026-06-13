import os
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze


@pytest.fixture
def summary(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    return analyze(db_v166, result.profile), db_v166


def test_total_attachment_bytes(summary):
    s, _ = summary
    # Fixture has parts with data_size: 1_500_000 + 8_000_000 + 200_000 + 3_000_000 + 12_000_000
    assert s.total_attachment_bytes == 24_700_000


def test_thread_count(summary):
    s, _ = summary
    assert len(s.threads) == 3


def test_schema_version(summary):
    s, _ = summary
    assert s.schema_version == 166


def test_no_writes_to_db(summary):
    s, db_path = summary
    mtime_before = os.path.getmtime(db_path)
    # Re-run to confirm no write on second call
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
