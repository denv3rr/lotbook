import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import core.database as database
import core.db_management as db_management
from core import models
from tests.harness import cleanup_sqlite_files, isolated_sqlite_path, make_isolated_engine
from web_api import diagnostics
from web_api.app import app
from web_api.routes import maintenance as maintenance_routes


TEST_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "test_runtime" / "web_api_maintenance"


def _setup_temp_db(request, monkeypatch):
    db_path = isolated_sqlite_path(request, "maintenance.db", runtime_dir=TEST_RUNTIME_DIR)
    engine, session_local = make_isolated_engine(db_path)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    monkeypatch.setattr(db_management, "engine", engine)
    monkeypatch.setattr(maintenance_routes, "SessionLocal", session_local)
    monkeypatch.setattr(diagnostics, "SessionLocal", session_local)
    return session_local, engine, db_path


@pytest.fixture()
def client(request, monkeypatch):
    session_local, engine, db_path = _setup_temp_db(request, monkeypatch)
    db_management.create_db_and_tables()
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "test_key")
    try:
        yield TestClient(app, headers={"X-API-Key": "test_key"}), session_local
    finally:
        engine.dispose()
        cleanup_sqlite_files(db_path)


def test_cleanup_orphans(client):
    test_client, session_local = client
    session = session_local()
    try:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.add(models.Holding(ticker="AAPL", quantity=1.0, account_id=999))
        session.add(
            models.Lot(
                purchase_date=None,
                purchase_price=10.0,
                quantity=1.0,
                holding_id=999,
            )
        )
        session.commit()
    finally:
        session.close()

    resp = test_client.post("/api/maintenance/cleanup-orphans", json={"confirm": True})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["removed_holdings"] == 1
    assert payload["removed_lots"] == 1


def test_cleanup_orphans_requires_confirm(client):
    test_client, _ = client
    resp = test_client.post("/api/maintenance/cleanup-orphans", json={"confirm": False})
    assert resp.status_code == 400


def test_clear_report_cache_requires_confirm(client):
    test_client, _ = client
    resp = test_client.post("/api/maintenance/clear-report-cache", json={"confirm": False})
    assert resp.status_code == 400


def test_normalize_lots_requires_confirm(client):
    test_client, _ = client
    resp = test_client.post("/api/maintenance/normalize-lots", json={"confirm": False})
    assert resp.status_code == 400
