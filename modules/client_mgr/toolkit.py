import numpy as np
import pandas as pd
import time
import logging
import os
import json
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from rich.console import Console, Group

from modules.client_mgr import calculations
from modules.client_mgr.patterns import PatternSuite
from modules.client_mgr.client_model import Client, Account
from modules.client_mgr.toolkit_menu import ToolkitMenuMixin
from modules.client_mgr.toolkit_payloads import (
    TOOLKIT_INTERVAL,
    TOOLKIT_PERIOD,
    ToolkitPayloadsMixin,
)
from modules.client_mgr.toolkit_runs import ToolkitRunMixin
from modules.client_mgr.valuation import ValuationEngine
from modules.client_mgr.toolkit_ai import build_ai_panel
from modules.market_data.quotes import fetch_close_frame

# Cache for CAPM computations to avoid redundant API calls
_CAPM_CACHE = {}  # key -> {"ts": int, "data": dict}
_CAPM_TTL_SECONDS = 900  # 15 minutes

# Metric glossary for Tools output (plain-language context).

# Suppress yfinance logs
logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# REGIME SNAPSHOT CONTRACT
# ---------------------------------------------------------------------------
# The UI consumes this structure only.
# The underlying model (Markov / HMM / etc.) must conform to this output.
#
# {
#   "model": "Markov",
#   "horizon": "1D",
#   "current_regime": str,
#   "confidence": float,
#   "state_probs": dict[str, float],
#   "transition_matrix": list[list[float]],
#   "expected_next": {"regime": str, "probability": float},
#   "stability": float,
#   "metrics": {"avg_return": float, "volatility": float}
# }
# ---------------------------------------------------------------------------

