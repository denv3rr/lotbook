from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from modules.client_mgr.regime import RegimeModels


TOOLKIT_PERIOD = {"1W": "1mo", "1M": "6mo", "3M": "1y", "6M": "2y", "1Y": "5y"}
TOOLKIT_INTERVAL = {"1W": "60m", "1M": "1d", "3M": "1d", "6M": "1d", "1Y": "1d"}


class ToolkitPayloadsMixin:
    def _get_pattern_payload(
        self,
        returns: pd.Series,
        interval: str,
        meta: str,
    ) -> Dict[str, Any]:
        key = (
            "pattern",
            interval,
            int(returns.index[-1].timestamp())
            if isinstance(returns.index, pd.DatetimeIndex)
            else len(returns),
        )
        cached = self._pattern_cache.get(key)
        if cached:
            return cached
        payload = self.patterns.build_payload(returns, interval, meta)
        self._pattern_cache[key] = payload
        return payload

    def build_risk_dashboard_payload(
        self,
        holdings: Dict[str, float],
        interval: str,
        label: str,
        scope: str = "Portfolio",
        benchmark_ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        interval = str(interval or self._selected_interval or "1M").upper()
        period = TOOLKIT_PERIOD.get(interval, "1y")
        benchmark = benchmark_ticker or self.benchmark_ticker
        returns, benchmark_returns, meta = self._get_portfolio_and_benchmark_returns(
            holdings,
            benchmark_ticker=benchmark,
            period=period,
            interval=TOOLKIT_INTERVAL.get(interval, "1d"),
        )
        if returns is None or returns.empty:
            return {
                "error": "Insufficient market data",
                "meta": meta,
                "interval": interval,
                "scope": scope,
                "label": label,
            }
        metrics = self._compute_risk_metrics(
            returns,
            benchmark_returns=benchmark_returns,
            risk_free_annual=0.04,
        )
        metrics["points"] = int(len(returns))
        profile = self.assess_risk_profile(metrics)
        return {
            "label": label,
            "scope": scope,
            "interval": interval,
            "benchmark": benchmark,
            "meta": meta,
            "metrics": metrics,
            "risk_profile": profile,
            "returns": self._series_from_returns(returns),
            "benchmark_returns": self._series_from_returns(benchmark_returns)
            if benchmark_returns is not None
            else [],
            "distribution": self._distribution_from_returns(returns),
        }

    def build_regime_snapshot_payload(
        self,
        holdings: Dict[str, float],
        lot_map: Dict[str, List[Dict[str, Any]]],
        interval: str,
        label: str,
        scope: str = "Portfolio",
        enriched: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        interval = str(interval or self._selected_interval or "1M").upper()
        period = TOOLKIT_PERIOD.get(interval, "1y")
        if not enriched:
            _, enriched = self.valuation.calculate_portfolio_value(
                holdings,
                history_period=period,
                history_interval=TOOLKIT_INTERVAL.get(interval, "1d"),
            )
        _, history = self.valuation.generate_portfolio_history_series(
            enriched_data=enriched,
            holdings=holdings,
            interval=interval,
            lot_map=None,
        )
        if not history:
            has_holdings = any(
                float(qty or 0.0) > 0 for qty in (holdings or {}).values()
            )
            has_price_history = any(
                info.get("history")
                for info in (enriched or {}).values()
                if isinstance(info, dict)
            )
            if not has_holdings:
                detail = "No holdings available to compute a regime series."
            elif not has_price_history:
                detail = (
                    "No historical price series available for holdings (manual lots "
                    "or missing price history)."
                )
            else:
                detail = "Not enough historical points to compute a regime series."
            return {
                "error": "Insufficient history for regime analysis",
                "error_detail": detail,
                "scope_label": scope,
                "interval": interval,
                "label": label,
            }
        snap = RegimeModels.snapshot_from_value_series(
            history,
            interval=interval,
            label=label,
        )
        snap["scope_label"] = scope
        snap["interval"] = interval
        snap["methodology"] = "Fixed current holdings on shared price timestamps. This is price-return reconstruction, not historical account performance; purchases are not investment returns."
        return snap

    def build_pattern_payload(
        self,
        holdings: Dict[str, float],
        interval: str,
        label: str,
        scope: str = "Portfolio",
    ) -> Dict[str, Any]:
        interval = str(interval or self._selected_interval or "1M").upper()
        period = TOOLKIT_PERIOD.get(interval, "1y")
        returns, _, meta = self._get_portfolio_and_benchmark_returns(
            holdings,
            benchmark_ticker=self.benchmark_ticker,
            period=period,
            interval=TOOLKIT_INTERVAL.get(interval, "1d"),
        )
        if returns is None or returns.empty:
            return {
                "error": "Insufficient market data",
                "meta": meta,
                "interval": interval,
                "scope": scope,
                "label": label,
            }
        payload = self._get_pattern_payload(returns, interval, meta)
        values = payload.get("values", []) or []
        spectrum = payload.get("spectrum", []) or []
        formatted_spectrum = [
            {"freq": float(freq), "power": float(power)} for freq, power in spectrum
        ]
        wave_surface, fft_surface = self.patterns.build_surfaces(values)
        if wave_surface.get("z"):
            wave_surface["axis"] = {
                "x_label": "Sample Index",
                "y_label": "Window Row",
                "z_label": "Return Value",
                "x_unit": "index",
                "y_unit": "row",
                "z_unit": "return",
            }
        if fft_surface.get("z"):
            fft_surface["axis"] = {
                "x_label": "Frequency",
                "y_label": "Window Start",
                "z_label": "Log Power",
                "x_unit": "cycles/sample",
                "y_unit": "index",
                "z_unit": "log power",
            }
        return {
            "label": label,
            "scope": scope,
            "interval": interval,
            "meta": meta,
            "entropy": payload.get("entropy"),
            "perm_entropy": payload.get("perm_entropy"),
            "perm_entropy_order": payload.get("perm_entropy_order"),
            "perm_entropy_delay": payload.get("perm_entropy_delay"),
            "hurst": payload.get("hurst"),
            "change_points": payload.get("change_points", []) or [],
            "motifs": payload.get("motifs", []) or [],
            "vol_forecast": payload.get("vol_forecast", []) or [],
            "spectrum": formatted_spectrum,
            "wave_surface": wave_surface,
            "fft_surface": fft_surface,
        }
