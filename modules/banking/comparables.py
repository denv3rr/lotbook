"""Operator-sourced EV/revenue and EV/EBITDA comparable valuation."""
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from modules.banking.valuation import DcfInputs, FiniteNumber, _json_number


class Peer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    enterprise_value: FiniteNumber = Field(gt=0)
    revenue: FiniteNumber | None = None
    ebitda: FiniteNumber | None = None
    source_note: str = Field(min_length=1, max_length=4000)


class CompsInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    peers: list[Peer] = Field(min_length=1, max_length=50)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    period_basis: Literal["LTM", "NTM"]
    source_note: str = Field(min_length=1, max_length=4000)
    target_revenue: FiniteNumber | None = None
    target_ebitda: FiniteNumber | None = None
    debt: FiniteNumber = Field(ge=0)
    cash: FiniteNumber = Field(ge=0)
    other_claims: FiniteNumber = Field(ge=0)
    non_operating_assets: FiniteNumber = Field(ge=0)
    diluted_shares: FiniteNumber | None = Field(default=None, gt=0)

    @field_validator("as_of", mode="before")
    @classmethod
    def calendar_date(cls, value):
        return DcfInputs.calendar_date(value)

    @field_validator("as_of")
    @classmethod
    def not_future(cls, value):
        return DcfInputs.not_future(value)

    @model_validator(mode="after")
    def unique_peers(self):
        names = [" ".join(peer.name.casefold().split()) for peer in self.peers]
        if len(set(names)) != len(names):
            raise ValueError("Each peer may appear only once.")
        return self


def calculate_comps(inputs: CompsInputs) -> dict:
    inputs = CompsInputs.model_validate(inputs.model_dump())
    with localcontext() as context:
        context.prec = 768
        ratios, peers, summaries = {"revenue": [], "ebitda": []}, [], []
        for peer in inputs.peers:
            row = {"name": peer.name, "source_note": peer.source_note}
            for metric in ratios:
                denominator = getattr(peer, metric)
                ratio = peer.enterprise_value / denominator if denominator is not None and denominator > 0 else None
                row["ev_" + metric] = _json_number(ratio) if ratio is not None else None
                if ratio is not None:
                    ratios[metric].append(ratio)
            peers.append(row)
        for metric, values in ratios.items():
            values.sort()
            target, cases = getattr(inputs, "target_" + metric), []
            for label, fraction in [("Minimum", "0"), ("Lower quartile", ".25"), ("Median", ".5"), ("Upper quartile", ".75"), ("Maximum", "1")]:
                multiple = None
                if values:
                    position = (len(values) - 1) * Decimal(fraction)
                    lower = int(position)
                    multiple = values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)
                ev = multiple * target if multiple is not None and target is not None and target > 0 else None
                equity = ev + inputs.cash + inputs.non_operating_assets - inputs.debt - inputs.other_claims if ev is not None else None
                share = equity / inputs.diluted_shares if equity is not None and inputs.diluted_shares is not None else None
                cases.append({"label": label, **{key: _json_number(value) if value is not None else None for key, value in {"multiple": multiple, "enterprise_value": ev, "equity_value": equity, "value_per_share": share}.items()}})
            summaries.append({"metric": metric, "included_peers": len(values), "total_peers": len(inputs.peers), "cases": cases})
        return {"schema_version": "comps.v1", "inputs": inputs.model_dump(mode="json"), "peers": peers, "summaries": summaries,
            "warnings": ["Operator-supplied peers and financials are unverified. Use consistent currency units, accounting adjustments, observation dates and LTM/NTM periods.", "Missing, zero and negative denominators are excluded. Coverage is reported per multiple.", "Small peer sets, outliers, growth, risk and margin differences can make quartiles misleading. No automatic outlier removal or control premium is applied.", "Negative equity residuals are retained, not treated as a valuation of shareholder limited liability."],
            "methodology": {"multiples": "EV / revenue or EBITDA. Linear-interpolated percentiles at (n-1)*p.", "implied_value": "Target metric * multiple. Equity adds cash and non-operating assets, subtracts debt and other claims. Per-share requires diluted shares.", "source": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/vebitnote.html"}}
