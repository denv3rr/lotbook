from __future__ import annotations

import time
from typing import Tuple, Optional, Dict, Any

import pandas as pd
from modules.client_mgr import calculations
from modules.market_data.quotes import fetch_close_frame

# Cache for CAPM computations to avoid redundant API calls
_CAPM_CACHE = {}  # key -> {"ts": int, "data": dict}
_CAPM_TTL_SECONDS = 900  # 15 minutes



def get_portfolio_and_benchmark_returns(
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
        reason = snapshot.get("error") or "Market data empty"
        if len(download_list) > 1 and snapshot.get("missing"):
            return None, None, "Ticker identity unavailable in price data"
        return None, None, str(reason)

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
    meta = f"Fixed current holdings; price-return reconstruction, not cash-flow-adjusted account performance. Period: {period} | Interval: {interval} | Points: {len(port_ret)}"
    return port_ret, bench_ret, meta


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
        port_ret, mkt_ret, meta = get_portfolio_and_benchmark_returns(
            holdings,
            benchmark_ticker=benchmark_ticker,
            period=period,
            interval="1d",
        )

        if port_ret is None:
            data = {"error": meta, "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}
            _CAPM_CACHE[key] = {"ts": ts, "data": data}
            return data

        capm = calculations.compute_capm_metrics_from_returns(
            port_ret,
            mkt_ret,
            risk_free_annual=risk_free_annual,
            min_points=30,
        )
        capm.update({
            "benchmark": str(benchmark_ticker).upper(),
            "period": period,
            "risk_free_annual": float(risk_free_annual),
        })

        _CAPM_CACHE[key] = {"ts": ts, "data": capm}
        return capm

    except Exception as ex:
        data = {"error": f"CAPM compute error: {ex}", "beta": None, "alpha_annual": None, "r_squared": None, "sharpe": None, "vol_annual": None, "points": 0}
        _CAPM_CACHE[key] = {"ts": ts, "data": data}
        return data
