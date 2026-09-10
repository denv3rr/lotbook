from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from modules.client_mgr import calculations


class RegimeModels:
    """
    Collection of regime-based predictive models.
    """

    DEFAULT_BINS = [
        -math.inf, -0.02, -0.005, 0.005, 0.02, math.inf
    ]

    STATE_LABELS = [
        "Strong Down",
        "Mild Down",
        "Flat",
        "Mild Up",
        "Strong Up"
    ]

    INTERVAL_POINTS = {
        "1W": 5,
        "1M": 21,
        "3M": 63,
        "6M": 126,
        "1Y": 252,
    }

    ANNUALIZATION = {
        "1W": 252.0 * 6.5,  # 60m bars, approx 6.5 trading hours/day
        "1M": 252.0,
        "3M": 252.0,
        "6M": 252.0,
        "1Y": 252.0,
        "1D": 252.0,
        "1WK": 52.0,
        "1MO": 12.0,
        "60M": 252.0 * 6.5,
    }

    @staticmethod
    def _annualization_factor(interval: str | None) -> float:
        if not interval:
            return 252.0
        key = str(interval).upper().strip()
        return float(RegimeModels.ANNUALIZATION.get(key, 252.0))

    @staticmethod
    def _annualization_from_timestamps(timestamps: list) -> Optional[float]:
        if not timestamps or len(timestamps) < 2:
            return None
        deltas = []
        for i in range(1, len(timestamps)):
            a = timestamps[i - 1]
            b = timestamps[i]
            if not hasattr(a, "timestamp") or not hasattr(b, "timestamp"):
                continue
            delta = (b - a).total_seconds()
            if delta > 0:
                deltas.append(delta)
        if not deltas:
            return None
        avg_delta = sum(deltas) / len(deltas)
        seconds_per_year = 365.25 * 24 * 60 * 60
        return seconds_per_year / avg_delta

    @staticmethod
    def _stationary_distribution(P: list[list[float]], tol: float = 1e-12, max_iter: int = 5000) -> list[float]:
        """
        Power-iteration stationary distribution for a row-stochastic Markov chain.

        Returns pi such that pi = pi * P, sum(pi)=1.

        No clamping. No flooring. Converges for ergodic chains; otherwise returns last iterate.
        """
        n = len(P)
        if n <= 0:
            return []

        # Start uniform
        pi = [1.0 / n] * n

        it = 0
        while it < max_iter:
            # pi_next[j] = sum_i pi[i] * P[i][j]
            pi_next = [0.0] * n
            i = 0
            while i < n:
                row = P[i]
                w = float(pi[i])
                j = 0
                while j < n:
                    pi_next[j] += w * float(row[j])
                    j += 1
                i += 1

            s = float(sum(pi_next))
            if s > 0:
                inv = 1.0 / s
                j = 0
                while j < n:
                    pi_next[j] *= inv
                    j += 1

            # L1 diff
            diff = 0.0
            j = 0
            while j < n:
                diff += abs(pi_next[j] - pi[j])
                j += 1

            pi = pi_next
            if diff < tol:
                break

            it += 1

        return pi

    @staticmethod
    def _evolution_surface(
        P: list[list[float]],
        current_state: int,
        steps: int,
        include_initial: bool = False,
    ) -> list[list[float]]:
        """
        Returns a matrix (steps+1) x n where row t is the state probability vector at time t,
        starting from a one-hot distribution at current_state.
        """
        n = len(P)
        if n <= 0:
            return []

        out = []
        probs = [0.0] * n
        probs[current_state] = 1.0
        if include_initial:
            out.append(probs[:])

        t = 0
        while t < steps:
            nxt = [0.0] * n
            i = 0
            while i < n:
                pi = float(probs[i])
                if pi != 0.0:
                    row = P[i]
                    j = 0
                    while j < n:
                        nxt[j] += pi * float(row[j])
                        j += 1
                i += 1

            s = float(sum(nxt))
            if s > 0:
                inv = 1.0 / s
                j = 0
                while j < n:
                    nxt[j] *= inv
                    j += 1

            probs = nxt
            out.append(probs[:])
            t += 1

        return out

    @staticmethod
    def snapshot_from_value_series(values: list[float], interval: str = "1M", label: str = "Portfolio") -> dict:
        n = RegimeModels.INTERVAL_POINTS.get(interval, 21)
        series = values[-(n + 1):] if values and len(values) >= (n + 1) else values

        returns = []
        if series and len(series) >= 8:
            for i in range(1, len(series)):
                prev = float(series[i - 1])
                curr = float(series[i])
                if prev > 0:
                    returns.append((curr - prev) / prev)

        snap = RegimeModels.compute_markov_snapshot(
            returns,
            horizon=1,
            label=f"{label} ({interval})",
            interval=interval,
        )
        snap["interval"] = interval
        return snap

    @staticmethod
    def compute_markov_snapshot(
        returns: list[float],
        horizon: int = 1,
        label: str = "1D",
        interval: str | None = None,
        timestamps: list | None = None,
    ) -> dict:
        if not returns or len(returns) < 8:
            return {"error": "Insufficient data for regime analysis"}

        bins = RegimeModels._make_bins_quantiles(returns)
        states = RegimeModels._discretize(returns, bins)
        n = len(bins) - 1

        P = RegimeModels._transition_matrix(states, n)

        current_state = states[-1]
        probs = RegimeModels._project(P, current_state, horizon)

        next_state = max(probs, key=probs.get)

        avg_return = sum(returns) / len(returns)
        if len(returns) > 1:
            volatility = math.sqrt(
                sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
            )
        else:
            volatility = 0.0
        ann_factor = RegimeModels._annualization_from_timestamps(timestamps) or RegimeModels._annualization_factor(interval)
        avg_return_annual = avg_return * ann_factor
        volatility_annual = volatility * math.sqrt(ann_factor)

        # --- Surfaces (pure Markov; interval-compatible) ---
        pi = RegimeModels._stationary_distribution(P)
        evo_steps = 12
        evo = RegimeModels._evolution_surface(P, current_state, evo_steps, include_initial=False)

        return {
            "model": "Markov",
            "horizon": label,
            "current_regime": RegimeModels.STATE_LABELS[current_state],
            "stay_probability": probs[current_state],
            "confidence": probs[current_state],
            "state_probs": {
                RegimeModels.STATE_LABELS[i]: probs[i]
                for i in range(n)
            },
            "transition_matrix": P,
            "expected_next": {
                "regime": RegimeModels.STATE_LABELS[next_state],
                "probability": probs[next_state],
            },
            "stability": P[current_state][current_state],
            "samples": len(returns),
            "metrics": {
                "avg_return": avg_return_annual,
                "volatility": volatility_annual,
                "avg_return_raw": avg_return,
                "volatility_raw": volatility,
            },
            "stationary": {
                RegimeModels.STATE_LABELS[i]: pi[i] for i in range(n)
            },
            "evolution": {
                "steps": evo_steps,
                "series": [
                    {RegimeModels.STATE_LABELS[i]: evo[t][i] for i in range(n)}
                    for t in range(len(evo))
                ],
            },
        }

    @staticmethod
    def generate_snapshot(
        ticker: str,
        benchmark_ticker: str = "SPY",
        period: str = "1y",
        interval: str = "1d",
        risk_free_annual: float = 0.04,
    ) -> dict:
        """Generate a Markov regime snapshot using real historical returns."""
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return {"error": "Missing ticker"}

        try:
            df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        except Exception as exc:
            return {"error": f"Failed to fetch data: {exc}"}

        if df is None or df.empty or "Close" not in df.columns:
            return {"error": "No historical data available"}

        returns = df["Close"].pct_change().dropna()
        if returns.empty or len(returns) < 8:
            return {"error": "Insufficient data for regime analysis"}

        snap = RegimeModels.compute_markov_snapshot(
            returns.tolist(),
            horizon=1,
            label=f"{symbol} ({period})",
            interval=interval,
            timestamps=list(df.index),
        )
        if "error" in snap:
            return snap

        bench_returns = pd.Series(dtype=float)
        if benchmark_ticker:
            try:
                bench = yf.download(
                    str(benchmark_ticker).upper(),
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                )
                if bench is not None and not bench.empty and "Close" in bench.columns:
                    bench_returns = bench["Close"].pct_change().dropna()
            except Exception:
                bench_returns = pd.Series(dtype=float)

        metrics = calculations.compute_core_metrics(returns, bench_returns, risk_free_annual)

        if not bench_returns.empty and "beta" in metrics:
            combined = pd.concat([returns, bench_returns], axis=1).dropna()
            if len(combined) > 5:
                ann_factor = calculations.annualization_factor_from_index(combined.iloc[:, 0])
                avg_p = float(combined.iloc[:, 0].mean() * ann_factor)
                avg_m = float(combined.iloc[:, 1].mean() * ann_factor)
                beta = metrics["beta"]
                metrics["alpha_annual"] = (
                    float(avg_p - (risk_free_annual + beta * (avg_m - risk_free_annual)))
                    if beta is not None and math.isfinite(beta) else None
                )
                metrics["r_squared"] = None
                if combined.iloc[:, 0].std(ddof=1) > 0 and combined.iloc[:, 1].std(ddof=1) > 0:
                    corr = float(combined.iloc[:, 0].corr(combined.iloc[:, 1]))
                    if math.isfinite(corr):
                        metrics["r_squared"] = corr * corr

        snap["metrics"].update(metrics)
        snap["ticker"] = symbol
        snap["benchmark"] = str(benchmark_ticker).upper() if benchmark_ticker else None
        return snap

    @staticmethod
    def _bin_returns_sigma(returns: pd.Series) -> pd.Series:
        """Bins returns using Standard Deviation thresholds for stability."""
        mu = returns.mean()
        std = returns.std()

        # Thresholds: +/- 1.0 sigma for Mild, +/- 2.0 sigma for Strong
        bins = [-np.inf, mu - 2 * std, mu - std, mu + std, mu + 2 * std, np.inf]
        labels = ["Strong Down", "Mild Down", "Neutral", "Mild Up", "Strong Up"]

        return pd.cut(returns, bins=bins, labels=labels)

    @staticmethod
    def _discretize(returns, bins):
        return (np.digitize(returns, bins, right=False) - 1).tolist()

    @staticmethod
    def _transition_matrix(states: list[int], n: int, k: float = 0.75, self_floor: float = 0.0):
        """
        Dirichlet-smoothed transition matrix.

        k: smoothing strength (higher = more smoothing)
        self_floor: minimum probability of staying in the same regime
                (prevents unrealistically jumpy chains in sparse data)
        """
        counts = [[0.0] * n for _ in range(n)]
        for a, b in zip(states[:-1], states[1:]):
            counts[a][b] += 1.0

        P = []
        for i in range(n):
            row = counts[i]
            # Dirichlet prior: start with uniform pseudo-counts
            smoothed = [(c + k) for c in row]
            sm_total = sum(smoothed)
            probs = [v / sm_total for v in smoothed]
            P.append(probs)

        return P

    @staticmethod
    def _make_bins_quantiles(returns: list[float]) -> list[float]:
        """
        Build 5-state bins from return quantiles so states are populated.
        Produces 6 edges: [-inf, q20, q40, q60, q80, +inf]
        """
        r = [float(x) for x in returns if x is not None]
        if len(r) < 20:
            # fallback if too few points
            return [-math.inf, -0.02, -0.005, 0.005, 0.02, math.inf]

        qs = np.quantile(r, [0.20, 0.40, 0.60, 0.80]).tolist()

        # guard against identical quantiles (flat series)
        # if too many duplicates, revert to static bins
        if len(set(round(q, 10) for q in qs)) < 3:
            return [-math.inf, -0.02, -0.005, 0.005, 0.02, math.inf]

        return [-math.inf, qs[0], qs[1], qs[2], qs[3], math.inf]

    @staticmethod
    def _project(P, current, steps):
        probs = {i: 0.0 for i in range(len(P))}
        probs[current] = 1.0

        for _ in range(steps):
            next_probs = defaultdict(float)
            for i, p in probs.items():
                for j, w in enumerate(P[i]):
                    next_probs[j] += p * w
            probs = next_probs

        return probs
