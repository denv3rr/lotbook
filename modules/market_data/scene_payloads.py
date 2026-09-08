from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from modules.market_data.collectors import CONFLICT_CATEGORIES
from modules.market_data.intel import (
    REGIONS,
    MarketIntel,
    _aggregate_news_metrics,
    _filter_conflict_news,
    _filter_news_categories,
    _impact_for_conflict,
    _risk_level,
    _score_conflict,
    _score_weather,
)
from modules.market_data.theaters import headlines_from_items, match_theaters

REGIONAL_INTEL_METHODOLOGY = {
    "methodology_id": "regional_intel_v1",
    "derived": True,
    "geometry_truth_level": "region-centroid",
    "units": {
        "score": "0-10 ordinal support/severity score",
        "presentation_intensity": "0-1 display scalar",
        "counts": "deduped article/context observations",
    },
    "formulas": {
        "combined_score": (
            "Weighted mean over available components: weather 0.35, "
            "conflict 0.35, news 0.30; rounded and clamped to 0-10."
        ),
        "presentation_intensity": (
            "max(combined_score / 10, news_article_count / 16), "
            "then clamped for display."
        ),
        "priority_sort": (
            "max(combined_score, conflict_score, conflict article-count proxy, "
            "conflict event-tag count) so critical conflict signals do not sink "
            "below calmer mixed indicators."
        ),
    },
    "coverage": {
        "regions": "Configured world regions excluding Global.",
        "geometry": "Representative region centroid only; not incident geometry.",
    },
    "freshness": (
        "Weather and conflict components use route build time when fetched; "
        "news uses RSS cache timestamp plus cached/stale flags."
    ),
}

REGIONAL_CONFLICT_PULSE_METHODOLOGY = {
    "methodology_id": "regional_conflict_pulse_v1",
    "derived": True,
    "geometry_truth_level": "region-centroid-highlight",
    "units": {
        "pulse_intensity": "0-1 display scalar",
        "article_count": "supporting article/context observations",
        "event_counts": "supporting article tag counts",
    },
    "count_semantics": (
        "article_count and event_counts are supporting article/tag counts, "
        "not resolved incidents, alerts, or exact event footprints."
    ),
    "formula": (
        "max(conflict_score / 10, conflict_event_tag_count / 8), "
        "clamped to the display pulse range."
    ),
    "coverage": {
        "regions": "Configured world regions with conflict score or conflict event tags.",
        "geometry": "Centroid highlight only; not polygon or incident geometry.",
    },
}

SIGNAL_HIGHLIGHT_METHODOLOGY = {
    "methodology_id": "regional_signal_highlight_v1",
    "derived": True,
    "geometry_truth_level": "theater-or-region-centroid-highlight",
    "units": {
        "pulse_intensity": "0-1 display scalar",
        "article_count": "supporting article/context observations",
    },
    "count_semantics": (
        "Counts are supporting articles or sample observations, not resolved "
        "incidents, weather fields, or legal boundaries."
    ),
    "formula": (
        "Weather highlights use the region's representative sample point. "
        "News, emotion, and conflict highlights move to a reviewed theater "
        "centroid when article text matches that theater; otherwise they stay "
        "on the parent region centroid."
    ),
    "coverage": {
        "geometry": "Centroid highlight only; not a heatmap grid or incident polygon.",
    },
}


def _signal_pulse_feature(
    *,
    feature_id: str,
    channel: str,
    label: str,
    region: str,
    theater: Optional[str],
    lat: float,
    lon: float,
    target_id: str,
    intensity: float,
    headlines: Sequence[Mapping[str, Any]],
    extra: Optional[Mapping[str, Any]] = None,
    source: str,
    ts: Optional[int],
    freshness: Optional[Mapping[str, Any]],
    display_note: str,
) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "label": label,
        "region": region,
        "theater": theater,
        "kind": "signal-highlight",
        "channel": channel,
        "category": channel,
        "display_scope": "theater-centroid-highlight" if theater else "region-centroid-highlight",
        "scope_kind": "centroid-highlight",
        "target_id": target_id,
        "headlines": list(headlines),
        "presentation": {
            "pulse_intensity": max(0.26, min(1.0, float(intensity))),
            "channel": channel,
        },
        "brief": {
            "channel": channel,
            "headlines": list(headlines),
            "geometry_note": display_note,
        },
        "provenance": {
            "display_note": display_note,
        },
    }
    if extra:
        properties.update(dict(extra))
    return geo_feature(
        feature_id,
        "regional-signal-overlays" if channel != "conflict" else "regional-conflict-overlays",
        {"type": "Point", "coordinates": [lon, lat]},
        properties=properties,
        source=source,
        ts=ts,
        confidence=None,
        freshness=freshness,
        warnings=[display_note],
    )


def geo_feature(
    feature_id: str,
    layer: str,
    geometry: Dict[str, Any],
    *,
    properties: Optional[Mapping[str, Any]] = None,
    source: str = "trackers",
    ts: Optional[int] = None,
    confidence: Optional[float] = None,
    freshness: Optional[Mapping[str, Any]] = None,
    warnings: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(feature_id),
        "layer": str(layer),
        "geometry": geometry,
        "ts": ts,
        "properties": dict(properties or {}),
        "source": source,
        "confidence": confidence,
        "freshness": dict(freshness or {}),
        "warnings": list(warnings or []),
    }


def geo_layer_payload(
    layer_id: str,
    kind: str,
    *,
    label: Optional[str] = None,
    features: Optional[Sequence[Mapping[str, Any]]] = None,
    legend: Optional[Sequence[Mapping[str, Any]]] = None,
    filters: Optional[Mapping[str, Any]] = None,
    style_hints: Optional[Mapping[str, Any]] = None,
    time_bounds: Optional[Mapping[str, Any]] = None,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(layer_id),
        "kind": str(kind),
        "label": label or str(layer_id),
        "features": [dict(feature) for feature in (features or [])],
        "legend": [dict(entry) for entry in (legend or [])],
        "filters": dict(filters or {}),
        "style_hints": dict(style_hints or {}),
        "time_bounds": dict(time_bounds or {}),
        "meta": dict(meta or {}),
    }


