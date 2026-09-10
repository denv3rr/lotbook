import math
import unittest
from datetime import datetime

import pandas as pd
import numpy as np

from modules.client_mgr import calculations


class TestFinancialCalculations(unittest.TestCase):
    def test_black_scholes_known_value(self):
        call_price, put_price = calculations.black_scholes_price(
            spot_price=100.0,
            strike_price=100.0,
            time_years=1.0,
            volatility=0.2,
            risk_free=0.05,
        )
        self.assertAlmostEqual(call_price, 10.4506, places=3)
        self.assertAlmostEqual(put_price, 5.5735, places=3)

    def test_calculate_max_drawdown_known(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=6, freq="D")
        returns = pd.Series([0.10, -0.05, -0.05, 0.02, 0.01], index=dates[1:])
        drawdown = calculations.calculate_max_drawdown(returns)
        self.assertLess(drawdown, 0.0)
        self.assertAlmostEqual(drawdown, -0.0975, places=4)

    def test_calculate_var_cvar(self):
        dates = pd.date_range(datetime(2025, 1, 1), periods=6, freq="D")
        returns = pd.Series([-0.10, 0.02, -0.03, 0.04, 0.01], index=dates[1:])
        var_95, cvar_95 = calculations.calculate_var_cvar(returns, 0.95)
        expected_q = returns.quantile(0.05)
        expected_tail = returns[returns <= expected_q].mean()
        self.assertAlmostEqual(var_95, float(expected_q), places=6)
        self.assertAlmostEqual(cvar_95, float(expected_tail), places=6)
        empty_var, empty_cvar = calculations.calculate_var_cvar(pd.Series(dtype=float), 0.95)
        self.assertIsNone(empty_var)
        self.assertIsNone(empty_cvar)

    def test_downside_deviation_uses_full_sample(self):
        returns = pd.Series([0.02, -0.04, 0.01, -0.02])
        threshold = 0.0
        expected = math.sqrt(((0.0 ** 2) + ((-0.04) ** 2) + (0.0 ** 2) + ((-0.02) ** 2)) / 4)
        self.assertAlmostEqual(
            calculations.downside_deviation(returns, threshold),
            expected,
            places=6,
        )

    def test_shannon_entropy(self):
        returns = pd.Series([0.01, 0.01, 0.01, 0.01, 0.01])
        entropy = calculations.shannon_entropy(returns)
        self.assertAlmostEqual(entropy, 0.0, places=6)
        self.assertIsNone(calculations.shannon_entropy(pd.Series([0.01, 0.02])))

    def test_permutation_entropy(self):
        values = [1.0, 2.0, 3.0, 4.0]
        pe = calculations.permutation_entropy(values, order=3, delay=1)
        self.assertAlmostEqual(pe, 0.0, places=6)

        values = [1.0, 3.0, 2.0, 4.0]
        pe = calculations.permutation_entropy(values, order=3, delay=1)
        expected = 1.0 / math.log2(math.factorial(3))
        self.assertAlmostEqual(pe, expected, places=6)

    def test_hurst_exponent(self):
        increments = pd.Series(
            [(((index * 23) % 127) / 126.0 - 0.5) * 0.02 for index in range(1200)]
        )
        values = (100 + increments.cumsum()).tolist()
        hurst = calculations.hurst_exponent(values)
        self.assertIsNotNone(hurst)
        self.assertGreaterEqual(hurst, 0.0)
        self.assertLessEqual(hurst, 1.0)
        self.assertIsNone(calculations.hurst_exponent([1.0, 2.0, 3.0]))

    def test_fft_spectrum(self):
        # A simple sine wave should have a dominant frequency
        t = np.linspace(0, 1, 100)
        values = np.sin(2 * np.pi * 10 * t).tolist() # 10 Hz signal
        spectrum = calculations.fft_spectrum(values, top_n=1)
        self.assertEqual(len(spectrum), 1)
        self.assertAlmostEqual(spectrum[0][0], 0.1, delta=0.01)

    def test_cusum_change_points(self):
        returns = pd.Series([0.001] * 30 + [0.08] * 20)
        change_points = calculations.cusum_change_points(returns, threshold=2.0)
        self.assertTrue(any(28 <= point <= 36 for point in change_points))

    def test_motif_similarity(self):
        returns = pd.Series([0.01, 0.02, 0.03] * 10)
        motifs = calculations.motif_similarity(returns, window=3, top=1)
        self.assertEqual(len(motifs), 1)
        self.assertAlmostEqual(motifs[0]["distance"], 0.0, places=6)

    def test_ewma_vol_forecast(self):
        returns = pd.Series([0.01, -0.01] * 20)
        forecast = calculations.ewma_vol_forecast(returns)
        self.assertEqual(len(forecast), 6)
        for f in forecast:
            self.assertGreaterEqual(f, 0.0)

    def test_compute_capm_metrics_from_returns_known_values(self):
        returns = pd.Series([0.01, 0.02, 0.03])
        benchmark_returns = pd.Series([0.01, 0.02, 0.03])
        metrics = calculations.compute_capm_metrics_from_returns(returns, benchmark_returns, min_points=3)
        self.assertAlmostEqual(metrics['beta'], 1.0, places=6)
        self.assertAlmostEqual(metrics['alpha_annual'], 0.0, places=6)
        self.assertAlmostEqual(metrics['r_squared'], 1.0, places=6)

    def test_black_scholes_put_call_parity(self):
        spot = 100.0
        strike = 100.0
        time_years = 1.0
        vol = 0.2
        rf = 0.05
        call_price, put_price = calculations.black_scholes_price(
            spot_price=spot,
            strike_price=strike,
            time_years=time_years,
            volatility=vol,
            risk_free=rf,
        )
        lhs = call_price - put_price
        rhs = spot - strike * math.exp(-rf * time_years)
        self.assertAlmostEqual(lhs, rhs, places=6)

    def test_empty_risk_metrics_are_unavailable(self):
        metrics = calculations.compute_risk_metrics(pd.Series(dtype=float), None, 0.04)
        self.assertIsNone(metrics["sharpe"])
        self.assertIsNone(metrics["max_drawdown"])
        self.assertIsNone(metrics["var_95"])


if __name__ == "__main__":
    unittest.main()
