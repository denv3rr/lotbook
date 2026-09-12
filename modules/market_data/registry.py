from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from modules.market_data.collectors import DEFAULT_SOURCES


def _env_list(key: str) -> List[str]:
    return [item.strip() for item in os.getenv(key, "").split(",") if item.strip()]


def _load_news_health() -> Dict[str, Dict[str, Any]]:
    path = os.path.join("data", "news_health.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _health_status(health: Dict[str, Any]) -> str:
    from utils.identity import getenv

    now = int(getenv("LOTBOOK_TIME_OVERRIDE", "0") or 0) or None
    if now is None:
        now = int(__import__("time").time())
    backoff_until = int(health.get("backoff_until", 0) or 0)
    fail_count = int(health.get("fail_count", 0) or 0)
    last_ok = health.get("last_ok")
    if backoff_until and backoff_until > now:
        return "backoff"
    if fail_count > 0:
        return "degraded"
    if last_ok:
        return "ok"
    return "unknown"


def build_feed_registry() -> Dict[str, Any]:
    news_health = _load_news_health()
    flight_urls = _env_list("FLIGHT_DATA_URL")
    flight_paths = _env_list("FLIGHT_DATA_PATH")
    shipping_url = os.getenv("SHIPPING_DATA_URL")
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    opensky_basic = bool(os.getenv("OPENSKY_USERNAME") and os.getenv("OPENSKY_PASSWORD"))
    opensky_oauth = bool(os.getenv("OPENSKY_CLIENT_ID") and os.getenv("OPENSKY_CLIENT_SECRET"))
    opensky_creds = opensky_basic or opensky_oauth

    sources = [
        {
            "id": "finnhub",
            "label": "Finnhub",
            "category": "market",
            "configured": bool(finnhub_key),
            "notes": "Symbol/quote lookup (optional).",
        },
        {
            "id": "yahoo_finance",
            "label": "Yahoo Finance",
            "category": "market",
            "configured": True,
            "notes": "Historical data source.",
        },
        {
            "id": "opensky",
            "label": "OpenSky",
            "category": "trackers",
            "configured": bool(opensky_creds),
            "notes": "Flight tracking feed (OAuth preferred).",
        },
        {
            "id": "flight_urls",
            "label": "Flight URL Feeds",
            "category": "trackers",
            "configured": bool(flight_urls),
            "notes": f"{len(flight_urls)} URL source(s).",
        },
        {
            "id": "flight_paths",
            "label": "Flight File Feeds",
            "category": "trackers",
            "configured": bool(flight_paths),
            "notes": f"{len(flight_paths)} file source(s).",
        },
        {
            "id": "shipping",
            "label": "Shipping Feed",
            "category": "trackers",
            "configured": bool(shipping_url),
            "notes": "Vessel tracking endpoint.",
        },
        {
            "id": "open_meteo",
            "label": "Open-Meteo",
            "category": "intel",
            "configured": True,
            "notes": "Weather signals.",
        },
        {
            "id": "gdelt",
            "label": "GDELT",
            "category": "osint",
            "configured": True,
            "notes": "Conflict/news signals (RSS fallback).",
        },
    ]

    for collector in DEFAULT_SOURCES:
        health = news_health.get(collector.name, {})
        status = _health_status(health)
        sources.append({
            "id": f"rss::{collector.name}",
            "label": collector.name,
            "category": "news",
            "configured": True,
            "notes": "RSS news source.",
            "health": health,
            "status": status,
        })

    return {"sources": sources}


def summarize_feed_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    sources = registry.get("sources", []) if isinstance(registry, dict) else []
    summary = {
        "total": len(sources),
        "configured": 0,
        "unconfigured": 0,
        "categories": {},
        "health_counts": {"ok": 0, "degraded": 0, "backoff": 0, "unknown": 0},
        "warnings": [],
    }
    for source in sources:
        configured = bool(source.get("configured"))
        category = source.get("category", "other")
        summary["categories"].setdefault(category, {"total": 0, "configured": 0})
        summary["categories"][category]["total"] += 1
        status = source.get("status")
        if status in summary["health_counts"]:
            summary["health_counts"][status] += 1
        if configured:
            summary["configured"] += 1
            summary["categories"][category]["configured"] += 1
        else:
            summary["unconfigured"] += 1

    for category in ("market", "trackers", "news"):
        cat = summary["categories"].get(category, {})
        if cat and cat.get("configured", 0) == 0:
            summary["warnings"].append(f"No configured sources for {category}.")
    if summary["health_counts"]["backoff"] > 0:
        summary["warnings"].append("Some feeds are in backoff.")
    if summary["health_counts"]["degraded"] > 0:
        summary["warnings"].append("Some feeds are degraded.")
    return summary