def geo_scene_payload(
    scene_id: str,
    *,
    title: Optional[str] = None,
    kind: str = "osint",
    camera_defaults: Optional[Mapping[str, Any]] = None,
    timeline: Optional[Mapping[str, Any]] = None,
    layers: Optional[Sequence[Mapping[str, Any]]] = None,
    focus_targets: Optional[Sequence[Mapping[str, Any]]] = None,
    bounds: Optional[Mapping[str, Any]] = None,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "scene_id": str(scene_id),
        "title": title or str(scene_id).replace("-", " ").title(),
        "kind": str(kind),
        "camera_defaults": dict(camera_defaults or {}),
        "timeline": dict(timeline or {}),
        "layers": [dict(layer) for layer in (layers or [])],
        "focus_targets": [dict(target) for target in (focus_targets or [])],
        "bounds": dict(bounds or {}),
        "meta": dict(meta or {}),
    }


def _freshness(ts: Optional[int], now: Optional[int] = None) -> Dict[str, Any]:
    now_value = int(now if now is not None else time.time())
    if ts is None:
        return {
            "timestamp": None,
            "age_sec": None,
            "state": "unknown",
            "is_stale": True,
        }
    try:
        ts_value = int(ts)
    except Exception:
        return {
            "timestamp": None,
            "age_sec": None,
            "state": "unknown",
            "is_stale": True,
        }
    age = max(0, now_value - ts_value)
    state = "fresh" if age <= 300 else "warm" if age <= 3600 else "stale"
    return {
        "timestamp": ts_value,
        "age_sec": age,
        "state": state,
        "is_stale": age > 3600,
    }


