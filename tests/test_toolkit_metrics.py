import math
import unittest
from unittest import mock
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from modules.client_mgr.toolkit import FinancialToolkit
from modules.client_mgr.client_model import Client


class ToolkitMetricsTests(unittest.TestCase):
    def test_market_data_failure_does_not_expose_exception_detail(self):
        toolkit = FinancialToolkit(Client())
        with mock.patch(
            "modules.client_mgr.toolkit.fetch_close_frame",
            return_value=(pd.DataFrame(), {"error": "Market data unavailable."}),
        ):
            portfolio, benchmark, error = toolkit._get_portfolio_and_benchmark_returns(
                {"AAPL": 1.0},
                "^GSPC",
                "1mo",
                "1d",
            )

        self.assertIsNone(portfolio)
        self.assertIsNone(benchmark)
        self.assertEqual(error, "Market data unavailable.")
        self.assertNotIn("PRIVATE_MARKET_SENTINEL", error)

    def test_annualization_factor_from_index_daily(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=6, freq="D")
        returns = pd.Series([0.01, -0.005, 0.002, 0.0, 0.003], index=dates[1:])
        ann = FinancialToolkit._annualization_factor_from_index(returns)
        self.assertGreater(ann, 300.0)
        self.assertLess(ann, 400.0)

    def test_compute_risk_metrics_constant(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=10, freq="D")
        returns = pd.Series([0.01] * 9, index=dates[1:])
        toolkit = FinancialToolkit(Client())
        metrics = toolkit._compute_risk_metrics(returns, None, risk_free_annual=0.0)
        ann = FinancialToolkit._annualization_factor_from_index(returns)
        expected_mean = returns.mean() * ann
        self.assertAlmostEqual(metrics["vol_annual"], 0.0, places=6)
        self.assertAlmostEqual(metrics["mean_annual"], expected_mean, places=6)

    def test_compute_core_metrics_mean(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=6, freq="D")
        returns = pd.Series([0.01, 0.00, -0.01, 0.02, 0.01], index=dates[1:])
        metrics = FinancialToolkit._compute_core_metrics(returns)
        ann = FinancialToolkit._annualization_factor_from_index(returns)
        expected = returns.mean() * ann
        self.assertTrue(math.isfinite(metrics["mean_return"]))
        self.assertAlmostEqual(metrics["mean_return"], expected, places=6)

    def test_compute_core_metrics_beta(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=8, freq="D")
        returns = pd.Series([0.01, 0.02, -0.01, 0.00, 0.02, 0.01, 0.03], index=dates[1:])
        bench = pd.Series([0.01, 0.02, -0.01, 0.00, 0.02, 0.01, 0.03], index=dates[1:])
        metrics = FinancialToolkit._compute_core_metrics(returns, bench)
        combined = pd.concat([returns, bench], axis=1).dropna()
        cov = np.cov(combined.iloc[:, 0], combined.iloc[:, 1], ddof=1)[0, 1]
        mkt_var = np.var(combined.iloc[:, 1], ddof=1)
        expected_beta = cov / mkt_var if mkt_var != 0 else None
        self.assertAlmostEqual(metrics["beta"], expected_beta, places=6)

    def test_pattern_payload_includes_perm_entropy_context(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=20, freq="D")
        returns = pd.Series([0.01] * 19, index=dates[1:])
        toolkit = FinancialToolkit(Client())
        payload = toolkit._get_pattern_payload(returns, "1M", "test")
        self.assertIn("perm_entropy_order", payload)
        self.assertIn("perm_entropy_delay", payload)
        self.assertGreaterEqual(payload.get("perm_entropy_order", 0), 2)
        self.assertGreaterEqual(payload.get("perm_entropy_delay", 0), 1)

    def test_compute_risk_metrics_with_benchmark(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=13, freq="D")
        data = [0.01, 0.02, 0.00, -0.01, 0.03, 0.02, 0.01, -0.02, 0.015, 0.005, 0.01, 0.0]
        returns = pd.Series(data, index=dates[1:])
        bench = pd.Series([val * 0.9 + 0.001 for val in data], index=dates[1:])
        toolkit = FinancialToolkit(Client())
        metrics = toolkit._compute_risk_metrics(returns, bench, risk_free_annual=0.0)
        combined = pd.concat([returns, bench], axis=1).dropna()
        p = combined.iloc[:, 0].values
        m = combined.iloc[:, 1].values
        expected_beta = float(np.cov(p, m, ddof=1)[0][1]) / float(np.var(m, ddof=1))
        expected_r2 = float(np.corrcoef(p, m)[0][1]) ** 2
        self.assertAlmostEqual(metrics["beta"], expected_beta, places=6)
        self.assertAlmostEqual(metrics["r_squared"], expected_r2, places=6)
        self.assertIsNotNone(metrics["sharpe"])
        self.assertIsNotNone(metrics["sortino"])
        self.assertIsNotNone(metrics["tracking_error"])
        self.assertIsNotNone(metrics["information_ratio"])
        self.assertIsNotNone(metrics["treynor"])
        self.assertIsNotNone(metrics["m_squared"])
        self.assertIsNotNone(metrics["var_95"])
        self.assertIsNotNone(metrics["cvar_95"])
        self.assertIsNotNone(metrics["var_99"])
        self.assertIsNotNone(metrics["cvar_99"])

    def test_compute_capm_from_returns(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=8, freq="D")
        returns = pd.Series([0.01, 0.02, 0.00, -0.01, 0.03, -0.02, 0.01], index=dates[1:])
        bench = pd.Series([0.01, 0.02, 0.00, -0.01, 0.03, -0.02, 0.01], index=dates[1:])
        capm = FinancialToolkit.compute_capm_metrics_from_returns(
            returns,
            bench,
            risk_free_annual=0.0,
            min_points=5,
        )
        self.assertEqual(capm.get("error"), "")
        self.assertAlmostEqual(capm.get("beta"), 1.0, places=6)
        self.assertAlmostEqual(capm.get("r_squared"), 1.0, places=6)
        self.assertIsNotNone(capm.get("vol_annual"))
        self.assertIsNotNone(capm.get("downside_vol_annual"))

    def test_compute_capm_from_returns_insufficient(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=4, freq="D")
        returns = pd.Series([0.01, 0.02, 0.00], index=dates[1:])
        bench = pd.Series([0.01, 0.02, 0.00], index=dates[1:])
        capm = FinancialToolkit.compute_capm_metrics_from_returns(
            returns,
            bench,
            risk_free_annual=0.0,
            min_points=5,
        )
        self.assertNotEqual(capm.get("error"), "")
        self.assertIsNone(capm.get("beta"))

    def test_get_interval_or_select_reuses_existing(self):
        toolkit = FinancialToolkit(Client())
        toolkit._selected_interval = "1M"
        with mock.patch.object(toolkit, "_select_interval", side_effect=AssertionError("Should not prompt")):
            self.assertEqual(toolkit._get_interval_or_select(), "1M")

    def test_get_interval_or_select_force_updates(self):
        toolkit = FinancialToolkit(Client())
        toolkit._selected_interval = "1M"
        with mock.patch.object(toolkit, "_select_interval", return_value="3M") as mocked:
            self.assertEqual(toolkit._get_interval_or_select(force=True), "3M")
            self.assertEqual(toolkit._selected_interval, "3M")
            mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
