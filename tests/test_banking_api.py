"""Real isolated SQLite route writes; workflow evidence, not financial data validation."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import Base
from tests.harness import make_isolated_engine
from web_api.routes import banking, clients


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine, sessions = make_isolated_engine(tmp_path / "advisory.db")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(clients.router)
    app.include_router(banking.router)
    def database():
        with sessions() as session:
            yield session
    app.dependency_overrides[clients.get_db] = database
    monkeypatch.setenv("CLEAR_WEB_API_KEY", "isolated-verification-key")
    with TestClient(app, headers={"X-API-Key": "isolated-verification-key"}) as client:
        yield client
    engine.dispose()


def client_id(api, name="Clear workflow verification"):
    result = api.post("/api/clients", json={"name": name, "accounts": []})
    assert result.status_code == 200
    return result.json()["client_id"]


def deal_input(client):
    return {"client_id": client, "owner": "Verification operator", "source_note": "Isolated API acceptance run; arithmetic inputs are unit evidence only.", "name": "Advisory acceptance record", "deal_type": "sell_side", "currency": "USD", "expected_value": "10000.10", "fee_bps": "100", "close_probability": "0.5"}


def test_saved_models_recompute_results_and_preserve_versions(api):
    from tests.test_banking_comparables import assumptions
    cid = client_id(api)
    body = {"client_id": cid, "name": "Reviewed arithmetic version", "model_kind": "comps", "inputs": assumptions(), "owner": "Verification operator", "source_note": "Isolated acceptance only"}
    response = api.post("/api/banking/valuations", json=body)
    assert response.status_code == 201, response.text
    first = response.json()["valuation"]
    assert first["result"]["summaries"][0]["cases"][2]["equity_value"] == 450
    assert api.patch(f'/api/banking/valuations/{first["id"]}', json={"expected_revision": 1, "name": "Overwrite"}).status_code == 422
    second = api.post("/api/banking/valuations", json={**body, "supersedes_id": first["id"]})
    assert second.status_code == 201
    assert second.json()["valuation"]["supersedes_id"] == first["id"]
    assert api.post("/api/banking/valuations", json={**body, "result": {"equity_value": 1}}).status_code == 422
    other = client_id(api, "Other model scope")
    assert api.post("/api/banking/valuations", json={**body, "client_id": other, "supersedes_id": first["id"]}).status_code == 422
    assert len(api.get("/api/banking/workspace").json()["valuations"]) == 2


def test_real_workspace_lifecycle_and_revision_protection(api):
    cid = client_id(api)
    created = api.post("/api/banking/deals", json=deal_input(cid))
    assert created.status_code == 201, created.text
    deal = created.json()["deal"]
    assert deal["revision"] == 1
    updated = api.patch(f'/api/banking/deals/{deal["id"]}', json={"expected_revision": 1, "stage": "mandated", "next_action": "Review source financials"})
    assert updated.status_code == 200
    assert updated.json()["deal"]["expected_value"] == "10000.10"
    assert api.patch(f'/api/banking/deals/{deal["id"]}', json={"expected_revision": 1, "stage": "lost"}).status_code == 409
    summary = api.get("/api/banking/workspace").json()["summary"]
    assert summary["active_deals"] == 1
    assert summary["by_currency"][0]["expected_fees"] == "100.001"
    assert summary["by_currency"][0]["weighted_fees"] == "50.0005"
    task = api.post("/api/banking/tasks", json={"client_id": cid, "deal_id": deal["id"], "title": "Review source financials", "owner": "Verification operator", "source_note": "Recorded through the actual API in isolated storage."}).json()["task"]
    assert api.patch(f'/api/banking/tasks/{task["id"]}', json={"expected_revision": 1, "status": "completed"}).status_code == 200
    exported = api.get("/api/banking/export").json()
    assert len(exported["activities"]) == 4
    assert exported["summary"]["open_tasks"] == 0
    assert exported["methodology"]["fees"]


def test_duplicates_cross_client_links_and_bad_inputs_fail_without_writes(api):
    cid = client_id(api)
    other = client_id(api, "Second verification scope")
    deal = api.post("/api/banking/deals", json=deal_input(cid)).json()["deal"]
    duplicate = {**deal_input(cid), "name": "  advisory   ACCEPTANCE record "}
    assert api.post("/api/banking/deals", json=duplicate).status_code == 409
    assert api.post("/api/banking/tasks", json={"client_id": other, "deal_id": deal["id"], "title": "Invalid cross-client task", "owner": "Verifier", "source_note": "Negative validation"}).status_code == 422
    for value in (True, "NaN", "Infinity", "abc", -1):
        assert api.post("/api/banking/deals", json={**deal_input(cid), "expected_value": value}).status_code == 422
    assert len(api.get("/api/banking/export").json()["activities"]) == 1
    assert api.patch(f'/api/banking/deals/{deal["id"]}', json={"expected_revision": 1, "owner": None}).status_code == 422
    assert api.patch(f'/api/banking/deals/{deal["id"]}', json={"expected_revision": 1, "client_id": other}).status_code == 422


def test_currency_separation_unknown_coverage_and_auth(api):
    cid = client_id(api)
    api.post("/api/banking/deals", json=deal_input(cid))
    api.post("/api/banking/deals", json={**deal_input(cid), "name": "Second currency", "currency": "EUR", "expected_value": None})
    summary = api.get("/api/banking/workspace").json()["summary"]["by_currency"]
    assert [row["currency"] for row in summary] == ["EUR", "USD"]
    assert summary[0]["pipeline_value"] is None
    assert summary[0]["value_coverage"] == 0
    assert api.get("/api/banking/export", headers={"X-API-Key": "invalid"}).status_code == 401


def test_contacts_persist_and_nullable_fields_clear(api):
    cid = client_id(api)
    contact = api.post("/api/banking/contacts", json={"client_id": cid, "name": "Verification contact", "owner": "Verifier", "source_note": "Acceptance run"}).json()["contact"]
    assert api.patch(f'/api/banking/contacts/{contact["id"]}', json={"expected_revision": 1, "notes": "Relationship note"}).status_code == 200
    deal = api.post("/api/banking/deals", json=deal_input(cid)).json()["deal"]
    cleared = api.patch(f'/api/banking/deals/{deal["id"]}', json={"expected_revision": 1, "expected_value": None}).json()["deal"]
    assert cleared["expected_value"] is None
