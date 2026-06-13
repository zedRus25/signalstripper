import time
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.browse import list_threads, get_messages

# Thread 10: 10 sms + 2 mms = 12 messages total
THREAD_10_MSG_COUNT = 12
# Thread 20: 10 sms + 1 mms = 11 messages
THREAD_20_MSG_COUNT = 11


@pytest.fixture
def profile(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    return result.profile


def test_list_threads_returns_all(db_v166, profile):
    threads = list_threads(db_v166, profile)
    assert len(threads) == 3


def test_thread_has_attachment_count(db_v166, profile):
    threads = list_threads(db_v166, profile)
    # Thread 10 has 2 parts (mms ids 1,2), thread 20 has 1, thread 30 has 2
    by_id = {t.thread_id: t for t in threads}
    assert by_id[10].attachment_count == 2
    assert by_id[20].attachment_count == 1
    assert by_id[30].attachment_count == 2


def test_get_messages_thread10(db_v166, profile):
    page = get_messages(db_v166, profile, thread_id=10)
    assert len(page.messages) == THREAD_10_MSG_COUNT
    assert page.cursor is None  # all fit in default page of 50


def test_get_messages_pagination(db_v166, profile):
    page1 = get_messages(db_v166, profile, thread_id=10, page_size=5)
    assert len(page1.messages) == 5
    assert page1.cursor is not None

    page2 = get_messages(db_v166, profile, thread_id=10, page_size=5, cursor=page1.cursor)
    assert len(page2.messages) == 5

    page3 = get_messages(db_v166, profile, thread_id=10, page_size=5, cursor=page2.cursor)
    assert len(page3.messages) == 2
    assert page3.cursor is None


def test_get_messages_page_size_one(db_v166, profile):
    """Boundary: page_size=1 yields exactly one message and a next cursor."""
    page = get_messages(db_v166, profile, thread_id=10, page_size=1)
    assert len(page.messages) == 1
    assert page.cursor is not None


def test_get_messages_page_size_exceeds_total(db_v166, profile):
    """page_size larger than message count: all messages returned, cursor is None."""
    page = get_messages(db_v166, profile, thread_id=10, page_size=1000)
    assert len(page.messages) == THREAD_10_MSG_COUNT
    assert page.cursor is None


def test_get_messages_after_filter(db_v166, profile):
    cutoff = int(time.time() * 1000) - 3 * 86_400_000  # 3 days ago
    page = get_messages(db_v166, profile, thread_id=10, after=cutoff)
    for msg in page.messages:
        assert msg["date"] > cutoff


def test_get_messages_before_filter(db_v166, profile):
    cutoff = int(time.time() * 1000) - 3 * 86_400_000  # 3 days ago
    page = get_messages(db_v166, profile, thread_id=10, before=cutoff)
    for msg in page.messages:
        assert msg["date"] < cutoff


def test_get_messages_date_window(db_v166, profile):
    """Combined before+after: only messages strictly within the window are returned."""
    now = int(time.time() * 1000)
    after = now - 6 * 86_400_000
    before = now - 2 * 86_400_000
    page = get_messages(db_v166, profile, thread_id=10, after=after, before=before)
    for msg in page.messages:
        assert after < msg["date"] < before


def test_get_messages_empty_thread(db_v166, profile):
    """Thread ID that has no messages returns empty list and no cursor."""
    page = get_messages(db_v166, profile, thread_id=99999)
    assert page.messages == []
    assert page.cursor is None


def test_messages_ordered_descending(db_v166, profile):
    page = get_messages(db_v166, profile, thread_id=10)
    dates = [m["date"] for m in page.messages]
    assert dates == sorted(dates, reverse=True)


def test_get_messages_mms_only_thread(db_v166, profile):
    """Thread 30 has only MMS rows — verify correct cross-table query with no sms rows."""
    page = get_messages(db_v166, profile, thread_id=30)
    assert len(page.messages) == 2
    assert all(m["source"] == "mms" for m in page.messages)
