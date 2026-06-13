import time
import pytest
from httpx import AsyncClient, ASGITransport
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze
from signalstripper.server import create_app

TOTAL_ATTACHMENT_BYTES = 24_700_000   # see build_fixture_db.py
THREAD_10_MSG_COUNT = 12              # 10 sms + 2 mms


@pytest.fixture
def app(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    return create_app(db_v166, result.profile, summary)


@pytest.fixture
def mock_app():
    from signalstripper.mock import mock_profile, mock_summary
    from pathlib import Path
    profile = mock_profile()
    summary = mock_summary()
    return create_app(Path("/mock/signal.db"), profile, summary, mock=True)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def mock_client(mock_app):
    async with AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://testserver") as c:
        yield c


async def test_analyze_endpoint(client):
    r = await client.get("/api/analyze")
    assert r.status_code == 200
    data = r.json()
    assert "total_attachment_bytes" in data
    assert data["total_attachment_bytes"] == TOTAL_ATTACHMENT_BYTES
    assert data["schema_version"] == 166


async def test_threads_endpoint(client):
    r = await client.get("/api/threads")
    assert r.status_code == 200
    threads = r.json()
    assert len(threads) == 3
    assert all("thread_id" in t for t in threads)


async def test_messages_endpoint(client):
    r = await client.get("/api/threads/10/messages")
    assert r.status_code == 200
    data = r.json()
    assert data["thread_id"] == 10
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) == THREAD_10_MSG_COUNT


async def test_messages_endpoint_before_filter(client):
    cutoff = int(time.time() * 1000) - 3 * 86_400_000
    r = await client.get(f"/api/threads/10/messages?before={cutoff}")
    assert r.status_code == 200
    data = r.json()
    for msg in data["messages"]:
        assert msg["date"] < cutoff


async def test_emit_endpoint_strip(client):
    payload = {"selections": [{"thread_id": 10, "intent": "strip_attachments"}]}
    r = await client.post("/api/emit", json=payload)
    assert r.status_code == 200
    text = r.text
    assert "--replaceattachments" in text
    assert "--onlyinthreads" in text
    assert "manually" in text.lower()


async def test_emit_endpoint_remove_thread(client):
    payload = {"selections": [{"thread_id": 20, "intent": "remove_thread"}]}
    r = await client.post("/api/emit", json=payload)
    assert r.status_code == 200
    assert "--croptothreads" in r.text


async def test_emit_endpoint_invalid_intent(client):
    payload = {"selections": [{"thread_id": 10, "intent": "destroy_everything"}]}
    r = await client.post("/api/emit", json=payload)
    assert r.status_code == 422
    assert "error" in r.json()


async def test_static_index(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "signalstripper" in r.text


async def test_no_socket_opened(app):
    """Test client never opens a real socket — ASGI transport is in-process."""
    import socket as _socket
    import unittest.mock as mock
    calls = []
    original_bind = _socket.socket.bind

    def patched_bind(self, addr):
        calls.append(addr)
        return original_bind(self, addr)

    with mock.patch.object(_socket.socket, "bind", patched_bind):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.get("/api/analyze")

    assert calls == [], f"Unexpected socket.bind calls: {calls}"


# ── Mock mode ────────────────────────────────────────────────────────────────

async def test_mock_analyze_endpoint(mock_client):
    r = await mock_client.get("/api/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["total_attachment_bytes"] > 0


async def test_mock_threads_endpoint(mock_client):
    r = await mock_client.get("/api/threads")
    assert r.status_code == 200
    threads = r.json()
    assert len(threads) > 0
    assert all("thread_id" in t for t in threads)
