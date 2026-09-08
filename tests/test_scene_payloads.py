from modules.market_data.intel import REGIONS
from modules.market_data.scene_payloads import (
    build_intel_scene,
    build_overview_scene,
    build_tracker_scene,
)


def test_build_tracker_scene_payload_composes_live_points_and_trails():
    snapshot = {
        "mode": "combined",
        "warnings": ["source warning"],
        "points": [
            {
                "id": "flt-1",
                "kind": "flight",
                "category": "commercial",
                "label": "AAL120",
                "lat": 40.64,
                "lon": -73.78,
                "updated_ts": 1700000100,
                "speed_heat": 0.6,
                "speed_vol_kts": 12.5,
                "icao24": "abc123",
                "callsign": "AAL120",
                "operator": "AAL",
                "operator_name": "American Airlines",
                "operator_country": "United States",
                "country": "United States",
            },
            {
                "id": "ship-1",
                "kind": "ship",
                "category": "cargo",
                "label": "EVER PRIME",
                "lat": 34.05,
                "lon": 120.3,
                "updated_ts": 1700000200,
                "speed_heat": 0.3,
                "speed_vol_kts": 4.4,
                "operator": "Evergreen",
                "operator_name": "Evergreen Marine",
                "country": "Singapore",
            },
        ],
    }

    histories = {
        "flt-1": {
            "history": [
                {"ts": 1700000000, "lat": 40.64, "lon": -73.78, "speed_kts": 420, "altitude_ft": 33000},
                {"ts": 1700000300, "lat": 40.2, "lon": -72.1, "speed_kts": 430, "altitude_ft": 33100},
            ],
            "summary": {
                "distance_km": 180.5,
                "duration_sec": 300,
                "avg_speed_kts": 425.0,
                "avg_altitude_ft": 33050.0,
                "route_hint": "JFK -> offshore",
            },
        }
    }

    scene = build_tracker_scene(
        snapshot,
        history_fetcher=lambda tracker_id: histories.get(tracker_id, {"history": []}),
        now=1700000400,
        trail_limit=2,
        filters={"category": "commercial", "country": "United States", "operator": "AAL"},
    )

    assert scene["scene_id"] == "osint-trackers"
    assert scene["kind"] == "osint"
    assert scene["layers"][0]["kind"] == "point"
    assert scene["layers"][1]["kind"] == "path"
    assert len(scene["layers"][0]["features"]) == 2
    assert len(scene["layers"][1]["features"]) == 1
    assert scene["layers"][0]["features"][0]["geometry"]["type"] == "Point"
    assert scene["layers"][1]["features"][0]["geometry"]["type"] == "LineString"
    assert scene["timeline"]["point_count"] == 2
    assert scene["timeline"]["trail_count"] == 1
    assert scene["focus_targets"]
    assert scene["meta"]["selected_point_count"] == 2
    assert scene["meta"]["filters"]["category"] == "commercial"
    assert scene["layers"][0]["filters"]["operator"] == "AAL"
    first_point = scene["layers"][0]["features"][0]["properties"]
    assert first_point["icao24"] == "abc123"
    assert first_point["callsign"] == "AAL120"
    assert first_point["operator_country"] == "United States"
    assert first_point["speed_vol_kts"] == 12.5
    assert first_point["latitude"] == 40.64
    assert first_point["longitude"] == -73.78
    assert first_point["popup_coordinates"] == {"lat": 40.64, "lon": -73.78}
    assert "source warning" in scene["meta"]["warnings"]


def test_build_tracker_scene_history_failure_does_not_expose_exception_detail():
    snapshot = {
        "mode": "flights",
        "warnings": [],
        "points": [
            {
                "id": "flt-private",
                "kind": "flight",
                "category": "commercial",
                "label": "TEST1",
                "lat": 40.0,
                "lon": -73.0,
                "updated_ts": 1700000100,
            }
        ],
    }

    def failing_history(_tracker_id):
        raise RuntimeError("PRIVATE_HISTORY_SENTINEL")

    scene = build_tracker_scene(
        snapshot,
        history_fetcher=failing_history,
        now=1700000400,
        trail_limit=1,
    )

    warnings = scene["meta"]["warnings"]
    assert "Tracker history fetch failed for flt-private." in warnings
    assert all("PRIVATE_HISTORY_SENTINEL" not in warning for warning in warnings)


