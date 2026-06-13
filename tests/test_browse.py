import time
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.browse import list_threads, get_messages

THREAD_10_MSG_COUNT = 12   # 10 sms + 2 mms
NOW_MS = int(time.time() * 1000)
DAY_MS = 86_400_000


@pytest.fixture
def profile(db_v166):
    return introspect(db_v166, load_profiles()).profile


def test_list_threads(db_v166, profile):
    threads = list_threads(db_v166, profile)
    assert len(threads) == 3
    by_id = {t.thread_id: t for t in threads}
    assert by_id[10].attachment_count == 2
    assert by_id[20].attachment_count == 1
    assert by_id[30].attachment_count == 2


def test_get_messages_returns_all(db_v166, profile):
    page = get_messages(db_v166, profile, thread_id=10)
    assert len(page.messages) == THREAD_10_MSG_COUNT
    assert page.cursor is None


def test_get_messages_pagination(db_v166, profile):
    page1 = get_messages(db_v166, profile, thread_id=10, page_size=5)
    assert len(page1.messages) == 5 and page1.cursor is not None

    page2 = get_messages(db_v166, profile, thread_id=10, page_size=5, cursor=page1.cursor)
    assert len(page2.messages) == 5 and page2.cursor is not None

    page3 = get_messages(db_v166, profile, thread_id=10, page_size=5, cursor=page2.cursor)
    assert len(page3.messages) == 2 and page3.cursor is None


@pytest.mark.parametrize("page_size,expected_count,expect_cursor", [
    pytest.param(1,    1,                  True,  id="page-size-one"),
    pytest.param(1000, THREAD_10_MSG_COUNT, False, id="page-size-exceeds-total"),
])
def test_get_messages_page_size_boundary(db_v166, profile, page_size, expected_count, expect_cursor):
    page = get_messages(db_v166, profile, thread_id=10, page_size=page_size)
    assert len(page.messages) == expected_count
    assert (page.cursor is not None) == expect_cursor


@pytest.mark.parametrize("filter_kwargs,check", [
    pytest.param({"after":  NOW_MS - 3*DAY_MS}, lambda d, c: d > c["after"],  id="after"),
    pytest.param({"before": NOW_MS - 3*DAY_MS}, lambda d, c: d < c["before"], id="before"),
    pytest.param(
        {"after": NOW_MS - 6*DAY_MS, "before": NOW_MS - 2*DAY_MS},
        lambda d, c: c["after"] < d < c["before"],
        id="window",
    ),
])
def test_get_messages_date_filter(db_v166, profile, filter_kwargs, check):
    page = get_messages(db_v166, profile, thread_id=10, **filter_kwargs)
    for msg in page.messages:
        assert check(msg["date"], filter_kwargs)


def test_get_messages_empty_thread(db_v166, profile):
    page = get_messages(db_v166, profile, thread_id=99999)
    assert page.messages == [] and page.cursor is None


def test_messages_ordered_descending(db_v166, profile):
    dates = [m["date"] for m in get_messages(db_v166, profile, thread_id=10).messages]
    assert dates == sorted(dates, reverse=True)


def test_get_messages_mms_only_thread(db_v166, profile):
    """Thread 30 has only MMS rows — no sms part of the UNION should still work."""
    page = get_messages(db_v166, profile, thread_id=30)
    assert len(page.messages) == 2
    assert all(m["source"] == "mms" for m in page.messages)
