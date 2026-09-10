"""Cash-flow-aware portfolio performance.

TWR follows the GIPS geometric-linking method: sub-period return
r = (EMV - BMV - CF) / BMV when cash flow is treated at period end, then
TWR = product(1+r) - 1. This is a methodological implementation, not a GIPS
compliance claim.

Money-weighted return uses XIRR (Newton-Raphson on dated cash flows). External
contributions are negative investor cash flows; distributions and ending value
are positive. Missing ending market value leaves XIRR/TWR unavailable — cash
alone is not an account return when securities remain.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, localcontext
from typing import Any

from modules.client_mgr.positions import decimal_value, money_text


def _as_date(value: str) -> date:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.date()


def time_weighted_return(periods: list[tuple[Decimal, Decimal, Decimal]]) -> Decimal | None:
    """periods: (beginning_market_value, ending_market_value, external_cash_flow)."""
    if not periods:
        return None
    with localcontext() as context:
        context.prec = 28
        growth = Decimal(1)
        for beginning, ending, cash_flow in periods:
            if beginning <= 0:
                return None
            growth *= (ending - cash_flow) / beginning
        return growth - Decimal(1)


def xirr(flows: list[tuple[date, Decimal]], guess: Decimal = Decimal("0.1")) -> Decimal | None:
    if len(flows) < 2:
        return None
    signed = [amount for _, amount in flows]
    if not any(amount > 0 for amount in signed) or not any(amount < 0 for amount in signed):
        return None
    start = flows[0][0]
    years = [Decimal((when - start).days) / Decimal(365) for when, _ in flows]
    rate = guess
    with localcontext() as context:
        context.prec = 28
        for _ in range(64):
            npv = Decimal(0)
            deriv = Decimal(0)
            for time_years, amount in zip(years, signed):
                growth = (Decimal(1) + rate) ** time_years
                if growth == 0:
                    return None
                npv += amount / growth
                if time_years != 0:
                    deriv -= time_years * amount / ((Decimal(1) + rate) ** (time_years + Decimal(1)))
            if deriv == 0:
                return None
            nxt = rate - npv / deriv
            if abs(nxt - rate) < Decimal("0.0000001"):
                if nxt <= Decimal("-0.999999"):
                    return None
                return nxt
            rate = nxt
            if rate <= Decimal("-0.999999") or abs(rate) > Decimal(10):
                return None
    return None


def cash_flow_performance(events: list[dict[str, Any]], cash: list[dict[str, Any]], positions: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = [
        "These figures use recorded ledger events only. They are not a live portfolio value.",
        "TWR and XIRR stay unavailable until an independently recorded ending market value is supplied; remaining securities are not priced here.",
        "GIPS and Damodaran references describe the formulas. This is not a compliance or suitability claim.",
    ]
    realized = Decimal(0)
    fees = Decimal(0)
    external = []
    currencies = set()
    for event in events:
        currencies.add(str(event.get("currency") or ""))
        fee = decimal_value(event.get("fee_amount") or 0)
        fees += fee
        pnl = event.get("realized_pnl")
        if pnl not in (None, ""):
            realized += decimal_value(pnl)
        kind = event.get("kind")
        amount = decimal_value(event.get("cash_amount") or 0)
        if kind in {"deposit", "transfer_in"}:
            external.append((_as_date(event["occurred_at"]), -abs(amount)))
        elif kind in {"withdrawal", "transfer_out"}:
            external.append((_as_date(event["occurred_at"]), abs(amount)))
    if len({code for code in currencies if code}) > 1:
        warnings.append("Mixed currencies are present. No FX conversion is applied; returns remain unavailable.")
        return {
            "realized_pnl": None,
            "fees": None,
            "twr": None,
            "xirr": None,
            "unrealized_pnl": None,
            "cash": cash,
            "position_count": len(positions),
            "priced_coverage": 0,
            "warnings": warnings,
            "methodology": {
                "twr": "GIPS geometric linking of sub-period returns; unavailable without beginning/ending market values.",
                "xirr": "Newton-Raphson IRR on dated external cash flows plus ending market value.",
                "realized_pnl": "Sum of allocated sell proceeds minus lot basis minus fees recorded on those sells.",
            },
        }
    open_positions = [row for row in positions if decimal_value(row.get("quantity") or 0) > 0]
    return {
        "realized_pnl": money_text(realized),
        "fees": money_text(fees),
        "twr": None,
        "xirr": None,
        "unrealized_pnl": None,
        "cash": cash,
        "position_count": len(open_positions),
        "priced_coverage": 0,
        "external_cash_flow_count": len(external),
        "warnings": warnings,
        "methodology": {
            "twr": "GIPS geometric linking of sub-period returns r=(EMV-CF)/BMV-1. Unavailable without valued sub-periods.",
            "xirr": "Money-weighted IRR of dated external contributions/distributions plus ending market value.",
            "realized_pnl": "Ledger sell realized P&L; unavailable sells never invent a gain.",
            "unrealized_pnl": "Requires a snapshot price for remaining lots; not fetched on this route.",
        },
    }
