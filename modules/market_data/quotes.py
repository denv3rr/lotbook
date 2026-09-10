"""Shared close-price snapshots for dashboard, risk, regime and CAPM paths.

This is not a live quote stream. Callers must label results as snapshots.
Missing symbols stay missing; empty results are cached briefly so a failed
provider call cannot stampede the process. Concurrent identical downloads
wait on one in-flight request.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Iterable, Sequence

import pandas as pd
from yfinance.exceptions import YFException

from modules.market_data.yfinance_client import YahooWrapper

_DOWNLOAD_ERRORS = (OSError, TimeoutError, RuntimeError, ValueError, TypeError, KeyError, LookupError, YFException)


PRICE_TTL_SECONDS = 60
EMPTY_TTL_SECONDS = 15
DOWNLOAD_WAIT_SECONDS = 45

_lock = threading.RLock()
_cache: dict[tuple[str, str, str], "_Entry"] = {}
_inflight: dict[tuple[str, str, str], threading.Event] = {}


@dataclass
class _Entry:
    expires_at: float
    fetched_at: float
    series: pd.Series | None


def _now() -> float:
    return time.time()


def _symbol(raw: str) -> str:
    return str(raw or "").strip().upper()


def cache_key(symbol: str, period: str, interval: str) -> tuple[str, str, str]:
    return (_symbol(symbol), str(period), str(interval))


def clear_quote_cache() -> None:
    with _lock:
        _cache.clear()
        _inflight.clear()


def _extract_close(data: pd.DataFrame, symbols: Sequence[str]) -> dict[str, pd.Series]:
    extracted: dict[str, pd.Series] = {}
    if data is None or getattr(data, "empty", True):
        return extracted
    columns = data.columns
    if isinstance(columns, pd.MultiIndex):
        levels = list(columns.levels[0]) if columns.nlevels else []
        price_key = "Close" if "Close" in levels else "Adj Close" if "Adj Close" in levels else None
        if price_key is None:
            return extracted
        block = data[price_key]
        if isinstance(block, pd.Series):
            if len(symbols) == 1:
                extracted[symbols[0]] = block.dropna()
            return extracted
        for symbol in symbols:
            if symbol in block.columns:
                series = block[symbol].dropna()
                if not series.empty:
                    extracted[symbol] = series
        return extracted
    price = data["Close"] if "Close" in data.columns else data["Adj Close"] if "Adj Close" in data.columns else None
    if price is None:
        return extracted
    if isinstance(price, pd.Series):
        if len(symbols) == 1 and not price.dropna().empty:
            extracted[symbols[0]] = price.dropna()
        return extracted
    for symbol in symbols:
        if symbol in price.columns:
            series = price[symbol].dropna()
            if not series.empty:
                extracted[symbol] = series
    return extracted


def _store(symbol: str, period: str, interval: str, series: pd.Series | None, fetched_at: float) -> None:
    ttl = PRICE_TTL_SECONDS if series is not None and not series.empty else EMPTY_TTL_SECONDS
    _cache[cache_key(symbol, period, interval)] = _Entry(
        expires_at=fetched_at + ttl,
        fetched_at=fetched_at,
        series=None if series is None or series.empty else series.copy(),
    )


def _download_symbols(symbols: list[str], period: str, interval: str) -> dict[str, pd.Series]:
    if not symbols:
        return {}
    frame = YahooWrapper._silent_download(
        symbols,
        period=period,
        interval=interval,
        progress=False,
        group_by="column",
        auto_adjust=True,
        threads=True,
    )
    return _extract_close(frame, symbols)


def fetch_close_frame(
    tickers: Iterable[str],
    period: str,
    interval: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return a Close-price frame keyed by ticker, plus snapshot metadata."""
    symbols = []
    seen: set[str] = set()
    for raw in tickers:
        symbol = _symbol(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    fetched_at = _now()
    if not symbols:
        return pd.DataFrame(), {
            "source": "none",
            "label": "Cached snapshot, not a live quote stream.",
            "fetched_at": int(fetched_at),
            "cache": "empty",
            "ttl_seconds": PRICE_TTL_SECONDS,
            "missing": [],
            "warnings": ["No symbols were requested."],
        }

    hits: dict[str, pd.Series] = {}
    missing_cached: list[str] = []
    to_fetch: list[str] = []
    wait_for: list[tuple[str, threading.Event]] = []
    with _lock:
        for symbol in symbols:
            key = cache_key(symbol, period, interval)
            entry = _cache.get(key)
            if entry is not None and entry.expires_at > fetched_at:
                if entry.series is None or entry.series.empty:
                    missing_cached.append(symbol)
                else:
                    hits[symbol] = entry.series.copy()
                continue
            event = _inflight.get(key)
            if event is not None:
                wait_for.append((symbol, event))
            else:
                _inflight[key] = threading.Event()
                to_fetch.append(symbol)

    downloaded: dict[str, pd.Series] = {}
    download_error = ""
    if to_fetch:
        try:
            downloaded = _download_symbols(to_fetch, period, interval)
        except _DOWNLOAD_ERRORS:
            download_error = "Market data unavailable."
            downloaded = {}
        stamp = _now()
        with _lock:
            for symbol in to_fetch:
                series = downloaded.get(symbol)
                _store(symbol, period, interval, series, stamp)
                event = _inflight.pop(cache_key(symbol, period, interval), None)
                if event is not None:
                    event.set()

    for symbol, event in wait_for:
        event.wait(timeout=DOWNLOAD_WAIT_SECONDS)
        with _lock:
            entry = _cache.get(cache_key(symbol, period, interval))
            if entry is not None and entry.series is not None and not entry.series.empty:
                hits[symbol] = entry.series.copy()
            elif entry is not None:
                missing_cached.append(symbol)

    stamp = _now()
    with _lock:
        for symbol in to_fetch:
            entry = _cache.get(cache_key(symbol, period, interval))
            if entry is not None and entry.series is not None and not entry.series.empty:
                hits[symbol] = entry.series.copy()
            else:
                missing_cached.append(symbol)
        fetched_at = max((entry.fetched_at for entry in _cache.values()), default=stamp)

    frame = pd.DataFrame(hits) if hits else pd.DataFrame()
    missing = [symbol for symbol in symbols if symbol not in hits]
    cache_state = "hit"
    if to_fetch and not wait_for and not (set(hits) - set(to_fetch)):
        cache_state = "miss"
    elif to_fetch or wait_for:
        cache_state = "mixed" if hits else "miss"
    elif missing_cached and not hits:
        cache_state = "empty"
    warnings = [
        "Prices are a cached market snapshot, not a live quote stream.",
        f"Snapshot cache TTL is {PRICE_TTL_SECONDS} seconds for successful closes.",
    ]
    if missing:
        warnings.append(
            "Missing close history for: " + ", ".join(missing) + ". Totals omit unavailable symbols."
        )
    if download_error:
        warnings.append(download_error)
    meta = {
        "source": "Yahoo Finance close prices",
        "label": "Cached snapshot, not a live quote stream.",
        "fetched_at": int(fetched_at),
        "cache": cache_state,
        "ttl_seconds": PRICE_TTL_SECONDS,
        "missing": missing,
        "warnings": warnings,
        "error": download_error or (None if hits else "Market data empty"),
    }
    return frame, meta
