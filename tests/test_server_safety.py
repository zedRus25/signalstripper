import pytest
from pathlib import Path
from signalstripper.server import serve, create_app, NonLoopbackBindError
from signalstripper.extract import _secure_wipe, decrypted_db


@pytest.fixture
def app(db_v166):
    from signalstripper.schema.registry import load_profiles
    from signalstripper.schema.introspect import introspect
    from signalstripper.analyze import analyze
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    return create_app(db_v166, result.profile, summary)


# ── Loopback bind enforcement ────────────────────────────────────────────────

@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost"])
def test_refuses_non_loopback_bind(app, host):
    with pytest.raises(NonLoopbackBindError):
        serve(app, host=host, port=8765)


# ── No plaintext left behind ──────────────────────────────────────────────────

def test_secure_wipe_removes_file(tmp_path):
    target = tmp_path / "secret.db"
    target.write_bytes(b"SENSITIVE DATA " * 100)
    _secure_wipe(target)
    assert not target.exists() and list(tmp_path.iterdir()) == []


def test_secure_wipe_zeros_file_before_deletion(tmp_path, monkeypatch):
    """_secure_wipe must overwrite with zeros before unlinking — not just delete."""
    target = tmp_path / "secret.db"
    target.write_bytes(b"SENSITIVE DATA " * 100)

    content_before_unlink = []
    original_unlink = Path.unlink

    def spy_unlink(self, *args, **kwargs):
        if self == target:
            content_before_unlink.append(self.read_bytes())
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", spy_unlink)
    _secure_wipe(target)

    assert len(content_before_unlink) == 1
    assert set(content_before_unlink[0]) == {0}, "file must be all-zeros before deletion"


def test_secure_wipe_removes_directory(tmp_path):
    subdir = tmp_path / "tmpdir"
    subdir.mkdir()
    (subdir / "file1.db").write_bytes(b"data1")
    (subdir / "file2.db").write_bytes(b"data2")
    _secure_wipe(subdir)
    assert not subdir.exists()


def test_secure_wipe_nonexistent_path_is_noop(tmp_path):
    _secure_wipe(tmp_path / "does_not_exist.db")  # must not raise


def test_decrypted_db_cleans_up_on_exception(tmp_path):
    """Context manager wipes temp dir even when _invoke raises before yield."""
    with pytest.raises(NotImplementedError):
        with decrypted_db(
            tmp_path / "fake.backup",
            "passphrase",
            Path("vendor/signalbackup-tools/signalbackup-tools"),
        ):
            pass

    import tempfile
    leftover = list(Path(tempfile.gettempdir()).glob("signalstripper_*"))
    assert leftover == [], f"Temp dirs not cleaned up: {leftover}"


def test_decrypted_db_cleans_up_after_normal_use(tmp_path, monkeypatch):
    """Context manager wipes temp dir on the success path (post-yield)."""
    def fake_invoke(backup, passphrase, out_path, binary):
        out_path.write_bytes(b"fake decrypted db")

    monkeypatch.setattr("signalstripper.extract._invoke_signalbackup_tools", fake_invoke)

    captured_dir = None
    with decrypted_db(tmp_path / "fake.bak", "passphrase", Path("vendor/bin")) as db_path:
        captured_dir = db_path.parent
        assert db_path.exists()

    assert captured_dir is not None and not captured_dir.exists()