def _point_geometry(point: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        lat = float(point.get("lat"))
        lon = float(point.get("lon"))
    except Exception:
        return None
    return {"type": "Point", "coordinates": [lon, lat]}


def _line_geometry(history: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    coordinates: List[List[float]] = []
    for entry in history:
        try:
            lat = float(entry.get("lat"))
            lon = float(entry.get("lon"))
        except Exception:
            continue
        coordinates.append([lon, lat])
    if len(coordinates) < 2:
        return None
    return {"type": "LineString", "coordinates": coordinates}


def _geometry_coords(geometry: Mapping[str, Any]) -> List[tuple[float, float]]:
    coords: List[tuple[float, float]] = []
    geometry_type = str(geometry.get("type") or "")
    raw_coords = geometry.get("coordinates")
    if geometry_type == "Point" and isinstance(raw_coords, list) and len(raw_coords) >= 2:
        try:
            coords.append((float(raw_coords[0]), float(raw_coords[1])))
        except Exception:
            pass
    elif geometry_type == "LineString" and isinstance(raw_coords, list):
        for coord in raw_coords:
            if isinstance(coord, list) and len(coord) >= 2:
                try:
                    coords.append((float(coord[0]), float(coord[1])))
                except Exception:
                    continue
    return coords


def _bounds_from_features(features: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    lon_values: List[float] = []
    lat_values: List[float] = []
    for feature in features:
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        for lon, lat in _geometry_coords(geometry):
            lon_values.append(lon)
            lat_values.append(lat)
    if not lon_values or not lat_values:
        return {}
    return {
        "min_lon": min(lon_values),
        "max_lon": max(lon_values),
        "min_lat": min(lat_values),
        "max_lat": max(lat_values),
    }


def _camera_defaults(bounds: Mapping[str, Any]) -> Dict[str, Any]:
    if not bounds:
        return {
            "target_lat": 0.0,
            "target_lon": 0.0,
            "distance": 3.2,
            "pitch": 24.0,
            "bearing": 0.0,
        }
    min_lat = float(bounds.get("min_lat", 0.0))
    max_lat = float(bounds.get("max_lat", 0.0))
    min_lon = float(bounds.get("min_lon", 0.0))
    max_lon = float(bounds.get("max_lon", 0.0))
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    lat_span = abs(max_lat - min_lat)
    lon_span = abs(max_lon - min_lon)
    spread = max(lat_span / 90.0, lon_span / 180.0)
    distance = max(2.6, min(5.4, 2.9 + spread * 2.6))
    pitch = max(18.0, min(34.0, 22.0 + spread * 10.0))
    return {
        "target_lat": round(center_lat, 4),
        "target_lon": round(center_lon, 4),
        "distance": round(distance, 2),
        "pitch": round(pitch, 1),
        "bearing": 0.0,
    }


def _interleave_focus_targets(
    primary: Sequence[Mapping[str, Any]],
    secondary: Sequence[Mapping[str, Any]],
    *,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    max_len = max(len(primary), len(secondary))
    for index in range(max_len):
        if index < len(primary):
            merged.append(dict(primary[index]))
        if index < len(secondary):
            merged.append(dict(secondary[index]))
        if len(merged) >= limit:
            break
    return merged[:limit]


def _history_summary(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if len(history) < 2:
        return {"points": len(history)}
    start = history[0]
    end = history[-1]
    try:
        start_lat = float(start.get("lat"))
        start_lon = float(start.get("lon"))
        end_lat = float(end.get("lat"))
        end_lon = float(end.get("lon"))
    except Exception:
        return {"points": len(history)}
    distance_km = _haversine_km(start_lat, start_lon, end_lat, end_lon)
    duration_sec = None
    try:
        duration_sec = max(0, int(end.get("ts")) - int(start.get("ts")))
    except Exception:
        duration_sec = None
    speeds = []
    altitudes = []
    for entry in history:
        try:
            if entry.get("speed_kts") is not None:
                speeds.append(float(entry.get("speed_kts")))
        except Exception:
            pass
        try:
            if entry.get("altitude_ft") is not None:
                altitudes.append(float(entry.get("altitude_ft")))
        except Exception:
            pass
    return {
        "points": len(history),
        "start": {"lat": start_lat, "lon": start_lon, "ts": start.get("ts")},
        "end": {"lat": end_lat, "lon": end_lon, "ts": end.get("ts")},
        "distance_km": round(distance_km, 2),
        "duration_sec": duration_sec,
        "avg_speed_kts": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "avg_altitude_ft": round(sum(altitudes) / len(altitudes), 1) if altitudes else None,
        "route_hint": f"{round(start_lat, 2)},{round(start_lon, 2)} -> {round(end_lat, 2)},{round(end_lon, 2)}",
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _latest_published_ts(items: Sequence[Mapping[str, Any]]) -> Optional[int]:
    timestamps: List[int] = []
    for item in items:
        try:
            published_ts = item.get("published_ts")
            if published_ts is None:
                continue
            timestamps.append(int(published_ts))
        except Exception:
            continue
    return max(timestamps) if timestamps else None


def _region_feature_id(name: str) -> str:
    slug = "-".join(str(name or "").lower().split())
    return f"region:{slug or 'unknown'}"


def _component_score(
    component: Mapping[str, Any],
    path: Sequence[str],
) -> float:
    current: Any = component
    for key in path:
        if not isinstance(current, Mapping):
            return 0.0
        current = current.get(key)
    try:
        return float(current or 0.0)
    except Exception:
        return 0.0


def _conflict_priority_score(properties: Mapping[str, Any]) -> float:
    conflict_score = _component_score(properties, ("conflict", "score"))
    conflict_count = _component_score(properties, ("conflict", "count"))
    news = properties.get("news", {})
    event_counts = news.get("event_counts", {}) if isinstance(news, Mapping) else {}
    event_score = 0.0
    if isinstance(event_counts, Mapping):
        for tag in CONFLICT_CATEGORIES:
            event_score += _component_score(event_counts, (str(tag),))
    return max(conflict_score, min(10.0, conflict_count / 2.0), min(10.0, event_score))


def _regional_priority_score(properties: Mapping[str, Any]) -> float:
    return max(
        _component_score(properties, ("combined_risk", "score")),
        _conflict_priority_score(properties),
    )


def _dominant_channel(
    weather_score: Optional[int],
    conflict_score: Optional[int],
    news_score: Optional[int],
) -> str:
    ranked = [
        ("weather", float(weather_score or 0)),
        ("conflict", float(conflict_score or 0)),
        ("news", float(news_score or 0)),
    ]
    ranked.sort(key=lambda item: (item[1], item[0] == "conflict", item[0] == "weather"), reverse=True)
    return ranked[0][0] if ranked and ranked[0][1] > 0 else "combined"


def build_intel_scene(
    intel: MarketIntel,
    *,
    scene_id: str = "osint-intel",
    title: str = "Regional Signals",
    source: str = "intel",
    industry_filter: str = "all",
    enabled_sources: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    current_time = int(now if now is not None else time.time())
    category_list = [str(category) for category in (categories or []) if str(category).strip()]
    source_list = [str(name) for name in (enabled_sources or []) if str(name).strip()]

    news_payload = intel.fetch_news_signals(
        ttl_seconds=600,
        enabled_sources=source_list or None,
    )
    all_news_items = [
        item for item in (news_payload.get("items", []) or []) if isinstance(item, Mapping)
    ]
    news_cache_stale = bool(news_payload.get("stale"))
    news_cache_cached = bool(news_payload.get("cached"))
    skipped_sources = [str(item) for item in (news_payload.get("skipped", []) or []) if item]
    base_warnings: List[str] = []
    if news_cache_stale:
        base_warnings.append("News cache is stale; regional signals may lag live conditions.")
    if skipped_sources:
        base_warnings.append("One or more news collectors were skipped during this refresh.")

    features: List[Dict[str, Any]] = []
    pulse_features: List[Dict[str, Any]] = []
    focus_targets: List[Dict[str, Any]] = []
    scene_warnings = list(base_warnings)
    timeline_ts: List[int] = []

    conflict_categories = {str(category).lower() for category in CONFLICT_CATEGORIES}
    categories_include_conflict = any(
        str(category).lower() in conflict_categories for category in category_list
    )

    for region in REGIONS:
        if region.name.lower() == "global":
            continue

        feature_warnings = [
            "Weather risk is sampled from a representative regional coordinate.",
            "Conflict risk reflects regional signal density, not precise event locations.",
            "News and emotion metrics reflect title-and-summary classification, not article geolocation.",
        ]

        region_news_items = intel.filter_news_items(
            all_news_items,
            region.name,
            industry_filter,
        )
        if category_list:
            region_news_items = _filter_news_categories(region_news_items, categories=category_list)
            if categories_include_conflict:
                region_news_items = _filter_conflict_news(
                    region_news_items,
                    region.name,
                    categories=category_list,
                )
        conflict_news_items = _filter_conflict_news(
            region_news_items,
            region.name,
            categories=category_list or None,
        )
        news_metrics = _aggregate_news_metrics(region_news_items)
        news_score = news_metrics.get("risk_score") if region_news_items else None
        latest_news_ts = _latest_published_ts(region_news_items)
        news_freshness = _freshness(latest_news_ts, now=current_time)
        if latest_news_ts is None:
            news_freshness = {
                "timestamp": None,
                "age_sec": None,
                "state": "stale" if news_cache_stale else "unknown",
                "is_stale": news_cache_stale,
            }
        elif news_cache_stale:
            news_freshness["state"] = "stale"
            news_freshness["is_stale"] = True
        if latest_news_ts is not None:
            timeline_ts.append(latest_news_ts)

        weather_raw = intel.weather.fetch(region)
        weather_status = "ok"
        weather_score: Optional[int] = None
        weather_level = "Unavailable"
        weather_signals: List[str] = []
        weather_impacts: List[str] = []
        weather_freshness = {
            "timestamp": None,
            "age_sec": None,
            "state": "unknown",
            "is_stale": True,
        }
        if weather_raw.get("error"):
            weather_status = "unavailable"
            feature_warnings.append("Weather sample unavailable for this region.")
        else:
            weather_score, weather_signals = _score_weather(
                weather_raw.get("temp_c"),
                weather_raw.get("wind_ms"),
                weather_raw.get("precip_mm"),
                float(weather_raw.get("precip_24h") or 0.0),
                float(weather_raw.get("wind_max") or 0.0),
                float(weather_raw.get("temp_min") or 0.0),
                float(weather_raw.get("temp_max") or 0.0),
            )
            weather_level = _risk_level(int(weather_score or 0))
            weather_impacts = intel._filter_impacts(
                [str(item) for item in (weather_raw.get("impacts", []) or [])],
                industry_filter,
            )
            weather_freshness = {
                "timestamp": current_time,
                "age_sec": 0,
                "state": "fresh",
                "is_stale": False,
            }

        conflict_raw = intel.conflict.fetch(region)
        conflict_status = "gdelt"
        conflict_score: Optional[int] = None
        conflict_level = "Unavailable"
        conflict_signals: List[str] = []
        conflict_impacts: List[str] = []
        conflict_freshness = {
            "timestamp": None,
            "age_sec": None,
            "state": "unknown",
            "is_stale": True,
        }
        conflict_themes: List[str] = []
        conflict_source_count = 0
        if conflict_raw.get("error"):
            conflict_items = conflict_news_items
            for item in conflict_items:
                conflict_themes.extend([str(theme) for theme in (item.get("tags") or []) if theme])
                conflict_themes.extend(
                    [str(theme) for theme in (item.get("industries") or []) if theme]
            )
            conflict_score, conflict_signals = _score_conflict(len(conflict_items), conflict_themes)
            conflict_level = _risk_level(int(conflict_score or 0))
            conflict_impacts = _impact_for_conflict(conflict_themes)
            conflict_status = "rss_fallback" if conflict_raw.get("cooldown") else "news_fallback"
            conflict_source_count = len(conflict_items)
            feature_warnings.append("Structured conflict feed unavailable; using news tags only.")
            conflict_freshness = dict(news_freshness)
        else:
            for row in conflict_raw.get("articles", []) or []:
                conflict_themes.append(str(row.get("themes", "")))
            conflict_source_count = int(conflict_raw.get("count", 0) or 0)
            conflict_score, conflict_signals = _score_conflict(conflict_source_count, conflict_themes)
            conflict_level = _risk_level(int(conflict_score or 0))
            conflict_impacts = intel._filter_impacts(
                [str(item) for item in (conflict_raw.get("impacts", []) or [])],
                industry_filter,
            )
            conflict_freshness = {
                "timestamp": current_time,
                "age_sec": 0,
                "state": "fresh",
                "is_stale": False,
            }

        components: Dict[str, int] = {}
        if weather_score is not None:
            components["weather"] = int(weather_score)
        if conflict_score is not None:
            components["conflict"] = int(conflict_score)
        if news_score is not None:
            components["news"] = int(news_score)
        if components:
            weights = {"weather": 0.35, "conflict": 0.35, "news": 0.3}
            weighted = 0.0
            total_weight = 0.0
            for key, value in components.items():
                weight = weights.get(key, 0.3)
                weighted += value * weight
                total_weight += weight
            combined_score = min(10, int(round(weighted / max(total_weight, 0.1))))
            combined_level = _risk_level(combined_score)
        else:
            combined_score = None
            combined_level = "Unavailable"

        dominant_channel = _dominant_channel(weather_score, conflict_score, news_score)
        top_signal = (
            (weather_signals[0] if dominant_channel == "weather" and weather_signals else None)
            or (conflict_signals[0] if dominant_channel == "conflict" and conflict_signals else None)
            or (
                next(iter(news_metrics.get("emotion_counts", {}) or {}), None)
                if dominant_channel == "news"
                else None
            )
            or "Regional monitoring active."
        )

        feature_freshness = {
            "timestamp": current_time if weather_score is not None or conflict_score is not None else news_freshness.get("timestamp"),
            "age_sec": 0 if weather_score is not None or conflict_score is not None else news_freshness.get("age_sec"),
            "state": (
                "fresh"
                if weather_score is not None or conflict_score is not None
                else str(news_freshness.get("state") or "unknown")
            ),
            "is_stale": bool(news_cache_stale) and weather_score is None and conflict_score is None,
        }
        intensity = round(
            max(
                float(combined_score or 0) / 10.0,
                float(news_metrics.get("count", 0) or 0) / 16.0,
            ),
            3,
        )
        emotion_counts = news_metrics.get("emotion_counts", {}) or {}
        event_counts = news_metrics.get("event_counts", {}) or {}
        impact_counts = news_metrics.get("impact_counts", {}) or {}
        emotion_total = sum(int(count or 0) for count in emotion_counts.values())
        dominant_emotion = (
            sorted(
                emotion_counts.items(),
                key=lambda item: int(item[1] or 0),
                reverse=True,
            )[0][0]
            if emotion_counts
            else None
        )
        feature_id = _region_feature_id(region.name)
        geometry = {"type": "Point", "coordinates": [region.lon, region.lat]}
        features.append(
            geo_feature(
                feature_id,
                "regional-intel",
                geometry,
                properties={
                    "label": region.name,
                    "region": region.name,
                    "kind": "region",
                    "category": combined_level.lower(),
                    "industries": list(region.industries),
                    "display_scope": "region-centroid",
                    "combined_risk": {
                        "score": combined_score,
                        "level": combined_level,
                        "confidence": None,
                    },
                    "weather": {
                        "score": weather_score,
                        "level": weather_level,
                        "confidence": None,
                        "status": weather_status,
                        "temp_c": weather_raw.get("temp_c"),
                        "wind_ms": weather_raw.get("wind_ms"),
                        "precip_mm": weather_raw.get("precip_mm"),
                        "precip_24h": weather_raw.get("precip_24h"),
                        "signals": weather_signals,
                        "impacts": weather_impacts,
                        "freshness": weather_freshness,
                    },
                    "conflict": {
                        "score": conflict_score,
                        "level": conflict_level,
                        "confidence": None,
                        "status": conflict_status,
                        "count": conflict_source_count,
                        "signals": conflict_signals,
                        "impacts": conflict_impacts,
                        "event_counts": event_counts,
                        "impact_counts": impact_counts,
                        "affected_markets": sorted(
                            impact_counts,
                            key=lambda key: (-int(impact_counts.get(key) or 0), key),
                        ),
                        "freshness": conflict_freshness,
                    },
                    "news": {
                        "count": int(news_metrics.get("count", 0) or 0),
                        "risk_score": news_score,
                        "confidence": None,
                        "sentiment_avg": news_metrics.get("sentiment_avg", 0.0),
                        "negative_ratio": news_metrics.get("negative_ratio", 0.0),
                        "category_counts": news_metrics.get("category_counts", {}),
                        "event_counts": event_counts,
                        "impact_counts": impact_counts,
                        "emotion_counts": emotion_counts,
                        "region_counts": news_metrics.get("region_counts", {}),
                        "subregion_counts": news_metrics.get("subregion_counts", {}),
                        "region_emotion_counts": news_metrics.get("region_emotion_counts", {}),
                        "industry_emotion_counts": news_metrics.get("industry_emotion_counts", {}),
                        "region_industry_emotion_counts": news_metrics.get("region_industry_emotion_counts", {}),
                        "emotion_series": news_metrics.get("emotion_series", []),
                        "top_sources": sorted(
                            {str(item.get("source", "")) for item in region_news_items if item.get("source")}
                        )[:4],
                        "stale": news_cache_stale,
                        "cached": news_cache_cached,
                        "skipped_sources": skipped_sources,
                        "health": news_payload.get("health", {}),
                        "freshness": news_freshness,
                        "headlines": headlines_from_items(region_news_items),
                    },
                    "emotion": {
                        "count": emotion_total,
                        "dominant": dominant_emotion,
                        "counts": emotion_counts,
                        "sentiment_avg": news_metrics.get("sentiment_avg", 0.0),
                        "negative_ratio": news_metrics.get("negative_ratio", 0.0),
                        "series": news_metrics.get("emotion_series", []),
                    },
                    "presentation": {
                        "dominant_channel": dominant_channel,
                        "intensity": max(0.2, min(1.0, intensity)),
                        "top_signal": top_signal,
                        "hotspot_visible": bool(
                            conflict_score
                            or any(int(event_counts.get(tag) or 0) > 0 for tag in CONFLICT_CATEGORIES)
                        ),
                    },
                    "coverage": {
                        "weather": weather_score is not None,
                        "conflict": conflict_score is not None,
                        "news": bool(region_news_items),
                    },
                },
                source=source,
                ts=current_time,
                confidence=None,
                freshness=feature_freshness,
                warnings=feature_warnings,
            )
        )
        news_theater_texts = [
            str(item.get("title") or "")
            for item in region_news_items
        ]
        conflict_theater_texts = [
            str(item.get("title") or "")
            for item in conflict_news_items
        ]
        conflict_theater_texts.extend(
            str(row.get("title") or row.get("themes") or "")
            for row in (conflict_raw.get("articles") or [])
            if isinstance(row, Mapping)
        )
        news_theaters = match_theaters(news_theater_texts, parent_region=region.name)
        conflict_theaters = match_theaters(conflict_theater_texts, parent_region=region.name)
        region_headlines = headlines_from_items(region_news_items)
        conflict_headlines = headlines_from_items(conflict_news_items)
        conflict_intensity = max(
            float(conflict_score or 0) / 10.0,
            sum(int(event_counts.get(tag) or 0) for tag in CONFLICT_CATEGORIES) / 8.0,
        )
        news_count = int(news_metrics.get("count", 0) or 0)
        emotion_count = int(sum(int(count or 0) for count in emotion_counts.values()))

        if weather_score is not None:
            pulse_features.append(
                _signal_pulse_feature(
                    feature_id=f"pulse:weather:{feature_id}",
                    channel="weather",
                    label=f"{region.name} weather sample",
                    region=region.name,
                    theater=None,
                    lat=region.lat,
                    lon=region.lon,
                    target_id=feature_id,
                    intensity=float(weather_score or 0) / 10.0,
                    headlines=region_headlines,
                    extra={
                        "weather_score": weather_score,
                        "signals": weather_signals,
                        "impacts": weather_impacts,
                    },
                    source=source,
                    ts=current_time,
                    freshness=weather_freshness,
                    display_note=(
                        "Weather highlight is the region's representative sample point, "
                        "not a forecast field or alert polygon."
                    ),
                )
            )

        if news_count > 0:
            news_targets = news_theaters or [None]
            for theater in news_targets:
                pulse_features.append(
                    _signal_pulse_feature(
                        feature_id=f"pulse:news:{theater.theater_id if theater else feature_id}",
                        channel="news",
                        label=f"{(theater.label if theater else region.name)} news pressure",
                        region=region.name,
                        theater=theater.label if theater else None,
                        lat=theater.lat if theater else region.lat,
                        lon=theater.lon if theater else region.lon,
                        target_id=feature_id,
                        intensity=min(1.0, news_count / 16.0),
                        headlines=region_headlines,
                        extra={"article_count": news_count, "risk_score": news_score},
                        source=source,
                        ts=current_time,
                        freshness=news_freshness,
                        display_note=(
                            theater.geometry_note
                            if theater
                            else "News highlight is a regional centroid, not article geocoding."
                        ),
                    )
                )

        if emotion_count > 0:
            pulse_features.append(
                _signal_pulse_feature(
                    feature_id=f"pulse:emotion:{feature_id}",
                    channel="emotion",
                    label=f"{region.name} emotion observations",
                    region=region.name,
                    theater=None,
                    lat=region.lat,
                    lon=region.lon,
                    target_id=feature_id,
                    intensity=min(1.0, emotion_count / 12.0),
                    headlines=region_headlines,
                    extra={
                        "emotion_count": emotion_count,
                        "dominant": dominant_emotion,
                    },
                    source=source,
                    ts=current_time,
                    freshness=news_freshness,
                    display_note=(
                        "Emotion highlight is derived from article language at the "
                        "region centroid, not a surveyed population map."
                    ),
                )
            )

        if conflict_score or any(int(event_counts.get(tag) or 0) > 0 for tag in CONFLICT_CATEGORIES):
            conflict_targets = conflict_theaters or [None]
            for theater in conflict_targets:
                pulse_features.append(
                    _signal_pulse_feature(
                        feature_id=f"pulse:conflict:{theater.theater_id if theater else feature_id}",
                        channel="conflict",
                        label=f"{(theater.label if theater else region.name)} conflict signal",
                        region=region.name,
                        theater=theater.label if theater else None,
                        lat=theater.lat if theater else region.lat,
                        lon=theater.lon if theater else region.lon,
                        target_id=feature_id,
                        intensity=conflict_intensity,
                        headlines=conflict_headlines,
                        extra={
                            "conflict_score": conflict_score,
                            "article_count": conflict_source_count,
                            "event_counts": event_counts,
                            "impact_counts": impact_counts,
                            "affected_markets": sorted(
                                impact_counts,
                                key=lambda key: (-int(impact_counts.get(key) or 0), key),
                            ),
                            "top_event_tags": [
                                key
                                for key, _value in sorted(
                                    event_counts.items(),
                                    key=lambda item: (-int(item[1] or 0), item[0]),
                                )[:4]
                            ],
                            "signals": conflict_signals,
                            "impacts": conflict_impacts,
                        },
                        source=source,
                        ts=current_time,
                        freshness=feature_freshness,
                        display_note=(
                            theater.geometry_note
                            if theater
                            else "Centroid pulse is a reviewed regional highlight, not incident geometry."
                        ),
                    )
                )
        focus_targets.append(
            {
                "id": feature_id,
                "layer": "regional-intel",
                "label": region.name,
                "domain": "intel",
                "kind": dominant_channel,
                "category": combined_level,
                "lat": region.lat,
                "lon": region.lon,
                "confidence": None,
            }
        )
        scene_warnings.extend(feature_warnings)

    features.sort(
        key=lambda feature: (
            _regional_priority_score(feature.get("properties", {})),
            _component_score(feature.get("properties", {}), ("news", "count")),
        ),
        reverse=True,
    )
    feature_rank = {
        feature["id"]: _regional_priority_score(feature.get("properties", {}))
        for feature in features
    }
    focus_targets.sort(
        key=lambda target: feature_rank.get(str(target.get("id") or ""), 0.0),
        reverse=True,
    )

    bounds = _bounds_from_features(features)
    layer_meta = {
        "source": source,
        "count": len(features),
        "warnings": list(dict.fromkeys(scene_warnings)),
        "cached_news": news_cache_cached,
        "stale_news": news_cache_stale,
        "skipped_sources": skipped_sources,
        "methodology": REGIONAL_INTEL_METHODOLOGY,
    }
    conflict_pulses = [
        feature
        for feature in pulse_features
        if (feature.get("properties") or {}).get("channel") == "conflict"
    ]
    signal_pulses = [
        feature
        for feature in pulse_features
        if (feature.get("properties") or {}).get("channel") != "conflict"
    ]
    pulse_layer_meta = {
        "source": source,
        "count": len(conflict_pulses),
        "warnings": [
            "Conflict pulses are centroid highlights, not exact event polygons.",
            *list(dict.fromkeys(scene_warnings)),
        ],
        "methodology": REGIONAL_CONFLICT_PULSE_METHODOLOGY,
    }
    signal_layer_meta = {
        "source": source,
        "count": len(signal_pulses),
        "warnings": [
            "Weather, news, and emotion highlights are centroid samples, not heat grids.",
        ],
        "methodology": SIGNAL_HIGHLIGHT_METHODOLOGY,
    }
    timeline = {
        "mode": "regional-intel",
        "start_ts": min(timeline_ts) if timeline_ts else None,
        "end_ts": max(timeline_ts) if timeline_ts else None,
        "point_count": len(features),
        "trail_count": 0,
        "selected_ids": [feature["id"] for feature in features[:4]],
    }

    return geo_scene_payload(
        scene_id,
        title=title,
        kind="osint",
        camera_defaults=_camera_defaults(bounds),
        timeline=timeline,
        layers=[
            geo_layer_payload(
                "regional-intel",
                "point",
                label="Regional Signals",
                features=features,
                legend=[
                    {"label": "Combined", "value": "combined", "color": "#48f1a6"},
                    {"label": "Weather", "value": "weather", "color": "#75d7ff"},
                    {"label": "Conflict", "value": "conflict", "color": "#ff8b73"},
                    {"label": "News", "value": "news", "color": "#ffd166"},
                ],
                filters={
                    "industry": industry_filter,
                    "categories": category_list,
                    "sources": source_list,
                },
                style_hints={
                    "color_by": "presentation.dominant_channel",
                    "size_by": "presentation.intensity",
                    "halo": "emissive",
                },
                time_bounds={
                    "start_ts": timeline["start_ts"],
                    "end_ts": timeline["end_ts"],
                },
                meta=layer_meta,
            ),
            geo_layer_payload(
                "regional-conflict-overlays",
                "pulse",
                label="Regional Conflict Signals",
                features=conflict_pulses,
                filters={
                    "industry": industry_filter,
                    "categories": category_list,
                    "sources": source_list,
                },
                style_hints={
                    "fill": "#ff5c6a",
                    "stroke": "#ff8b73",
                    "min_opacity": 0.14,
                    "max_opacity": 0.3,
                    "pulse_period_ms": 4200,
                    "blend_mode": "screen",
                },
                time_bounds={
                    "start_ts": timeline["start_ts"],
                    "end_ts": timeline["end_ts"],
                },
                meta=pulse_layer_meta,
            ),
            geo_layer_payload(
                "regional-signal-overlays",
                "pulse",
                label="Regional Weather, News, and Emotion Highlights",
                features=signal_pulses,
                filters={
                    "industry": industry_filter,
                    "categories": category_list,
                    "sources": source_list,
                },
                style_hints={
                    "fill": "#75d7ff",
                    "stroke": "#ffd166",
                    "min_opacity": 0.12,
                    "max_opacity": 0.28,
                    "pulse_period_ms": 4800,
                    "blend_mode": "screen",
                },
                time_bounds={
                    "start_ts": timeline["start_ts"],
                    "end_ts": timeline["end_ts"],
                },
                meta=signal_layer_meta,
            ),
        ],
        focus_targets=focus_targets[:6],
        bounds=bounds,
        meta={
            "source": source,
            "timestamp": current_time,
            "industry_filter": industry_filter,
            "categories": category_list,
            "sources": source_list,
            "region_count": len(features),
            "cached_news": news_cache_cached,
            "stale_news": news_cache_stale,
            "skipped_sources": skipped_sources,
            "available_lenses": ["combined", "weather", "conflict", "news", "emotion"],
            "available_overlays": ["regional-conflict-overlays", "regional-signal-overlays"],
            "emotion": {
                "supported": True,
                "fields": [
                    "count",
                    "dominant",
                    "sentiment_avg",
                    "negative_ratio",
                    "emotion_counts",
                    "event_counts",
                    "impact_counts",
                    "region_counts",
                    "subregion_counts",
                    "emotion_series",
                ],
            },
            "warnings": list(dict.fromkeys(scene_warnings)),
        },
    )


def build_tracker_scene(
    snapshot: Mapping[str, Any],
    *,
    history_fetcher: Optional[Callable[[str], Mapping[str, Any]]] = None,
    scene_id: str = "osint-trackers",
    title: str = "Trackers",
    source: str = "trackers",
    mode: Optional[str] = None,
    point_limit: int = 24,
    trail_limit: int = 8,
    filters: Optional[Mapping[str, Any]] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    current_time = int(now if now is not None else time.time())
    warnings = list(snapshot.get("warnings", []) or [])
    points = [point for point in (snapshot.get("points", []) or []) if isinstance(point, Mapping)]
    selected_points = points[: max(0, point_limit)]
    applied_filters = dict(filters or {})

    live_features: List[Dict[str, Any]] = []
    for index, point in enumerate(selected_points):
        geometry = _point_geometry(point)
        if not geometry:
            warnings.append(
                f"Tracker point missing coordinates: {point.get('id') or point.get('label') or index}"
            )
            continue
        point_ts = point.get("updated_ts")
        freshness = _freshness(point_ts, now=current_time)
        live_features.append(
            geo_feature(
                point.get("id") or point.get("label") or f"point-{index}",
                "live-trackers",
                geometry,
                properties={
                    "label": point.get("label"),
                    "kind": point.get("kind"),
                    "category": point.get("category"),
                    "icao24": point.get("icao24"),
                    "callsign": point.get("callsign"),
                    "operator": point.get("operator"),
                    "operator_name": point.get("operator_name"),
                    "operator_country": point.get("operator_country"),
                    "country": point.get("country"),
                    "flight_number": point.get("flight_number"),
                    "tail_number": point.get("tail_number"),
                    "latitude": point.get("lat"),
                    "longitude": point.get("lon"),
                    "popup_coordinates": {
                        "lat": point.get("lat"),
                        "lon": point.get("lon"),
                    },
                    "speed_kts": point.get("speed_kts"),
                    "speed_vol_kts": point.get("speed_vol_kts"),
                    "altitude_ft": point.get("altitude_ft"),
                    "heading_deg": point.get("heading_deg"),
                    "industry": point.get("industry"),
                    "speed_heat": point.get("speed_heat"),
                    "vol_heat": point.get("vol_heat"),
                },
                source=source,
                ts=point_ts if isinstance(point_ts, int) else None,
                confidence=None,
                freshness=freshness,
                warnings=[],
            )
        )

    trail_features: List[Dict[str, Any]] = []
    if history_fetcher and trail_limit > 0:
        trail_candidates = [point for point in selected_points if point.get("id")]
        for index, point in enumerate(trail_candidates[:trail_limit]):
            tracker_id = str(point.get("id"))
            try:
                history_payload = history_fetcher(tracker_id)
            except Exception as exc:
                warnings.append(f"Tracker history fetch failed for {tracker_id}.")
                continue
            history = history_payload.get("history", []) if isinstance(history_payload, Mapping) else []
            if not isinstance(history, list) or len(history) < 2:
                continue
            geometry = _line_geometry(history)
            if not geometry:
                continue
            summary = {}
            if isinstance(history_payload, Mapping):
                summary = dict(history_payload.get("summary", {}) or {})
            if not summary:
                summary = _history_summary(history)
            latest_ts = None
            try:
                latest_ts = int(history[-1].get("ts"))
            except Exception:
                latest_ts = None
            freshness = _freshness(latest_ts, now=current_time)
            trail_features.append(
                geo_feature(
                    f"{tracker_id}:trail",
                    "tracker-trails",
                    geometry,
                    properties={
                        "tracker_id": tracker_id,
                        "label": point.get("label"),
                        "kind": point.get("kind"),
                        "category": point.get("category"),
                        "points": len(history),
                        "distance_km": summary.get("distance_km"),
                        "duration_sec": summary.get("duration_sec"),
                        "route_hint": summary.get("route_hint"),
                        "avg_speed_kts": summary.get("avg_speed_kts"),
                        "avg_altitude_ft": summary.get("avg_altitude_ft"),
                    },
                    source=source,
                    ts=latest_ts,
                    confidence=None,
                    freshness=freshness,
                    warnings=[],
                )
            )

    live_bounds = _bounds_from_features(live_features)
    trail_bounds = _bounds_from_features(trail_features)
    bounds = dict(trail_bounds or live_bounds)
    if live_bounds and trail_bounds:
        bounds = {
            "min_lon": min(live_bounds["min_lon"], trail_bounds["min_lon"]),
            "max_lon": max(live_bounds["max_lon"], trail_bounds["max_lon"]),
            "min_lat": min(live_bounds["min_lat"], trail_bounds["min_lat"]),
            "max_lat": max(live_bounds["max_lat"], trail_bounds["max_lat"]),
        }

    timeline_ts = [
        feature.get("ts")
        for feature in live_features + trail_features
        if feature.get("ts") is not None
    ]
    timeline = {
        "mode": mode or snapshot.get("mode") or "combined",
        "start_ts": min(timeline_ts) if timeline_ts else None,
        "end_ts": max(timeline_ts) if timeline_ts else None,
        "point_count": len(live_features),
        "trail_count": len(trail_features),
        "selected_ids": [feature["id"] for feature in live_features[:trail_limit]],
    }

    focus_targets = []
    for feature in sorted(
        live_features,
        key=lambda item: (
            float(item.get("freshness", {}).get("age_sec") or 0),
            str(item.get("id") or ""),
        ),
    )[:6]:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [None, None]) if isinstance(geometry, dict) else [None, None]
        focus_targets.append(
            {
                "id": feature["id"],
                "layer": feature["layer"],
                "label": feature.get("properties", {}).get("label"),
                "domain": "trackers",
                "kind": feature.get("properties", {}).get("kind"),
                "category": feature.get("properties", {}).get("category"),
                "lat": coords[1],
                "lon": coords[0],
                "confidence": feature.get("confidence"),
            }
        )

    layers = [
        geo_layer_payload(
            "live-trackers",
            "point",
            label="Live Trackers",
            features=live_features,
            legend=[
                {"label": "Aircraft", "value": "flight", "color": "#48f1a6"},
                {"label": "Vessels", "value": "ship", "color": "#2bdc98"},
            ],
            filters={
                "mode": snapshot.get("mode", mode or "combined"),
                **applied_filters,
            },
            style_hints={
                "color_by": "kind",
                "size_by": "speed_heat",
                "halo": "emissive",
            },
            time_bounds={
                "start_ts": timeline["start_ts"],
                "end_ts": timeline["end_ts"],
            },
            meta={
                "source": source,
                "count": len(live_features),
                "warnings": warnings,
                "filters": {
                    "mode": snapshot.get("mode", mode or "combined"),
                    **applied_filters,
                },
            },
        ),
        geo_layer_payload(
            "tracker-trails",
            "path",
            label="Tracker Trails",
            features=trail_features,
            legend=[
                {"label": "Replay Trail", "value": "history", "color": "#48f1a6"},
            ],
            filters={"history_limit": trail_limit},
            style_hints={
                "stroke": "rgba(72,241,166,0.7)",
                "glow": "rgba(72,241,166,0.2)",
                "width": 2,
            },
            time_bounds={
                "start_ts": timeline["start_ts"],
                "end_ts": timeline["end_ts"],
            },
            meta={
                "source": source,
                "count": len(trail_features),
                "warnings": warnings,
            },
        ),
    ]

    return geo_scene_payload(
        scene_id,
        title=title,
        kind="osint",
        camera_defaults=_camera_defaults(bounds),
        timeline=timeline,
        layers=layers,
        focus_targets=focus_targets,
        bounds=bounds,
        meta={
            "source": source,
            "mode": snapshot.get("mode", mode or "combined"),
            "point_limit": point_limit,
            "trail_limit": trail_limit,
            "point_count": len(points),
            "selected_point_count": len(live_features),
            "selected_trail_count": len(trail_features),
            "filters": {
                "mode": snapshot.get("mode", mode or "combined"),
                **applied_filters,
            },
            "warnings": warnings,
        },
    )


def build_overview_scene(
    snapshot: Mapping[str, Any],
    intel: MarketIntel,
    *,
    history_fetcher: Optional[Callable[[str], Mapping[str, Any]]] = None,
    scene_id: str = "osint-overview",
    title: str = "World",
    mode: Optional[str] = None,
    point_limit: int = 24,
    trail_limit: int = 8,
    tracker_filters: Optional[Mapping[str, Any]] = None,
    industry_filter: str = "all",
    enabled_sources: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    tracker_scene = build_tracker_scene(
        snapshot,
        history_fetcher=history_fetcher,
        scene_id="osint-overview-trackers",
        title="World Trackers",
        source="trackers",
        mode=mode,
        point_limit=point_limit,
        trail_limit=trail_limit,
        filters=tracker_filters,
        now=now,
    )
    intel_scene = build_intel_scene(
        intel,
        scene_id="osint-overview-intel",
        title="World Signals",
        source="intel",
        industry_filter=industry_filter,
        enabled_sources=enabled_sources,
        categories=categories,
        now=now,
    )
    layers = [*tracker_scene.get("layers", []), *intel_scene.get("layers", [])]
    all_features = [
        feature
        for layer in layers
        for feature in (layer.get("features", []) or [])
        if isinstance(feature, Mapping)
    ]
    bounds = _bounds_from_features(all_features)
    timeline_ts = [
        int(feature.get("ts"))
        for feature in all_features
        if feature.get("ts") is not None
    ]
    focus_targets = _interleave_focus_targets(
        intel_scene.get("focus_targets", []),
        tracker_scene.get("focus_targets", []),
        limit=10,
    )
    warnings = list(
        dict.fromkeys(
            [
                *list(tracker_scene.get("meta", {}).get("warnings", []) or []),
                *list(intel_scene.get("meta", {}).get("warnings", []) or []),
            ]
        )
    )
    tracker_point_count = int(tracker_scene.get("meta", {}).get("selected_point_count", 0) or 0)
    regional_point_count = int(intel_scene.get("meta", {}).get("region_count", 0) or 0)
    trail_count = int(tracker_scene.get("meta", {}).get("selected_trail_count", 0) or 0)
    hotspot_count = len(
        next(
            (
                layer.get("features", [])
                for layer in intel_scene.get("layers", [])
                if str(layer.get("id") or "") == "regional-conflict-overlays"
            ),
            [],
        )
    )
    return geo_scene_payload(
        scene_id,
        title=title,
        kind="osint",
        camera_defaults=_camera_defaults(bounds),
        timeline={
            "mode": "overview",
            "start_ts": min(timeline_ts) if timeline_ts else None,
            "end_ts": max(timeline_ts) if timeline_ts else None,
            "point_count": tracker_point_count + regional_point_count,
            "trail_count": trail_count,
            "selected_ids": [target.get("id") for target in focus_targets[:6]],
        },
        layers=layers,
        focus_targets=focus_targets,
        bounds=bounds,
        meta={
            "source": "trackers+intel",
            "timestamp": int(now if now is not None else time.time()),
            "mode": mode or snapshot.get("mode") or "combined",
            "point_limit": point_limit,
            "trail_limit": trail_limit,
            "tracker_filters": dict(tracker_filters or {}),
            "industry_filter": industry_filter,
            "categories": [str(category) for category in (categories or []) if str(category).strip()],
            "sources": [str(source) for source in (enabled_sources or []) if str(source).strip()],
            "tracker_point_count": tracker_point_count,
            "regional_point_count": regional_point_count,
            "trail_count": trail_count,
            "hotspot_count": hotspot_count,
            "available_lenses": ["combined", "weather", "conflict", "news", "emotion"],
            "available_overlays": ["regional-conflict-overlays", "regional-signal-overlays"],
            "warnings": warnings,
        },
    )
