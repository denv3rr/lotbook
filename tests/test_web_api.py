"""Web API contract-shape and negative-path tests.

Functions named *_stubbed monkeypatch route internals to prove response
shape and filter wiring. They are not positive-path evidence under
docs/us_gov_standards.md. Isolated real-data coverage lives in
tests/test_web_api_clients.py, tests/test_web_api_maintenance.py, and
tests/test_security.py.
"""

import os
from unittest import mock

import pytest

from fastapi.testclient import TestClient

from web_api import app as web_app
from web_api.routes import clients as clients_routes
from web_api.routes import intel as intel_routes
from web_api.routes import scene as scene_routes
from web_api.routes import trackers as tracker_routes

def _api_headers():
    key = os.getenv("LOTBOOK_WEB_API_KEY")
    return {"X-API-Key": key} if key else {}


def test_health_endpoint():
    client = TestClient(web_app.app)
    resp = client.get("/api/health", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_endpoint_requires_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "test_key")
    client = TestClient(web_app.app)
    resp = client.get("/api/health")
    assert resp.status_code == 401
    resp = client.get("/api/health", headers={"X-API-Key": "test_key"})
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/api/clients", "get", None),
        ("/api/trackers/snapshot", "get", None),
        ("/api/intel/news", "get", None),
        ("/api/reports/client/test-client", "get", None),
        ("/api/tools/diagnostics", "get", None),
    ],
)
def test_protected_endpoints_require_key(monkeypatch, path, method, body):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    request = getattr(client, method)
    resp = request(path) if body is None else request(path, json=body)
    assert resp.status_code == 401


