from pathlib import Path
import os
import sqlite3
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool

from core.database import engine
from utils.recovery import encrypted_snapshot
from web_api.auth import require_api_key

router = APIRouter(prefix="/api/application", tags=["Recovery"], dependencies=[Depends(require_api_key)])
_backup_lock = Lock()


def canonical_database() -> Path:
    return Path(engine.url.database).resolve()


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool
    passphrase: SecretStr = Field(min_length=12, max_length=128)


@router.post("/backup")
def create_backup(payload: BackupRequest, request: Request, database: Path = Depends(canonical_database)):
    if not os.getenv("CLEAR_WEB_API_KEY"):
        raise HTTPException(409, "Configure an API key before exporting a complete database backup.")
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Database backup is available only on the local computer.")
    if not payload.confirm or request.headers.get("x-clear-backup") != "confirm":
        raise HTTPException(400, "Explicit database backup confirmation is required.")
    if not _backup_lock.acquire(blocking=False):
        raise HTTPException(409, "Another database backup is in progress.")
    try:
        archive = encrypted_snapshot(database, payload.passphrase.get_secret_value())
    except ValueError as failure:
        raise HTTPException(422, str(failure)) from failure
    except (OSError, sqlite3.Error) as failure:
        raise HTTPException(503, "Database backup failed. No operator data was modified.") from failure
    finally:
        _backup_lock.release()
    return Response(archive, media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="clear-database.clearbackup"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
