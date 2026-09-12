from unittest import mock

import time

from modules.market_data.trackers import GlobalTrackers, TrackerPoint, TrackerProviders


class DummyResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_flights_keeps_points_without_speed_or_alt(monkeypatch):
    monkeypatch.setenv("FLIGHT_DATA_URL", "http://example")
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("LOTBOOK_INCLUDE_COMMERCIAL", "1")
    payload = [
        {
            "lat": 33.63,
            "lon": -84.43,
            "callsign": "AAL123",
            "category": "commercial",
        }
    ]
    with mock.patch("modules.market_data.trackers.requests.get", return_value=DummyResponse(payload)):
        points, warnings = TrackerProviders.fetch_flights()
    assert points
    assert warnings == []


def test_fetch_flights_merges_multiple_urls(monkeypatch):
    monkeypatch.setenv("FLIGHT_DATA_URL", "http://example/a,http://example/b")
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("LOTBOOK_INCLUDE_COMMERCIAL", "1")

    def fake_get(url, timeout=8):
        if url.endswith("/a"):
            return DummyResponse([{"lat": 1.0, "lon": 2.0, "callsign": "AAA111"}])
        return DummyResponse([{"lat": 3.0, "lon": 4.0, "callsign": "BBB222"}])

    with mock.patch("modules.market_data.trackers.requests.get", side_effect=fake_get):
        points, warnings = TrackerProviders.fetch_flights()
    labels = {pt.label for pt in points}
    assert labels == {"AAA111", "BBB222"}
    assert warnings == []


def test_snapshot_marks_unknown_fields():
    trackers = GlobalTrackers()
    trackers._cached = {
        "flights": [
            TrackerPoint(
                lat=1.0,
                lon=2.0,
                label="NOINFO",
                category="commercial",
                kind="flight",
            )
        ],
        "ships": [],
        "warnings": [],
    }
    trackers._state["cached"] = trackers._cached
    snapshot = trackers.get_snapshot(mode="flights", allow_refresh=False)
    point = snapshot["points"][0]
    assert point["operator"] == "unknown"
    assert point["flight_number"] == "unknown"
    assert point["tail_number"] == "unknown"
    assert point["callsign"] == "unknown"
    assert point["icao24"] == "unknown"


