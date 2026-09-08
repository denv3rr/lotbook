"""Pure, assumption-driven annual FCFF valuation shared by dashboard and API.

This engine checks mathematical inputs; it does not verify financial evidence.
See docs/banking_valuation.md for the contract, formulas, and review limitations.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, localcontext
import math
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator


def _finite_number(value: Any) -> Decimal:
    """Do not coerce strings, booleans, nulls, or nonfinite values into money."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Enter a finite number, not text, a boolean, or null.")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
        encoded = float(number)
    except (ValueError, OverflowError, DecimalException) as exc:
        raise ValueError("Number exceeds the supported finite numeric range.") from exc
    if not number.is_finite() or not math.isfinite(encoded):
        raise ValueError("Number must be finite and within the supported numeric range.")
    if number != 0 and encoded == 0:
        raise ValueError("Number is too small for the supported numeric range.")
    return number


FiniteNumber = Annotated[Decimal, BeforeValidator(_finite_number)]


class DcfInputs(BaseModel):
    """All cash flows and bridge values use whole units of one currency."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cash_flows: list[FiniteNumber] = Field(min_length=1, max_length=20)
    wacc: FiniteNumber = Field(gt=0, le=1)
    terminal_growth: FiniteNumber = Field(gt=-1, le=Decimal("0.2"))
    debt: FiniteNumber = Field(ge=0)
    cash: FiniteNumber = Field(ge=0)
    other_claims: FiniteNumber = Field(ge=0)
    non_operating_assets: FiniteNumber = Field(ge=0)
    diluted_shares: FiniteNumber | None = Field(default=None, gt=0)
    currency: str = Field(strict=True, pattern=r"^[A-Z]{3}$")
    as_of: date
    source_note: str = Field(strict=True, min_length=1, max_length=4000)

    @field_validator("source_note")
    @classmethod
    def nonempty_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Record the source and basis of the supplied assumptions.")
        return value

    @field_validator("as_of", mode="before")
    @classmethod
    def calendar_date(cls, value: Any) -> date:
        # Pydantic otherwise accepts Unix timestamps and midnight datetimes.
        if type(value) is date:
            return value
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Use a calendar date in YYYY-MM-DD format.") from exc
            if value == parsed.isoformat():
                return parsed
        raise ValueError("Use a calendar date in YYYY-MM-DD format.")

    @field_validator("as_of")
    @classmethod
    def not_future(cls, value: date) -> date:
        if value > datetime.now(timezone.utc).date():
            raise ValueError("The assumption date must not be in the future (UTC).")
        return value

    @model_validator(mode="after")
    def convergent_terminal_value(self) -> DcfInputs:
        if self.wacc <= self.terminal_growth:
            raise ValueError("WACC must exceed terminal growth for a finite perpetuity value.")
        return self


def _json_number(value: Decimal) -> float:
    encoded = float(value)
    if not value.is_finite() or not math.isfinite(encoded):
        raise ValueError("Valuation exceeds the supported finite numeric range; review input scale and rates.")
    if value != 0 and encoded == 0:
        raise ValueError("Valuation falls below the supported numeric range; review input scale and rates.")
    return encoded


def _operating_value(
    cash_flows: list[Decimal], wacc: Decimal, growth: Decimal
) -> tuple[list[dict[str, Any]], Decimal, Decimal, Decimal, Decimal]:
    rows: list[dict[str, Any]] = []
    forecast_pv = Decimal(0)
    discount_factor = Decimal(1)
    for year, cash_flow in enumerate(cash_flows, start=1):
        discount_factor = Decimal(1) / (Decimal(1) + wacc) ** year
        present_value = cash_flow * discount_factor
        forecast_pv += present_value
        rows.append({
            "year": year,
            "cash_flow": _json_number(cash_flow),
            "discount_factor": _json_number(discount_factor),
            "present_value": _json_number(present_value),
        })
    terminal_value = cash_flows[-1] * (Decimal(1) + growth) / (wacc - growth)
    terminal_pv = terminal_value * discount_factor
    enterprise_value = forecast_pv + terminal_pv
    # Even a cancellation that leaves a finite EV must not serialize invalid
    # annual, subtotal, or terminal values.
    for value in (forecast_pv, terminal_value, terminal_pv, enterprise_value):
        _json_number(value)
    return rows, forecast_pv, terminal_value, terminal_pv, enterprise_value


def calculate_dcf(inputs: DcfInputs) -> dict[str, Any]:
    """Return JSON-ready screening math or raise ValueError on invalid output.

    Revalidation also protects direct callers from mutated lists or instances
    created with Pydantic's validation-bypassing construction helpers.
    """
    inputs = DcfInputs.model_validate(inputs.model_dump())
    try:
        with localcontext() as context:
            # Covers the full binary64 exponent span plus guard digits so large
            # offsetting bridge amounts do not erase a small equity residual.
            context.prec = 768
            return _calculate(inputs)
    except (DecimalException, OverflowError) as exc:
        raise ValueError("Valuation exceeds the supported numeric range; review input scale and rates.") from exc


def _calculate(inputs: DcfInputs) -> dict[str, Any]:
    rows, forecast_pv, terminal_value, terminal_pv, enterprise_value = _operating_value(
        inputs.cash_flows, inputs.wacc, inputs.terminal_growth
    )
    equity_value = (
        enterprise_value + inputs.cash + inputs.non_operating_assets
        - inputs.debt - inputs.other_claims
    )
    value_per_share = equity_value / inputs.diluted_shares if inputs.diluted_shares is not None else None
    terminal_share = terminal_pv / enterprise_value if enterprise_value > 0 and terminal_pv >= 0 else None
    wacc_values = [inputs.wacc + Decimal(index) * Decimal("0.005") for index in range(-2, 3)]
    growth_values = [inputs.terminal_growth + Decimal(index) * Decimal("0.0025") for index in range(-2, 3)]
    sensitivity: list[list[float | None]] = []
    for wacc in wacc_values:
        sensitivity_row: list[float | None] = []
        for growth in growth_values:
            if not (0 < wacc <= 1 and -1 < growth <= Decimal("0.2") and wacc > growth):
                sensitivity_row.append(None)
                continue
            try:
                *_, value = _operating_value(inputs.cash_flows, wacc, growth)
                sensitivity_row.append(_json_number(value))
            except (ValueError, DecimalException, OverflowError):
                # The base valuation remains valid when a neighboring case is
                # out of domain or cannot be represented as a finite number.
                sensitivity_row.append(None)
        sensitivity.append(sensitivity_row)

    warnings = [
        "Screening calculation only; supplied forecasts, WACC, terminal assumptions, and bridge values are unverified.",
        "FCFF must include operating taxes, capital expenditure, and working-capital reinvestment, before financing cash flows.",
        "The final forecast year must be normalized for sustainable perpetual growth; this engine does not derive reinvestment or ROIC.",
        "Review cash restrictions and all debt-like claims, including leases, pensions, preferred equity, and non-controlling interests; avoid double counting.",
        "FCFF with WACC may be unsuitable for financial institutions or distressed businesses; method selection requires review.",
    ]
    if inputs.diluted_shares is None:
        warnings.append("Value per share is unavailable because diluted shares were not supplied.")
    if inputs.cash_flows[-1] <= 0:
        warnings.append("Nonpositive final-year FCFF does not support a conventional going-concern perpetuity; review the terminal method.")
    if equity_value < 0:
        warnings.append("The equity bridge has a negative residual. It is retained for analysis, not a negative limited-liability share price or an equity floor.")
    if terminal_share is None:
        warnings.append("Terminal-value share is unavailable when enterprise value is nonpositive or terminal value is negative.")
    elif terminal_share > Decimal("0.5"):
        warnings.append("More than half of enterprise value comes from the terminal period; valuation depends heavily on the terminal assumptions.")
    if any(cell is None for row in sensitivity for cell in row):
        warnings.append("Blank sensitivity cells are outside the supported rate domain or finite numeric range.")

    normalized_inputs = {
        key: (
            [_json_number(item) for item in value] if isinstance(value, list)
            else _json_number(value) if isinstance(value, Decimal)
            else value.isoformat() if isinstance(value, date)
            else value
        )
        for key, value in inputs.model_dump().items()
    }
    return {
        "schema_version": "dcf.v1",
        "inputs": normalized_inputs,
        "forecast": rows,
        "forecast_present_value": _json_number(forecast_pv),
        "terminal_value": _json_number(terminal_value),
        "pv_terminal_value": _json_number(terminal_pv),
        "enterprise_value": _json_number(enterprise_value),
        "equity_value": _json_number(equity_value),
        "value_per_share": _json_number(value_per_share) if value_per_share is not None else None,
        "terminal_value_share": _json_number(terminal_share) if terminal_share is not None else None,
        "sensitivity": {
            "wacc_values": [_json_number(value) for value in wacc_values],
            "terminal_growth_values": [_json_number(value) for value in growth_values],
            "enterprise_values": sensitivity,
        },
        "methodology": {
            "method_id": "annual-end-year-fcff-perpetuity.v1",
            "calculation_integrity": "validated_inputs_and_finite_outputs",
            "decision_readiness": "screening_only_unverified_assumptions",
            "inputs": list(normalized_inputs),
            "formulas": {
                "forecast_present_value": "sum(FCFF[t] / (1 + WACC)^t), t = 1..N",
                "terminal_value": "FCFF[N] * (1 + terminal_growth) / (WACC - terminal_growth)",
                "pv_terminal_value": "terminal_value / (1 + WACC)^N",
                "enterprise_value": "forecast_present_value + pv_terminal_value",
                "equity_value": "enterprise_value + cash + non_operating_assets - debt - other_claims",
                "value_per_share": "equity_value / diluted_shares, if supplied",
                "terminal_value_share": "pv_terminal_value / enterprise_value, if EV > 0 and PV(TV) >= 0",
            },
            "timing": "Full annual periods after as_of; FCFF at each year-end; terminal value at end of year N, first perpetual FCFF in year N+1. No stub or mid-year convention.",
            "forecast_years": len(inputs.cash_flows),
            "currency": inputs.currency,
            "units": "Whole currency units for cash flows and bridge amounts; actual diluted share count; decimal annual rates; value per share in currency/share; terminal share is a fraction.",
            "source": "User-supplied assumptions; source note is recorded, not independently verified.",
            "source_note": inputs.source_note,
            "as_of": inputs.as_of.isoformat(),
            "freshness": "User-declared assumption date; source freshness has not been verified.",
            "precision": "768 significant decimal digits internally; finite binary64 JSON numbers at the output boundary; no intermediate currency rounding.",
            "sensitivity": "EV only; rows WACC +/-100 basis points in 50 bp steps; columns terminal growth +/-50 bp in 25 bp steps. Forecast and bridge held fixed. Invalid/overflow cases are null. This is a local parameter sensitivity, not a probability or scenario forecast.",
            "references": [
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcff.html",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalapproaches.htm",
            ],
            "warnings": warnings.copy(),
        },
        "warnings": warnings,
    }
