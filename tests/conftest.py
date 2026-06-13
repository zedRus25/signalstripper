import socket
import shutil
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_v166_path() -> Path:
    src = FIXTURES_DIR / "signal_v166.db"
    if not src.exists():
        from tests.fixtures.build_fixture_db import build_v166
        build_v166(src)
    return src


@pytest.fixture
def db_v166(fixture_v166_path, tmp_path) -> Path:
    copy = tmp_path / "signal_v166.db"
    shutil.copy2(fixture_v166_path, copy)
    return copy


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch):
    original = socket.getaddrinfo

    def patched(host, *args, **kwargs):
        loopback = {"127.0.0.1", "localhost", "::1", None, ""}
        if host not in loopback:
            raise AssertionError(
                f"Test made an outbound network call to {host!r} — "
                "signalstripper must not contact external hosts."
            )
        return original(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", patched)
