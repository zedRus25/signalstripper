import re
import pytest
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze
from signalstripper.select import (
    SelectionSet, ThreadSelection, estimate_reclaim, to_cli_args, validate_selection
)
from signalstripper.emit import emit_reclaim_command

THREAD_10_BYTES = 1_500_000 + 8_000_000
THREAD_10_IMAGE_BYTES = 1_500_000


@pytest.fixture
def setup(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    return db_v166, result.profile, summary


# ── validate_selection ────────────────────────────────────────────────────────

def test_validate_selection_valid_intents():
    validate_selection(ThreadSelection(thread_id=1, intent="strip_attachments"))
    validate_selection(ThreadSelection(thread_id=1, intent="remove_thread"))


def test_validate_selection_invalid_intent():
    with pytest.raises(ValueError, match="Unknown intent"):
        validate_selection(ThreadSelection(thread_id=1, intent="delete_everything"))


# ── to_cli_args: strip_attachments ───────────────────────────────────────────

@pytest.mark.parametrize("kwargs,expected_in_args", [
    pytest.param({},                                            ["--replaceattachments", "--onlyinthreads", "42"], id="basic"),
    pytest.param({"date_before": 9_999_999_999_000},           ["--onlyolderthan", "9999999999000"],              id="date-before"),
    pytest.param({"date_after":  1_000_000_000_000},           ["--onlynewerthan", "1000000000000"],              id="date-after"),
    pytest.param({"min_size_bytes": 500_000},                  ["--onlylargerthan", "500000"],                    id="min-size"),
])
def test_to_cli_args_strip_flags(kwargs, expected_in_args):
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", **kwargs)
    ])
    args = to_cli_args(sel)
    for token in expected_in_args:
        assert token in args


def test_to_cli_args_strip_content_types():
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", content_types=["image/*", "video/mp4"])
    ])
    args = to_cli_args(sel)
    assert args.count("--onlytype") == 2


def test_to_cli_args_strip_batches_same_fingerprint():
    """Same modifier fingerprint → one --replaceattachments with both thread ids."""
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", date_before=9_000_000_000_000),
        ThreadSelection(thread_id=20, intent="strip_attachments", date_before=9_000_000_000_000),
    ])
    args = to_cli_args(sel)
    assert args.count("--replaceattachments") == 1
    assert set(args[args.index("--onlyinthreads") + 1].split(",")) == {"10", "20"}


def test_to_cli_args_strip_different_filters_separate_blocks():
    """Different date_before → two separate --replaceattachments invocations."""
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", date_before=1_000_000_000_000),
        ThreadSelection(thread_id=20, intent="strip_attachments", date_before=2_000_000_000_000),
    ])
    assert to_cli_args(sel).count("--replaceattachments") == 2


def test_to_cli_args_empty_selection():
    assert to_cli_args(SelectionSet(selections=[])) == []


# ── to_cli_args: remove_thread ────────────────────────────────────────────────

def test_to_cli_args_remove_with_summary(setup):
    _, _, summary = setup
    args = to_cli_args(SelectionSet(selections=[
        ThreadSelection(thread_id=20, intent="remove_thread")
    ]), summary)
    assert "--croptothreads" in args
    keep_ids = set(args[args.index("--croptothreads") + 1].split(","))
    assert "20" not in keep_ids
    assert len(keep_ids) == 2


def test_to_cli_args_remove_without_summary_emits_placeholder():
    args = to_cli_args(SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="remove_thread")
    ]), summary=None)
    assert "--croptothreads" in args
    assert "42" in args[args.index("--croptothreads") + 1]


def test_to_cli_args_remove_all_threads_raises(setup):
    _, _, summary = setup
    sels = [ThreadSelection(thread_id=t.thread_id, intent="remove_thread") for t in summary.threads]
    with pytest.raises(ValueError, match="remove all threads"):
        to_cli_args(SelectionSet(selections=sels), summary)


# ── emit_reclaim_command ──────────────────────────────────────────────────────

def test_emit_strip_attachments(setup):
    db_path, _, summary = setup
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"),
                               SelectionSet(selections=[ThreadSelection(thread_id=10, intent="strip_attachments")]),
                               summary)
    assert "--replaceattachments" in cmd and "--onlyinthreads" in cmd and "10" in cmd


def test_emit_remove_thread(setup):
    db_path, _, summary = setup
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"),
                               SelectionSet(selections=[ThreadSelection(thread_id=20, intent="remove_thread")]),
                               summary)
    assert "--croptothreads" in cmd
    m = re.search(r"--croptothreads[\s\\]+([0-9,]+)", cmd)
    assert m and "20" not in m.group(1).split(",")


def test_emit_safety_header_and_estimate(setup):
    db_path, _, summary = setup
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"),
                               SelectionSet(selections=[ThreadSelection(thread_id=10, intent="strip_attachments")]),
                               summary)
    assert "signalstripper never auto-runs" in cmd
    m = re.search(r"~([\d.]+) GB", cmd)
    assert m and float(m.group(1)) > 0


# ── estimate_reclaim ──────────────────────────────────────────────────────────

def test_estimate_reclaim_strip_all(setup):
    _, _, summary = setup
    thread = next(t for t in summary.threads if t.thread_id == 10)
    sel = SelectionSet(selections=[ThreadSelection(thread_id=10, intent="strip_attachments")])
    assert estimate_reclaim(sel, summary) == thread.attachment_bytes == THREAD_10_BYTES


def test_estimate_reclaim_remove_thread(setup):
    _, _, summary = setup
    thread = summary.threads[0]
    sel = SelectionSet(selections=[ThreadSelection(thread_id=thread.thread_id, intent="remove_thread")])
    assert estimate_reclaim(sel, summary) == thread.total_bytes


@pytest.mark.parametrize("content_type", [
    pytest.param("image/*",    id="wildcard"),
    pytest.param("image/jpeg", id="full-mime"),
])
def test_estimate_reclaim_content_type_filter(setup, content_type):
    """Both 'image/*' and 'image/jpeg' resolve to the same 'image' bucket."""
    _, _, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", content_types=[content_type])
    ])
    assert estimate_reclaim(sel, summary) == THREAD_10_IMAGE_BYTES


def test_estimate_reclaim_unknown_thread(setup):
    _, _, summary = setup
    sel = SelectionSet(selections=[ThreadSelection(thread_id=99999, intent="strip_attachments")])
    assert estimate_reclaim(sel, summary) == 0
