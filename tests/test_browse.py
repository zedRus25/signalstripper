import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.browse import list_threads, get_messages


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
    # Thread 10 has 10 sms + 2 mms = 12 messages
    assert len(page.messages) == 12
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


def test_get_messages_date_filter(db_v166, profile):
    import time
    cutoff = int(time.time() * 1000) - 3 * 86_400_000  # 3 days ago
    page = get_messages(db_v166, profile, thread_id=10, after=cutoff)
    # Only messages newer than 3 days ago should appear
    for msg in page.messages:
        assert msg["date"] > cutoff


def test_messages_ordered_descending(db_v166, profile):
    page = get_messages(db_v166, profile, thread_id=10)
    dates = [m["date"] for m in page.messages]
    assert dates == sorted(dates, reverse=True)