def test_build_intel_scene_payload_uses_regional_centroids_and_provenance():
    class DummyWeather:
        def fetch(self, region):
            if region.name == "Middle East":
                return {"error": "Open-Meteo HTTP 503"}
            if region.name == "Europe":
                return {
                    "temp_c": 8.0,
                    "wind_ms": 18.0,
                    "precip_mm": 3.0,
                    "precip_24h": 14.0,
                    "wind_max": 22.0,
                    "temp_min": 4.0,
                    "temp_max": 13.0,
                    "impacts": ["Gusty conditions could slow air and sea logistics."],
                }
            return {
                "temp_c": 24.0,
                "wind_ms": 6.0,
                "precip_mm": 0.0,
                "precip_24h": 1.0,
                "wind_max": 8.0,
                "temp_min": 20.0,
                "temp_max": 27.0,
                "impacts": [],
            }

    class DummyConflict:
        def fetch(self, region):
            if region.name == "Europe":
                return {
                    "count": 9,
                    "articles": [
                        {"themes": "shipping, military"},
                        {"themes": "energy, logistics"},
                    ],
                    "impacts": ["Shipping and logistics risk elevated."],
                }
            if region.name == "Middle East":
                return {
                    "error": "GDELT is in cooldown. Try again later.",
                    "cooldown": True,
                }
            return {"count": 0, "articles": [], "impacts": []}

    class DummyIntel:
        def __init__(self):
            self.weather = DummyWeather()
            self.conflict = DummyConflict()

        def fetch_news_signals(self, ttl_seconds=600, enabled_sources=None):
            return {
                "items": [
                    {
                        "title": "European shipping disruption risk rises",
                        "source": "Reuters",
                        "published_ts": 1700000000,
                        "regions": ["Europe"],
                        "industries": ["shipping"],
                        "tags": ["conflict", "disruption"],
                        "event_tags": ["conflict", "disruption"],
                        "impact_channels": ["shipping_logistics"],
                        "categories": ["conflict"],
                        "sentiment": -0.6,
                        "emotions": {"fear": 2},
                    },
                    {
                        "title": "Middle East energy routes remain under pressure",
                        "source": "FT",
                        "published_ts": 1699999800,
                        "regions": ["Middle East"],
                        "industries": ["energy"],
                        "tags": ["conflict", "scarcity"],
                        "event_tags": ["conflict", "scarcity"],
                        "impact_channels": ["energy", "water_utilities"],
                        "categories": ["conflict"],
                        "sentiment": -0.4,
                        "emotions": {"fear": 1, "urgency": 1},
                    },
                    {
                        "title": "Asia-Pacific factories stabilize after port backlog clears",
                        "source": "Bloomberg",
                        "published_ts": 1699999700,
                        "regions": ["Asia-Pacific"],
                        "industries": ["manufacturing"],
                        "tags": ["supply-chain"],
                        "impact_channels": ["manufacturing_supply_chain"],
                        "categories": ["macro"],
                        "sentiment": 0.2,
                        "emotions": {"relief": 1},
                    },
                ],
                "cached": True,
                "stale": True,
                "skipped": ["AP"],
                "health": {"Reuters": {"last_ok": 1700000000}},
            }

        def filter_news_items(self, items, region_name, industry_filter, tickers=None):
            filtered = []
            for item in items:
                if region_name != "Global" and region_name not in (item.get("regions") or []):
                    continue
                if industry_filter != "all" and industry_filter not in (item.get("industries") or []):
                    continue
                filtered.append(item)
            return filtered

        def _filter_impacts(self, impacts, industry_filter):
            if industry_filter == "all":
                return impacts
            return [impact for impact in impacts if industry_filter.lower() in impact.lower()]

    scene = build_intel_scene(
        DummyIntel(),
        now=1700000400,
    )

    assert scene["scene_id"] == "osint-intel"
    assert scene["layers"][0]["kind"] == "point"
    assert scene["layers"][1]["kind"] == "pulse"
    assert len(scene["layers"][0]["features"]) == len(REGIONS) - 1
    assert "emotion" in scene["meta"]["available_lenses"]
    assert "regional-conflict-overlays" in scene["meta"]["available_overlays"]
    assert scene["meta"]["emotion"]["supported"] is True
    assert all(
        feature["properties"]["display_scope"] == "region-centroid"
        for feature in scene["layers"][0]["features"]
    )
    assert all(
        feature["properties"]["region"] != "Global"
        for feature in scene["layers"][0]["features"]
    )
    assert scene["meta"]["stale_news"] is True
    assert "News cache is stale; regional signals may lag live conditions." in scene["meta"]["warnings"]
    regional_layer = next(layer for layer in scene["layers"] if layer["id"] == "regional-intel")
    regional_methodology = regional_layer["meta"]["methodology"]
    assert regional_methodology["methodology_id"] == "regional_intel_v1"
    assert regional_methodology["derived"] is True
    assert regional_methodology["geometry_truth_level"] == "region-centroid"
    assert regional_methodology["units"]["score"] == "0-10 ordinal support/severity score"
    assert "weather 0.35" in regional_methodology["formulas"]["combined_score"]
    assert "news_article_count / 16" in regional_methodology["formulas"]["presentation_intensity"]
    assert "critical conflict signals" in regional_methodology["formulas"]["priority_sort"]
    assert "not incident geometry" in regional_methodology["coverage"]["geometry"]
    assert scene["focus_targets"][0]["label"] == "Europe"

    pulse_layer = next(layer for layer in scene["layers"] if layer["id"] == "regional-conflict-overlays")
    pulse_methodology = pulse_layer["meta"]["methodology"]
    assert pulse_methodology["methodology_id"] == "regional_conflict_pulse_v1"
    assert pulse_methodology["geometry_truth_level"] == "region-centroid-highlight"
    assert "not resolved incidents" in pulse_methodology["count_semantics"]
    assert "conflict_event_tag_count / 8" in pulse_methodology["formula"]

    europe = next(
        feature
        for feature in scene["layers"][0]["features"]
        if feature["properties"]["region"] == "Europe"
    )
    assert europe["properties"]["combined_risk"]["score"] is not None
    assert europe["properties"]["conflict"]["status"] == "gdelt"
    assert europe["properties"]["presentation"]["dominant_channel"] in {"weather", "conflict", "news", "combined"}
    assert europe["properties"]["emotion"]["count"] >= 0
    assert "dominant" in europe["properties"]["emotion"]
    assert "emotion_series" in europe["properties"]["news"]
    assert "subregion_counts" in europe["properties"]["news"]
    assert "region_counts" in europe["properties"]["news"]
    assert europe["properties"]["news"]["event_counts"]["conflict"] == 1
    assert "shipping_logistics" in europe["properties"]["news"]["impact_counts"]
    assert "affected_markets" in europe["properties"]["conflict"]

    middle_east = next(
        feature
        for feature in scene["layers"][0]["features"]
        if feature["properties"]["region"] == "Middle East"
    )
    assert middle_east["properties"]["weather"]["status"] == "unavailable"
    assert middle_east["properties"]["conflict"]["status"] == "rss_fallback"
    assert any(
        "precise event locations" in warning.lower() for warning in middle_east["warnings"]
    )
    pulse = next(
        feature
        for feature in scene["layers"][1]["features"]
        if feature["properties"]["region"] == "Europe"
    )
    assert pulse["properties"]["display_scope"] == "region-centroid-highlight"
    assert pulse["geometry"]["coordinates"] == [10.0, 50.0]
    weather_layer = next(layer for layer in scene["layers"] if layer["id"] == "regional-signal-overlays")
    assert weather_layer["kind"] == "pulse"
    assert any(feature["properties"]["channel"] == "weather" for feature in weather_layer["features"])
    assert any(feature["properties"]["channel"] == "news" for feature in weather_layer["features"])


