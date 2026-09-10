import yfinance as yf
import pandas as pd
import numpy as np

import time
import io
import warnings
import logging
import contextlib

from typing import Dict, List, Tuple, Any

# Suppress yfinance and urllib3 warnings/logs
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

class YahooWrapper:
    """
    Yahoo Finance wrapper (yfinance) with:
    - Chunked parallel downloads to prevent large-batch timeouts.
    - Negative Caching: Caches empty results to prevent infinite retry loops.
    """
    
    MACRO_TICKERS = {
        # =========================
        # Global Equity Indices
        # =========================
        "Indices": {

            "United States": {
                "^GSPC": "S&P 500",
                "^DJI": "Dow Jones",
                "^IXIC": "Nasdaq",
                "^RUT": "Russell 2K",
                "^VIX": "VIX"
            },

            "Europe": {
                "^FTSE": "FTSE 100",
                "^GDAXI": "DAX",
                "^FCHI": "CAC 40"
            },

            "Asia-Pacific": {
                "^N225": "Nikkei 225",
                "^HSI": "Hang Seng",
                "^STI": "Straits Times",
                "000001.SS": "Shanghai",
                "^KS11": "KOSPI"
            },

            "Latin America": {
                "^BVSP": "Bovespa",
                "^MXX": "IPC Mexico"
            }
        },

        # =========================
        # U.S. Mega-Cap / Big Tech
        # =========================
        "Big Tech": {
            "Mega-Cap Leaders": {
                "AAPL": "Apple",
                "MSFT": "Microsoft",
                "NVDA": "Nvidia",
                "GOOGL": "Google",
                "AMZN": "Amazon",
                "META": "Meta",
                "TSLA": "Tesla",
                "AMD": "AMD"
            }
        },

        # =========================
        # U.S. Sector ETFs
        # =========================
        "US Sectors": {
            "Cyclical & Growth": {
                "XLK": "Technology",
                "XLF": "Financials",
                "XLE": "Energy",
                "XLI": "Industrials",
                "XLY": "Cons. Disc"
            },

            "Defensive": {
                "XLV": "Healthcare",
                "XLP": "Cons. Stap",
                "XLU": "Utilities",
                "XLRE": "Real Estate"
            },

            "Communications & Materials": {
                "XLC": "Comm Svc",
                "XLB": "Materials"
            }
        },

        # =========================
        # Commodities (Futures)
        # =========================
        "Commodities": {

            "Energy": {
                "CL=F": "Crude Oil",
                "BZ=F": "Brent Crude",
                "NG=F": "Nat Gas",
                "RB=F": "Gasoline",
                "HO=F": "Heating Oil"
            },

            "Metals": {
                "GC=F": "Gold",
                "SI=F": "Silver",
                "HG=F": "Copper",
                "PL=F": "Platinum",
                "PA=F": "Palladium"
            },

            "Agriculture": {
                "ZC=F": "Corn",
                "ZW=F": "Wheat",
                "ZS=F": "Soybeans",
                "KC=F": "Coffee",
                "SB=F": "Sugar",
                "CC=F": "Cocoa",
                "CT=F": "Cotton"
            },

            "Livestock": {
                "LE=F": "Live Cattle",
                "GF=F": "Feeder Cattle",
                "HE=F": "Lean Hogs"
            }
        },

        # =========================
        # Foreign Exchange (FX)
        # =========================
        "FX": {

            "Major Pairs": {
                "EURUSD=X": "EUR/USD",
                "GBPUSD=X": "GBP/USD",
                "USDJPY=X": "USD/JPY",
                "AUDUSD=X": "AUD/USD",
                "NZDUSD=X": "NZD/USD"
            },

            "USD Crosses": {
                "USDCAD=X": "USD/CAD",
                "USDCHF=X": "USD/CHF",
                "USDSEK=X": "USD/SEK",
                "USDNOK=X": "USD/NOK",
                "USDZAR=X": "USD/ZAR"
            },

            "Emerging Markets": {
                "USDMXN=X": "USD/MXN",
                "USDTRY=X": "USD/TRY",
                "USDCNY=X": "USD/CNY",
                "USDHKD=X": "USD/HKD",
                "USDINR=X": "USD/INR"
            },

            "Dollar Index": {
                "DX-Y.NYB": "DXY Index"
            }
        },

        # =========================
        # Interest Rates & Volatility
        # =========================
        "Rates": {

            "U.S. Treasury Yields": {
                "^IRX": "13W T-Bill",
                "^FVX": "5Y Treasury",
                "^TNX": "10Y Treasury",
                "^TYX": "30Y Treasury"
            },

            "Fixed Income Volatility": {
                "^MOVE": "Bond Vol"
            }
        },

        # =========================
        # Cryptocurrencies
        # =========================
        "Crypto": {

            "Large-Cap": {
                "BTC-USD": "Bitcoin",
                "ETH-USD": "Ethereum"
            },

            "Altcoins": {
                "SOL-USD": "Solana",
                "XRP-USD": "Ripple",
                "ADA-USD": "Cardano",
                "DOGE-USD": "Dogecoin"
            }
        },

        # =========================
        # Macro & Cross-Asset ETFs
        # =========================
        "Macro ETFs": {

            "Equity Exposure": {
                "SPY": "S&P 500 ETF",
                "QQQ": "Nasdaq 100",
                "IWM": "Russell 2000",
                "EEM": "Emerging Mkts",
                "VEA": "Dev Markets"
            },

            "Rates & Credit": {
                "TLT": "20Y Bond ETF",
                "IEF": "7-10Y Bond",
                "HYG": "High Yield",
                "LQD": "Inv Grade"
            },

            "Currency": {
                "UUP": "USD Bullish",
                "FXE": "Euro ETF",
                "FXY": "Yen ETF"
            },

            "Commodities": {
                "GLD": "Gold ETF",
                "SLV": "Silver ETF",
                "DBC": "Commodity ETF",
                "USO": "Oil ETF"
            },

            "Global Trade": {
                "BDRY": "Dry Bulk",
                "SEA": "Shipping"
            }
        }
    }

    # Failure cache (avoid repeated lag on known-bad tickers)
    _BAD_SYMBOL_UNTIL: Dict[str, int] = {}
    _BAD_TTL_SECONDS = 1800  # 30 minutes

    # Last missing symbols from the most recent snapshot call
    _LAST_MISSING: List[str] = []

    # Snapshot cache (period, interval) -> (ts, results)
    _SNAPSHOT_CACHE: Dict[Tuple[str, str], Tuple[int, List[Dict[str, Any]]]] = {}
    _SNAPSHOT_EMPTY_BACKOFF: Dict[Tuple[str, str], int] = {}
    _SNAPSHOT_TTL_SECONDS = 120  # Cache Macro view for 2 mins

    # Detailed quote cache (ticker, period, interval) -> (ts, data)
    _DETAILED_CACHE: Dict[Tuple[str, str, str], Tuple[int, Dict[str, Any]]] = {}
    _DETAILED_TTL_SECONDS = 60 

    # Global RAM cache for ultra-fast refresh (within same run)
    _FAST_CACHE: Dict[str, Tuple[int, Any]] = {}
    _FAST_TTL = 10 


    @classmethod
    def _get_fast_cache(cls, key: str):
        data = cls._FAST_CACHE.get(key)
        if data and (cls._now() - data[0]) < cls._FAST_TTL:
            return data[1]
        return None

    @classmethod
    def _set_fast_cache(cls, key: str, val: Any):
        cls._FAST_CACHE[key] = (cls._now(), val)

    @staticmethod
    def _now() -> int:
        return int(time.time())

    @classmethod
    def _is_bad(cls, symbol: str) -> bool:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return True
        until = int(cls._BAD_SYMBOL_UNTIL.get(sym, 0) or 0)
        return cls._now() < until

    @classmethod
    def _mark_bad(cls, symbol: str, ttl_seconds: int = None) -> None:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return
        ttl = int(ttl_seconds if ttl_seconds is not None else cls._BAD_TTL_SECONDS)
        cls._BAD_SYMBOL_UNTIL[sym] = cls._now() + max(60, ttl)

    @staticmethod
    def _silent_download(tickers, **kwargs) -> pd.DataFrame:
        """
        Wraps yf.download to suppress stderr/stdout noise.
        Forces threads=True for speed unless explicitly disabled.
        """
        # Ensure threading is enabled for speed unless caller forbids it
        if "threads" not in kwargs:
            kwargs["threads"] = True
            
        # Add ignore_tz to speed up parsing in newer pandas/yf versions
        if "ignore_tz" not in kwargs:
            kwargs["ignore_tz"] = True

        buf = io.StringIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            warnings.simplefilter("ignore", category=UserWarning)
            # Redirect stderr to swallow the progress bars and error logs
            with contextlib.redirect_stderr(buf):
                return yf.download(tickers, **kwargs)

    @classmethod
    def get_last_missing_symbols(cls) -> List[str]:
        return list(cls._LAST_MISSING)

    # ----------------------- Detailed Quote -----------------------

    def get_detailed_quote(self, ticker: str, period: str = "1d", interval: str = "15m") -> Dict[str, Any]:
        sym = str(ticker or "").strip().upper()
        if not sym:
            return {"error": "Empty ticker"}

        if YahooWrapper._is_bad(sym):
            return {"error": f"No data (cached failure): {sym}"}

        cache_key = (sym, str(period), str(interval))
        fast_key = f"dq::{sym}:{period}:{interval}"
        
        # Check L1 (Fast RAM)
        fast_hit = YahooWrapper._get_fast_cache(fast_key)
        if fast_hit: return fast_hit

        # Check L2 (TTL Cache)
        cached = YahooWrapper._DETAILED_CACHE.get(cache_key)
        if cached:
            ts, data = cached
            if (YahooWrapper._now() - int(ts or 0)) <= YahooWrapper._DETAILED_TTL_SECONDS:
                return data

        try:
            from modules.market_data.quotes import fetch_close_frame

            close, snapshot = fetch_close_frame([sym], period, interval)
            if sym not in close.columns:
                YahooWrapper._mark_bad(sym)
                return {"error": snapshot.get("error") or f"No history returned for {sym}"}
            closes = close[sym].dropna()
            if closes.empty:
                YahooWrapper._mark_bad(sym)
                return {"error": f"No close series returned for {sym}"}

            current = float(closes.iloc[-1])
            start = float(closes.iloc[0])
            change = current - start
            pct = (change / start) * 100 if start != 0 else 0.0
            high = float(closes.max())
            low = float(closes.min())
            volume = 0.0
            name = sym
            sector = "unspecified"
            mkt_cap = None

            data = {
                "ticker": sym,
                "name": name,
                "sector": sector,
                "mkt_cap": mkt_cap,
                "price": float(current),
                "change": float(change),
                "pct": float(pct),
                "high": float(high),
                "low": float(low),
                "volume": int(volume),
                "history": closes.tolist(),
                "history_dates": [
                    (idx.to_pydatetime().replace(tzinfo=None) if hasattr(idx, "to_pydatetime") else idx).strftime("%Y-%m-%d %H:%M:%S")
                    for idx in closes.index
                ],
            }

            YahooWrapper._DETAILED_CACHE[cache_key] = (YahooWrapper._now(), data)
            YahooWrapper._set_fast_cache(fast_key, data)
            return data

        except Exception as e:
            YahooWrapper._mark_bad(sym)
            return {"error": str(e)}

    # ----------------------- Macro Snapshot -----------------------

    @staticmethod
    def _chunk(seq: List[str], size: int) -> List[List[str]]:
        return [seq[i:i + size] for i in range(0, len(seq), size)]

    def get_macro_snapshot(self, period: str = "1d", interval: str = "15m") -> List[Dict[str, Any]]:
        key = (str(period), str(interval))
        fast_key = f"macro::{period}:{interval}"
        
        # L1 Cache
        fast_hit = YahooWrapper._get_fast_cache(fast_key)
        if fast_hit: return fast_hit

        # L2 Cache
        cached = YahooWrapper._SNAPSHOT_CACHE.get(key)
        if cached:
            ts, data = cached
            if (YahooWrapper._now() - int(ts or 0)) <= YahooWrapper._SNAPSHOT_TTL_SECONDS:
                return data
        backoff_until = int(YahooWrapper._SNAPSHOT_EMPTY_BACKOFF.get(key, 0) or 0)
        if backoff_until > YahooWrapper._now():
            return []
        YahooWrapper._SNAPSHOT_EMPTY_BACKOFF.pop(key, None)

        # Prepare Ticker List
        ticker_meta: Dict[str, Dict[str, str]] = {}
        
        # Nested dict parsing
        for cat, subcats in YahooWrapper.MACRO_TICKERS.items():
            for subcat, symbols in subcats.items():
                for sym, name in symbols.items():
                    s = str(sym or "").strip().upper()
                    if s:
                        ticker_meta[s] = {
                            "name": name, 
                            "category": cat, 
                            "subcategory": subcat
                        }

        requested = list(ticker_meta.keys())
        # Filter out "known bad" symbols to speed up batch processing
        flat_list = [s for s in requested if not YahooWrapper._is_bad(s)]

        results: List[Dict[str, Any]] = []
        missing: List[str] = []

        def process_download_frame(data: pd.DataFrame, symbols: List[str]) -> None:
            nonlocal results, missing
            if data is None or data.empty:
                missing.extend(symbols)
                return

            is_multi = isinstance(data.columns, pd.MultiIndex)

            for sym in symbols:
                meta = ticker_meta.get(sym, {"name": sym, "category": "Other", "subcategory": ""})
                try:
                    if is_multi:
                        if sym not in data["Close"].columns:
                            missing.append(sym)
                            continue
                        
                        closes = data["Close"][sym].dropna()
                        # Optional columns
                        highs = data["High"][sym].dropna() if "High" in data else pd.Series(dtype=float)
                        lows = data["Low"][sym].dropna() if "Low" in data else pd.Series(dtype=float)
                        vols = data["Volume"][sym].dropna() if "Volume" in data else pd.Series(dtype=float)
                    else:
                        closes = data.get("Close", pd.Series(dtype=float)).dropna()
                        highs = data.get("High", pd.Series(dtype=float)).dropna()
                        lows = data.get("Low", pd.Series(dtype=float)).dropna()
                        vols = data.get("Volume", pd.Series(dtype=float)).dropna()

                    if closes.empty:
                        missing.append(sym)
                        continue

                    current = float(closes.iloc[-1])
                    start = float(closes.iloc[0])
                    change = current - start
                    pct = (change / start) * 100 if start != 0 else 0.0

                    h_val = float(highs.max()) if not highs.empty else current
                    l_val = float(lows.min()) if not lows.empty else current
                    v_val = float(vols.iloc[-1]) if not vols.empty else 0.0

                    results.append({
                        "ticker": sym,
                        "name": meta.get("name", sym),
                        "category": meta.get("category", "Other"),
                        "subcategory": meta.get("subcategory", ""),
                        "price": float(current),
                        "change": float(change),
                        "pct": float(pct),
                        "high": float(h_val),
                        "low": float(l_val),
                        "volume": int(v_val),
                        "history": closes.tolist(),
                    })
                except Exception:
                    missing.append(sym)

        try:
            # --- PERFORMANCE FIX: Smaller chunks + Always Cache ---
            # Breaking into chunks of 20 avoids the "10s timeout" if one ticker is bad
            for chunk in YahooWrapper._chunk(flat_list, 20):
                d = YahooWrapper._silent_download(
                    chunk,
                    period=period,
                    interval=interval,
                    progress=False,
                    group_by="column",
                    auto_adjust=True,
                    threads=True
                )
                process_download_frame(d, chunk)

        except Exception:
            # Return old cache if everything explodes
            cached = YahooWrapper._SNAPSHOT_CACHE.get(key)
            if cached: return cached[1]
            # Don't return empty yet, let the next block handle caching failure
        
        # Mark persistently missing symbols as bad
        YahooWrapper._LAST_MISSING = sorted(set(missing))
        for m in YahooWrapper._LAST_MISSING:
            YahooWrapper._mark_bad(m)

        # --- CRITICAL FIX: Cache result even if empty ---
        # If we don't cache empty results, the app will retry the download
        # on the NEXT loop (0.1s later), causing the infinite lag.
        # We cache it for at least 15 seconds to give the UI breathing room.
        
        if results:
            YahooWrapper._SNAPSHOT_CACHE[key] = (YahooWrapper._now(), results)
            YahooWrapper._SNAPSHOT_EMPTY_BACKOFF.pop(key, None)
            YahooWrapper._set_fast_cache(fast_key, results)
        else:
            # Back off briefly after an empty batch so the UI does not thrash the feed.
            YahooWrapper._SNAPSHOT_EMPTY_BACKOFF[key] = YahooWrapper._now() + 15

        return results
