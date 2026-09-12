"""Real isolated SQLite recovery evidence; no financial data is fabricated."""
import sqlite3
from contextlib import closing

import pytest

from utils.recovery import encrypted_snapshot, restore_to_new_file


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "source.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE verification (event TEXT NOT NULL)")
        connection.execute("INSERT INTO verification VALUES ('actual isolated recovery test')")
        connection.commit()
    return path


def test_encrypted_snapshot_roundtrip_preserves_real_committed_data(database, tmp_path):
    archive = encrypted_snapshot(database, "recovery-test-passphrase")
    assert b"actual isolated recovery test" not in archive
    recovered = tmp_path / "recovered.db"
    manifest = restore_to_new_file(archive, "recovery-test-passphrase", recovered)
    assert manifest["scope"] == "canonical-sqlite-database"
    with closing(sqlite3.connect(recovered)) as connection:
        assert connection.execute("SELECT event FROM verification").fetchall() == [("actual isolated recovery test",)]
    with pytest.raises(ValueError, match="already exists"):
        restore_to_new_file(archive, "recovery-test-passphrase", database)


def test_snapshot_includes_committed_wal_without_checkpoint(database, tmp_path):
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO verification VALUES ('committed WAL event')")
        writer.commit()
        archive = encrypted_snapshot(database, "recovery-test-passphrase")
        restored = tmp_path / "wal-recovered.db"
        restore_to_new_file(archive, "recovery-test-passphrase", restored)
        with closing(sqlite3.connect(restored)) as result:
            assert result.execute("SELECT count(*) FROM verification").fetchone()[0] == 2


def test_snapshot_rejects_size_limit_and_broken_relations(database, monkeypatch):
    import utils.recovery as recovery
    monkeypatch.setattr(recovery, "MAX_DATABASE_BYTES", 1)
    with pytest.raises(ValueError, match="64 MiB"):
        encrypted_snapshot(database, "recovery-test-passphrase")
    monkeypatch.undo()
    with closing(sqlite3.connect(database)) as writer:
        writer.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id REFERENCES parent(id)); INSERT INTO child VALUES(9);")
    with pytest.raises(ValueError, match="foreign-key"):
        encrypted_snapshot(database, "recovery-test-passphrase")


def test_restore_accepts_legacy_clear_backup_magic(database, tmp_path, monkeypatch):
    import utils.recovery as recovery

    monkeypatch.setattr(recovery, "MAGIC", recovery.LEGACY_MAGIC)
    archive = encrypted_snapshot(database, "recovery-test-passphrase")
    assert archive.startswith(recovery.LEGACY_MAGIC)
    monkeypatch.undo()
    recovered = tmp_path / "legacy-recovered.db"
    restore_to_new_file(archive, "recovery-test-passphrase", recovered)


def test_recovery_authentication_and_input_guards(database, tmp_path):
    archive = encrypted_snapshot(database, "recovery-test-passphrase")
    for damaged, password in [(archive, "wrong-passphrase-value"), (archive[:-1] + bytes([archive[-1] ^ 1]), "recovery-test-passphrase"), (b"invalid", "recovery-test-passphrase")]:
        with pytest.raises(ValueError):
            restore_to_new_file(damaged, password, tmp_path / "untrusted.db")
        assert not (tmp_path / "untrusted.db").exists()
    with pytest.raises(ValueError, match="passphrase"):
        encrypted_snapshot(database, "short")


def test_backup_api_requires_key_locality_and_confirmation(database, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web_api.routes.recovery import canonical_database, router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[canonical_database] = lambda: database
    payload = {"confirm": True, "passphrase": "recovery-test-passphrase"}
    headers = {"X-API-Key": "isolated-recovery-key", "X-Lotbook-Backup": "confirm"}
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", headers["X-API-Key"])
    with TestClient(app, client=("127.0.0.1", 40001)) as client:
        assert client.post("/api/application/backup", json=payload).status_code == 401
        assert client.post("/api/application/backup", json=payload, headers={"X-API-Key": headers["X-API-Key"]}).status_code == 400
        assert client.post("/api/application/backup", json={**payload, "confirm": False}, headers=headers).status_code == 400
        result = client.post("/api/application/backup", json=payload, headers=headers)
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        restore_to_new_file(result.content, payload["passphrase"], tmp_path / "api-recovered.db")
        monkeypatch.delenv("LOTBOOK_WEB_API_KEY")
        assert client.post("/api/application/backup", json=payload, headers=headers).status_code == 409
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", headers["X-API-Key"])
    with TestClient(app, client=("192.0.2.1", 40001)) as client:
        assert client.post("/api/application/backup", json=payload, headers=headers).status_code == 403
