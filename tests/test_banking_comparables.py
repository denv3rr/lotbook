"""Deterministic formula examples, not market-data integration evidence."""
import pytest
from pydantic import ValidationError
from modules.banking.comparables import CompsInputs, calculate_comps


def assumptions():
    return {"peers": [{"name": "Arithmetic A", "enterprise_value": 100, "revenue": 50, "ebitda": 10, "source_note": "Unit arithmetic only"}, {"name": "Arithmetic B", "enterprise_value": 300, "revenue": 100, "ebitda": 20, "source_note": "Unit arithmetic only"}], "currency": "USD", "as_of": "2026-01-01", "period_basis": "LTM", "source_note": "Unit arithmetic only", "target_revenue": 200, "target_ebitda": 40, "cash": 20, "debt": 70, "other_claims": 0, "non_operating_assets": 0}


def test_multiples_median_quartiles_and_equity_bridge():
    result = calculate_comps(CompsInputs.model_validate(assumptions()))
    revenue, ebitda = result["summaries"]
    assert revenue["cases"][1]["multiple"] == 2.25
    assert ebitda["cases"][3]["multiple"] == 13.75
    for summary in result["summaries"]:
        median = summary["cases"][2]
        assert median["enterprise_value"] == 500
        assert median["equity_value"] == 450
        assert median["value_per_share"] is None


def test_nonpositive_and_missing_denominators_are_excluded():
    body = assumptions()
    body["peers"][0]["ebitda"] = 0
    body["peers"][1]["ebitda"] = -20
    result = calculate_comps(CompsInputs.model_validate(body))["summaries"][1]
    assert result["included_peers"] == 0
    assert all(row["multiple"] is None and row["enterprise_value"] is None for row in result["cases"])


@pytest.mark.parametrize("value", [True, "100", float("nan"), float("inf"), 0, -1])
def test_invalid_peer_ev_rejected(value):
    body = assumptions()
    body["peers"][0]["enterprise_value"] = value
    with pytest.raises(ValidationError):
        CompsInputs.model_validate(body)


def test_duplicate_peers_do_not_bias_percentiles():
    body = assumptions()
    body["peers"][1]["name"] = " arithmetic   A "
    with pytest.raises(ValidationError):
        CompsInputs.model_validate(body)
