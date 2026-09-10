"""Bond and option boundary calculators. Unsupported day-counts stay unavailable."""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.banking.screening import _calendar_date
from modules.banking.valuation import FiniteNumber, _json_number
from modules.client_mgr.calculations import black_scholes_price


class BondInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    face: FiniteNumber = Field(gt=0)
    coupon_rate: FiniteNumber = Field(ge=0, le=1)
    yield_to_maturity: FiniteNumber = Field(ge=0, le=1)
    years: FiniteNumber = Field(gt=0, le=100)
    frequency: Literal[1, 2, 4] = 2
    day_count: Literal["30/360", "ACT/365", "ACT/ACT"] = "30/360"
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
            raise ValueError("Record the source of the bond assumptions.")
        return value


def calculate_bond(inputs: BondInputs) -> dict:
    periods = int(inputs.years * inputs.frequency)
    if Decimal(periods) != inputs.years * inputs.frequency:
        return {
            "inputs": inputs.model_dump(mode="json"),
            "price": None,
            "macaulay_duration": None,
            "modified_duration": None,
            "convexity": None,
            "warnings": ["Years × payment frequency must be a whole number of periods."],
            "methodology": {"day_count": inputs.day_count, "formula": "Standard periodic closed-form price on a whole number of remaining coupon periods."},
        }
    coupon = inputs.face * inputs.coupon_rate / Decimal(inputs.frequency)
    y = inputs.yield_to_maturity / Decimal(inputs.frequency)
    price = Decimal(0)
    weighted = Decimal(0)
    convex = Decimal(0)
    for step in range(1, periods + 1):
        discount = (Decimal(1) + y) ** step
        cash = coupon if step < periods else coupon + inputs.face
        present = cash / discount
        price += present
        years_t = Decimal(step) / Decimal(inputs.frequency)
        weighted += years_t * present
        convex += present * years_t * (years_t + Decimal(1) / Decimal(inputs.frequency))
    macaulay = weighted / price if price else None
    modified = macaulay / (Decimal(1) + y) if macaulay is not None else None
    convexity = convex / (price * (Decimal(1) + y) ** 2) if price else None
    return {
        "inputs": inputs.model_dump(mode="json"),
        "price": _json_number(price),
        "macaulay_duration": None if macaulay is None else _json_number(macaulay),
        "modified_duration": None if modified is None else _json_number(modified),
        "convexity": None if convexity is None else _json_number(convexity),
        "warnings": [
            f"Day-count {inputs.day_count} is recorded for accrued-interest review; this price is a remaining-period closed form with no stub or accrued.",
            "No OAS, call schedule or credit spread is modeled.",
        ],
        "methodology": {
            "price": "Sum of discounted coupons plus face. Period rate = YTM / frequency.",
            "duration": "Macaulay = sum(t*PVCF)/price. Modified = Macaulay / (1 + y/f).",
            "convexity": "sum(t*(t+1/f)*PVCF) / (price * (1+y/f)^2).",
        },
    }


class OptionInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    spot: FiniteNumber = Field(gt=0)
    strike: FiniteNumber = Field(gt=0)
    years: FiniteNumber = Field(ge=0, le=100)
    volatility: FiniteNumber = Field(ge=0, le=5)
    risk_free: FiniteNumber = Field(ge=0, le=1)
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
            raise ValueError("Record the source of the option assumptions.")
        return value


def calculate_option(inputs: OptionInputs) -> dict:
    spot = float(inputs.spot)
    strike = float(inputs.strike)
    years = float(inputs.years)
    vol = float(inputs.volatility)
    rate = float(inputs.risk_free)
    warnings = ["European Black-Scholes-Merton, no dividends. Not a listed-option mark."]
    if years == 0:
        call = max(spot - strike, 0.0)
        put = max(strike - spot, 0.0)
        warnings.append("Zero tenor uses intrinsic value. No discounting remains.")
    elif vol == 0:
        forward = spot * math.exp(rate * years)
        call = math.exp(-rate * years) * max(forward - strike, 0.0)
        put = math.exp(-rate * years) * max(strike - forward, 0.0)
        warnings.append("Zero volatility uses discounted intrinsic on the forward.")
    else:
        call, put = black_scholes_price(spot, strike, years, vol, rate)
        if not math.isfinite(call) or not math.isfinite(put):
            return {
                "inputs": inputs.model_dump(mode="json"),
                "call": None,
                "put": None,
                "parity_gap": None,
                "warnings": warnings + ["The Black-Scholes evaluation was not finite for these inputs."],
                "methodology": {"model": "Black-Scholes-Merton European, no dividend yield."},
            }
    discount_strike = strike * math.exp(-rate * years) if years > 0 else strike
    parity = call - put - (spot - discount_strike)
    return {
        "inputs": inputs.model_dump(mode="json"),
        "call": call,
        "put": put,
        "parity_gap": parity,
        "warnings": warnings,
        "methodology": {
            "model": "Black-Scholes-Merton European, no dividend yield.",
            "parity": "C - P = S - K e^{-rt}. A non-zero gap is a numerical residual, not an arbitrage signal.",
        },
    }
