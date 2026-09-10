"""Assumption-driven WACC, capital structure, debt schedule and three-statement linkage.

Formula tests prove arithmetic. They do not verify company evidence. Damodaran
cost-of-capital notes are methodological references, not a certification.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from modules.banking.valuation import FiniteNumber, _json_number


def _calendar_date(value: Any) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        if value == parsed.isoformat():
            if parsed > datetime.now(timezone.utc).date():
                raise ValueError("The assumption date must not be in the future (UTC).")
            return parsed
    raise ValueError("Use a calendar date in YYYY-MM-DD format.")


class WaccInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    equity_weight: FiniteNumber = Field(ge=0, le=1)
    debt_weight: FiniteNumber = Field(ge=0, le=1)
    preferred_weight: FiniteNumber = Field(default=Decimal(0), ge=0, le=1)
    cost_of_equity: FiniteNumber = Field(ge=0, le=1)
    pretax_cost_of_debt: FiniteNumber = Field(ge=0, le=1)
    cost_of_preferred: FiniteNumber = Field(default=Decimal(0), ge=0, le=1)
    tax_rate: FiniteNumber = Field(ge=0, le=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    source_note: str = Field(min_length=1, max_length=4000)

    @field_validator("as_of", mode="before")
    @classmethod
    def dated(cls, value):
        return _calendar_date(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Record the source of the capital-structure weights and rates.")
        return value

    @model_validator(mode="after")
    def weights(self):
        total = self.equity_weight + self.debt_weight + self.preferred_weight
        if abs(total - Decimal(1)) > Decimal("0.00000001"):
            raise ValueError("Equity, debt and preferred weights must sum to 1.")
        return self


def calculate_wacc(inputs: WaccInputs) -> dict[str, Any]:
    after_tax_debt = inputs.pretax_cost_of_debt * (Decimal(1) - inputs.tax_rate)
    wacc = (
        inputs.equity_weight * inputs.cost_of_equity
        + inputs.debt_weight * after_tax_debt
        + inputs.preferred_weight * inputs.cost_of_preferred
    )
    return {
        "inputs": inputs.model_dump(mode="json"),
        "after_tax_cost_of_debt": _json_number(after_tax_debt),
        "wacc": _json_number(wacc),
        "warnings": [
            "Weights are operator-supplied book or target weights, not a solved market-value capital structure.",
            "After-tax cost of debt uses a constant tax rate and ignores interest-deduction limits.",
        ],
        "methodology": {
            "formula": "WACC = we*ke + wd*kd*(1-t) + wp*kp",
            "reference": "Damodaran, cost of capital notes: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/costofcapital.html",
        },
    }


class CapitalStructureInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cash: FiniteNumber = Field(ge=0)
    debt: FiniteNumber = Field(ge=0)
    other_claims: FiniteNumber = Field(ge=0)
    equity_value: FiniteNumber | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    source_note: str = Field(min_length=1, max_length=4000)

    @field_validator("as_of", mode="before")
    @classmethod
    def dated(cls, value):
        return _calendar_date(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Record the source of the capital-structure amounts.")
        return value


def calculate_capital_structure(inputs: CapitalStructureInputs) -> dict[str, Any]:
    net_debt = inputs.debt + inputs.other_claims - inputs.cash
    enterprise = None if inputs.equity_value is None else inputs.equity_value + net_debt
    leverage = None
    if enterprise not in (None, 0) and enterprise > 0:
        leverage = net_debt / enterprise
    return {
        "inputs": inputs.model_dump(mode="json"),
        "net_debt": _json_number(net_debt),
        "enterprise_value": None if enterprise is None else _json_number(enterprise),
        "net_debt_to_enterprise": None if leverage is None else _json_number(leverage),
        "warnings": [
            "Enterprise value is equity residual plus net debt-like claims. Negative net debt is a net cash position.",
            "No rating, covenant or going-concern conclusion is implied.",
        ],
        "methodology": {"formula": "Net debt = debt + other claims - cash. EV = equity + net debt when equity is supplied."},
    }


class DebtPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    beginning_balance: FiniteNumber = Field(ge=0)
    draw: FiniteNumber = Field(default=Decimal(0), ge=0)
    mandatory_paydown: FiniteNumber = Field(default=Decimal(0), ge=0)
    optional_paydown: FiniteNumber = Field(default=Decimal(0), ge=0)
    cash_sweep: FiniteNumber = Field(default=Decimal(0), ge=0)
    interest_rate: FiniteNumber = Field(ge=0, le=1)


class DebtScheduleInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    periods: list[DebtPeriod] = Field(min_length=1, max_length=40)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    source_note: str = Field(min_length=1, max_length=4000)

    @field_validator("as_of", mode="before")
    @classmethod
    def dated(cls, value):
        return _calendar_date(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Record the source of the debt schedule assumptions.")
        return value


def calculate_debt_schedule(inputs: DebtScheduleInputs) -> dict[str, Any]:
    rows = []
    previous_end = None
    with localcontext() as context:
        context.prec = 28
        for index, period in enumerate(inputs.periods, start=1):
            if previous_end is not None and period.beginning_balance != previous_end:
                raise ValueError(f"Period {index} beginning balance must equal the prior ending balance.")
            interest = period.beginning_balance * period.interest_rate
            paydown = period.mandatory_paydown + period.optional_paydown + period.cash_sweep
            ending = period.beginning_balance + period.draw - paydown
            if ending < 0:
                raise ValueError(f"Period {index} paydowns exceed beginning balance plus draws.")
            rows.append({
                "period": index,
                "beginning_balance": _json_number(period.beginning_balance),
                "draw": _json_number(period.draw),
                "interest": _json_number(interest),
                "mandatory_paydown": _json_number(period.mandatory_paydown),
                "optional_paydown": _json_number(period.optional_paydown),
                "cash_sweep": _json_number(period.cash_sweep),
                "ending_balance": _json_number(ending),
            })
            previous_end = ending
    return {
        "inputs": inputs.model_dump(mode="json"),
        "schedule": rows,
        "ending_balance": rows[-1]["ending_balance"],
        "warnings": ["Interest is beginning-balance * period rate. No OID, PIK toggle or covenant test is modeled."],
        "methodology": {"formula": "Ending = beginning + draws - mandatory - optional - cash sweep. Interest = beginning * rate."},
    }


class StatementInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    revenue: FiniteNumber
    operating_costs: FiniteNumber
    depreciation: FiniteNumber = Field(ge=0)
    tax_rate: FiniteNumber = Field(ge=0, le=1)
    capex: FiniteNumber
    nwc_increase: FiniteNumber
    beginning_cash: FiniteNumber
    beginning_other_assets: FiniteNumber = Field(ge=0)
    beginning_debt: FiniteNumber = Field(ge=0)
    beginning_other_liabilities: FiniteNumber = Field(ge=0)
    beginning_equity: FiniteNumber
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    source_note: str = Field(min_length=1, max_length=4000)

    @field_validator("as_of", mode="before")
    @classmethod
    def dated(cls, value):
        return _calendar_date(value)

    @field_validator("source_note")
    @classmethod
    def evidence(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Record the source of the statement assumptions.")
        return value


def calculate_statements(inputs: StatementInputs) -> dict[str, Any]:
    ebit = inputs.revenue - inputs.operating_costs - inputs.depreciation
    tax = ebit * inputs.tax_rate if ebit > 0 else Decimal(0)
    net_income = ebit - tax
    ending_cash = inputs.beginning_cash + net_income + inputs.depreciation - inputs.capex - inputs.nwc_increase
    assets = ending_cash + inputs.beginning_other_assets
    equity = inputs.beginning_equity + net_income
    liabilities = inputs.beginning_debt + inputs.beginning_other_liabilities + equity
    balanced = assets == liabilities
    warnings = []
    if not balanced:
        warnings.append("The balance sheet does not balance. No plug was invented; review cash, NWC, capex and opening balances.")
    if ebit < 0:
        warnings.append("Negative EBIT: tax is recorded as zero rather than a refund unless a separate tax attribute is supplied.")
    return {
        "inputs": inputs.model_dump(mode="json"),
        "income": {
            "ebit": _json_number(ebit),
            "tax": _json_number(tax),
            "net_income": _json_number(net_income),
        },
        "cash_flow": {
            "ending_cash": _json_number(ending_cash),
            "depreciation_addback": _json_number(inputs.depreciation),
            "capex": _json_number(inputs.capex),
            "nwc_increase": _json_number(inputs.nwc_increase),
        },
        "balance_sheet": {
            "assets": _json_number(assets),
            "liabilities_and_equity": _json_number(liabilities),
            "ending_equity": _json_number(equity),
            "balances": balanced,
        },
        "warnings": warnings,
        "methodology": {
            "formula": "EBIT = revenue - operating costs - D&A. NI = EBIT - tax on positive EBIT. Cash = opening cash + NI + D&A - capex - ΔNWC. BS must balance without a hidden plug.",
        },
    }
