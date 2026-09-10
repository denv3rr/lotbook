"""Arithmetic-only TWR, XIRR, WACC, merger, LBO, bond and option boundaries."""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from modules.client_mgr import calculations
from modules.client_mgr.performance import time_weighted_return, xirr
from modules.banking.screening import DebtPeriod, DebtScheduleInputs, StatementInputs, WaccInputs, calculate_debt_schedule, calculate_statements, calculate_wacc
from modules.banking.deals_math import LboInputs, MergerInputs, calculate_lbo, calculate_merger
from modules.banking.instruments import BondInputs, OptionInputs, calculate_bond, calculate_option


def test_twr_links_subperiods():
    result = time_weighted_return([
        (Decimal(100), Decimal(110), Decimal(0)),
        (Decimal(110), Decimal(121), Decimal(0)),
    ])
    assert result == pytest.approx(Decimal("0.21"))


def test_xirr_round_trip_simple():
    rate = xirr([(date(2021, 1, 1), Decimal(-1000)), (date(2022, 1, 1), Decimal(1100))])
    assert rate == pytest.approx(Decimal("0.1"), rel=Decimal("0.001"))


def test_wacc_after_tax_debt():
    result = calculate_wacc(WaccInputs(
        equity_weight=Decimal("0.6"),
        debt_weight=Decimal("0.4"),
        cost_of_equity=Decimal("0.1"),
        pretax_cost_of_debt=Decimal("0.05"),
        tax_rate=Decimal("0.2"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert result["after_tax_cost_of_debt"] == pytest.approx(0.04)
    assert result["wacc"] == pytest.approx(0.076)


def test_debt_schedule_rejects_unlinked_balances():
    with pytest.raises(ValueError, match="beginning balance"):
        calculate_debt_schedule(DebtScheduleInputs(
            periods=[
                DebtPeriod(beginning_balance=Decimal("100"), interest_rate=Decimal("0.1"), mandatory_paydown=Decimal("10")),
                DebtPeriod(beginning_balance=Decimal("50"), interest_rate=Decimal("0.1")),
            ],
            currency="USD",
            as_of="2026-01-01",
            source_note="Isolated arithmetic.",
        ))


def test_statements_fail_closed_when_unbalanced():
    result = calculate_statements(StatementInputs(
        revenue=Decimal("100"),
        operating_costs=Decimal("40"),
        depreciation=Decimal("10"),
        tax_rate=Decimal("0"),
        capex=Decimal("5"),
        nwc_increase=Decimal("0"),
        beginning_cash=Decimal("0"),
        beginning_other_assets=Decimal("0"),
        beginning_debt=Decimal("0"),
        beginning_other_liabilities=Decimal("0"),
        beginning_equity=Decimal("0"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert result["income"]["net_income"] == 50
    assert result["balance_sheet"]["balances"] is False
    assert any("does not balance" in warning for warning in result["warnings"])


def test_merger_accretion():
    result = calculate_merger(MergerInputs(
        acquirer_net_income=Decimal("100"),
        target_net_income=Decimal("20"),
        synergies_after_tax=Decimal("0"),
        incremental_interest_after_tax=Decimal("0"),
        acquirer_shares=Decimal("10"),
        new_shares=Decimal("2"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert result["standalone_eps"] == 10
    assert result["pro_forma_eps"] == 10
    assert result["accretion"] == 0


def test_lbo_moic_and_irr():
    result = calculate_lbo(LboInputs(
        sponsor_equity=Decimal("100"),
        exit_year=1,
        exit_equity=Decimal("120"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert result["moic"] == pytest.approx(1.2)
    assert result["irr"] == pytest.approx(0.2, rel=0.02)


def test_bond_whole_periods_and_option_boundaries():
    bond = calculate_bond(BondInputs(
        face=Decimal("100"),
        coupon_rate=Decimal("0"),
        yield_to_maturity=Decimal("0"),
        years=Decimal("1"),
        frequency=1,
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert bond["price"] == 100
    intrinsic = calculate_option(OptionInputs(
        spot=Decimal("110"),
        strike=Decimal("100"),
        years=Decimal("0"),
        volatility=Decimal("0.2"),
        risk_free=Decimal("0"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert intrinsic["call"] == 10
    assert intrinsic["put"] == 0
    zero_vol = calculate_option(OptionInputs(
        spot=Decimal("100"),
        strike=Decimal("100"),
        years=Decimal("1"),
        volatility=Decimal("0"),
        risk_free=Decimal("0"),
        currency="USD",
        as_of="2026-01-01",
        source_note="Isolated arithmetic.",
    ))
    assert zero_vol["call"] == 0
    assert zero_vol["put"] == 0


def test_insufficient_entropy_is_unavailable():
    assert calculations.shannon_entropy(pd.Series([0.01, 0.02])) is None
    assert calculations.permutation_entropy([1.0], order=3) is None