def test_conflict_pulse_uses_ukraine_theater_not_germany_centroid():
    class DummyWeather:
        def fetch(self, region):
            return {"error": "offline"}

    class DummyConflict:
        def fetch(self, region):
            return {"error": "offline", "cooldown": True}

    class DummyIntel:
        def __init__(self):
            self.weather = DummyWeather()
            self.conflict = DummyConflict()

        def fetch_news_signals(self, ttl_seconds=600, enabled_sources=None):
            return {
                "items": [
                    {
                        "title": "Kyiv reports overnight strikes across Ukraine",
                        "source": "Reuters",
                        "published_ts": 1700000000,
                        "regions": ["Europe"],
                        "industries": ["energy"],
                        "tags": ["conflict"],
                        "event_tags": ["conflict"],
                        "impact_channels": ["energy"],
                        "categories": ["conflict"],
                        "sentiment": -0.7,
                        "emotions": {"fear": 2},
                    },
                    {
                        "title": "Myanmar junta clashes continue in Rakhine",
                        "source": "AP",
                        "published_ts": 1700000001,
                        "regions": ["Asia-Pacific"],
                        "industries": ["shipping"],
                        "tags": ["conflict"],
                        "event_tags": ["conflict"],
                        "impact_channels": ["shipping_logistics"],
                        "categories": ["conflict"],
                        "sentiment": -0.5,
                        "emotions": {"fear": 1},
                    },
                ],
                "cached": True,
                "stale": False,
                "skipped": [],
                "health": {},
            }

        def filter_news_items(self, items, region_name, industry_filter, tickers=None):
            return [
                item
                for item in items
                if region_name in (item.get("regions") or [])
            ]

        def _filter_impacts(self, impacts, industry_filter):
            return impacts

    scene = build_intel_scene(DummyIntel(), now=1700000400)
    pulses = next(
        layer for layer in scene["layers"] if layer["id"] == "regional-conflict-overlays"
    )["features"]
    ukraine = next(feature for feature in pulses if feature["properties"].get("theater") == "Ukraine")
    myanmar = next(feature for feature in pulses if feature["properties"].get("theater") == "Myanmar")
    assert ukraine["geometry"]["coordinates"] == [31.17, 48.38]
    assert myanmar["geometry"]["coordinates"] == [96.15, 21.92]
    assert ukraine["properties"]["headlines"][0]["title"].startswith("Kyiv")
    europe_centroid_conflict = [
        feature
        for feature in pulses
        if feature["properties"].get("region") == "Europe" and not feature["properties"].get("theater")
    ]
    assert europe_centroid_conflict == []


