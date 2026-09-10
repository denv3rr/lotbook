"""Recorded positions, cash and ledger events, independently of quote availability.

Basis is per unit. Decimal intermediates avoid summation artifacts; stored lots
remain JSON-compatible with the existing numeric holdings/lot contracts.
Unrelated tickers are never rewritten. Cash and positions share one book hash
so a stale editor cannot overwrite a concurrent cash or lot change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from modules.client_mgr.holdings import normalize_ticker


QUANTUM = Decimal("0.00000001")
LEDGER_KINDS = (
    "buy",
    "sell",
    "deposit",
    "withdrawal",
    "fee",
    "transfer_in",
    "transfer_out",
    "dividend",
    "interest",
    "split",
    "spinoff",
    "merger",
    "cash_correction",
)


def decimal_value(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("A numeric amount is required.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as failure:
        raise ValueError("A finite numeric amount is required.") from failure
    if not number.is_finite():
        raise ValueError("A finite numeric amount is required.")
    return number


def money_text(value: Decimal) -> str:
    quantized = value.quantize(QUANTUM)
    return format(quantized, "f")


def json_amount(value: Decimal) -> float:
    encoded = float(value)
    if not value.is_finite():
        raise ValueError("Amount is outside the supported numeric range.")
    return encoded


class PositionLot(BaseModel):
    model_config = ConfigDict(extra="allow")
    qty: Decimal = Field(gt=0, le=1_000_000_000, max_digits=16, decimal_places=8)
    basis: Decimal = Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=8)
    timestamp: str

    @field_validator("qty", "basis", mode="before")
    @classmethod
    def finite_amount(cls, value):
        return decimal_value(value)

    @field_validator("timestamp")
    @classmethod
    def valid_date(cls, value):
        value = value.strip()
        if value in {"UNKNOWN", "LEGACY", "AGGREGATE"}:
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as failure:
            raise ValueError("Use an ISO acquisition date or UNKNOWN.") from failure
        if parsed.date() > datetime.now(timezone.utc).date():
            raise ValueError("An acquisition date cannot be in the future.")
        return value


class PositionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    ticker: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.^=/:-]+$")
    mode: Literal["quantity", "lots", "delete"]
    quantity: Decimal | None = Field(default=None, gt=0, le=1_000_000_000, max_digits=16, decimal_places=8)
    lots: list[PositionLot] = Field(default_factory=list, max_length=500)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_note: str = Field(min_length=1, max_length=1000)
    confirm: StrictBool = False

    @field_validator("ticker")
    @classmethod
    def symbol(cls, value):
        return normalize_ticker(value)

    @field_validator("quantity", mode="before")
    @classmethod
    def finite_quantity(cls, value):
        return None if value is None else decimal_value(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        if not value.strip():
            raise ValueError("Record the source or reason for this correction.")
        return value.strip()

    @model_validator(mode="after")
    def mode_fields(self):
        if self.mode == "quantity" and (self.quantity is None or self.lots):
            raise ValueError("Quantity mode requires a total quantity and no lots.")
        if self.mode == "lots" and (not self.lots or self.quantity is not None):
            raise ValueError("Lot mode requires at least one lot and derives quantity from lots.")
        if self.mode == "delete" and (not self.confirm or self.lots or self.quantity is not None):
            raise ValueError("Removal requires explicit confirmation and no replacement values.")
        return self


class CashWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Decimal = Field(max_digits=20, decimal_places=8)
    source_note: str = Field(min_length=1, max_length=1000)
    confirm: StrictBool = False

    @field_validator("amount", mode="before")
    @classmethod
    def finite_amount(cls, value):
        return decimal_value(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        if not value.strip():
            raise ValueError("Record the source or reason for this cash correction.")
        return value.strip()

    @model_validator(mode="after")
    def confirmed_negative(self):
        if self.amount < 0 and not self.confirm:
            raise ValueError("A negative cash balance requires explicit confirmation.")
        return self


class LedgerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    occurred_at: str
    kind: Literal[
        "buy",
        "sell",
        "deposit",
        "withdrawal",
        "fee",
        "transfer_in",
        "transfer_out",
        "dividend",
        "interest",
        "split",
        "spinoff",
        "merger",
        "cash_correction",
    ]
    ticker: str | None = Field(default=None, max_length=32)
    quantity: Decimal | None = Field(default=None, max_digits=16, decimal_places=8)
    unit_price: Decimal | None = Field(default=None, max_digits=16, decimal_places=8)
    cash_amount: Decimal | None = Field(default=None, max_digits=20, decimal_places=8)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=8)
    source_note: str = Field(min_length=1, max_length=1000)
    confirm: StrictBool = False
    lot_indices: list[int] = Field(default_factory=list, max_length=500)

    @field_validator("ticker")
    @classmethod
    def symbol(cls, value):
        return normalize_ticker(value) if value else None

    @field_validator("quantity", "unit_price", "cash_amount", "fee_amount", mode="before")
    @classmethod
    def finite_optional(cls, value):
        return None if value is None else decimal_value(value)

    @field_validator("occurred_at")
    @classmethod
    def dated(cls, value):
        value = value.strip()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as failure:
            raise ValueError("Use an ISO date and time for the event.") from failure
        if parsed.date() > datetime.now(timezone.utc).date():
            raise ValueError("An event date cannot be in the future.")
        return value

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        if not value.strip():
            raise ValueError("Record the source or reason for this transaction.")
        return value.strip()

    @model_validator(mode="after")
    def kind_fields(self):
        if self.kind in {"buy", "sell", "split", "spinoff", "merger"} and not self.ticker:
            raise ValueError("Security events require a ticker.")
        if self.kind in {"buy", "sell"} and (self.quantity is None or self.quantity <= 0 or self.unit_price is None or self.unit_price < 0):
            raise ValueError("Buys and sells require a positive quantity and a non-negative unit price.")
        if self.kind == "split" and (self.quantity is None or self.quantity <= 0):
            raise ValueError("A split factor must be a positive number (for example 2 for a 2-for-1).")
        if self.kind in {"deposit", "transfer_in", "dividend", "interest"} and (self.cash_amount is None or self.cash_amount <= 0):
            raise ValueError("Inflows require a positive cash amount.")
        if self.kind in {"withdrawal", "transfer_out", "fee"} and (self.cash_amount is None or self.cash_amount == 0) and self.fee_amount == 0:
            raise ValueError("Outflows require a non-zero cash or fee amount.")
        return self


class ImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: str
    kind: Literal[
        "buy",
        "sell",
        "deposit",
        "withdrawal",
        "fee",
        "transfer_in",
        "transfer_out",
        "dividend",
        "interest",
        "split",
        "cash_correction",
    ]
    ticker: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    cash_amount: Decimal | None = None
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    source_note: str = Field(min_length=1, max_length=1000)
    confirm: StrictBool = False

    @field_validator("ticker")
    @classmethod
    def symbol(cls, value):
        return normalize_ticker(value) if value else None

    @field_validator("quantity", "unit_price", "cash_amount", "fee_amount", mode="before")
    @classmethod
    def finite_optional(cls, value):
        return None if value is None else decimal_value(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        if not value.strip():
            raise ValueError("Each imported row needs a source or reason.")
        return value.strip()


class ImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: list[ImportRow] = Field(min_length=1, max_length=2000)
    confirm: StrictBool = False


def normalized_map(value: dict | None) -> dict:
    result = {}
    for key, row in (value or {}).items():
        ticker = normalize_ticker(key)
        if not ticker or ticker in result:
            raise ValueError("Ambiguous ticker keys require reconciliation before editing.")
        result[ticker] = row
    return result


def cash_map(extra: dict | None) -> dict[str, Decimal]:
    balances = {}
    raw = (extra or {}).get("cash_balances") or {}
    if not isinstance(raw, dict):
        raise ValueError("Cash balances are unreadable and must be reconciled before editing.")
    for currency, amount in raw.items():
        code = str(currency or "").strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("Cash balances use ISO-4217 currency codes.")
        balances[code] = decimal_value(amount)
    return balances


def store_cash(extra: dict, balances: dict[str, Decimal]) -> dict:
    extra = dict(extra or {})
    extra["cash_balances"] = {code: money_text(amount) for code, amount in sorted(balances.items())}
    return extra


def book_payload(holdings, lots, extra) -> dict:
    extra = extra or {}
    return {
        "holdings": holdings or {},
        "lots": lots or {},
        "cash_balances": extra.get("cash_balances") or {},
        "position_details": extra.get("position_details") or {},
    }


def positions_revision(holdings, lots, extra) -> str:
    raw = json.dumps(book_payload(holdings, lots, extra), sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def lot_quantity(entries) -> Decimal:
    total = Decimal(0)
    for lot in entries or []:
        total += decimal_value(lot.get("qty", 0))
    return total


def position_rows(holdings, lots, extra) -> list[dict]:
    holdings, lots = normalized_map(holdings), normalized_map(lots)
    details = (extra or {}).get("position_details", {})
    rows = []
    for ticker in sorted(holdings.keys() | lots.keys()):
        entries = lots.get(ticker, [])
        quantity = decimal_value(holdings[ticker]) if ticker in holdings else None
        lot_qty = lot_quantity(entries)
        basis = sum((decimal_value(lot["qty"]) * decimal_value(lot["basis"]) for lot in entries), Decimal(0)) if entries else None
        warnings = []
        if entries and quantity is not None and lot_qty != quantity:
            warnings.append("Recorded quantity differs from lot quantity. Reconcile explicitly before relying on totals.")
        if any(decimal_value(lot["qty"]) <= 0 or decimal_value(lot["basis"]) < 0 for lot in entries):
            warnings.append("Legacy lot amounts require correction.")
            basis = None
        metadata = details.get(ticker, {}) if isinstance(details, dict) else {}
        if not metadata.get("currency"):
            warnings.append("Cost-basis currency is unspecified; no currency conversion is implied.")
        rows.append({
            "ticker": ticker,
            "quantity": money_text(quantity) if quantity is not None else None,
            "lot_quantity": money_text(lot_qty),
            "lot_count": len(entries),
            "lots": entries,
            "total_basis": money_text(basis) if basis is not None else None,
            "average_basis": money_text(basis / lot_qty) if basis is not None and lot_qty > 0 else None,
            "mode": "lots" if entries else "quantity",
            "currency": metadata.get("currency"),
            "source_note": metadata.get("source_note", ""),
            "warnings": warnings,
        })
    return rows


def cash_rows(extra) -> list[dict]:
    rows = []
    for currency, amount in sorted(cash_map(extra).items()):
        rows.append({"currency": currency, "amount": money_text(amount)})
    return rows


def stored_lot(lot: PositionLot) -> dict:
    payload = lot.model_dump()
    payload["qty"] = json_amount(lot.qty)
    payload["basis"] = json_amount(lot.basis)
    return payload


def apply_position(holdings, lots, extra, command: PositionWrite):
    holdings, lots, extra = normalized_map(holdings), normalized_map(lots), dict(extra or {})
    ticker = command.ticker
    if command.mode == "delete":
        if ticker not in holdings and ticker not in lots:
            raise ValueError("Position does not exist.")
        holdings.pop(ticker, None)
        lots.pop(ticker, None)
    elif command.mode == "quantity":
        if lots.get(ticker) and not command.confirm:
            raise ValueError("Replacing lot history with a total quantity requires explicit confirmation.")
        holdings[ticker] = json_amount(command.quantity)
        lots.pop(ticker, None)
    else:
        quantity = sum((lot.qty for lot in command.lots), Decimal(0))
        if quantity > Decimal("1000000000"):
            raise ValueError("Total lot quantity exceeds the supported limit.")
        holdings[ticker] = json_amount(quantity)
        lots[ticker] = [stored_lot(lot) for lot in command.lots]
    details = dict(extra.get("position_details", {}))
    if command.mode == "delete":
        details.pop(ticker, None)
    else:
        details[ticker] = {
            "currency": command.currency,
            "source_note": command.source_note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    extra["position_details"] = details
    return holdings, lots, extra


def apply_cash(holdings, lots, extra, command: CashWrite):
    extra = store_cash(extra, {**cash_map(extra), command.currency: command.amount})
    details = dict((extra or {}).get("position_details", {}))
    details[f"CASH:{command.currency}"] = {
        "currency": command.currency,
        "source_note": command.source_note,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    extra["position_details"] = details
    return holdings, lots, extra


def _lot_sort_key(lot: dict) -> tuple:
    stamp = str(lot.get("timestamp") or "")
    if stamp in {"UNKNOWN", "LEGACY", "AGGREGATE", ""}:
        return ("1", stamp)
    return ("0", stamp)


def _reduce_lots(entries: list[dict], quantity: Decimal, indices: list[int] | None) -> tuple[list[dict], Decimal]:
    remaining = list(entries)
    to_sell = quantity
    allocated_basis = Decimal(0)
    order = list(indices) if indices else [index for index, _ in sorted(enumerate(remaining), key=lambda item: _lot_sort_key(item[1]))]
    for index in order:
        if to_sell <= 0:
            break
        if index < 0 or index >= len(remaining):
            raise ValueError("A specified lot index is out of range.")
        lot = remaining[index]
        available = decimal_value(lot.get("qty", 0))
        if available <= 0:
            continue
        take = available if available <= to_sell else to_sell
        allocated_basis += take * decimal_value(lot.get("basis", 0))
        leftover = available - take
        to_sell -= take
        if leftover == 0:
            remaining[index] = None
        else:
            remaining[index] = {**lot, "qty": json_amount(leftover)}
    if to_sell > 0:
        raise ValueError("Sell quantity exceeds remaining lots.")
    kept = [lot for lot in remaining if lot is not None]
    return kept, allocated_basis


def apply_ledger(holdings, lots, extra, command: LedgerWrite):
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        holdings, lots, extra = normalized_map(holdings), normalized_map(lots), dict(extra or {})
        balances = cash_map(extra)
        currency = command.currency
        cash = balances.get(currency, Decimal(0))
        fee = command.fee_amount or Decimal(0)
        realized = None
        ticker = command.ticker
        cash_delta = command.cash_amount

        if command.kind == "buy":
            proceeds = command.quantity * command.unit_price
            cash_delta = -(proceeds + fee) if cash_delta is None else cash_delta
            if cash_delta >= 0:
                raise ValueError("A buy must reduce cash.")
            if cash + cash_delta < 0 and not command.confirm:
                raise ValueError("This buy would overdraw recorded cash. Confirm if that is an explicit correction.")
            entries = list(lots.get(ticker) or [])
            entries.append({
                "qty": json_amount(command.quantity),
                "basis": json_amount(command.unit_price),
                "timestamp": command.occurred_at,
                "source": "LEDGER",
                "kind": "lot",
            })
            lots[ticker] = entries
            holdings[ticker] = json_amount(lot_quantity(entries))
        elif command.kind == "sell":
            proceeds = command.quantity * command.unit_price
            cash_delta = proceeds - fee if cash_delta is None else cash_delta
            entries = list(lots.get(ticker) or [])
            if not entries:
                raise ValueError("A sell requires lot history so realized P&L can be allocated.")
            kept, allocated_basis = _reduce_lots(entries, command.quantity, command.lot_indices or None)
            realized = cash_delta + fee - allocated_basis
            if kept:
                lots[ticker] = kept
                holdings[ticker] = json_amount(lot_quantity(kept))
            else:
                lots.pop(ticker, None)
                holdings.pop(ticker, None)
        elif command.kind == "split":
            factor = command.quantity
            entries = list(lots.get(ticker) or [])
            if not entries:
                raise ValueError("A split requires lot history.")
            lots[ticker] = [
                {**lot, "qty": json_amount(decimal_value(lot["qty"]) * factor), "basis": json_amount(decimal_value(lot["basis"]) / factor)}
                for lot in entries
            ]
            holdings[ticker] = json_amount(lot_quantity(lots[ticker]))
            cash_delta = Decimal(0)
        elif command.kind in {"deposit", "transfer_in", "dividend", "interest"}:
            cash_delta = command.cash_amount
        elif command.kind in {"withdrawal", "transfer_out"}:
            cash_delta = -abs(command.cash_amount)
            if cash + cash_delta < 0 and not command.confirm:
                raise ValueError("This outflow would overdraw recorded cash. Confirm if that is an explicit correction.")
        elif command.kind == "fee":
            cash_delta = -(abs(command.cash_amount) if command.cash_amount else fee)
            if cash + cash_delta < 0 and not command.confirm:
                raise ValueError("This fee would overdraw recorded cash. Confirm if that is an explicit correction.")
        elif command.kind == "cash_correction":
            if cash_delta is None:
                raise ValueError("A cash correction requires the signed cash amount.")
        elif command.kind in {"spinoff", "merger"}:
            raise ValueError("Spin-off and merger events require a reviewed corporate-action template in a later release.")
        else:
            raise ValueError("Unsupported ledger event.")

        cash_delta = Decimal(0) if cash_delta is None else cash_delta
        balances[currency] = cash + cash_delta
        extra = store_cash(extra, balances)
        event = {
            "occurred_at": command.occurred_at,
            "kind": command.kind,
            "ticker": ticker,
            "quantity": money_text(command.quantity) if command.quantity is not None else None,
            "unit_price": money_text(command.unit_price) if command.unit_price is not None else None,
            "cash_amount": money_text(cash_delta),
            "currency": currency,
            "fee_amount": money_text(fee),
            "source_note": command.source_note,
            "realized_pnl": money_text(realized) if realized is not None else None,
        }
        return holdings, lots, extra, event


def preview_import(holdings, lots, extra, rows: list[ImportRow]) -> dict:
    current_holdings, current_lots, current_extra = holdings, lots, extra
    applied = []
    errors = []
    for index, row in enumerate(rows):
        command = LedgerWrite(
            expected_revision="0" * 64,
            occurred_at=row.occurred_at,
            kind=row.kind,
            ticker=row.ticker,
            quantity=row.quantity,
            unit_price=row.unit_price,
            cash_amount=row.cash_amount,
            currency=row.currency,
            fee_amount=row.fee_amount,
            source_note=row.source_note,
            confirm=row.confirm,
        )
        try:
            current_holdings, current_lots, current_extra, event = apply_ledger(
                current_holdings, current_lots, current_extra, command
            )
            applied.append({"index": index, **event})
        except (ValueError, KeyError, TypeError) as failure:
            errors.append({"index": index, "message": str(failure)})
            break
    return {
        "applied_count": len(applied),
        "error_count": len(errors),
        "events": applied,
        "errors": errors,
        "cash": cash_rows(current_extra),
        "positions": position_rows(current_holdings, current_lots, current_extra),
        "would_write": not errors,
        "holdings": current_holdings,
        "lots": current_lots,
        "extra": current_extra,
    }
