import pytest
from pathlib import Path
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze
from signalstripper.select import SelectionSet, ThreadSelection, estimate_reclaim, to_cli_args
from signalstripper.emit import emit_reclaim_command


@pytest.fixture
def setup(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    return db_v166, result.profile, summary


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
    # --croptothreads takes the complement (threads to KEEP)
    assert "--croptothreads" in cmd
    # Thread 20 is being removed, so it must not appear in the keep list
    import re
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
    # Should show a non-zero GB estimate
    import re
    match = re.search(r"~([\d.]+) GB", cmd)
    assert match, "Expected an estimated reclaim size in the output"
    assert float(match.group(1)) > 0


def test_to_cli_args_strip(setup):
    _, _, summary = setup
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=42, intent="strip_attachments", date_before=9999999999000)
    ])
    args = to_cli_args(sel)
    assert "--replaceattachments" in args
    assert "--onlyinthreads" in args
    assert "42" in args
    assert "--onlyolderthan" in args


def test_estimate_reclaim_remove_thread(setup):
    _, _, summary = setup
    thread_id = summary.threads[0].thread_id
    expected = summary.threads[0].total_bytes
    sel = SelectionSet(selections=[
        ThreadSelection(thread_id=thread_id, intent="remove_thread")
    ])
    assert estimate_reclaim(sel, summary) == expected
