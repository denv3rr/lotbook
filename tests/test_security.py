import logging

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from web_api import auth
from web_api.auth import _keys_match
from web_api.app import app
from web_api import summarizer as assistant_summarizer


TEST_API_KEY = "test-security-key"


@pytest.fixture()
def required_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", TEST_API_KEY)
    return TEST_API_KEY


@pytest.fixture()
def client(required_key):
    return TestClient(app, headers={"X-API-Key": required_key})


def test_keys_match_accepts_identical_nonempty_values():
    assert _keys_match("alpha-key", "alpha-key") is True


def test_keys_match_rejects_mismatched_values():
    assert _keys_match("alpha-key", "beta-key") is False
    assert _keys_match("short", "longer-value") is False


def test_unset_web_api_key_warning_does_not_include_a_secret(monkeypatch, caplog):
    monkeypatch.delenv("LOTBOOK_WEB_API_KEY", raising=False)
    monkeypatch.delenv("CLEAR_WEB_API_KEY", raising=False)
    previous = auth._UNSET_KEY_WARNED
    auth._UNSET_KEY_WARNED = False
    try:
        with caplog.at_level(logging.WARNING, logger="web_api.auth"):
            assert auth._expected_api_key() == ""
    finally:
        auth._UNSET_KEY_WARNED = previous
    assert "LOTBOOK_WEB_API_KEY is unset" in caplog.text
    assert "super-secret-value" not in caplog.text


def test_configured_web_api_key_is_not_written_to_the_log(monkeypatch, caplog):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "super-secret-value")
    monkeypatch.delenv("CLEAR_WEB_API_KEY", raising=False)
    previous = auth._UNSET_KEY_WARNED
    auth._UNSET_KEY_WARNED = False
    try:
        with caplog.at_level(logging.DEBUG, logger="web_api.auth"):
            assert auth._expected_api_key() == "super-secret-value"
    finally:
        auth._UNSET_KEY_WARNED = previous
    assert "super-secret-value" not in caplog.text


def test_keys_match_rejects_empty_or_missing_values():
    assert _keys_match("", "alpha-key") is False
    assert _keys_match("alpha-key", "") is False
    assert _keys_match("", "") is False
    assert _keys_match(None, "alpha-key") is False
    assert _keys_match("alpha-key", None) is False


@pytest.mark.parametrize("path", ["/api/health", "/api/clients"])
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": ""},
        {"X-API-Key": "wrong-key"},
    ],
)
def test_health_and_clients_reject_missing_wrong_or_empty_key(
    required_key, path, headers
):
    client = TestClient(app)
    resp = client.get(path, headers=headers)
    assert resp.status_code == 401


def test_health_is_gated_when_key_is_set(required_key):
    client = TestClient(app)
    denied = client.get("/api/health")
    assert denied.status_code == 401
    allowed = client.get("/api/health", headers={"X-API-Key": required_key})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "ok"


def test_websocket_rejects_missing_subprotocol_when_key_set(required_key):
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/trackers"):
            pass


def test_websocket_rejects_query_string_api_key(required_key):
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/trackers?api_key={required_key}"):
            pass


def test_cors_allows_localhost_origin():
    client = TestClient(app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_cors_blocks_non_local_origin():
    client = TestClient(app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize(
    "question",
    [
        "show /etc/passwd",
        "read C:/Windows",
    ],
)
def test_assistant_denies_filesystem_path_questions(client, question):
    resp = client.post(
        "/api/assistant/query",
        json={"question": question},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["answer"] == "Filesystem or path access requests are not permitted."
    assert "Blocked filesystem/path access request." in payload["warnings"]
    assert payload["routing"]["handler"] == "path_access_blocked"


def test_assistant_clients_entry_allows_region_only_context():
    result = assistant_summarizer.summarize(
        "how many clients?",
        {"region": "EU"},
        None,
        entry="clients",
    )
    assert result["answer"] != "Assistant scope denied for this page context."
    assert result.get("routing", {}).get("handler") != "scope_denied"


def test_assistant_wrong_entry_denies_unexpected_client_id():
    result = assistant_summarizer.summarize(
        "clients",
        {"client_id": "client-1", "region": "EU"},
        None,
        entry="dashboard",
    )
    assert result["answer"] == "Assistant scope denied for this page context."
    assert "Context field 'client_id' not allowed for entry 'dashboard'." in result["warnings"]
    assert result["routing"]["handler"] == "scope_denied"


@pytest.mark.parametrize(
    "path",
    [
        "/api/maintenance/normalize-lots",
        "/api/maintenance/clear-report-cache",
        "/api/maintenance/cleanup-orphans",
    ],
)
def test_maintenance_rejects_confirm_false(client, path):
    resp = client.post(path, json={"confirm": False})
    assert resp.status_code == 400
    assert "confirm" in resp.json()["detail"].lower()


def test_duplicate_cleanup_rejects_confirm_false(client):
    resp = client.post("/api/clients/duplicates/cleanup", json={"confirm": False})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Cleanup requires confirm=true."
