import re
import pytest
from pathlib import Path
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze
from signalstripper.select import (
    SelectionSet, ThreadSelection, estimate_reclaim, to_cli_args, validate_selection
)
from signalstripper.emit import emit_reclaim_command

# Named constants from build_fixture_db.py
THREAD_10_BYTES = 1_500_000 + 8_000_000
THREAD_10_IMAGE_BYTES = 1_500_000
THREAD_20_BYTES = 200_000
THREAD_30_BYTES = 3_000_000 + 12_000_000


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

def test_to_cli_args_strip_basic(setup):
    _, _, _ = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments")
    ])
    args = to_cli_args(sel)
    assert "--replaceattachments" in args
    assert "--onlyinthreads" in args
    assert "42" in args


def test_to_cli_args_strip_date_before():
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", date_before=9999999999000)
    ])
    args = to_cli_args(sel)
    assert "--onlyolderthan" in args
    assert "9999999999000" in args


def test_to_cli_args_strip_date_after():
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", date_after=1000000000000)
    ])
    args = to_cli_args(sel)
    assert "--onlynewerthan" in args
    assert "1000000000000" in args


def test_to_cli_args_strip_min_size_bytes():
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", min_size_bytes=500_000)
    ])
    args = to_cli_args(sel)
    assert "--onlylargerthan" in args
    assert "500000" in args


def test_to_cli_args_strip_content_types():
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", content_types=["image/*", "video/mp4"])
    ])
    args = to_cli_args(sel)
    onlytype_indices = [i for i, a in enumerate(args) if a == "--onlytype"]
    assert len(onlytype_indices) == 2


def test_to_cli_args_strip_batches_same_fingerprint():
    """Two strips with identical filters → single --replaceattachments, both thread ids."""
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", date_before=9_000_000_000_000),
        ThreadSelection(thread_id=20, intent="strip_attachments", date_before=9_000_000_000_000),
    ])
    args = to_cli_args(sel)
    assert args.count("--replaceattachments") == 1
    idx = args.index("--onlyinthreads")
    ids = set(args[idx + 1].split(","))
    assert ids == {"10", "20"}


def test_to_cli_args_strip_different_filters_separate_blocks():
    """Different date_before values → two separate --replaceattachments invocations."""
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", date_before=1_000_000_000_000),
        ThreadSelection(thread_id=20, intent="strip_attachments", date_before=2_000_000_000_000),
    ])
    args = to_cli_args(sel)
    assert args.count("--replaceattachments") == 2


def test_to_cli_args_empty_selection():
    sel = SelectionSet(selections=[])
    assert to_cli_args(sel) == []


# ── to_cli_args: remove_thread ────────────────────────────────────────────────

def test_to_cli_args_remove_with_summary(setup):
    _, _, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=20, intent="remove_thread")
    ])
    args = to_cli_args(sel, summary)
    assert "--croptothreads" in args
    idx = args.index("--croptothreads")
    keep_ids = set(args[idx + 1].split(","))
    assert "20" not in keep_ids    # removed thread not in keep list
    assert len(keep_ids) == 2      # the other two threads are kept


def test_to_cli_args_remove_without_summary_emits_placeholder():
    """Without summary, emits a placeholder containing the removed thread id."""
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="remove_thread")
    ])
    args = to_cli_args(sel, summary=None)
    assert "--croptothreads" in args
    idx = args.index("--croptothreads")
    assert "42" in args[idx + 1]


def test_to_cli_args_remove_all_threads_raises(setup):
    _, _, summary = setup
    all_ids = [t.thread_id for t in summary.threads]
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=tid, intent="remove_thread") for tid in all_ids
    ])
    with pytest.raises(ValueError, match="remove all threads"):
        to_cli_args(sel, summary)


# ── emit_reclaim_command ──────────────────────────────────────────────────────

def test_emit_strip_attachments(setup):
    db_path, profile, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments")
    ])
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"), sel, summary)
    assert "--replaceattachments" in cmd
    assert "--onlyinthreads" in cmd
    assert "10" in cmd


def test_emit_remove_thread(setup):
    db_path, profile, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=20, intent="remove_thread")
    ])
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"), sel, summary)
    assert "--croptothreads" in cmd
    # --croptothreads lists threads to KEEP; cmd uses backslash-continuation
    croptothreads_match = re.search(r"--croptothreads[\s\\]+([0-9,]+)", cmd)
    assert croptothreads_match, "Expected --croptothreads <ids> in command"
    keep_ids = croptothreads_match.group(1).split(",")
    assert "20" not in keep_ids


def test_emit_contains_safety_header(setup):
    db_path, profile, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments")
    ])
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"), sel, summary)
    assert "manually" in cmd.lower()
    assert "signalstripper never auto-runs" in cmd


def test_emit_estimate_nonzero(setup):
    db_path, profile, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments")
    ])
    cmd = emit_reclaim_command(db_path, db_path.with_suffix(".stripped.db"), sel, summary)
    match = re.search(r"~([\d.]+) GB", cmd)
    assert match, "Expected an estimated reclaim size in the output"
    assert float(match.group(1)) > 0


# ── estimate_reclaim ──────────────────────────────────────────────────────────

def test_estimate_reclaim_strip_all(setup):
    _, _, summary = setup
    thread = next(t for t in summary.threads if t.thread_id == 10)
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments")
    ])
    assert estimate_reclaim(sel, summary) == thread.attachment_bytes == THREAD_10_BYTES


def test_estimate_reclaim_remove_thread(setup):
    _, _, summary = setup
    thread_id = summary.threads[0].thread_id
    expected = summary.threads[0].total_bytes
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=thread_id, intent="remove_thread")
    ])
    assert estimate_reclaim(sel, summary) == expected


def test_estimate_reclaim_content_type_filter(setup):
    """Content-type filter picks only the matching MIME prefix bucket."""
    _, _, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", content_types=["image/*"])
    ])
    reclaim = estimate_reclaim(sel, summary)
    assert reclaim == THREAD_10_IMAGE_BYTES


def test_estimate_reclaim_content_type_full_mime(setup):
    """'image/jpeg' strips to 'image' bucket same as 'image/*'."""
    _, _, summary = setup
    sel_slash = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", content_types=["image/jpeg"])
    ])
    sel_wildcard = SelectionSet(selections=[
        ThreadSelection(thread_id=10, intent="strip_attachments", content_types=["image/*"])
    ])
    assert estimate_reclaim(sel_slash, summary) == estimate_reclaim(sel_wildcard, summary)


def test_estimate_reclaim_unknown_thread(setup):
    """Unknown thread_id contributes 0 to the estimate."""
    _, _, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=99999, intent="strip_attachments")
    ])
    assert estimate_reclaim(sel, summary) == 0