def test_fetch_flights_uses_opensky_when_no_feed(monkeypatch):
    monkeypatch.delenv("FLIGHT_DATA_URL", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("LOTBOOK_INCLUDE_COMMERCIAL", "1")
    TrackerProviders._OPENSKY_LAST_REQUEST = 0.0
    TrackerProviders._OPENSKY_BACKOFF_UNTIL = 0.0

    class OpenSkyResponse:
        status_code = 200

        def json(self):
            return {
                "states": [
                    [
                        "abc123",
                        "AAL123",
                        "United States",
                        1700000000,
                        1700000001,
                        -84.43,
                        33.63,
                        10000.0,
                        False,
                        200.0,
                        90.0,
                        0.0,
                        None,
                        11000.0,
                        "1200",
                        False,
                        0,
                    ]
                ]
            }

    with mock.patch("modules.market_data.trackers.requests.get", return_value=OpenSkyResponse()):
        points, warnings = TrackerProviders.fetch_flights()
    assert points
    assert warnings == []


def test_opensky_oauth_uses_bearer_token(monkeypatch):
    monkeypatch.delenv("FLIGHT_DATA_URL", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("LOTBOOK_INCLUDE_COMMERCIAL", "1")
    monkeypatch.setenv("OPENSKY_CLIENT_ID", "client")
    monkeypatch.setenv("OPENSKY_CLIENT_SECRET", "secret")
    TrackerProviders._OPENSKY_LAST_REQUEST = 0.0
    TrackerProviders._OPENSKY_BACKOFF_UNTIL = 0.0
    TrackerProviders._OPENSKY_TOKEN = None
    TrackerProviders._OPENSKY_TOKEN_EXPIRES = 0.0

    class TokenResponse:
        status_code = 200

        def json(self):
            return {"access_token": "token", "expires_in": 1800}

    class OpenSkyResponse:
        status_code = 200

        def json(self):
            return {
                "states": [
                    [
                        "abc123",
                        "AAL123",
                        "United States",
                        1700000000,
                        1700000001,
                        -84.43,
                        33.63,
                        10000.0,
                        False,
                        200.0,
                        90.0,
                        0.0,
                        None,
                        11000.0,
                        "1200",
                        False,
                        0,
                    ]
                ]
            }

    def fake_post(url, data=None, headers=None, timeout=8, proxies=None):
        return TokenResponse()

    def fake_get(url, timeout=8, auth=None, headers=None, params=None, proxies=None):
        assert headers
        assert headers.get("Authorization") == "Bearer token"
        return OpenSkyResponse()

    with mock.patch("modules.market_data.trackers.requests.post", side_effect=fake_post) as mocked_post:
        with mock.patch("modules.market_data.trackers.requests.get", side_effect=fake_get):
            points, warnings = TrackerProviders.fetch_flights()
    assert points
    assert warnings == []
    mocked_post.assert_called_once()


def test_opensky_throttle_respects_min_refresh(monkeypatch):
    monkeypatch.delenv("FLIGHT_DATA_URL", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("OPENSKY_MIN_REFRESH", "120")
    TrackerProviders._OPENSKY_LAST_REQUEST = time.time()
    TrackerProviders._OPENSKY_BACKOFF_UNTIL = 0.0
    with mock.patch("modules.market_data.trackers.requests.get") as mocked_get:
        points, warnings = TrackerProviders.fetch_flights()
    assert points == []
    assert any("OpenSky refresh throttled" in warning for warning in warnings)
    mocked_get.assert_not_called()


def test_opensky_backoff_on_429(monkeypatch):
    monkeypatch.delenv("FLIGHT_DATA_URL", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.delenv("OPENSKY_MIN_REFRESH", raising=False)
    TrackerProviders._OPENSKY_BACKOFF_UNTIL = 0.0
    TrackerProviders._OPENSKY_LAST_REQUEST = 0.0

    class RateLimitResponse:
        status_code = 429
        headers = {"Retry-After": "120"}

        def json(self):
            return {}

    with mock.patch("modules.market_data.trackers.requests.get", return_value=RateLimitResponse()):
        points, warnings = TrackerProviders.fetch_flights()
    assert points == []
    assert any("OpenSky HTTP 429" in warning for warning in warnings)
    assert TrackerProviders._OPENSKY_BACKOFF_UNTIL > time.time()


def test_opensky_min_refresh_invalid_value(monkeypatch):
    monkeypatch.delenv("FLIGHT_DATA_URL", raising=False)
    monkeypatch.delenv("FLIGHT_DATA_PATH", raising=False)
    monkeypatch.setenv("OPENSKY_MIN_REFRESH", "not-a-number")
    monkeypatch.setenv("LOTBOOK_INCLUDE_COMMERCIAL", "1")
    TrackerProviders._OPENSKY_BACKOFF_UNTIL = 0.0
    TrackerProviders._OPENSKY_LAST_REQUEST = 0.0

    class OpenSkyResponse:
        status_code = 200

        def json(self):
            return {
                "states": [
                    [
                        "abc123",
                        "AAL123",
                        "United States",
                        1700000000,
                        1700000001,
                        -84.43,
                        33.63,
                        10000.0,
                        False,
                        200.0,
                        90.0,
                        0.0,
                        None,
                        11000.0,
                        "1200",
                        False,
                        0,
                    ]
                ]
            }

    with mock.patch(
        "modules.market_data.trackers.requests.get",
        return_value=OpenSkyResponse(),
    ) as mocked_get:
        points, warnings = TrackerProviders.fetch_flights()
    assert points
    assert any("min refresh" in warning.lower() for warning in warnings)
    mocked_get.assert_called_once()
