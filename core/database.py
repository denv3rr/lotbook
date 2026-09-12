from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def adopt_legacy_database(current: Path, legacy: Path) -> Path:
    """Use lotbook.db; rename an older clear.db only outside pytest."""
    if current.exists():
        return current
    if not legacy.exists():
        return current
    if "pytest" in sys.modules:
        return current
    current.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        src = Path(f"{legacy}{suffix}")
        dst = Path(f"{current}{suffix}")
        if src.exists() and not dst.exists():
            src.rename(dst)
    return current


def sqlite_url() -> str:
    override = os.getenv("LOTBOOK_DATABASE_URL") or os.getenv("CLEAR_DATABASE_URL")
    if override:
        return override
    adopt_legacy_database(_data_dir() / "lotbook.db", _data_dir() / "clear.db")
    return "sqlite:///./data/lotbook.db"


DATABASE_URL = sqlite_url()

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
