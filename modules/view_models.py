from __future__ import annotations

from typing import Any, Dict, Iterable, List
from core.models import Client, Account

from modules.client_mgr.toolkit import FinancialToolkit, TOOLKIT_INTERVAL, TOOLKIT_PERIOD
from modules.client_mgr.regime import RegimeModels
from modules.client_mgr.valuation import ValuationEngine
from modules.client_mgr.holdings import normalize_ticker
from modules.client_mgr.client_model import Client as ClientPayload


def _holdings_count(holdings: Dict[str, float]) -> int:
    count = 0
    for _, qty in (holdings or {}).items():
        try:
            if float(qty or 0.0) != 0.0:
                count += 1
        except Exception:
            continue
    return count


def _manual_value(manual_holdings: List[Dict[str, Any]]) -> float:
    total = 0.0
    for entry in manual_holdings or []:
        try:
            total += float(entry.get("total_value", 0.0) or 0.0)
        except Exception:
            continue
    return total


def _client_accounts(client: Any) -> List[Any]:
    if isinstance(client, dict):
        return list(client.get("accounts", []) or [])
    return list(getattr(client, "accounts", []) or [])


def _account_holdings(account: Any) -> Dict[str, Any]:
    if isinstance(account, dict):
        return account.get("holdings", {}) or {}
    return getattr(account, "holdings", {}) or {}


def _account_lots(account: Any) -> Dict[str, List[Dict[str, Any]]]:
    if isinstance(account, dict):
        return account.get("lots", {}) or {}
    return getattr(account, "lots", {}) or {}


def _account_manual_holdings(account: Any) -> List[Dict[str, Any]]:
    if isinstance(account, dict):
        return account.get("manual_holdings", []) or []
    return list(getattr(account, "manual_holdings", []) or [])


def _account_label(account: Any) -> str:
    if isinstance(account, dict):
        return str(account.get("account_name") or "")
    return str(getattr(account, "account_name", "") or getattr(account, "name", ""))


def _account_identifier(account: Any) -> Any:
    if isinstance(account, dict):
        return account.get("account_id")
    return getattr(account, "id", None) or getattr(account, "account_id", None)


def _account_type(account: Any) -> str:
    if isinstance(account, dict):
        return str(account.get("account_type") or "")
    return str(getattr(account, "account_type", "") or "")


def _client_identifier(client: Any) -> Any:
    if isinstance(client, dict):
        return client.get("client_id")
    return getattr(client, "id", None) or getattr(client, "client_id", None)


def _client_label(client: Any) -> str:
    if isinstance(client, dict):
        return str(client.get("name") or "")
    return str(getattr(client, "name", "") or "")


def _client_risk_profile(client: Any) -> str:
    if isinstance(client, dict):
        return str(client.get("risk_profile") or "")
    return str(getattr(client, "risk_profile", "") or "")


def _client_risk_profile_source(client: Any) -> str:
    if isinstance(client, dict):
        return str(client.get("risk_profile_source") or "")
    return str(getattr(client, "risk_profile_source", "") or "")


def _client_active_interval(client: Any) -> str:
    if isinstance(client, dict):
        return str(client.get("active_interval") or "")
    return str(getattr(client, "active_interval", "") or "")


def _client_tax_profile(client: Any) -> Dict[str, Any]:
    if isinstance(client, dict):
        return client.get("tax_profile", {}) or {}
    return getattr(client, "tax_profile", {}) or {}


def _client_extra(client: Any) -> Dict[str, Any]:
    if isinstance(client, dict):
        return client.get("extra", {}) or {}
    return getattr(client, "extra", {}) or {}


def _account_current_value(account: Any) -> float:
    if isinstance(account, dict):
        try:
            return float(account.get("current_value", 0.0) or 0.0)
        except Exception:
            return 0.0
    try:
        return float(getattr(account, "current_value", 0.0) or 0.0)
    except Exception:
        return 0.0


def _account_active_interval(account: Any) -> str:
    if isinstance(account, dict):
        return str(account.get("active_interval") or "")
    return str(getattr(account, "active_interval", "") or "")


def _account_extra(account: Any) -> Dict[str, Any]:
    if isinstance(account, dict):
        return account.get("extra", {}) or {}
    return getattr(account, "extra", {}) or {}