class FinancialToolkit(ToolkitPayloadsMixin, ToolkitRunMixin, ToolkitMenuMixin):
    """
    Advanced financial analysis tools context-aware of a specific client's portfolio.
    """
    PERM_ENTROPY_ORDER = 3
    PERM_ENTROPY_DELAY = 1

    def __init__(self, client: Client):
        self.client = client
        self.console = Console()
        self.valuation = ValuationEngine()
        self.benchmark_ticker = "SPY" # Using S&P 500 ETF as standard benchmark
        self._pattern_cache = {}
        self._settings_file = os.path.join(os.getcwd(), "config", "settings.json")
        tool_settings = self._load_tool_settings()
        self.perm_entropy_order = tool_settings["perm_entropy_order"]
        self.perm_entropy_delay = tool_settings["perm_entropy_delay"]
        self.patterns = PatternSuite(
            perm_entropy_order=self.perm_entropy_order,
            perm_entropy_delay=self.perm_entropy_delay,
        )
        interval = str(self.client.active_interval or "1M").upper()
        self._selected_interval = interval if interval in TOOLKIT_PERIOD else "1M"

    def _load_ai_settings(self) -> dict:
        defaults = {
            "enabled": True,
            "provider": "auto",
            "model_id": "rule_based_v1",
            "persona": "advisor_legal_v1",
            "cache_ttl": 21600,
            "cache_file": "data/ai_report_cache.json",
            "endpoint": "",
        }
        if not os.path.exists(self._settings_file):
            return defaults
        try:
            with open(self._settings_file, "r", encoding="ascii") as f:
                data = json.load(f)
            ai_conf = data.get("ai", {}) if isinstance(data, dict) else {}
        except Exception:
            return defaults
        if not isinstance(ai_conf, dict):
            ai_conf = {}
        for key, value in defaults.items():
            if key not in ai_conf:
                ai_conf[key] = value
        return ai_conf

    def _load_tool_settings(self) -> dict:
        defaults = {
            "perm_entropy_order": self.PERM_ENTROPY_ORDER,
            "perm_entropy_delay": self.PERM_ENTROPY_DELAY,
        }
        if not os.path.exists(self._settings_file):
            return defaults
        try:
            with open(self._settings_file, "r", encoding="ascii") as f:
                data = json.load(f)
            tools_conf = data.get("tools", {}) if isinstance(data, dict) else {}
        except Exception:
            return defaults
        if not isinstance(tools_conf, dict):
            tools_conf = {}
        order = tools_conf.get("perm_entropy_order", defaults["perm_entropy_order"])
        delay = tools_conf.get("perm_entropy_delay", defaults["perm_entropy_delay"])
        try:
            order = int(order)
        except Exception:
            order = defaults["perm_entropy_order"]
        try:
            delay = int(delay)
        except Exception:
            delay = defaults["perm_entropy_delay"]
        if order < 2:
            order = defaults["perm_entropy_order"]
        if delay < 1:
            delay = defaults["perm_entropy_delay"]
        return {
            "perm_entropy_order": order,
            "perm_entropy_delay": delay,
        }

    def _build_ai_panel(self, report: dict, report_type: str) -> Optional[Group]:
        return build_ai_panel(self._load_ai_settings(), report, report_type)

    @staticmethod
    def _annualization_factor_from_index(returns: pd.Series) -> float:
        return calculations.annualization_factor_from_index(returns)

    @staticmethod
    def assess_risk_profile(metrics: Dict[str, Any], min_points: int = 30) -> str:
        """
        Classifies risk profile based on CAPM beta when sufficient data exists.
        Returns "Not Assessed" if inputs are insufficient.
        """
        if not metrics or metrics.get("error"):
            return "Not Assessed"
        points = int(metrics.get("points", 0) or 0)
        beta = metrics.get("beta")
        if points < min_points or beta is None:
            return "Not Assessed"

        try:
            beta_val = float(beta)
        except Exception:
            return "Not Assessed"

        # Heuristic thresholds commonly used for beta-based risk buckets.
        if beta_val < 0.8:
            return "Conservative"
        if beta_val <= 1.2:
            return "Moderate"
        return "Aggressive"

    @staticmethod
    def _series_from_returns(returns: pd.Series, limit: int = 180) -> List[Dict[str, Any]]:
        if returns is None or returns.empty:
            return []
        tail = returns.tail(limit)
        series = []
        for idx, value in tail.items():
            if hasattr(idx, "timestamp"):
                ts = int(idx.timestamp())
            else:
                try:
                    ts = int(idx)
                except Exception:
                    ts = 0
            try:
                val = float(value)
            except Exception:
                val = 0.0
            series.append({"ts": ts, "value": val})
        return series

    @staticmethod
    def _distribution_from_returns(returns: pd.Series, bins: int = 12) -> List[Dict[str, Any]]:
        if returns is None or returns.empty:
            return []
        vals = np.array([float(v) for v in returns.values if v is not None], dtype=float)
        if vals.size == 0:
            return []
        counts, edges = np.histogram(vals, bins=bins)
        distribution = []
        for idx, count in enumerate(counts):
            distribution.append({
                "bin_start": float(edges[idx]),
                "bin_end": float(edges[idx + 1]),
                "count": int(count),
            })
        return distribution

    def _select_interval(self) -> Optional[str]:
        options = list(TOOLKIT_PERIOD.keys())
        options_map = {opt: opt for opt in options}
        options_map["0"] = "Back"
        choice = prompt_menu("Select Interval", options_map, show_back=True)
        if choice in ("0", "m"):
            return None
        return choice.upper()

    def _get_interval_or_select(self, force: bool = False) -> Optional[str]:
        if not force and self._selected_interval:
            return self._selected_interval
        choice = self._select_interval()
        if choice:
            self._selected_interval = choice
        return choice

    def _aggregate_holdings(self) -> Dict[str, float]:
        consolidated = {}
        for acc in self.client.accounts:
            for ticker, qty in acc.holdings.items():
                consolidated[ticker] = consolidated.get(ticker, 0) + qty
        return consolidated

    def _get_portfolio_and_benchmark_returns(
        self,
        holdings: Dict[str, float],
        benchmark_ticker: str,
        period: str,
        interval: str,
    ) -> Tuple[Optional[pd.Series], Optional[pd.Series], str]:
        tickers = [t for t, q in holdings.items() if str(t).strip() and float(q or 0.0) != 0.0]
        if not tickers:
            return None, None, "No non-zero holdings"

        download_list = sorted(set([str(t).upper() for t in tickers] + [str(benchmark_ticker).upper()]))
        close, snapshot = fetch_close_frame(download_list, period, interval)
        if close is None or close.empty:
            return None, None, snapshot.get("error") or "Market data unavailable."
        bench = str(benchmark_ticker).upper()
        if bench not in close.columns:
            return None, None, f"Benchmark '{bench}' missing"

        port_val = None
        for t, qty in holdings.items():
            t_norm = str(t).upper()
            if not float(qty):
                continue
            if t_norm not in close.columns:
                return None, None, f"Holding '{t_norm}' missing price history"
            series = close[t_norm] * float(qty)
            port_val = series if port_val is None else (port_val + series)

        if port_val is None:
            return None, None, "No overlapping price series"

        port_ret = port_val.pct_change(fill_method=None).dropna()
        bench_ret = close[bench].pct_change(fill_method=None).dropna()
        meta = f"Period: {period} | Interval: {interval} | Points: {len(port_ret)}"
        return port_ret, bench_ret, meta

    def _compute_risk_metrics(
        self,
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series],
        risk_free_annual: float,
    ) -> Dict[str, Any]:
        return calculations.compute_risk_metrics(
            returns,
            benchmark_returns,
            risk_free_annual,
        )

    @staticmethod
    def compute_capm_metrics_from_holdings(
        holdings: Dict[str, float],
        benchmark_ticker: str = "SPY",
        risk_free_annual: float = 0.04,
        period: str = "1y",
    ) -> Dict[str, Any]:
        """
        Computes CAPM + basic risk metrics for a portfolio represented by {ticker: qty}.
        Returns a dict; never raises in normal flows.

        Output keys:
        - beta, alpha_annual, r_squared, sharpe, vol_annual, points, error
        """
        ts = int(time.time())

        if not holdings:
            return {"error": "No holdings", "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}

        # Cache key includes tickers+qty, benchmark, period, rf
        fp = tuple(sorted((str(k).upper(), round(float(v or 0.0), 6)) for k, v in holdings.items() if str(k).strip()))
        key = (fp, str(benchmark_ticker).upper(), period, float(risk_free_annual))

        cached = _CAPM_CACHE.get(key)
        if cached and (ts - int(cached.get("ts", 0))) <= _CAPM_TTL_SECONDS:
            return cached["data"]

        try:
            tickers = [t for t, q in fp if q != 0.0]
            if not tickers:
                data = {"error": "No non-zero holdings", "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}
                _CAPM_CACHE[key] = {"ts": ts, "data": data}
                return data

            holdings_map = {ticker: quantity for ticker, quantity in fp}
            port_ret, mkt_ret, meta = self._get_portfolio_and_benchmark_returns(
                holdings_map,
                str(benchmark_ticker).upper(),
                period,
                "1d",
            )
            if port_ret is None or mkt_ret is None:
                data = {"error": meta or "No market data returned", "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}
                _CAPM_CACHE[key] = {"ts": ts, "data": data}
                return data
            bench = str(benchmark_ticker).upper()

            capm = calculations.compute_capm_metrics_from_returns(
                port_ret,
                mkt_ret,
                risk_free_annual=risk_free_annual,
                min_points=30,
            )
            capm.update({
                "benchmark": bench,
                "period": period,
                "risk_free_annual": float(risk_free_annual),
            })

            _CAPM_CACHE[key] = {"ts": ts, "data": capm}
            return capm

        except Exception as ex:
            data = {"error": f"CAPM compute error: {ex}", "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}
            _CAPM_CACHE[key] = {"ts": ts, "data": data}
            return data

    @staticmethod
    def compute_capm_metrics_from_returns(
        returns: pd.Series,
        benchmark_returns: pd.Series,
        risk_free_annual: float = 0.04,
        min_points: int = 30,
    ) -> Dict[str, Any]:
        return calculations.compute_capm_metrics_from_returns(
            returns,
            benchmark_returns,
            risk_free_annual=risk_free_annual,
            min_points=min_points,
        )
    @staticmethod
    def _compute_core_metrics(returns: pd.Series, benchmark_returns: pd.Series = None) -> dict:
        return calculations.compute_core_metrics(returns, benchmark_returns)