def test_cors_allows_localhost_origin():
    client = TestClient(web_app.app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_cors_blocks_non_local_origin():
    client = TestClient(web_app.app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


def test_settings_endpoint():
    client = TestClient(web_app.app)
    resp = client.get("/api/settings", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert "settings" in payload
    assert "credentials" in payload["settings"]
    assert "system" in payload
    assert "system_metrics" in payload


def test_diagnostics_endpoint():
    client = TestClient(web_app.app)
    resp = client.get("/api/tools/diagnostics", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert "system" in payload
    assert "metrics" in payload
    assert "feeds" in payload
    assert "registry" in payload["feeds"]
    assert "summary" in payload["feeds"]
    assert "health_counts" in payload["feeds"]["summary"]
    assert "duplicates" in payload
    assert "accounts" in payload["duplicates"]
    assert "client_names" in payload["duplicates"]
    assert "news" in payload["duplicates"]
    assert "orphans" in payload
    assert "holdings" in payload["orphans"]
    assert "lots" in payload["orphans"]


def test_intel_summary_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(intel_routes.MarketIntel, "combined_report") as mocked:
        mocked.return_value = {"title": "ok", "summary": [], "sections": []}
        resp = client.get("/api/intel/summary", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["title"] == "ok"


def test_intel_news_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(intel_routes.MarketIntel, "fetch_news_signals") as mocked:
        mocked.return_value = {"items": [{"title": "A"}], "cached": False, "stale": False, "skipped": []}
        resp = client.get("/api/intel/news?limit=1", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]


def test_tracker_search_endpoint_stubbed():
    client = TestClient(web_app.app)
    sample = {
        "points": [
            {
                "id": "abc123",
                "kind": "flight",
                "label": "AAL762",
                "category": "commercial",
                "operator": "AAL",
                "flight_number": "762",
                "tail_number": "N123AA",
                "country": "United States",
            }
        ]
    }
    with mock.patch.object(tracker_routes.GlobalTrackers, "get_snapshot") as mocked:
        mocked.return_value = sample
        resp = client.get("/api/trackers/search?q=aal&mode=combined", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1


def test_tracker_snapshot_endpoint_stubbed():
    client = TestClient(web_app.app)
    sample = {
        "mode": "combined",
        "count": 1,
        "warnings": [],
        "points": [{"id": "abc123", "kind": "flight", "label": "AAL762"}],
    }
    with mock.patch.object(tracker_routes.GlobalTrackers, "get_snapshot") as mocked:
        mocked.return_value = sample
        resp = client.get("/api/trackers/snapshot?mode=combined", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["points"]
    assert payload["count"] == len(payload["points"])


def test_tracker_snapshot_filters_stubbed():
    client = TestClient(web_app.app)
    sample = {
        "mode": "combined",
        "count": 2,
        "warnings": [],
        "points": [
            {
                "id": "abc123",
                "kind": "flight",
                "label": "AAL762",
                "category": "commercial",
                "country": "United States",
                "operator": "AAL",
                "operator_name": "American Airlines",
                "lat": 35.0,
                "lon": -120.0,
            },
            {
                "id": "ship-1",
                "kind": "ship",
                "label": "MSC TEST",
                "category": "cargo",
                "country": "Canada",
                "operator": "MSC",
                "operator_name": "MSC",
                "lat": 10.0,
                "lon": 10.0,
            },
        ],
    }
    with mock.patch.object(tracker_routes.GlobalTrackers, "get_snapshot") as mocked:
        mocked.return_value = sample
        resp = client.get(
            "/api/trackers/snapshot?mode=combined&category=commercial&country=united&operator=aal&bbox=30,-130,40,-110",
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["points"][0]["id"] == "abc123"


def test_tracker_snapshot_invalid_bbox():
    client = TestClient(web_app.app)
    resp = client.get(
        "/api/trackers/snapshot?bbox=1,2,3",
        headers=_api_headers(),
    )
    assert resp.status_code == 400
    assert "bbox" in resp.json()["detail"]


def test_tracker_detail_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(tracker_routes.GlobalTrackers, "get_detail") as mocked:
        mocked.return_value = {"id": "abc123", "point": {"label": "AAL762"}, "history": []}
        resp = client.get("/api/trackers/detail/abc123", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["point"]["label"] == "AAL762"

def test_tracker_history_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(tracker_routes.GlobalTrackers, "get_history") as mocked:
        mocked.return_value = {"id": "abc123", "history": [{"ts": 1, "lat": 10.0, "lon": 20.0}]}
        resp = client.get("/api/trackers/history/abc123", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == "abc123"
    assert payload["history"]


def test_osint_tracker_scene_endpoint_stubbed():
    client = TestClient(web_app.app)
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
                "speed_vol_kts": 13.5,
                "icao24": "abc123",
                "callsign": "AAL120",
                "operator": "AAL",
                "operator_name": "American Airlines",
                "operator_country": "United States",
                "country": "United States",
            }
        ],
    }
    history = {
        "id": "flt-1",
        "history": [
            {"ts": 1700000000, "lat": 40.64, "lon": -73.78, "speed_kts": 420},
            {"ts": 1700000300, "lat": 40.2, "lon": -72.1, "speed_kts": 430},
        ],
        "summary": {"distance_km": 180.5, "duration_sec": 300, "route_hint": "JFK -> offshore"},
    }
    filtered_snapshot = dict(snapshot)
    filtered_snapshot["points"] = list(snapshot["points"])
    with mock.patch.object(scene_routes.GlobalTrackers, "get_snapshot") as mocked_snapshot, mock.patch.object(
        scene_routes.GlobalTrackers, "apply_filters"
    ) as mocked_filters, mock.patch.object(scene_routes.GlobalTrackers, "get_history") as mocked_history:
        mocked_snapshot.return_value = snapshot
        mocked_filters.return_value = filtered_snapshot
        mocked_history.return_value = history
        resp = client.get(
            "/api/osint/scene/trackers?mode=combined&category=commercial&country=United%20States&operator=AAL&bbox=30,-90,50,-60",
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    mocked_filters.assert_called_once_with(
        snapshot,
        category="commercial",
        country="United States",
        operator="AAL",
        bbox=(30.0, -90.0, 50.0, -60.0),
    )
    assert payload["scene_id"] == "osint-trackers"
    assert payload["layers"][0]["kind"] == "point"
    assert payload["layers"][1]["kind"] == "path"
    assert payload["meta"]["route"] == "/api/osint/scene/trackers"
    assert payload["meta"]["filters"]["category"] == "commercial"
    assert payload["meta"]["filters"]["operator"] == "AAL"
    point = payload["layers"][0]["features"][0]["properties"]
    assert point["icao24"] == "abc123"
    assert point["callsign"] == "AAL120"
    assert point["operator_country"] == "United States"
    assert point["speed_vol_kts"] == 13.5
    assert point["popup_coordinates"] == {"lat": 40.64, "lon": -73.78}


def test_osint_tracker_scene_rejects_invalid_bbox(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.get(
        "/api/osint/scene/trackers?bbox=1,2,3",
        headers={"X-API-Key": "secret"},
    )
    assert resp.status_code == 400
    assert "bbox" in resp.json()["detail"]


def test_osint_tracker_scene_requires_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.get("/api/osint/scene/trackers")
    assert resp.status_code == 401
    resp = client.get(
        "/api/osint/scene/trackers",
        headers={"X-API-Key": "secret"},
    )
    assert resp.status_code == 200


def test_osint_intel_scene_endpoint_stubbed():
    client = TestClient(web_app.app)
    sentinel_intel = object()
    scene_payload = {
        "scene_id": "osint-intel",
        "title": "Regional Signals",
        "kind": "osint",
        "camera_defaults": {"target_lat": 25.0, "target_lon": 15.0, "distance": 3.5},
        "timeline": {"mode": "regional-intel", "point_count": 2, "trail_count": 0},
        "layers": [
            {
                "id": "regional-intel",
                "kind": "point",
                "label": "Regional Signals",
                "features": [
                    {
                        "id": "region:europe",
                        "layer": "regional-intel",
                        "geometry": {"type": "Point", "coordinates": [10.0, 50.0]},
                        "properties": {
                            "region": "Europe",
                            "emotion": {
                                "count": 3,
                                "dominant": "fear",
                            },
                            "news": {
                                "emotion_series": [{"emotion": "fear", "count": 2}],
                                "subregion_counts": {"Northern Europe": 1},
                                "region_counts": {"Europe": 3},
                            },
                        },
                    }
                ],
                "meta": {
                    "methodology": {
                        "methodology_id": "regional_intel_v1",
                        "geometry_truth_level": "region-centroid",
                    },
                },
            }
        ],
        "focus_targets": [
            {"id": "region:europe", "label": "Europe", "lat": 50.0, "lon": 10.0}
        ],
        "meta": {
            "warnings": ["Scene warning"],
            "available_lenses": ["combined", "weather", "conflict", "news", "emotion"],
            "emotion": {
                "supported": True,
                "fields": [
                    "count",
                    "dominant",
                    "sentiment_avg",
                    "negative_ratio",
                    "emotion_counts",
                    "region_counts",
                    "subregion_counts",
                    "emotion_series",
                ],
            },
        },
    }
    with mock.patch.object(scene_routes, "MarketIntel") as mocked_intel_cls, mock.patch.object(
        scene_routes, "build_intel_scene"
    ) as mocked_builder:
        mocked_intel_cls.return_value = sentinel_intel
        mocked_builder.return_value = scene_payload
        resp = client.get(
            "/api/osint/scene/intel?industry=energy&categories=conflict,macro&sources=Reuters,FT",
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    mocked_builder.assert_called_once_with(
        sentinel_intel,
        industry_filter="energy",
        categories=["conflict", "macro"],
        enabled_sources=["Reuters", "FT"],
    )
    assert payload["scene_id"] == "osint-intel"
    assert payload["layers"][0]["kind"] == "point"
    assert payload["meta"]["route"] == "/api/osint/scene/intel"
    assert "Scene warning" in payload["meta"]["warnings"]
    assert "emotion" in payload["meta"]["available_lenses"]
    assert payload["meta"]["emotion"]["supported"] is True
    assert payload["layers"][0]["meta"]["methodology"]["methodology_id"] == "regional_intel_v1"
    assert payload["layers"][0]["features"][0]["properties"]["emotion"]["dominant"] == "fear"
    assert payload["layers"][0]["features"][0]["properties"]["news"]["emotion_series"]


def test_osint_intel_scene_requires_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.get("/api/osint/scene/intel")
    assert resp.status_code == 401
    with mock.patch.object(scene_routes, "build_intel_scene") as mocked_builder:
        mocked_builder.return_value = {
            "scene_id": "osint-intel",
            "camera_defaults": {},
            "timeline": {},
            "layers": [{"id": "regional-intel", "kind": "point", "features": []}],
            "focus_targets": [],
            "meta": {"warnings": []},
        }
        resp = client.get(
            "/api/osint/scene/intel",
            headers={"X-API-Key": "secret"},
        )
    assert resp.status_code == 200


def test_osint_overview_scene_endpoint_stubbed():
    client = TestClient(web_app.app)
    sentinel_intel = object()
    snapshot = {"mode": "combined", "points": [], "warnings": []}
    scene_payload = {
        "scene_id": "osint-overview",
        "title": "World",
        "kind": "osint",
        "camera_defaults": {"target_lat": 25.0, "target_lon": 15.0, "distance": 3.5},
        "timeline": {"mode": "overview", "point_count": 3, "trail_count": 1},
        "layers": [
            {"id": "live-trackers", "kind": "point", "features": []},
            {"id": "tracker-trails", "kind": "path", "features": []},
            {"id": "regional-intel", "kind": "point", "features": []},
            {"id": "regional-conflict-overlays", "kind": "pulse", "features": []},
        ],
        "focus_targets": [
            {"id": "region:europe", "label": "Europe", "domain": "intel"},
            {"id": "flt-1", "label": "AAL120", "domain": "trackers"},
        ],
        "meta": {
            "warnings": ["Overview warning"],
            "available_lenses": ["combined", "weather", "conflict", "news", "emotion"],
            "available_overlays": ["regional-conflict-overlays"],
            "tracker_point_count": 1,
            "regional_point_count": 2,
        },
    }
    with mock.patch.object(scene_routes.GlobalTrackers, "get_snapshot") as mocked_snapshot, mock.patch.object(
        scene_routes.GlobalTrackers, "apply_filters"
    ) as mocked_filters, mock.patch.object(
        scene_routes, "MarketIntel"
    ) as mocked_intel_cls, mock.patch.object(
        scene_routes, "build_overview_scene"
    ) as mocked_builder:
        mocked_snapshot.return_value = snapshot
        mocked_filters.return_value = snapshot
        mocked_intel_cls.return_value = sentinel_intel
        mocked_builder.return_value = scene_payload
        resp = client.get(
            "/api/osint/scene/overview?mode=combined&category=commercial&country=United%20States&operator=AAL&industry=energy&categories=conflict&sources=Reuters",
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    mocked_builder.assert_called_once_with(
        snapshot,
        sentinel_intel,
        history_fetcher=mock.ANY,
        mode="combined",
        point_limit=24,
        trail_limit=8,
        tracker_filters={
            "category": "commercial",
            "country": "United States",
            "operator": "AAL",
        },
        industry_filter="energy",
        categories=["conflict"],
        enabled_sources=["Reuters"],
    )
    assert payload["scene_id"] == "osint-overview"
    assert payload["meta"]["route"] == "/api/osint/scene/overview"
    assert payload["focus_targets"][0]["domain"] == "intel"


def test_osint_overview_scene_survives_intel_failure():
    client = TestClient(web_app.app)
    snapshot = {"mode": "combined", "points": [], "warnings": []}
    tracker_scene = {
        "scene_id": "osint-overview",
        "title": "World",
        "kind": "osint",
        "camera_defaults": {"target_lat": 0.0, "target_lon": 0.0, "distance": 3.5},
        "timeline": {"mode": "trackers", "point_count": 0, "trail_count": 0},
        "layers": [{"id": "live-trackers", "kind": "point", "features": []}],
        "focus_targets": [],
        "meta": {"warnings": []},
    }
    with mock.patch.object(scene_routes.GlobalTrackers, "get_snapshot") as mocked_snapshot, mock.patch.object(
        scene_routes.GlobalTrackers, "apply_filters"
    ) as mocked_filters, mock.patch.object(
        scene_routes, "MarketIntel"
    ) as mocked_intel_cls, mock.patch.object(
        scene_routes, "build_tracker_scene"
    ) as mocked_tracker_builder:
        mocked_snapshot.return_value = snapshot
        mocked_filters.return_value = snapshot
        mocked_intel_cls.side_effect = RuntimeError("intel feed timeout")
        mocked_tracker_builder.return_value = tracker_scene
        resp = client.get("/api/osint/scene/overview?mode=combined", headers=_api_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["scene_id"] == "osint-overview"
    assert any("Regional signals unavailable" in item for item in payload["meta"]["warnings"])


def test_osint_overview_scene_requires_key(monkeypatch):
    monkeypatch.setenv("LOTBOOK_WEB_API_KEY", "secret")
    client = TestClient(web_app.app)
    resp = client.get("/api/osint/scene/overview")
    assert resp.status_code == 401


def test_tracker_analysis_endpoint_stubbed():
    client = TestClient(web_app.app)
    sample = {
        "id": "abc123",
        "replay": [{"ts": 1, "lat": 10.0, "lon": 20.0}],
        "loiter": {"detected": False},
        "geofences": {"events": [], "active": []},
    }
    with mock.patch.object(tracker_routes.GlobalTrackers, "analyze_tracker") as mocked:
        mocked.return_value = sample
        resp = client.get("/api/trackers/analysis/abc123", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == "abc123"


def test_tracker_analysis_custom_endpoint_stubbed():
    client = TestClient(web_app.app)
    sample = {
        "id": "abc123",
        "replay": [{"ts": 1, "lat": 10.0, "lon": 20.0}],
        "loiter": {"detected": False},
        "geofences": {"events": [], "active": []},
    }
    with mock.patch.object(tracker_routes.GlobalTrackers, "analyze_tracker") as mocked:
        mocked.return_value = sample
        resp = client.post(
            "/api/trackers/analysis",
            json={
                "tracker_id": "abc123",
                "window_sec": 3600,
                "loiter_radius_km": 10.0,
                "loiter_min_minutes": 20.0,
                "geofences": [
                    {"id": "f1", "label": "Test", "lat": 10.0, "lon": 20.0, "radius_km": 5.0}
                ],
            },
            headers=_api_headers(),
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == "abc123"


def test_client_dashboard_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(clients_routes.DbClientStore, "fetch_client") as mocked_client, mock.patch.object(
        clients_routes, "portfolio_dashboard"
    ) as mocked_dash:
        mocked_client.return_value = {"client_id": "c1", "name": "Test Client", "accounts": []}
        mocked_dash.return_value = {
            "client": {"client_id": "c1"},
            "totals": {},
            "holdings": [],
            "manual_holdings": [],
            "history": [],
            "risk": {},
            "regime": {},
            "warnings": [],
        }
        resp = client.get("/api/clients/c1/dashboard?interval=1M", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["client"]["client_id"] == "c1"


def test_account_dashboard_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(clients_routes.DbClientStore, "fetch_client") as mocked_client, mock.patch.object(
        clients_routes, "account_dashboard"
    ) as mocked_dash:
        mocked_client.return_value = {
            "client_id": "c1",
            "name": "Test Client",
            "accounts": [{"account_id": "a1", "account_name": "Alpha", "holdings": {}}],
        }
        mocked_dash.return_value = {
            "client": {"client_id": "c1"},
            "account": {"account_id": "a1"},
            "totals": {},
            "holdings": [],
            "manual_holdings": [],
            "history": [],
            "risk": {},
            "regime": {},
            "warnings": [],
        }
        resp = client.get("/api/clients/c1/accounts/a1/dashboard?interval=1M", headers=_api_headers())
    assert resp.status_code == 200
    assert resp.json()["account"]["account_id"] == "a1"


def test_client_patterns_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(clients_routes.DbClientStore, "fetch_client") as mocked_client, mock.patch.object(
        clients_routes, "client_patterns"
    ) as mocked_patterns:
        mocked_client.return_value = {"client_id": "c1", "name": "Test Client", "accounts": []}
        mocked_patterns.return_value = {"entropy": 0.1, "wave_surface": {"z": []}}
        resp = client.get("/api/clients/c1/patterns?interval=1M", headers=_api_headers())
    assert resp.status_code == 200
    assert "entropy" in resp.json()


def test_account_patterns_endpoint_stubbed():
    client = TestClient(web_app.app)
    with mock.patch.object(clients_routes.DbClientStore, "fetch_client") as mocked_client, mock.patch.object(
        clients_routes, "account_patterns"
    ) as mocked_patterns:
        mocked_client.return_value = {
            "client_id": "c1",
            "name": "Test Client",
            "accounts": [{"account_id": "a1", "account_name": "Alpha", "holdings": {}}],
        }
        mocked_patterns.return_value = {"entropy": 0.1, "wave_surface": {"z": []}}
        resp = client.get("/api/clients/c1/accounts/a1/patterns?interval=1M", headers=_api_headers())
    assert resp.status_code == 200
    assert "entropy" in resp.json()
