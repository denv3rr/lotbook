import os
from unittest import mock

from fastapi.testclient import TestClient

from web_api import app as web_app
from web_api import summarizer as assistant_summarizer
from web_api.routes import assistant as assistant_routes


def _api_headers():
    key = os.getenv("LOTBOOK_WEB_API_KEY")
    return {"X-API-Key": key} if key else {}


def test_assistant_summary_endpoint_uses_payload():
    client = TestClient(web_app.app)
    with mock.patch.object(assistant_routes, "summarize") as mocked:
        mocked.return_value = {
            "answer": "OK",
            "sources": [{"route": "/api/clients", "source": "database", "timestamp": 1}],
            "confidence": None,
            "warnings": [],
        }
        resp = client.post(
            "/api/assistant/query",
            json={"question": "How many clients?"},
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["answer"] == "OK"
    assert payload["confidence"] is None
    assert payload["meta"]["route"] == "/api/assistant/query"
    assert payload["meta"]["status"] == "ok"
    args, _ = mocked.call_args
    assert args[0] == "How many clients?"
    assert args[1] is None
    assert args[3] is None


def test_assistant_non_summary_mode_is_explicit():
    client = TestClient(web_app.app)
    with mock.patch.object(assistant_routes, "summarize") as mocked:
        resp = client.post(
            "/api/assistant/query",
            json={"question": "Compare clients", "mode": "compare"},
            headers=_api_headers(),
        )
    assert resp.status_code == 501
    payload = resp.json()
    assert payload["answer"] == "Mode 'compare' is not yet implemented."
    assert payload["confidence"] is None
    assert payload["meta"]["route"] == "/api/assistant/query"
    assert payload["meta"]["status"] == "error"
    mocked.assert_not_called()


def test_summarize_news_uses_context_and_sources():
    with mock.patch.object(assistant_summarizer, "get_news") as mocked:
        mocked.return_value = {
            "items": [{"title": "A"}],
            "cached": False,
            "stale": False,
            "skipped": [],
            "health": {},
        }
        result = assistant_summarizer.summarize(
            "latest news",
            {"region": "EU", "industry": "tech"},
            ["bbc.com"],
            entry="osint",
        )
    mocked.assert_called_with({"region": "EU", "industry": "tech"}, ["bbc.com"])
    assert result["confidence"] is None
    assert result["sources"]
    assert result["sources"][0]["route"] == "/api/intel/news"


def test_summarize_news_warns_when_empty():
    with mock.patch.object(assistant_summarizer, "get_news") as mocked:
        mocked.return_value = {
            "items": [],
            "cached": False,
            "stale": False,
            "skipped": [],
            "health": {},
        }
        result = assistant_summarizer.summarize("news", None, None, entry="osint")
    assert "News feed returned no items." in result["warnings"]


def test_summarize_clients_with_client_scope():
    class DummyStore:
        def fetch_client(self, client_ref):
            if client_ref == "client-1":
                return {
                    "client_id": "client-1",
                    "name": "Alpha",
                    "accounts": [
                        {
                            "account_id": "acct-1",
                            "account_name": "Main",
                            "holdings": {"AAPL": 1},
                        }
                    ],
                }
            return None

        def fetch_all_clients(self):
            return []

    with mock.patch.object(assistant_summarizer, "DbClientStore", DummyStore):
        result = assistant_summarizer.summarize(
            "client summary",
            {"client_id": "client-1"},
            None,
            entry="clients",
        )
    assert "Client client-1" in result["answer"]
    assert result["sources"][0]["route"] == "/api/clients/client-1"
    assert result["routing"]["rule"] == "clients"


def test_summarize_clients_with_account_scope():
    class DummyStore:
        def fetch_client(self, client_ref):
            return None

        def fetch_all_clients(self):
            return [
                {
                    "client_id": "client-1",
                    "name": "Alpha",
                    "accounts": [
                        {
                            "account_id": "acct-1",
                            "account_name": "Main",
                            "holdings": {"AAPL": 1},
                        }
                    ],
                }
            ]

    with mock.patch.object(assistant_summarizer, "DbClientStore", DummyStore):
        result = assistant_summarizer.summarize(
            "client account",
            {"account_id": "acct-1"},
            None,
            entry="clients",
        )
    assert "Account acct-1" in result["answer"]
    assert (
        result["sources"][0]["route"]
        == "/api/clients/client-1/accounts/acct-1"
    )
    assert result["routing"]["rule"] == "clients"


def test_summarize_clients_warns_on_invalid_client_id():
    with mock.patch.object(assistant_summarizer, "get_clients") as mocked:
        mocked.return_value = {"clients": []}
        result = assistant_summarizer.summarize(
            "clients",
            {"client_id": "../etc/passwd"},
            None,
            entry="clients",
        )
    assert "Invalid client ID format; ignoring." in result["warnings"]
    assert "No clients available." in result["warnings"]


def test_summarize_clients_warns_on_account_not_found_for_client():
    class DummyStore:
        def fetch_client(self, client_ref):
            if client_ref == "client-1":
                return {"client_id": "client-1", "name": "Alpha", "accounts": []}
            return None

        def fetch_all_clients(self):
            return []

    with mock.patch.object(assistant_summarizer, "DbClientStore", DummyStore):
        result = assistant_summarizer.summarize(
            "client summary",
            {"client_id": "client-1", "account_id": "acct-1"},
            None,
            entry="clients",
        )
    assert "Account ID not found for client." in result["warnings"]
    assert result["sources"][0]["route"] == "/api/clients/client-1"


def test_summarize_clients_warns_on_ambiguous_account_id():
    class DummyStore:
        def fetch_client(self, client_ref):
            return None

        def fetch_all_clients(self):
            return [
                {"client_id": "client-1", "name": "Alpha", "accounts": [{"account_id": "acct-1"}]},
                {"client_id": "client-2", "name": "Beta", "accounts": [{"account_id": "acct-1"}]},
            ]

    with mock.patch.object(assistant_summarizer, "DbClientStore", DummyStore):
        result = assistant_summarizer.summarize(
            "clients",
            {"account_id": "acct-1"},
            None,
            entry="clients",
        )
    assert "Account ID matches multiple clients; provide a client ID." in result["warnings"]


def test_assistant_export_endpoint_returns_payload():
    client = TestClient(web_app.app)
    payload = {
        "history": [
            {
                "question": "How many clients?",
                "answer": "You have 2 clients.",
                "confidence": None,
                "warnings": [],
                "sources": [{"route": "/api/clients", "source": "database", "timestamp": 1}],
            }
        ],
        "context": {"region": "Global", "industry": "all"},
        "format": "markdown",
    }
    resp = client.post(
        "/api/assistant/history/export",
        json=payload,
        headers=_api_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["route"] == "/api/assistant/history/export"
    assert data["export"]["entries"][0]["question"] == "How many clients?"
    assert "markdown" in data


def test_assistant_query_requires_api_key_when_set(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/query",
        json={"question": "How many clients?"},
        headers={},
    )
    assert resp.status_code == 401


def test_assistant_export_requires_api_key_when_set(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/history/export",
        json={"history": []},
        headers={},
    )
    assert resp.status_code == 401


def test_assistant_query_blocks_unknown_scope():
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/query",
        json={"question": "show /etc/passwd"},
        headers=_api_headers(),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["confidence"] is None
    assert "Blocked filesystem/path access request." in payload["warnings"]
    assert payload["answer"] == "Filesystem or path access requests are not permitted."


def test_assistant_query_denies_client_scope_on_dashboard_entry():
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/query",
        json={
            "question": "clients",
            "entry": "dashboard",
            "context": {"client_id": "client-1"},
        },
        headers=_api_headers(),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["confidence"] is None
    assert payload["answer"] == "Assistant scope denied for this page context."


def test_assistant_query_allows_client_scope_on_clients_entry():
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/query",
        json={
            "question": "clients",
            "entry": "clients",
            "context": {"client_id": "client-1"},
        },
        headers=_api_headers(),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["answer"] != "Assistant scope denied for this page context."


def test_assistant_query_rejects_invalid_context():
    client = TestClient(web_app.app)
    resp = client.post(
        "/api/assistant/query",
        json={"question": "news", "context": ["invalid"]},
        headers=_api_headers(),
    )
    assert resp.status_code == 422