def account_summary(account: Account) -> Dict[str, Any]:
    return {
        "account_id": _account_identifier(account),
        "account_name": _account_label(account),
        "account_type": _account_type(account),
        "holdings_count": _holdings_count(_account_holdings(account)),
    }


def account_detail(account: Account) -> Dict[str, Any]:
    holdings: Dict[str, float] = {}
    for ticker, qty in (_account_holdings(account) or {}).items():
        try:
            holdings[normalize_ticker(ticker)] = float(qty or 0.0)
        except Exception:
            continue
    return {
        **account_summary(account),
        "current_value": _account_current_value(account),
        "active_interval": _account_active_interval(account),
        "holdings": holdings,
        "lots": _account_lots(account),
        "manual_holdings": _account_manual_holdings(account),
        "ownership_type": (
            account.get("ownership_type")
            if isinstance(account, dict)
            else getattr(account, "ownership_type", None)
        ),
        "custodian": (
            account.get("custodian") if isinstance(account, dict) else getattr(account, "custodian", None)
        ),
        "tags": (account.get("tags") if isinstance(account, dict) else getattr(account, "tags", None)) or [],
        "tax_settings": (
            account.get("tax_settings")
            if isinstance(account, dict)
            else getattr(account, "tax_settings", None)
        ),
        "extra": _account_extra(account),
    }


def client_summary(client: Client) -> Dict[str, Any]:
    holdings_count = sum(_holdings_count(_account_holdings(acc)) for acc in _client_accounts(client))
    return {
        "client_id": _client_identifier(client),
        "name": _client_label(client),
        "risk_profile": _client_risk_profile(client),
        "accounts_count": len(_client_accounts(client)),
        "holdings_count": holdings_count,
    }


def client_detail(client: Client) -> Dict[str, Any]:
    return {
        **client_summary(client),
        "risk_profile_source": _client_risk_profile_source(client),
        "active_interval": _client_active_interval(client),
        "tax_profile": _client_tax_profile(client),
        "accounts": [account_detail(account) for account in _client_accounts(client)],
        "extra": _client_extra(client),
    }


def list_clients(clients: Iterable[Client]) -> List[Dict[str, Any]]:
    return [client_summary(client) for client in clients]


def _aggregate_holdings(accounts: Iterable[Account]) -> Dict[str, float]:
    consolidated: Dict[str, float] = {}
    for account in accounts:
        for ticker, qty in (_account_holdings(account) or {}).items():
            try:
                consolidated[ticker] = consolidated.get(ticker, 0.0) + float(qty or 0.0)
            except Exception:
                consolidated[ticker] = consolidated.get(ticker, 0.0)
    return consolidated


def _aggregate_lots(accounts: Iterable[Account]) -> Dict[str, List[Dict[str, Any]]]:
    lots: Dict[str, List[Dict[str, Any]]] = {}
    for account in accounts:
        for ticker, entries in (_account_lots(account) or {}).items():
            lots.setdefault(ticker, []).extend(entries or [])
    return lots


def _aggregate_manual_holdings(accounts: Iterable[Account]) -> List[Dict[str, Any]]:
    manual: List[Dict[str, Any]] = []
    for account in accounts:
        manual.extend(list(_account_manual_holdings(account) or []))
    return manual


def _history_payload(dates: List[Any], values: List[float]) -> List[Dict[str, Any]]:
    if not values:
        return []
    series = []
    for idx, value in enumerate(values):
        ts = None
        if idx < len(dates):
            try:
                ts = int(getattr(dates[idx], "timestamp")())
            except Exception:
                ts = None
        series.append({"ts": ts, "value": float(value or 0.0)})
    return series


def _regime_window_payload(
    dates: List[Any], values: List[float], interval: str
) -> Dict[str, Any]:
    if not values:
        return {"interval": interval, "series": []}
    window = RegimeModels.INTERVAL_POINTS.get(interval, 21) + 1
    window_values = values[-window:] if len(values) > window else values
    window_dates = dates[-len(window_values) :] if dates else []
    return {
        "interval": interval,
        "series": _history_payload(window_dates, window_values),
    }


