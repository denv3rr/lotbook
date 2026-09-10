"""Arithmetic-only method controls and offline reference traceability checks.

These inputs are not provider observations or business/visual fixtures.
"""
import json
from pathlib import Path
import re

import pandas as pd
import pytest

from modules.client_mgr import calculations


def test_single_observation_does_not_invent_sample_volatility_or_sharpe():
    returns = pd.Series([0.01])
    core = calculations.compute_core_metrics(returns)
    risk = calculations.compute_risk_metrics(returns, None, 0.0)
    assert core["volatility_annual"] is None
    assert core["sharpe"] is None
    assert risk["vol_annual"] is None
    assert risk["sharpe"] is None
    assert core["mean_return"] == pytest.approx(2.52)
    json.dumps([core, risk], allow_nan=False)


def test_capm_requires_two_samples_and_variable_benchmark_for_r_squared():
    assert calculations.compute_capm_metrics_from_returns(
        pd.Series([.01]), pd.Series([.02]), min_points=1
    )["error"]
    result = calculations.compute_capm_metrics_from_returns(
        pd.Series([-.01, .02] * 10), pd.Series([0.] * 20), min_points=3
    )
    assert result["beta"] is None
    assert result["r_squared"] is None
    json.dumps(result, allow_nan=False)


def test_regime_preserves_undefined_benchmark_metrics_unit(monkeypatch):
    from modules.client_mgr import regime
    # Arithmetic-only adapter check, not evidence of provider availability.
    index = pd.date_range("2026-01-01", periods=21)
    portfolio = pd.DataFrame({"Close": [100., 101.] * 10 + [100.]}, index=index)
    benchmark = pd.DataFrame({"Close": [100.] * 21}, index=index)
    monkeypatch.setattr(
        regime.yf, "download", lambda ticker, **kwargs: portfolio if ticker == "UNIT" else benchmark
    )
    metrics = regime.RegimeModels.generate_snapshot(
        "UNIT", "UNITBENCH", risk_free_annual=.04
    )["metrics"]
    assert metrics["beta"] is None
    assert metrics["alpha_annual"] is None
    assert metrics["r_squared"] is None
    assert metrics["risk_free_annual"] == .04
    json.dumps(metrics, allow_nan=False)


@pytest.mark.parametrize("q", [0.0, 1.0, -0.1, 1.1, float("nan")])
def test_tail_confidence_outside_open_unit_interval_is_unavailable(q):
    assert calculations.calculate_var_cvar(pd.Series([-.1, .02]), q) == (None, None)


def test_tail_missing_values_fail_closed_and_ties_use_inclusive_convention():
    assert calculations.calculate_var_cvar(pd.Series([-.1, float("nan")]), .95) == (None, None)
    # One of four observations is strictly below the cutoff. Both ties count.
    var, cvar = calculations.calculate_var_cvar(pd.Series([-.1, -.05, -.05, .1]), .5)
    assert var == pytest.approx(-.05)
    assert cvar == pytest.approx(-.2 / 3)


def test_readme_references_have_local_implementation_and_evidence_links():
    root = Path(__file__).resolve().parents[1]
    register = json.loads((root / "docs/reference_register.json").read_text(encoding="utf-8"))
    corpus = json.loads((root / "docs/inspection/corpus.json").read_text(encoding="utf-8"))
    assert {"docs/reference_coverage.md", "docs/reference_register.json"} <= set(corpus["files"])
    readme = (root / "README.md").read_text(encoding="utf-8")
    scope = readme.split("### Standards And Governance", 1)[1].split("### Data And Feeds", 1)[0]
    urls = set(re.findall(r"https://[^\s)]+", scope))
    assert urls == {entry["url"] for entry in register["references"]}
    assert len({entry["id"] for entry in register["references"]}) == len(register["references"])
    for entry in register["references"]:
        assert entry["coverage"] in {"partial", "method", "background"}
        assert entry["limitation"] and entry["version"]
        for group in ("implementation", "verification"):
            assert entry[group]
            for name in entry[group]:
                target = (root / name).resolve()
                assert target.is_relative_to(root) and target.is_file(), name
