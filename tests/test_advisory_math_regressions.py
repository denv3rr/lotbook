"""Unit-scoped analytic controls for independently identified financial defects."""
from datetime import date
import pandas as pd
import pytest

from modules.client_mgr import calculations
from modules.client_mgr.valuation import ValuationEngine
from modules.client_mgr.tax import TaxEngine


def test_opening_loss_and_constant_hurst():
    assert calculations.calculate_max_drawdown(pd.Series([-0.1])) == pytest.approx(-0.1)
    assert calculations.calculate_max_drawdown(pd.Series([-0.1, -0.1, .01])) == pytest.approx(-0.19)
    assert calculations.hurst_exponent([1.] * 200) is None


def test_constant_benchmark_does_not_invent_alpha_or_r_squared():
    result = calculations.compute_risk_metrics(pd.Series([-.01, .02] * 10), pd.Series([0.] * 20), .04)
    assert result["beta"] is None
    assert result["alpha_annual"] is None
    assert result["r_squared"] is None


def test_history_requires_shared_dates_and_complete_coverage():
    engine = ValuationEngine()
    rows = {"A": {"history": [10, 20], "history_dates": ["2025-01-01", "2025-01-02"]}, "B": {"history": [100, 200], "history_dates": ["2025-01-02", "2025-01-03"]}}
    dates, values = engine.generate_portfolio_history_series(rows, {"A": 1, "B": 1})
    assert len(dates) == 1
    assert values == [120]
    assert engine.generate_portfolio_history_series(rows, {"A": 1, "B": 1, "C": 1}) == ([], [])
    rows["A"]["history_dates"] = []
    assert engine.generate_portfolio_history_series(rows, {"A": 1}) == ([], [])


def test_us_holding_period_is_more_than_calendar_year():
    assert not TaxEngine.is_long_term(date(2023, 3, 1), date(2024, 3, 1), "US", 365)
    assert TaxEngine.is_long_term(date(2023, 3, 1), date(2024, 3, 2), "US", 365)
    assert not TaxEngine.is_long_term(date(2024, 2, 29), date(2025, 2, 28), "US", 365)
    assert TaxEngine.is_long_term(date(2024, 2, 29), date(2025, 3, 1), "US", 365)


def test_held_benchmark_and_missing_holding_arithmetic_unit(monkeypatch):
    from modules.client_mgr import data
    # Isolated arithmetic only; this is not provider or route evidence.
    close = pd.DataFrame({"Close": [100., 110., 99.]}, index=pd.date_range("2026-01-01", periods=3))
    monkeypatch.setattr(data.yf, "download", lambda *args, **kwargs: close)
    portfolio, benchmark, meta = data.get_portfolio_and_benchmark_returns({"SPY": 2}, "SPY", "1mo", "1d")
    assert portfolio.tolist() == pytest.approx([.1, -.1])
    assert portfolio.tolist() == benchmark.tolist()
    assert "reconstruction" in meta
    portfolio, _, reason = data.get_portfolio_and_benchmark_returns({"SPY": 2, "MISSING": 1}, "SPY", "1mo", "1d")
    assert portfolio is None
    assert "identity unavailable" in reason