def test_conflict_pulse_ignores_locations_from_non_conflict_news():
    class DummyWeather:
        def fetch(self, region):
            return {"error": "offline"}

    class DummyConflict:
        def fetch(self, region):
            return {"error": "offline", "cooldown": True}

    class DummyIntel:
        def __init__(self):
            self.weather = DummyWeather()
            self.conflict = DummyConflict()

        def fetch_news_signals(self, ttl_seconds=600, enabled_sources=None):
            return {
                "items": [
                    {
                        "title": "Ukraine technology exports expand",
                        "source": "Market Wire",
                        "published_ts": 1700000000,
                        "regions": ["Europe"],
                        "industries": ["technology"],
                        "event_tags": ["trade"],
                        "categories": ["business"],
                    },
                    {
                        "title": "European conflict monitoring continues",
                        "source": "Reuters",
                        "published_ts": 1700000001,
                        "regions": ["Europe"],
                        "industries": ["shipping"],
                        "event_tags": ["conflict"],
                        "categories": ["conflict"],
                    },
                ],
                "cached": True,
                "stale": False,
                "skipped": [],
                "health": {},
            }

        def filter_news_items(self, items, region_name, industry_filter, tickers=None):
            return [item for item in items if region_name in (item.get("regions") or [])]

        def _filter_impacts(self, impacts, industry_filter):
            return impacts

    scene = build_intel_scene(DummyIntel(), now=1700000400)
    pulse_layers = {
        layer["id"]: layer["features"]
        for layer in scene["layers"]
        if layer["kind"] == "pulse"
    }
    conflict_pulses = [
        feature
        for feature in pulse_layers["regional-conflict-overlays"]
        if feature["properties"].get("region") == "Europe"
    ]
    assert len(conflict_pulses) == 1
    assert conflict_pulses[0]["properties"].get("theater") is None
    assert conflict_pulses[0]["geometry"]["coordinates"] == [10.0, 50.0]
    assert conflict_pulses[0]["properties"]["headlines"][0]["title"].startswith("European conflict")
    news_pulses = [
        feature
        for feature in pulse_layers["regional-signal-overlays"]
        if feature["properties"].get("channel") == "news"
        and feature["properties"].get("region") == "Europe"
    ]
    assert any(feature["properties"].get("theater") == "Ukraine" for feature in news_pulses)


