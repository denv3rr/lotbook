"""Shared close-price cache: hits, misses and coalescing. No provider network."""
import threading
from datetime import datetime

import pandas as pd
import pytest

from modules.market_data import quotes


@pytest.fixture(autouse=True)
def isolated_cache():
    quotes.clear_quote_cache()
    yield
    quotes.clear_quote_cache()


def _close(values, name="SPY"):
    index = pd.date_range(datetime(2026, 1, 1), periods=len(values), freq="D")
    return pd.DataFrame({"Close": values}, index=index)


def test_missing_symbol_is_not_filled(monkeypatch):
    monkeypatch.setattr(quotes, "_download_symbols", lambda symbols, period, interval: {"SPY": _close([100.0, 110.0])["Close"]})
    frame, meta = quotes.fetch_close_frame(["SPY", "MISSING"], "1mo", "1d")
    assert list(frame.columns) == ["SPY"]
    assert "MISSING" in meta["missing"]
    assert frame["SPY"].iloc[-1] == 110.0


def test_cache_hit_does_not_redownload(monkeypatch):
    calls = {"n": 0}

    def download(symbols, period, interval):
        calls["n"] += 1
        return {symbol: _close([1.0, 2.0])["Close"] for symbol in symbols}

    monkeypatch.setattr(quotes, "_download_symbols", download)
    quotes.fetch_close_frame(["AAPL"], "1mo", "1d")
    quotes.fetch_close_frame(["AAPL"], "1mo", "1d")
    assert calls["n"] == 1


def test_concurrent_downloads_coalesce(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def download(symbols, period, interval):
        calls["n"] += 1
        started.set()
        release.wait(timeout=2)
        return {symbol: _close([3.0, 4.0])["Close"] for symbol in symbols}

    monkeypatch.setattr(quotes, "_download_symbols", download)
    results = []

    def worker():
        results.append(quotes.fetch_close_frame(["MSFT"], "1mo", "1d")[0]["MSFT"].iloc[-1])

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    assert started.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert calls["n"] == 1
    assert results == [4.0, 4.0]
