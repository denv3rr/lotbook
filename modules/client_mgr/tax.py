import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from modules.client_mgr.client_model import Client, Account
from modules.client_mgr.holdings import parse_timestamp


class TaxEngine:
    """
    Config-driven tax estimator for unrealized gains.
    No jurisdiction rules are assumed without explicit config.
    """

    DEFAULT_RULES = {
        "DEFAULT": {
            "long_term_days": 365,
            "rates": {
                "short_term": None,
                "long_term": None,
                "ordinary_income": None,
                "withholding_default": None
            },
            "apply_withholding_to_gains": False,
            "currency": "USD"
        }
    }

    def __init__(self, rules_path: str = None):
        self.rules_path = rules_path or os.path.join("config", "tax_rules.json")
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                return self.DEFAULT_RULES
        return self.DEFAULT_RULES

    @staticmethod
    def _parse_timestamp(raw: Any) -> Optional[datetime]:
        return parse_timestamp(raw)

    @staticmethod
    def is_long_term(acquired: date, as_of: date, jurisdiction: str, threshold: int) -> bool:
        if jurisdiction.upper() in ("US", "USA", "UNITED STATES"):
            try:
                anniversary = acquired.replace(year=acquired.year + 1)
            except ValueError:
                anniversary = date(acquired.year + 1, 2, 28)
            return as_of > anniversary
        return (as_of - acquired).days >= threshold

    def _get_rules_for_account(self, account: Account, client_tax: Dict[str, Any]) -> Dict[str, Any]:
        jurisdiction = (account.tax_settings or {}).get("jurisdiction") or client_tax.get("tax_country") or client_tax.get("residency_country") or "DEFAULT"
        key = str(jurisdiction).strip().upper()
        return self.rules.get(key, self.rules.get("DEFAULT", {}))

    def estimate_account_unrealized_tax(
        self,
        account: Account,
        price_map: Dict[str, Any],
        client_tax_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        settings = account.tax_settings or {}
        jurisdiction = str(settings.get("jurisdiction") or client_tax_profile.get("tax_country") or client_tax_profile.get("residency_country") or "DEFAULT")
        rules = self._get_rules_for_account(account, client_tax_profile or {})
        rates = rules.get("rates", {}) if isinstance(rules, dict) else {}
        long_term_days = int(rules.get("long_term_days", 365) or 365)
        apply_withholding = bool(rules.get("apply_withholding_to_gains", False))

        withholding_rate = settings.get("withholding_rate")
        tax_exempt = bool(settings.get("tax_exempt", False))
        account_ccy = settings.get("account_currency", "USD") or "USD"

        totals = {
            "short_term": 0.0,
            "long_term": 0.0,
            "unknown_term": 0.0
        }
        tax_total = 0.0
        warnings: List[str] = []

        if not account.lots:
            warnings.append("No lot history; tax estimates require lots.")

        for raw_ticker, lots in (account.lots or {}).items():
            ticker = str(raw_ticker).strip().upper()
            info = price_map.get(ticker, {}) if isinstance(price_map, dict) else {}
            price = float(info.get("price", 0.0) or 0.0)
            if price <= 0:
                warnings.append(f"Missing price for {ticker}")
                continue
            for lot in lots or []:
                if not isinstance(lot, dict):
                    continue
                qty = float(lot.get("qty", 0.0) or 0.0)
                basis = float(lot.get("basis", 0.0) or 0.0)
                gain = (price - basis) * qty
                ts = self._parse_timestamp(lot.get("timestamp"))
                if ts is None:
                    totals["unknown_term"] += gain
                    continue
                if ts.date() > date.today():
                    totals["unknown_term"] += gain
                    warnings.append(f"Future acquisition date for {ticker}; term unavailable.")
                    continue
                if self.is_long_term(ts.date(), date.today(), jurisdiction, long_term_days):
                    totals["long_term"] += gain
                else:
                    totals["short_term"] += gain

        if tax_exempt:
            tax_total = 0.0
        else:
            short_rate = rates.get("short_term")
            long_rate = rates.get("long_term")
            ordinary_rate = rates.get("ordinary_income")
            withhold_rate = rates.get("withholding_default") if apply_withholding else None

            def _rate(val, fallback):
                if val is None:
                    return fallback
                try:
                    return float(val)
                except Exception:
                    return fallback

            short_rate = _rate(short_rate, ordinary_rate)
            long_rate = _rate(long_rate, ordinary_rate)

            if short_rate is not None:
                tax_total += totals["short_term"] * (short_rate / 100.0)
            if long_rate is not None:
                tax_total += totals["long_term"] * (long_rate / 100.0)
            if withhold_rate is not None:
                tax_total += (totals["short_term"] + totals["long_term"]) * (float(withhold_rate) / 100.0)

        total_gain = totals["short_term"] + totals["long_term"] + totals["unknown_term"]
        effective_rate = (tax_total / total_gain * 100.0) if total_gain != 0 else None

        if rates and all(rates.get(k) is None for k in rates.keys()):
            warnings.append("Tax rates missing for jurisdiction.")

        return {
            "currency": account_ccy,
            "total_unrealized": total_gain,
            "estimated_tax": tax_total if tax_total != 0 else (0.0 if tax_exempt else None),
            "effective_rate": effective_rate,
            "by_term": totals,
            "warnings": warnings,
            "jurisdiction": (settings.get("jurisdiction") or client_tax_profile.get("tax_country") or "DEFAULT"),
        }

    def estimate_client_unrealized_tax(self, client: Client, price_map: Dict[str, Any]) -> Dict[str, Any]:
        totals = {
            "short_term": 0.0,
            "long_term": 0.0,
            "unknown_term": 0.0
        }
        tax_total = 0.0
        warnings: List[str] = []
        currency = (client.tax_profile or {}).get("reporting_currency", "USD") or "USD"

        for account in client.accounts:
            acct = self.estimate_account_unrealized_tax(
                account,
                price_map,
                client.tax_profile or {},
            )
            term = acct.get("by_term", {})
            totals["short_term"] += float(term.get("short_term", 0.0) or 0.0)
            totals["long_term"] += float(term.get("long_term", 0.0) or 0.0)
            totals["unknown_term"] += float(term.get("unknown_term", 0.0) or 0.0)
            tax_total += float(acct.get("estimated_tax") or 0.0) if acct.get("estimated_tax") is not None else 0.0
            warnings.extend(acct.get("warnings", []))

        total_gain = totals["short_term"] + totals["long_term"] + totals["unknown_term"]
        effective_rate = (tax_total / total_gain * 100.0) if total_gain != 0 else None

        return {
            "currency": currency,
            "total_unrealized": total_gain,
            "estimated_tax": tax_total if tax_total != 0 else None,
            "effective_rate": effective_rate,
            "by_term": totals,
            "warnings": warnings,
            "jurisdiction": (client.tax_profile or {}).get("tax_country") or "DEFAULT",
        }