def test_build_overview_scene_combines_tracker_and_intel_layers():
    snapshot = {
        "mode": "combined",
        "warnings": [],
        "points": [
            {
                "id": "flt-1",
                "kind": "flight",
                "category": "commercial",
                "label": "AAL120",
                "lat": 40.64,
                "lon": -73.78,
                "updated_ts": 1700000100,
                "speed_heat": 0.6,
                "operator_name": "American Airlines",
                "country": "United States",
            }
        ],
    }

    class DummyWeather:
        def fetch(self, region):
            return {
                "temp_c": 20.0,
                "wind_ms": 6.0,
                "precip_mm": 0.0,
                "precip_24h": 1.0,
                "wind_max": 8.0,
                "temp_min": 18.0,
                "temp_max": 23.0,
                "impacts": [],
            }

    class DummyConflict:
        def fetch(self, region):
            return {"count": 0, "articles": [], "impacts": []}

    class DummyIntel:
        def __init__(self):
            self.weather = DummyWeather()
            self.conflict = DummyConflict()

        def fetch_news_signals(self, ttl_seconds=600, enabled_sources=None):
            return {
                "items": [
                    {
                        "title": "Europe conflict risk rises",
                        "source": "Reuters",
                        "published_ts": 1700000000,
                        "regions": ["Europe"],
                        "industries": ["shipping"],
                        "event_tags": ["conflict"],
                        "impact_channels": ["shipping_logistics"],
                        "categories": ["conflict"],
                        "sentiment": -0.4,
                        "emotions": {"fear": 2},
                    }
                ],
                "cached": True,
                "stale": False,
                "skipped": [],
                "health": {},
            }

        def filter_news_items(self, items, region_name, industry_filter, tickers=None):
            return [item for item in items if region_name in (item.get("regions") or [])]

        def _filter_impacts(self, impacts, industry_filter):
            return impacts

    scene = build_overview_scene(
        snapshot,
        DummyIntel(),
        history_fetcher=lambda tracker_id: {"history": []},
        now=1700000400,
    )

    assert scene["scene_id"] == "osint-overview"
    assert len(scene["layers"]) == 5
    assert scene["meta"]["tracker_point_count"] == 1
    assert scene["meta"]["regional_point_count"] > 0
    assert "regional-conflict-overlays" in scene["meta"]["available_overlays"]
    assert "regional-signal-overlays" in scene["meta"]["available_overlays"]
    assert {target["domain"] for target in scene["focus_targets"][:2]} == {"intel", "trackers"}
