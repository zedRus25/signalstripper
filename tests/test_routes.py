import pytest
from httpx import AsyncClient, ASGITransport
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect
from signalstripper.analyze import analyze
from signalstripper.server import create_app


@pytest.fixture
def app(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    summary = analyze(db_v166, result.profile)
    return create_app(db_v166, result.profile, summary)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def test_analyze_endpoint(client):
    r = await client.get("/api/analyze")
    assert r.status_code == 200
    data = r.json()
    assert "total_attachment_bytes" in data
    assert data["total_attachment_bytes"] == 24_700_000
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
    assert len(data["messages"]) == 12


async def test_emit_endpoint(client):
    payload = {"selections": [{"thread_id": 10, "intent": "strip_attachments"}]}
    r = await client.post("/api/emit", json=payload)
    assert r.status_code == 200
    text = r.text
    assert "--remove-attachments-from-thread" in text
    assert "manually" in text.lower()


async def test_static_index(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "signalstripper" in r.text


async def test_no_socket_opened(app):
    """Test client never opens a real socket — ASGI transport is in-process."""
    import socket as _socket
    calls = []
    original_bind = _socket.socket.bind

    def patched_bind(self, addr):
        calls.append(addr)
        return original_bind(self, addr)

    import unittest.mock as mock
    with mock.patch.object(_socket.socket, "bind", patched_bind):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.get("/api/analyze")

    assert calls == [], f"Unexpected socket.bind calls: {calls}"