def portfolio_dashboard(client: Client, interval: str = "1M") -> Dict[str, Any]:
    valuation = ValuationEngine()
    accounts = _client_accounts(client)
    holdings = _aggregate_holdings(accounts)
    lots = _aggregate_lots(accounts)
    manual_entries = _aggregate_manual_holdings(accounts)
    warnings: List[str] = []

    total_value = 0.0
    enriched: Dict[str, Any] = {}
    if holdings:
        total_value, enriched = valuation.calculate_portfolio_value(
            holdings,
            history_period=TOOLKIT_PERIOD.get(interval, "1y"),
            history_interval=TOOLKIT_INTERVAL.get(interval, "1d"),
        )
    else:
        warnings.append("No holdings available for valuation.")

    manual_total, manual_holdings = valuation.calculate_manual_holdings_value(manual_entries)
    manual_compatible = all(entry.get("currency", "USD").upper() == "USD" for entry in manual_holdings)
    if not manual_compatible:
        warnings.append("Combined valuation unavailable: non-USD manual assets require reviewed FX conversion. Native amounts remain in the holdings list.")
    history_dates, history_values = valuation.generate_portfolio_history_series(
        enriched_data=enriched,
        holdings=holdings,
        interval=interval,
        lot_map=lots,
    )
    client_obj = ClientPayload.from_dict(client) if isinstance(client, dict) else client
    toolkit = FinancialToolkit(client_obj)
    risk_payload = toolkit.build_risk_dashboard_payload(
        holdings=holdings,
        interval=interval,
        label=_client_label(client),
        scope="Portfolio",
    )
    regime_payload = toolkit.build_regime_snapshot_payload(
        holdings=holdings,
        lot_map=lots,
        interval=interval,
        label=_client_label(client),
        scope="Portfolio",
    )
    # The regime payload carries its own fixed-holdings calculation window.


    holdings_list = sorted(
        enriched.values(),
        key=lambda entry: float(entry.get("market_value", 0.0) or 0.0),
        reverse=True,
    )
    holdings_list = holdings_list[:25]

    sector_totals: Dict[str, float] = {}
    for entry in enriched.values():
        sector = str(entry.get("sector", "N/A") or "N/A")
        value = float(entry.get("market_value", 0.0) or 0.0)
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value
    sector_rows = sorted(sector_totals.items(), key=lambda item: item[1], reverse=True)
    hhi = 0.0
    for _, value in sector_rows:
        if total_value > 0:
            pct = value / total_value
            hhi += pct * pct

    movers = sorted(
        enriched.values(),
        key=lambda entry: float(entry.get("pct", 0.0) or 0.0),
        reverse=True,
    )
    gainers = movers[:5]
    losers = list(reversed(movers[-5:])) if len(movers) > 5 else []

    return {
        "client": client_summary(client),
        "interval": interval,
        "totals": {
            "market_value": float(total_value),
            "manual_value": float(manual_total) if manual_compatible else None,
            "total_value": float(total_value + manual_total) if manual_compatible else None,
            "holdings_count": len(holdings),
            "manual_count": len(manual_holdings),
        },
        "holdings": holdings_list,
        "manual_holdings": manual_holdings,
        "history": _history_payload(history_dates, history_values),
        "risk": risk_payload,
        "regime": regime_payload,
        "diagnostics": {
            "sectors": [
                {
                    "sector": sector,
                    "value": float(value),
                    "pct": float(value / total_value) if total_value > 0 else 0.0,
                }
                for sector, value in sector_rows[:8]
            ],
            "hhi": float(hhi),
            "gainers": [
                {
                    "ticker": row.get("ticker"),
                    "pct": float(row.get("pct", 0.0) or 0.0),
                    "change": float(row.get("change", 0.0) or 0.0),
                }
                for row in gainers
            ],
            "losers": [
                {
                    "ticker": row.get("ticker"),
                    "pct": float(row.get("pct", 0.0) or 0.0),
                    "change": float(row.get("change", 0.0) or 0.0),
                }
                for row in losers
            ],
        },
        "warnings": warnings,
    }


