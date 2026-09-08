"""Analytic math identities and invalid domains, not empirical valuation evidence."""
import json
from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from modules.banking.valuation import DcfInputs, calculate_dcf


def assumptions(**overrides):
    return DcfInputs(**{ "cash_flows": [100], "wacc": 0.1, "terminal_growth": 0, "debt": 150, "cash": 50, "other_claims": 10, "non_operating_assets": 20, "diluted_shares": 10, "currency": "USD", "as_of": "2025-01-01", "source_note": "Analytic constant-perpetuity unit identity, not company data.", **overrides })


def test_constant_perpetuity_and_equity_bridge():
    output = calculate_dcf(assumptions())
    assert output["enterprise_value"] == pytest.approx(1000)
    assert output["equity_value"] == pytest.approx(910)
    assert output["value_per_share"] == pytest.approx(91)
    assert output["forecast_present_value"] + output["pv_terminal_value"] == pytest.approx(1000)
    json.dumps(output, allow_nan=False)
    assert calculate_dcf(assumptions(cash_flows=[100] * 20))["enterprise_value"] == pytest.approx(1000)


def test_sensitivity_monotonic_and_unknown_shares():
    output = calculate_dcf(assumptions(diluted_shares=None))
    assert output["value_per_share"] is None
    grid = output["sensitivity"]["enterprise_values"]
    assert grid[2][2] == output["enterprise_value"]
    assert all(row == sorted(row) for row in grid)
    assert grid[0][2] > grid[4][2]
    assert calculate_dcf(assumptions(debt=2000))["equity_value"] < 0


@pytest.mark.parametrize("change", [ {"wacc": 0}, {"wacc": True}, {"wacc": "0.1"}, {"terminal_growth": 0.1}, {"cash_flows": []}, {"cash_flows": [float("nan")]}, {"debt": -1}, {"cash": None}, {"diluted_shares": 0}, {"as_of": (date.today() + timedelta(days=2)).isoformat()}, {"source_note": " "} ])
def test_invalid_assumptions_rejected(change):
    with pytest.raises(ValidationError):
        assumptions(**change)


def test_boundary_sensitivity_is_unavailable_not_infinity():
    result = calculate_dcf(assumptions(wacc=0.001))
    assert result["sensitivity"]["enterprise_values"][0][0] is None
    with pytest.raises(ValueError):
        calculate_dcf(assumptions(cash_flows=[1e308]))
