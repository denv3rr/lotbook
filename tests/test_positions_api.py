"""Isolated SQLite positions, cash and import routes."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import Base
from tests.harness import make_isolated_engine
from web_api.routes import clients, positions


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine, sessions = make_isolated_engine(tmp_path / "positions.db")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(clients.router)
    app.include_router(positions.router)

    def database():
        with sessions() as session:
            yield session

    app.dependency_overrides[clients.get_db] = database
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "isolated-verification-key")
    with TestClient(app, headers={"X-API-Key": "isolated-verification-key"}) as client:
        yield client
    engine.dispose()


def setup_account(api):
    client = api.post("/api/clients", json={"name": "Positions verification", "accounts": []}).json()
    account = api.post(
        f"/api/clients/{client['client_id']}/accounts",
        json={"account_name": "Brokerage", "account_type": "Taxable"},
    ).json()["account"]
    book = api.get(f"/api/clients/{client['client_id']}/positions").json()["accounts"][0]
    return client["client_id"], account["account_id"], book["revision"]


def test_positions_preserve_other_tickers_and_reject_stale_revision(api):
    client_id, account_id, revision = setup_account(api)
    first = api.put(
        f"/api/clients/{client_id}/accounts/{account_id}/positions",
        json={
            "expected_revision": revision,
            "ticker": "AAPL",
            "mode": "lots",
            "lots": [{"qty": "2", "basis": "10", "timestamp": "2024-01-01"}],
            "source_note": "Isolated lot A.",
        },
    )
    assert first.status_code == 200, first.text
    book = first.json()
    second = api.put(
        f"/api/clients/{client_id}/accounts/{account_id}/positions",
        json={
            "expected_revision": book["revision"],
            "ticker": "MSFT",
            "mode": "lots",
            "lots": [{"qty": "3", "basis": "20", "timestamp": "2024-01-02"}],
            "source_note": "Isolated lot B.",
        },
    )
    assert second.status_code == 200, second.text
    tickers = {row["ticker"] for row in second.json()["positions"]}
    assert tickers == {"AAPL", "MSFT"}
    stale = api.put(
        f"/api/clients/{client_id}/accounts/{account_id}/positions",
        json={
            "expected_revision": book["revision"],
            "ticker": "AAPL",
            "mode": "delete",
            "confirm": True,
            "source_note": "Stale delete.",
        },
    )
    assert stale.status_code == 409


def test_cash_transaction_import_preview_and_auth(api):
    client_id, account_id, revision = setup_account(api)
    cash = api.put(
        f"/api/clients/{client_id}/accounts/{account_id}/cash",
        json={"expected_revision": revision, "currency": "USD", "amount": "1000", "source_note": "Opening cash."},
    )
    assert cash.status_code == 200, cash.text
    buy = api.post(
        f"/api/clients/{client_id}/accounts/{account_id}/transactions",
        json={
            "expected_revision": cash.json()["revision"],
            "occurred_at": "2024-02-01T00:00:00",
            "kind": "buy",
            "ticker": "AAPL",
            "quantity": "10",
            "unit_price": "20",
            "currency": "USD",
            "source_note": "Isolated buy.",
        },
    )
    assert buy.status_code == 200, buy.text
    assert buy.json()["cash"][0]["amount"].startswith("800")
    preview = api.post(
        f"/api/clients/{client_id}/accounts/{account_id}/transactions/import",
        json={
            "expected_revision": buy.json()["revision"],
            "confirm": False,
            "rows": [
                {"occurred_at": "2024-03-01T00:00:00", "kind": "deposit", "cash_amount": "50", "currency": "USD", "source_note": "Preview deposit."}
            ],
        },
    )
    assert preview.status_code == 200
    assert preview.json()["would_write"] is True
    assert buy.json()["cash"][0]["amount"].startswith("800")
    denied = api.get(f"/api/clients/{client_id}/positions", headers={"X-API-Key": "invalid"})
    assert denied.status_code == 401
