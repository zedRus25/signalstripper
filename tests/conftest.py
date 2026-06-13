import socket
import shutil
import threading
import time
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_PREINSTALLED_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


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


# ── Playwright: live server + browser path ────────────────────────────────────

@pytest.fixture(scope="session")
def browser_type_launch_args(pytestconfig):
    """Point pytest-playwright at the pre-installed Chromium binary."""
    args = {"headless": True}
    if Path(_PREINSTALLED_CHROMIUM).exists():
        args["executable_path"] = _PREINSTALLED_CHROMIUM
    return args


@pytest.fixture(scope="session")
def live_url() -> str:
    """Start the mock signalstripper server once per test session."""
    import uvicorn
    import httpx
    from signalstripper.mock import mock_profile, mock_summary
    from signalstripper.server import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    app = create_app(Path("/mock/signal.db"), mock_profile(), mock_summary(), mock=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/analyze", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    t.join(timeout=3)
