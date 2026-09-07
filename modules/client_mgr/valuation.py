from __future__ import annotations

import concurrent.futures
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from modules.market_data.finnhub_client import FinnhubWrapper
from modules.market_data.yfinance_client import YahooWrapper
import yfinance as yf
from modules.client_mgr.holdings import normalize_ticker, parse_timestamp, select_nearest_price

class ValuationEngine:
    """\
    Valuation engine for pricing ticker-based holdings, with a safe fallback path.

    Design goals:
        - Never raise in normal UI flows.
        - Always return predictable keys for quote lookups.
        - Support a separate manual/off-market valuation stream (estimated).
    """

    def __init__(
        self,
        logger: Any = None
    ):
        self._finnhub: Optional[FinnhubWrapper] = None
        self._yahoo: Optional[YahooWrapper] = None
        self.logger = logger

    @property
    def finnhub(self) -> FinnhubWrapper:
        if self._finnhub is None:
            self._finnhub = FinnhubWrapper()
        return self._finnhub

    @property
    def yahoo(self) -> YahooWrapper:
        if self._yahoo is None:
            self._yahoo = YahooWrapper()
        return self._yahoo


    def _log(self, level: str, message: str) -> None:
        if self.logger is None:
            return
        try:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(message)
        except Exception:
            return

    @staticmethod
    def _normalize_ticker(raw: str) -> str:
        return normalize_ticker(raw)

    @staticmethod
    def _parse_timestamp(raw: Any) -> Optional[datetime]:
        return parse_timestamp(raw)

    # -------------------------------
    # Public: Quote & history fetches
    # -------------------------------

    def get_quote_data(self, ticker: str) -> Dict[str, Any]:
        """\
        Lightweight quote lookup used by multiple UI flows.

        Always returns a dict with at least:
            - ticker, price, change, pct, change_pct, source, timestamp, error
        Never raises.
        """
        t = self._normalize_ticker(ticker)
        ts = int(time.time())

        if not t:
            return {
                "ticker": "",
                "price": 0.0,
                "change": 0.0,
                "pct": 0.0,
                "change_pct": 0.0,
                "currency": "USD",
                "timestamp": ts,
                "source": "N/A",
                "error": "Empty ticker",
            }

        # 1) Finnhub (fast)
        try:
            fh = self.finnhub.get_quote(t)
            if isinstance(fh, dict) and fh.get("price"):
                pct = float(fh.get("percent", 0.0) or 0.0)
                chg = float(fh.get("change", 0.0) or 0.0)
                price = float(fh.get("price", 0.0) or 0.0)
                return {
                    "ticker": t,
                    "price": price,
                    "change": chg,
                    "pct": pct,
                    "change_pct": pct,
                    "currency": "USD",
                    "timestamp": ts,
                    "source": "Finnhub",
                    "error": "",
                }
        except Exception:
            pass

        # 2) Yahoo (fallback)
        try:
            yd = self.yahoo.get_detailed_quote(t, period="1d", interval="15m")
            if isinstance(yd, dict) and not yd.get("error") and float(yd.get("price", 0.0) or 0.0) > 0:
                pct = float(yd.get("pct", 0.0) or 0.0)
                chg = float(yd.get("change", 0.0) or 0.0)
                price = float(yd.get("price", 0.0) or 0.0)
                return {
                    "ticker": t,
                    "price": price,
                    "change": chg,
                    "pct": pct,
                    "change_pct": pct,
                    "currency": "USD",
                    "timestamp": ts,
                    "source": "Yahoo",
                    "error": "",
                }
        except Exception:
            pass

        return {
            "ticker": t,
            "price": 0.0,
            "change": 0.0,
            "pct": 0.0,
            "change_pct": 0.0,
            "currency": "USD",
            "timestamp": ts,
            "source": "N/A",
            "error": f"Could not fetch live price for {t}",
        }

    def get_historical_price(self, ticker: str, timestamp: datetime) -> Optional[float]:
        """Return the closest historical close price near the timestamp."""
        t = self._normalize_ticker(ticker)
        if not t or not isinstance(timestamp, datetime):
            return None

        day_start = datetime(timestamp.year, timestamp.month, timestamp.day)
        day_end = day_start + timedelta(days=1)
        interval = "1m" if timestamp.time() != datetime.min.time() else "1d"

        def _fetch(interval_value: str) -> Optional[float]:
            try:
                hist = yf.download(
                    t,
                    start=day_start,
                    end=day_end,
                    interval=interval_value,
                    progress=False,
                    auto_adjust=True,
                )
            except Exception:
                return None

            if hist is None or hist.empty or "Close" not in hist.columns:
                return None

            closes = hist["Close"].dropna()
            if closes.empty:
                return None

            if interval_value == "1d":
                return float(closes.iloc[-1])

            idx = closes.index
            if hasattr(idx, "tz"):
                idx = idx.tz_localize(None)
                closes = closes.copy()
                closes.index = idx

            series = list(zip(list(idx), list(closes)))
            return select_nearest_price(series, timestamp)

        price = _fetch(interval)
        if price is None and interval != "1d":
            price = _fetch("1d")

        return price

    def get_detailed_data(self, ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        """\
        Fetches richer data used for account/portfolio tables (includes history for sparklines).
        Prefers Yahoo for history, falls back to Finnhub for price-only.
        """
        t = self._normalize_ticker(ticker)

        try:
            data = self.yahoo.get_detailed_quote(t, period=period, interval=interval)
            if isinstance(data, dict) and "error" not in data:
                # Ensure key consistency
                data["ticker"] = data.get("ticker", t)
                data["pct"] = float(data.get("pct", 0.0) or 0.0)
                data["change"] = float(data.get("change", 0.0) or 0.0)
                data["price"] = float(data.get("price", 0.0) or 0.0)
                data["history_dates"] = data.get("history_dates", []) or []
                return data
        except Exception as ex:
            self._log("warning", f"Yahoo detailed fetch failed for {t}: {ex}")

        # Fallback: Finnhub price-only
        q = self.get_quote_data(t)
        return {
            "ticker": t,
            "name": t,
            "sector": "N/A",
            "mkt_cap": None,
            "price": float(q.get("price", 0.0) or 0.0),
            "change": float(q.get("change", 0.0) or 0.0),
            "pct": float(q.get("pct", 0.0) or 0.0),
            "high": 0.0,
            "low": 0.0,
            "volume": 0,
            "history": [],
            "history_dates": [],
        }

    # -------------------------------
    # Portfolio valuation
    # -------------------------------

    def calculate_portfolio_value(
        self,
        holdings: Dict[str, float],
        history_period: str = "1mo",
        history_interval: str = "1d",
    ) -> Tuple[float, Dict[str, Any]]:
        """\
        Threaded calculation of market-priced holdings.

        Returns:
            (total_market_value, enriched_holdings)

        enriched_holdings[ticker] includes:
            - quantity, price, market_value, change, pct, change_pct, history, sector, name
        """
        total_value = 0.0
        enriched_holdings: Dict[str, Any] = {}

        if not holdings:
            return 0.0, enriched_holdings

        tickers = [self._normalize_ticker(t) for t in list(holdings.keys()) if str(t).strip()]
        unique_tickers = sorted(set(tickers))

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(self.get_detailed_data, t, history_period, history_interval): t
                for t in unique_tickers
            }

            for future in concurrent.futures.as_completed(future_to_ticker):
                t = future_to_ticker[future]
                data: Dict[str, Any] = {}
                try:
                    data = future.result()
                except Exception as ex:
                    self._log("warning", f"Detailed quote failed for {t}: {ex}")
                    data = {"price": 0.0, "change": 0.0, "pct": 0.0, "history": [], "sector": "N/A", "name": t}

                qty = 0.0
                try:
                    if t in holdings:
                        qty = float(holdings.get(t, 0.0) or 0.0)
                    else:
                        for k, v in holdings.items():
                            if self._normalize_ticker(k) == t:
                                qty = float(v or 0.0)
                                break
                except Exception:
                    qty = 0.0

                price = float(data.get("price", 0.0) or 0.0)
                mkt_val = price * qty
                total_value += mkt_val

                pct = float(data.get("pct", 0.0) or 0.0)
                enriched_holdings[t] = {
                    "ticker": t,
                    "name": data.get("name", t),
                    "sector": data.get("sector", "N/A"),
                    "quantity": qty,
                    "price": price,
                    "market_value": mkt_val,
                    "change": float(data.get("change", 0.0) or 0.0),
                    "pct": pct,
                    "change_pct": pct,  # manager reads change_pct in a few places
                    "history": data.get("history", []) or [],
                    "history_dates": data.get("history_dates", []) or [],
                    "mkt_cap": data.get("mkt_cap", None),
                }

        return total_value, enriched_holdings

    # -------------------------------
    # Manual / off-market valuation
    # -------------------------------

    def calculate_manual_holdings_value(self, manual_holdings: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Computes estimated total for manual/off-market assets.

        Accepts entries that provide either:
        - unit_price + quantity, or
        - total_value

        Returns:
        (manual_total_value, normalized_entries_sorted_desc)
        """
        total = 0.0
        normalized: List[Dict[str, Any]] = []

        if not manual_holdings:
            return 0.0, normalized

        for raw in manual_holdings:
            if not isinstance(raw, dict):
                continue

            name = str(raw.get("name", "")).strip() or "Manual Asset"
            currency = str(raw.get("currency", "USD")).strip() or "USD"
            notes = str(raw.get("notes", "")).strip()

            # quantity
            try:
                qty = float(raw.get("quantity", 0.0) or 0.0)
            except Exception:
                qty = 0.0

            # unit_price
            unit_price = None
            try:
                if raw.get("unit_price") is not None and str(raw.get("unit_price")).strip() != "":
                    unit_price = float(raw.get("unit_price"))
            except Exception:
                unit_price = None

            # total_value
            total_value = None
            try:
                if raw.get("total_value") is not None and str(raw.get("total_value")).strip() != "":
                    total_value = float(raw.get("total_value"))
            except Exception:
                total_value = None

            if total_value is None:
                if unit_price is None:
                    total_value = 0.0
                else:
                    total_value = unit_price * qty
            else:
                if unit_price is None and qty > 0:
                    unit_price = total_value / qty

            total += float(total_value or 0.0)

            normalized.append({
                "name": name,
                "quantity": float(qty),
                "unit_price": float(unit_price or 0.0),
                "total_value": float(total_value or 0.0),
                "currency": currency,
                "notes": notes,
            })

        normalized.sort(key=lambda x: x.get("total_value", 0.0), reverse=True)
        return total, normalized

    # -------------------------------
    # Aggregate history (dashboard)
    # -------------------------------

    def generate_aggregate_portfolio_history(
        self, enriched_data: dict, holdings: dict, interval: str = "1M",
        lot_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> list[float]:
        return self.generate_portfolio_history_series(enriched_data, holdings, interval, lot_map)[1]

    def generate_portfolio_history_series(
        self, enriched_data: Dict[str, Any], holdings: Dict[str, float],
        interval: str = "1M", lot_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Tuple[List[datetime], List[float]]:
        """Complete-coverage values on shared observed timestamps.

        Without lots this reconstructs current holdings, not actual historical
        account performance. With lots it is a value series including purchases,
        which must not be fed into a return model.
        """
        import math
        from datetime import timezone

        def timestamp(value):
            parsed = self._parse_timestamp(value)
            if parsed is not None and parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        quantities: Dict[str, float] = {}
        lots_by_ticker = {}
        try:
            for ticker, quantity in holdings.items():
                key = self._normalize_ticker(ticker)
                quantities[key] = quantities.get(key, 0.0) + float(quantity)
            for ticker, lots in (lot_map or {}).items():
                if not lots:
                    continue
                entries = [(timestamp(lot.get("timestamp")), float(lot.get("qty", 0))) for lot in lots]
                if any(ts is None or not math.isfinite(qty) for ts, qty in entries):
                    return [], []
                lots_by_ticker[self._normalize_ticker(ticker)] = entries
            if any(not math.isfinite(qty) for qty in quantities.values()):
                return [], []
        except (TypeError, ValueError, AttributeError):
            return [], []
        required = {ticker for ticker, qty in quantities.items() if qty != 0} | set(lots_by_ticker)
        if not required:
            return [], []
        normalized = {self._normalize_ticker(ticker): info for ticker, info in enriched_data.items()}
        paths = {}
        for ticker in required:
            info = normalized.get(ticker, {})
            prices, dates = info.get("history", []), info.get("history_dates", [])
            if not prices or len(prices) != len(dates):
                return [], []
            try:
                pairs = [(timestamp(ts), float(price)) for ts, price in zip(dates, prices)]
            except (ValueError, TypeError):
                return [], []
            if any(ts is None or not math.isfinite(price) or price <= 0 for ts, price in pairs):
                return [], []
            if len({ts for ts, _ in pairs}) != len(pairs):
                return [], []
            paths[ticker] = dict(pairs)
        shared = sorted(set.intersection(*(set(path) for path in paths.values())))
        values = []
        for ts in shared:
            amounts = []
            for ticker in sorted(required):
                qty = sum(quantity for acquired, quantity in lots_by_ticker[ticker] if acquired <= ts) if ticker in lots_by_ticker else quantities[ticker]
                amounts.append(paths[ticker][ts] * qty)
            value = math.fsum(amounts)
            if not math.isfinite(value):
                return [], []
            values.append(value)
        return shared, values