def account_dashboard(client: Client, account: Account, interval: str = "1M") -> Dict[str, Any]:
    valuation = ValuationEngine()
    holdings = dict(_account_holdings(account) or {})
    lots = dict(_account_lots(account) or {})
    warnings: List[str] = []

    total_value = 0.0
    enriched: Dict[str, Any] = {}
    if holdings:
        total_value, enriched = valuation.calculate_portfolio_value(
            holdings,
            history_period=TOOLKIT_PERIOD.get(interval, "1y"),
            history_interval=TOOLKIT_INTERVAL.get(interval, "1d"),
        )
    else:
        warnings.append("No holdings available for valuation.")

    manual_total, manual_holdings = valuation.calculate_manual_holdings_value(_account_manual_holdings(account) or [])
    manual_compatible = all(entry.get("currency", "USD").upper() == "USD" for entry in manual_holdings)
    if not manual_compatible:
        warnings.append("Combined valuation unavailable: non-USD manual assets require reviewed FX conversion. Native amounts remain in the holdings list.")
    history_dates, history_values = valuation.generate_portfolio_history_series(
        enriched_data=enriched,
        holdings=holdings,
        interval=interval,
        lot_map=lots,
    )
    client_obj = ClientPayload.from_dict(client) if isinstance(client, dict) else client
    toolkit = FinancialToolkit(client_obj)
    risk_payload = toolkit.build_risk_dashboard_payload(
        holdings=holdings,
        interval=interval,
        label=_account_label(account),
        scope="Account",
    )
    regime_payload = toolkit.build_regime_snapshot_payload(
        holdings=holdings,
        lot_map=lots,
        interval=interval,
        label=_account_label(account),
        scope="Account",
    )
    # The regime payload carries its own fixed-holdings calculation window.


    holdings_list = sorted(
        enriched.values(),
        key=lambda entry: float(entry.get("market_value", 0.0) or 0.0),
        reverse=True,
    )
    holdings_list = holdings_list[:20]

    sector_totals: Dict[str, float] = {}
    for entry in enriched.values():
        sector = str(entry.get("sector", "N/A") or "N/A")
        value = float(entry.get("market_value", 0.0) or 0.0)
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value
    sector_rows = sorted(sector_totals.items(), key=lambda item: item[1], reverse=True)
    hhi = 0.0
    for _, value in sector_rows:
        if total_value > 0:
            pct = value / total_value
            hhi += pct * pct

    movers = sorted(
        enriched.values(),
        key=lambda entry: float(entry.get("pct", 0.0) or 0.0),
        reverse=True,
    )
    gainers = movers[:5]
    losers = list(reversed(movers[-5:])) if len(movers) > 5 else []

    return {
        "client": client_summary(client),
        "account": account_detail(account),
        "interval": interval,
        "totals": {
            "market_value": float(total_value),
            "manual_value": float(manual_total) if manual_compatible else None,
            "total_value": float(total_value + manual_total) if manual_compatible else None,
            "holdings_count": _holdings_count(_account_holdings(account)),
            "manual_count": len(manual_holdings),
        },
        "holdings": holdings_list,
        "manual_holdings": manual_holdings,
        "history": _history_payload(history_dates, history_values),
        "risk": risk_payload,
        "regime": regime_payload,
        "diagnostics": {
            "sectors": [
                {
                    "sector": sector,
                    "value": float(value),
                    "pct": float(value / total_value) if total_value > 0 else 0.0,
                }
                for sector, value in sector_rows[:8]
            ],
            "hhi": float(hhi),
            "gainers": [
                {
                    "ticker": row.get("ticker"),
                    "pct": float(row.get("pct", 0.0) or 0.0),
                    "change": float(row.get("change", 0.0) or 0.0),
                }
                for row in gainers
            ],
            "losers": [
                {
                    "ticker": row.get("ticker"),
                    "pct": float(row.get("pct", 0.0) or 0.0),
                    "change": float(row.get("change", 0.0) or 0.0),
                }
                for row in losers
            ],
        },
        "warnings": warnings,
    }


def client_patterns(client: Client, interval: str = "1M") -> Dict[str, Any]:
    holdings = _aggregate_holdings(_client_accounts(client))
    client_obj = ClientPayload.from_dict(client) if isinstance(client, dict) else client
    toolkit = FinancialToolkit(client_obj)
    return toolkit.build_pattern_payload(
        holdings=holdings,
        interval=interval,
        label=_client_label(client),
        scope="Portfolio",
    )


def account_patterns(client: Client, account: Account, interval: str = "1M") -> Dict[str, Any]:
    holdings = dict(_account_holdings(account) or {})
    client_obj = ClientPayload.from_dict(client) if isinstance(client, dict) else client
    toolkit = FinancialToolkit(client_obj)
    return toolkit.build_pattern_payload(
        holdings=holdings,
        interval=interval,
        label=_account_label(account),
        scope="Account",
    )
