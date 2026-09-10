"""Client-scoped recorded positions and cash; no market-provider request is needed."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.models import Account, AccountLedger, PositionEvent
from modules.client_store import DbClientStore
from modules.client_mgr.performance import cash_flow_performance
from modules.client_mgr.positions import (
    CashWrite,
    ImportPreview,
    LedgerWrite,
    PositionWrite,
    apply_cash,
    apply_ledger,
    apply_position,
    cash_rows,
    position_rows,
    positions_revision,
    preview_import,
)
from web_api.auth import require_api_key
from web_api.routes.clients import get_db
from web_api.view_model import attach_meta

router = APIRouter(dependencies=[Depends(require_api_key)], tags=["Positions"])


def validation_error(failure: Exception) -> HTTPException:
    message = str(failure) if isinstance(failure, ValueError) else "Request could not be applied."
    return HTTPException(422, message)


def client_accounts(db, client_id):
    store = DbClientStore(db)
    client = store.fetch_client(client_id)
    if client is None:
        raise HTTPException(404, "Client not found.")
    owner = store._find_client(db, client_id)
    return owner, db.scalars(select(Account).where(Account.client_id == owner.id).order_by(Account.id)).all()


def original_book(account):
    return account.holdings_map, account.lots, account.extra


def persist_book(db, owner, account, original, holdings, lots, extra, ticker, action, source_note, event=None, events=None, import_batch_id=None):
    revision = positions_revision(*original)
    next_revision = positions_revision(holdings, lots, extra)
    result = db.execute(
        update(Account)
        .where(
            Account.id == account.id,
            Account.client_id == owner.id,
            Account.holdings_map == original[0],
            Account.lots == original[1],
            Account.extra == original[2],
        )
        .values(holdings_map=holdings, lots=lots, extra=extra, book_revision=next_revision)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Positions changed concurrently. Reload and review before saving.")
    stamp = datetime.now(timezone.utc).isoformat()
    if action in {"quantity", "lots", "delete"}:
        before = [row for row in position_rows(*original) if row["ticker"] == ticker]
        after = [row for row in position_rows(holdings, lots, extra) if row["ticker"] == ticker]
        db.add(PositionEvent(
            account_id=account.id,
            created_at=stamp,
            ticker=ticker or "",
            action=action,
            previous_revision=revision,
            revision=next_revision,
            change={"before": before, "after": after, "source_note": source_note},
        ))
    ledger_rows = []
    if event is not None:
        ledger_rows.append(event)
    ledger_rows.extend(events or [])
    for item in ledger_rows:
        db.add(AccountLedger(
            account_id=account.id,
            created_at=stamp,
            occurred_at=item["occurred_at"],
            kind=item["kind"],
            ticker=item.get("ticker"),
            quantity=item.get("quantity"),
            unit_price=item.get("unit_price"),
            cash_amount=item["cash_amount"],
            currency=item["currency"],
            fee_amount=item.get("fee_amount") or "0",
            source_note=item["source_note"],
            import_batch_id=import_batch_id,
            previous_revision=revision,
            revision=next_revision,
            change=item,
        ))
    db.commit()
    db.refresh(account)
    return account_view(db, account)


def account_view(db, account):
    history = db.scalars(select(PositionEvent).where(PositionEvent.account_id == account.id).order_by(PositionEvent.id.desc()).limit(20)).all()
    ledger = db.scalars(select(AccountLedger).where(AccountLedger.account_id == account.id).order_by(AccountLedger.id.desc()).limit(50)).all()
    book = original_book(account)
    return {
        "account_id": account.account_uid or str(account.id),
        "account_name": account.name,
        "revision": positions_revision(*book),
        "positions": position_rows(*book),
        "cash": cash_rows(account.extra),
        "history": [
            {"id": row.id, "created_at": row.created_at, "ticker": row.ticker, "action": row.action, "revision": row.revision, "change": row.change}
            for row in history
        ],
        "ledger": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "occurred_at": row.occurred_at,
                "kind": row.kind,
                "ticker": row.ticker,
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "cash_amount": row.cash_amount,
                "currency": row.currency,
                "fee_amount": row.fee_amount,
                "source_note": row.source_note,
                "realized_pnl": (row.change or {}).get("realized_pnl"),
                "revision": row.revision,
            }
            for row in ledger
        ],
        "warnings": [
            "Recorded book values, not live quotes. Basis is per unit; no FX conversion is performed.",
            "A local operator label is not an authenticated identity. Ledger history is not a tamper-proof audit log.",
        ],
    }


def load_account(db, client_id, account_id):
    owner, _ = client_accounts(db, client_id)
    account = DbClientStore(db)._find_account(db, owner.id, account_id)
    if account is None:
        raise HTTPException(404, "Account does not belong to this client.")
    return owner, account


@router.get("/api/clients/{client_id}/positions")
def read_positions(client_id: str, db: Session = Depends(get_db)):
    _, accounts = client_accounts(db, client_id)
    try:
        return attach_meta(
            {"client_id": client_id, "accounts": [account_view(db, row) for row in accounts]},
            route="/api/clients/{client_id}/positions",
            source="canonical-database",
            warnings=["Recorded positions, not live quotes. Basis is per unit; no FX conversion or execution is performed."],
        )
    except (ValueError, KeyError, TypeError):
        raise HTTPException(409, "Stored holdings need reconciliation before this view can be edited.") from None


@router.put("/api/clients/{client_id}/accounts/{account_id}/positions")
def write_position(client_id: str, account_id: str, payload: PositionWrite, db: Session = Depends(get_db)):
    owner, account = load_account(db, client_id, account_id)
    original = original_book(account)
    try:
        if positions_revision(*original) != payload.expected_revision:
            raise HTTPException(409, "Positions changed since this editor opened. Reload and review before saving.")
        holdings, lots, extra = apply_position(*original, payload)
        return persist_book(db, owner, account, original, holdings, lots, extra, payload.ticker, payload.mode, payload.source_note)
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as failure:
        db.rollback()
        raise validation_error(failure) from None


@router.put("/api/clients/{client_id}/accounts/{account_id}/cash")
def write_cash(client_id: str, account_id: str, payload: CashWrite, db: Session = Depends(get_db)):
    owner, account = load_account(db, client_id, account_id)
    original = original_book(account)
    try:
        if positions_revision(*original) != payload.expected_revision:
            raise HTTPException(409, "The cash book changed since this editor opened. Reload and review before saving.")
        holdings, lots, extra = apply_cash(*original, payload)
        event = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "kind": "cash_correction",
            "ticker": None,
            "quantity": None,
            "unit_price": None,
            "cash_amount": str(payload.amount),
            "currency": payload.currency,
            "fee_amount": "0",
            "source_note": payload.source_note,
            "realized_pnl": None,
        }
        return persist_book(db, owner, account, original, holdings, lots, extra, None, "cash_correction", payload.source_note, event=event)
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as failure:
        db.rollback()
        raise validation_error(failure) from None


@router.post("/api/clients/{client_id}/accounts/{account_id}/transactions")
def write_transaction(client_id: str, account_id: str, payload: LedgerWrite, db: Session = Depends(get_db)):
    owner, account = load_account(db, client_id, account_id)
    original = original_book(account)
    try:
        if positions_revision(*original) != payload.expected_revision:
            raise HTTPException(409, "The account book changed since this editor opened. Reload and review before saving.")
        holdings, lots, extra, event = apply_ledger(*original, payload)
        return persist_book(db, owner, account, original, holdings, lots, extra, payload.ticker, payload.kind, payload.source_note, event=event)
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as failure:
        db.rollback()
        raise validation_error(failure) from None


@router.post("/api/clients/{client_id}/accounts/{account_id}/transactions/import")
def import_transactions(client_id: str, account_id: str, payload: ImportPreview, db: Session = Depends(get_db)):
    owner, account = load_account(db, client_id, account_id)
    original = original_book(account)
    try:
        if positions_revision(*original) != payload.expected_revision:
            raise HTTPException(409, "The account book changed since this editor opened. Reload and review before saving.")
        preview = preview_import(*original, payload.rows)
        if not payload.confirm:
            preview.pop("holdings", None)
            preview.pop("lots", None)
            preview.pop("extra", None)
            return attach_meta(preview, route="/api/clients/{client_id}/accounts/{account_id}/transactions/import", source="canonical-database", warnings=["Preview only. Nothing was written."])
        if preview["errors"]:
            raise HTTPException(422, preview["errors"][0]["message"])
        batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        holdings, lots, extra = preview["holdings"], preview["lots"], preview["extra"]
        return persist_book(
            db,
            owner,
            account,
            original,
            holdings,
            lots,
            extra,
            None,
            "import",
            "Import batch",
            events=preview["events"],
            import_batch_id=batch,
        )
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError) as failure:
        db.rollback()
        raise validation_error(failure) from None


@router.get("/api/clients/{client_id}/accounts/{account_id}/performance")
def read_performance(client_id: str, account_id: str, db: Session = Depends(get_db)):
    _, account = load_account(db, client_id, account_id)
    ledger = db.scalars(select(AccountLedger).where(AccountLedger.account_id == account.id).order_by(AccountLedger.occurred_at, AccountLedger.id)).all()
    events = [
        {
            "occurred_at": row.occurred_at,
            "kind": row.kind,
            "cash_amount": row.cash_amount,
            "currency": row.currency,
            "fee_amount": row.fee_amount,
            "realized_pnl": (row.change or {}).get("realized_pnl"),
        }
        for row in ledger
    ]
    payload = cash_flow_performance(events, cash_rows(account.extra), position_rows(*original_book(account)))
    return attach_meta(payload, route="/api/clients/{client_id}/accounts/{account_id}/performance", source="canonical-database", warnings=payload.get("warnings") or [])
