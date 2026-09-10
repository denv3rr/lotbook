from __future__ import annotations

import logging

from sqlalchemy import text
from core.database import Base, engine

LOGGER = logging.getLogger(__name__)


def _existing_columns(table_name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _add_column(table: str, column: str, column_type: str, default_sql: str | None = None) -> None:
    clause = f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
    if default_sql is not None:
        clause += f" DEFAULT {default_sql}"
    with engine.connect() as conn:
        conn.execute(text(clause))
        conn.commit()


def _ensure_index(table: str, index_name: str, columns: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})"))
        conn.commit()


def ensure_client_schema() -> None:
    clients_cols = _existing_columns("clients")
    accounts_cols = _existing_columns("accounts")

    client_updates = {
        "client_uid": ("TEXT", None),
        "name_key": ("TEXT", "''"),
        "risk_profile_source": ("TEXT", "'auto'"),
        "active_interval": ("TEXT", "'1M'"),
        "tax_profile": ("TEXT", "'{}'"),
        "extra": ("TEXT", "'{}'"),
    }
    for column, (col_type, default) in client_updates.items():
        if column not in clients_cols:
            _add_column("clients", column, col_type, default)

    account_updates = {
        "account_uid": ("TEXT", None),
        "identity_key": ("TEXT", "''"),
        "current_value": ("REAL", "0.0"),
        "active_interval": ("TEXT", "'1M'"),
        "ownership_type": ("TEXT", "'Individual'"),
        "custodian": ("TEXT", "''"),
        "tags": ("TEXT", "'[]'"),
        "tax_settings": ("TEXT", "'{}'"),
        "holdings_map": ("TEXT", "'{}'"),
        "lots": ("TEXT", "'{}'"),
        "manual_holdings": ("TEXT", "'[]'"),
        "extra": ("TEXT", "'{}'"),
        "book_revision": ("TEXT", "''"),
    }
    for column, (col_type, default) in account_updates.items():
        if column not in accounts_cols:
            _add_column("accounts", column, col_type, default)

    _ensure_index("clients", "ix_clients_name_key", "name_key")
    _ensure_index("accounts", "ix_accounts_identity_key", "identity_key")

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)
    try:
        ensure_client_schema()
    except Exception:
        LOGGER.exception("Client schema verification failed during startup")
        raise
