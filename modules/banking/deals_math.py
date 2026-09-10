"""Merger accretion/dilution, LBO returns and precedent transaction screens.

Assumption-driven calculators. Not deal advice and not a fairness opinion.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from modules.banking.screening import _calendar_date
from modules.banking.valuation import FiniteNumber, _json_number
from modules.client_mgr.performance import xirr


class MergerInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    acquirer_net_income: FiniteNumber
    target_net_income: FiniteNumber
    synergies_after_tax: FiniteNumber = Decimal(0)
    incremental_interest_after_tax: FiniteNumber = Field(default=Decimal(0), ge=0)
    acquirer_shares: FiniteNumber = Field(gt=0)
    new_shares: FiniteNumber = Field(default=Decimal(0), ge=0)
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
            raise ValueError("Record the source of the merger assumptions.")
        return value


def calculate_merger(inputs: MergerInputs) -> dict[str, Any]:
    standalone_eps = inputs.acquirer_net_income / inputs.acquirer_shares
    pro_forma_income = (
        inputs.acquirer_net_income
        + inputs.target_net_income
        + inputs.synergies_after_tax
        - inputs.incremental_interest_after_tax
    )
    pro_forma_shares = inputs.acquirer_shares + inputs.new_shares
    pro_forma_eps = pro_forma_income / pro_forma_shares
    accretion = None if standalone_eps == 0 else pro_forma_eps / standalone_eps - Decimal(1)
    warnings = []
    if standalone_eps <= 0:
        warnings.append("Standalone EPS is not positive; accretion percentage is unavailable.")
    if pro_forma_income < 0:
        warnings.append("Pro forma net income is negative; EPS remains visible and is not replaced with zero.")
    return {
        "inputs": inputs.model_dump(mode="json"),
        "standalone_eps": _json_number(standalone_eps),
        "pro_forma_net_income": _json_number(pro_forma_income),
        "pro_forma_shares": _json_number(pro_forma_shares),
        "pro_forma_eps": _json_number(pro_forma_eps),
        "accretion": None if accretion is None else _json_number(accretion),
        "warnings": warnings,
        "methodology": {
            "formula": "PF NI = acquirer NI + target NI + after-tax synergies - after-tax incremental interest. PF EPS = PF NI / (acquirer shares + new shares). Accretion = PF EPS / standalone EPS - 1.",
        },
    }


class LboInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sponsor_equity: FiniteNumber = Field(gt=0)
    exit_year: int = Field(ge=1, le=20)
    exit_equity: FiniteNumber
    intermediate_equity_flows: list[FiniteNumber] = Field(default_factory=list, max_length=20)
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
            raise ValueError("Record the source of the LBO assumptions.")
        return value

    @model_validator(mode="after")
    def flow_length(self):
        if self.intermediate_equity_flows and len(self.intermediate_equity_flows) != self.exit_year - 1:
            raise ValueError("Supply one intermediate sponsor cash flow per year before exit, or none.")
        return self


def calculate_lbo(inputs: LboInputs) -> dict[str, Any]:
    moic = inputs.exit_equity / inputs.sponsor_equity
    start = inputs.as_of
    flows = [(start, -inputs.sponsor_equity)]
    for offset, amount in enumerate(inputs.intermediate_equity_flows, start=1):
        flows.append((date(start.year + offset, start.month, min(start.day, 28)), amount))
    flows.append((date(start.year + inputs.exit_year, start.month, min(start.day, 28)), inputs.exit_equity))
    rate = xirr(flows)
    warnings = [
        "MOIC uses exit equity / sponsor equity and ignores intermediate flows.",
        "IRR uses dated sponsor flows with a 365-day year. Calendar day 29-31 is stored as day 28 for anniversary dating so invalid calendar dates are not invented.",
    ]
    if rate is None:
        warnings.append("IRR is unavailable for this cash-flow pattern.")
    return {
        "inputs": inputs.model_dump(mode="json"),
        "moic": _json_number(moic),
        "irr": None if rate is None else _json_number(rate),
        "warnings": warnings,
        "methodology": {
            "moic": "Exit equity / sponsor equity.",
            "irr": "XIRR on sponsor equity outflows and inflows, 365-day year.",
        },
    }


class PrecedentDeal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    enterprise_value: FiniteNumber = Field(gt=0)
    revenue: FiniteNumber | None = None
    ebitda: FiniteNumber | None = None
    announced_premium: FiniteNumber | None = None


class PrecedentInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    deals: list[PrecedentDeal] = Field(min_length=1, max_length=40)
    target_revenue: FiniteNumber | None = None
    target_ebitda: FiniteNumber | None = None
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
            raise ValueError("Record the source of the precedent transactions.")
        return value

    @model_validator(mode="after")
    def unique_names(self):
        names = [" ".join(deal.name.casefold().split()) for deal in self.deals]
        if len(names) != len(set(names)):
            raise ValueError("Precedent deal names must be unique after spacing is normalized.")
        return self


def _percentiles(values: list[Decimal]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None, "coverage": 0}
    ordered = sorted(values)
    n = len(ordered)

    def at(p: Decimal) -> Decimal:
        if n == 1:
            return ordered[0]
        index = p * Decimal(n - 1)
        low = int(index)
        high = min(low + 1, n - 1)
        weight = index - Decimal(low)
        return ordered[low] * (Decimal(1) - weight) + ordered[high] * weight

    return {
        "min": _json_number(ordered[0]),
        "q1": _json_number(at(Decimal("0.25"))),
        "median": _json_number(at(Decimal("0.5"))),
        "q3": _json_number(at(Decimal("0.75"))),
        "max": _json_number(ordered[-1]),
        "coverage": n,
    }


def calculate_precedent(inputs: PrecedentInputs) -> dict[str, Any]:
    ev_rev = []
    ev_ebitda = []
    premiums = []
    rows = []
    for deal in inputs.deals:
        revenue_multiple = None if not deal.revenue or deal.revenue <= 0 else deal.enterprise_value / deal.revenue
        ebitda_multiple = None if not deal.ebitda or deal.ebitda <= 0 else deal.enterprise_value / deal.ebitda
        if revenue_multiple is not None:
            ev_rev.append(revenue_multiple)
        if ebitda_multiple is not None:
            ev_ebitda.append(ebitda_multiple)
        if deal.announced_premium is not None:
            premiums.append(deal.announced_premium)
        rows.append({
            "name": deal.name,
            "enterprise_value": _json_number(deal.enterprise_value),
            "ev_revenue": None if revenue_multiple is None else _json_number(revenue_multiple),
            "ev_ebitda": None if ebitda_multiple is None else _json_number(ebitda_multiple),
            "announced_premium": None if deal.announced_premium is None else _json_number(deal.announced_premium),
        })
    def median(values: list[Decimal]) -> Decimal:
        ordered = sorted(values)
        count = len(ordered)
        if count % 2:
            return ordered[count // 2]
        return (ordered[count // 2 - 1] + ordered[count // 2]) / Decimal(2)

    implied = {}
    if inputs.target_revenue and inputs.target_revenue > 0 and ev_rev:
        implied["ev_from_revenue_median"] = _json_number(inputs.target_revenue * median(ev_rev))
    if inputs.target_ebitda and inputs.target_ebitda > 0 and ev_ebitda:
        implied["ev_from_ebitda_median"] = _json_number(inputs.target_ebitda * median(ev_ebitda))
    return {
        "inputs": inputs.model_dump(mode="json"),
        "deals": rows,
        "ev_revenue": _percentiles(ev_rev),
        "ev_ebitda": _percentiles(ev_ebitda),
        "premiums": _percentiles(premiums),
        "implied": implied,
        "warnings": [
            "Multiples exclude non-positive denominators. Coverage is the count of included deals, not a quality score.",
            "No control premium is added unless supplied as an announced premium on a deal.",
        ],
        "methodology": {
            "formula": "EV / positive revenue or EBITDA. Percentiles use linear interpolation at (n-1)*p.",
        },
    }
