"""Recorded lots, cash and ledger: Decimal math, unrelated-ticker preservation, import preview."""
from datetime import date

from modules.client_mgr.positions import (
    CashWrite,
    ImportRow,
    LedgerWrite,
    PositionLot,
    PositionWrite,
    apply_cash,
    apply_ledger,
    apply_position,
    position_rows,
    positions_revision,
    preview_import,
)


REVISION = "a" * 64


def test_lot_edit_does_not_touch_other_tickers():
    holdings = {"AAPL": 2.0, "MSFT": 3.0}
    lots = {
        "AAPL": [{"qty": 2.0, "basis": 10.0, "timestamp": "2024-01-01T00:00:00"}],
        "MSFT": [{"qty": 3.0, "basis": 20.0, "timestamp": "2024-01-02T00:00:00"}],
    }
    extra = {}
    command = PositionWrite(
        expected_revision=REVISION,
        ticker="AAPL",
        mode="lots",
        lots=[PositionLot(qty="2.5", basis="11", timestamp="2024-01-01")],
        source_note="Operator lot correction in isolated test.",
    )
    next_holdings, next_lots, _ = apply_position(holdings, lots, extra, command)
    assert next_holdings["AAPL"] == 2.5
    assert next_holdings["MSFT"] == 3.0
    assert next_lots["MSFT"][0]["qty"] == 3.0


def test_quantity_mismatch_is_warned_not_silently_fixed():
    rows = position_rows({"AAPL": 5.0}, {"AAPL": [{"qty": 2.0, "basis": 10.0, "timestamp": "2024-01-01T00:00:00"}]}, {})
    assert any("differs from lot quantity" in warning for warning in rows[0]["warnings"])


def test_buy_appends_lot_and_reduces_cash():
    extra = {"cash_balances": {"USD": "1000"}}
    command = LedgerWrite(
        expected_revision=REVISION,
        occurred_at="2024-02-01T00:00:00",
        kind="buy",
        ticker="AAPL",
        quantity="10",
        unit_price="20",
        currency="USD",
        source_note="Isolated buy.",
    )
    holdings, lots, extra, event = apply_ledger({}, {}, extra, command)
    assert holdings["AAPL"] == 10.0
    assert lots["AAPL"][0]["basis"] == 20.0
    assert extra["cash_balances"]["USD"] == "800.00000000"
    assert event["cash_amount"].startswith("-200")


def test_overdraft_buy_requires_confirmation():
    command = LedgerWrite(
        expected_revision=REVISION,
        occurred_at="2024-02-01T00:00:00",
        kind="buy",
        ticker="AAPL",
        quantity="10",
        unit_price="20",
        currency="USD",
        source_note="Would overdraw.",
    )
    try:
        apply_ledger({}, {}, {"cash_balances": {"USD": "10"}}, command)
        raise AssertionError("overdraft buy must fail closed")
    except ValueError as failure:
        assert "overdraw" in str(failure)


def test_fifo_sell_realizes_basis():
    lots = {"AAPL": [
        {"qty": 2.0, "basis": 10.0, "timestamp": "2024-01-01T00:00:00"},
        {"qty": 2.0, "basis": 20.0, "timestamp": "2024-02-01T00:00:00"},
    ]}
    extra = {"cash_balances": {"USD": "0"}}
    command = LedgerWrite(
        expected_revision=REVISION,
        occurred_at="2024-03-01T00:00:00",
        kind="sell",
        ticker="AAPL",
        quantity="3",
        unit_price="30",
        currency="USD",
        source_note="Isolated sell.",
    )
    holdings, lots, extra, event = apply_ledger({"AAPL": 4.0}, lots, extra, command)
    assert holdings["AAPL"] == 1.0
    assert lots["AAPL"][0]["qty"] == 1.0
    assert event["realized_pnl"] == "50.00000000"


def test_import_preview_does_not_need_write_and_stops_on_error():
    rows = [
        ImportRow(occurred_at="2024-01-01T00:00:00", kind="deposit", cash_amount="100", currency="USD", source_note="Seed cash."),
        ImportRow(occurred_at="2024-01-02T00:00:00", kind="buy", ticker="AAPL", quantity="1", unit_price="40", currency="USD", source_note="Buy."),
        ImportRow(occurred_at="2024-01-03T00:00:00", kind="buy", ticker="AAPL", quantity="1", unit_price="1000", currency="USD", source_note="Too expensive."),
    ]
    preview = preview_import({}, {}, {}, rows)
    assert preview["applied_count"] == 2
    assert preview["error_count"] == 1
    assert preview["would_write"] is False
    assert preview["errors"][0]["index"] == 2


def test_revision_changes_when_unrelated_cash_changes():
    holdings = {"AAPL": 1.0}
    lots = {"AAPL": [{"qty": 1.0, "basis": 1.0, "timestamp": "2024-01-01T00:00:00"}]}
    extra = {"cash_balances": {"USD": "0"}}
    before = positions_revision(holdings, lots, extra)
    _, _, extra = apply_cash(holdings, lots, extra, CashWrite(expected_revision=REVISION, currency="USD", amount="5", source_note="Cash seed.", confirm=False))
    assert positions_revision(holdings, lots, extra) != before
