import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from web_api.routes import stream as stream_route
from web_api.app import app


def _api_headers() -> dict:
    api_key = os.getenv("LOTBOOK_WEB_API_KEY")
    if api_key:
        return {"X-API-Key": api_key}
    return {}

def test_trackers_websocket_stream():
    client = TestClient(app)
    with client.websocket_connect(
        "/ws/trackers?mode=combined&interval=1",
        headers=_api_headers(),
    ) as websocket:
        payload = websocket.receive_json()
        assert isinstance(payload, dict)
        assert "points" in payload


def test_trackers_websocket_rejects_missing_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/trackers?mode=combined&interval=1"):
            pass


def test_trackers_websocket_accepts_subprotocol_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(app)
    with client.websocket_connect(
        "/ws/trackers?mode=combined&interval=1",
        headers={"sec-websocket-protocol": "lotbook-key.secret"},
    ) as websocket:
        payload = websocket.receive_json()
        assert isinstance(payload, dict)


def test_trackers_websocket_accepts_legacy_subprotocol_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(app)
    with client.websocket_connect(
        "/ws/trackers?mode=combined&interval=1",
        headers={"sec-websocket-protocol": "clear-key.secret"},
    ) as websocket:
        payload = websocket.receive_json()
        assert isinstance(payload, dict)


class _FakeTrackers:
    def get_snapshot(self, mode: str = "combined") -> dict:
        return {
            "mode": mode,
            "count": 1,
            "points": [{"id": "flight-1", "lat": 0.0, "lon": 0.0}],
        }


class _FakeWebSocket:
    def __init__(self, send_exc: Exception):
        self.headers = {}
        self.send_exc = send_exc
        self.accepted_subprotocol = None
        self.closed = None

    async def accept(self, subprotocol=None):
        self.accepted_subprotocol = subprotocol

    async def close(self, code=None, reason=None):
        self.closed = (code, reason)

    async def send_json(self, payload):
        raise self.send_exc


def test_trackers_stream_suppresses_expected_transport_reset(monkeypatch):
    monkeypatch.delenv("LOTBOOK_WEB_API_KEY", raising=False)
    monkeypatch.setattr(stream_route, "GlobalTrackers", _FakeTrackers)
    websocket = _FakeWebSocket(
        ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host"),
    )

    asyncio.run(stream_route.trackers_stream(websocket, mode="combined", interval=1))

    assert websocket.accepted_subprotocol is None
    assert websocket.closed is None


def test_trackers_stream_suppresses_close_message_runtime(monkeypatch):
    monkeypatch.delenv("LOTBOOK_WEB_API_KEY", raising=False)
    monkeypatch.setattr(stream_route, "GlobalTrackers", _FakeTrackers)
    websocket = _FakeWebSocket(RuntimeError("Cannot call send once a close message has been sent."))

    asyncio.run(stream_route.trackers_stream(websocket, mode="combined", interval=1))

    assert websocket.accepted_subprotocol is None
    assert websocket.closed is None


def test_trackers_stream_reraises_unexpected_runtime(monkeypatch):
    monkeypatch.delenv("LOTBOOK_WEB_API_KEY", raising=False)
    monkeypatch.setattr(stream_route, "GlobalTrackers", _FakeTrackers)
    websocket = _FakeWebSocket(RuntimeError("unexpected stream failure"))

    with pytest.raises(RuntimeError, match="unexpected stream failure"):
        asyncio.run(stream_route.trackers_stream(websocket, mode="combined", interval=1))
