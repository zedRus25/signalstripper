import pytest
from pathlib import Path
from signalstripper.server import serve, create_app, NonLoopbackBindError
from signalstripper.extract import _secure_wipe, decrypted_db


# ── Loopback bind enforcement ────────────────────────────────────────────────

def test_refuses_all_interfaces_bind(db_v166):
    from signalstripper.schema.registry import load_profiles
    from signalstripper.schema.introspect import introspect
    from signalstripper.analyze import analyze
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    app = create_app(db_v166, result.profile, summary)
    with pytest.raises(NonLoopbackBindError):
        serve(app, host="0.0.0.0", port=8765)


def test_refuses_ipv6_any(db_v166):
    from signalstripper.schema.registry import load_profiles
    from signalstripper.schema.introspect import introspect
    from signalstripper.analyze import analyze
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    app = create_app(db_v166, result.profile, summary)
    with pytest.raises(NonLoopbackBindError):
        serve(app, host="::", port=8765)


def test_refuses_localhost_string(db_v166):
    """Require literal '127.0.0.1'; reject 'localhost' (no DNS resolution)."""
    from signalstripper.schema.registry import load_profiles
    from signalstripper.schema.introspect import introspect
    from signalstripper.analyze import analyze
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    app = create_app(db_v166, result.profile, summary)
    with pytest.raises(NonLoopbackBindError):
        serve(app, host="localhost", port=8765)


# ── No plaintext left behind ──────────────────────────────────────────────────

def test_secure_wipe_removes_file(tmp_path):
    target = tmp_path / "secret.db"
    target.write_bytes(b"SENSITIVE DATA " * 100)
    _secure_wipe(target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_secure_wipe_removes_directory(tmp_path):
    subdir = tmp_path / "tmpdir"
    subdir.mkdir()
    (subdir / "file1.db").write_bytes(b"data1")
    (subdir / "file2.db").write_bytes(b"data2")
    _secure_wipe(subdir)
    assert not subdir.exists()


def test_decrypted_db_cleans_up_on_exception(tmp_path):
    """Context manager must wipe temp files even when body raises."""
    captured_dir = []
    with pytest.raises(NotImplementedError):
        with decrypted_db(
            tmp_path / "fake.backup",
            "passphrase",
            Path("vendor/signalbackup-tools/signalbackup-tools"),
        ) as db_path:
            captured_dir.append(db_path.parent)
    # NotImplementedError is raised by _invoke_signalbackup_tools before yield,
    # so captured_dir is empty — the tmp_dir itself should still be wiped
    # (it's created before the invoke call and cleaned in finally)
    # Test that no signalstripper_ prefixed dirs linger in /tmp
    import tempfile
    tmpbase = Path(tempfile.gettempdir())
    leftover = list(tmpbase.glob("signalstripper_*"))
    assert leftover == [], f"Temp dirs not cleaned up: {leftover}"
