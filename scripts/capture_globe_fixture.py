from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_api import app as web_app  # noqa: E402


FIXTURE_VERSION = 1
SCENE_CAPTURE_CONFIG = {
    "intel": {
        "fixture_id": "intel-globe-loaded",
        "output": ROOT / "web" / "tests" / "fixtures" / "intel-globe.fixture.json",
        "scene_route": "/api/osint/scene/intel?industry=all",
        "extra_routes": {
            "intel_meta_payload": "/api/intel/meta",
        },
        "news_cache": ROOT / "data" / "intel_news.json",
        "review_notes": [
            "Derived from the real local FastAPI scene contract, not hand-authored test JSON.",
            "Scene content reflects capture-time source availability, warnings, and freshness semantics.",
            "Conflict overlays remain centroid highlights rather than incident polygons or country fills.",
        ],
    },
    "tracker": {
        "fixture_id": "tracker-globe-loaded",
        "output": ROOT / "web" / "tests" / "fixtures" / "tracker-globe.fixture.json",
        "scene_route": "/api/osint/scene/trackers?mode=combined",
        "extra_routes": {
            "tracker_snapshot_payload": "/api/trackers/snapshot?mode=combined",
        },
        "review_notes": [
            "Capture requires a real loaded tracker scene with at least one point feature and one focus target.",
            "Do not capture from fallback, empty, or degraded-only tracker routes.",
            "Tracker positions and trails remain capture-time artifacts and must preserve real source warnings and freshness.",
        ],
        "validator": "tracker_loaded",
    },
}


def _load_root_env_value(*names: str) -> str:
    for name in names:
        from_process = os.getenv(name)
        if from_process:
            return from_process
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    parsed: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, value = trimmed.split("=", 1)
        parsed[key.strip()] = value.strip().strip("'\"")
    for name in names:
        if parsed.get(name):
            return parsed[name]
    return ""


def _to_utc_iso(ts: int | float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _hash_payload(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _load_news_cache_summary(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path.relative_to(ROOT)),
            "exists": False,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    unique_sources = sorted(
        {
            str(item.get("source")).strip()
            for item in items
            if isinstance(item, dict) and str(item.get("source", "")).strip()
        }
    )
    latest_published = max(
        (
            int(item.get("published_ts"))
            for item in items
            if isinstance(item, dict) and isinstance(item.get("published_ts"), int)
        ),
        default=None,
    )
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "cache_ts": payload.get("ts") if isinstance(payload, dict) else None,
        "cache_ts_utc": _to_utc_iso(payload.get("ts") if isinstance(payload, dict) else None),
        "file_mtime_utc": _to_utc_iso(path.stat().st_mtime),
        "item_count": len(items),
        "latest_published_ts": latest_published,
        "latest_published_utc": _to_utc_iso(latest_published),
        "sources": unique_sources,
    }


def _load_tracker_input_summary() -> Dict[str, Any]:
    return {
        "flight_data_path_configured": bool(_load_root_env_value("FLIGHT_DATA_PATH")),
        "flight_data_url_configured": bool(_load_root_env_value("FLIGHT_DATA_URL")),
        "shipping_data_url_configured": bool(_load_root_env_value("SHIPPING_DATA_URL")),
        "opensky_oauth_configured": bool(
            _load_root_env_value("OPENSKY_CLIENT_ID") and _load_root_env_value("OPENSKY_CLIENT_SECRET")
        ),
    }


def _headers() -> Dict[str, str]:
    api_key = _load_root_env_value("LOTBOOK_WEB_API_KEY", "CLEAR_WEB_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def _capture_json(client: TestClient, route: str, headers: Dict[str, str]) -> Dict[str, Any]:
    response = client.get(route, headers=headers)
    response.raise_for_status()
    return response.json()


def validate_tracker_scene_capture(payloads: Dict[str, Dict[str, Any]]) -> None:
    scene_payload = payloads.get("scene_payload", {})
    layers = scene_payload.get("layers", []) if isinstance(scene_payload, dict) else []
    point_layer = next(
        (
            layer
            for layer in layers
            if isinstance(layer, dict) and str(layer.get("kind")) == "point"
        ),
        None,
    )
    point_count = len(point_layer.get("features", [])) if isinstance(point_layer, dict) else 0
    focus_count = len(scene_payload.get("focus_targets", []) or []) if isinstance(scene_payload, dict) else 0
    if point_count > 0 and focus_count > 0:
        return
    warnings = []
    if isinstance(scene_payload, dict):
        warnings = list(scene_payload.get("meta", {}).get("warnings", []) or [])
    warning_preview = "; ".join(str(item) for item in warnings[:4]) or "no warnings provided"
    raise RuntimeError(
        "Tracker fixture capture failed closed: the current environment returned no loaded tracker scene. "
        "Configure a real tracker feed or reviewed local feed file, then retry. "
        f"Observed point_count={point_count}, focus_count={focus_count}. Warnings: {warning_preview}"
    )


def _validate_capture(scene: str, payloads: Dict[str, Dict[str, Any]]) -> None:
    validator = SCENE_CAPTURE_CONFIG[scene].get("validator")
    if validator == "tracker_loaded":
        validate_tracker_scene_capture(payloads)


def capture_fixture(scene: str, output_path: Path | None = None) -> Path:
    config = SCENE_CAPTURE_CONFIG[scene]
    destination = output_path or Path(config["output"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = _headers()

    with TestClient(web_app.app) as client:
        payloads: Dict[str, Dict[str, Any]] = {
            "scene_payload": _capture_json(client, str(config["scene_route"]), headers)
        }
        for payload_key, route in dict(config.get("extra_routes", {})).items():
            payloads[payload_key] = _capture_json(client, str(route), headers)

    _validate_capture(scene, payloads)
    scene_payload = payloads["scene_payload"]

    envelope = {
        "fixture_version": FIXTURE_VERSION,
        "fixture_id": config["fixture_id"],
        "captured_at_utc": captured_at,
        "capture_method": {
            "type": "fastapi-testclient",
            "app_module": "web_api.app:app",
            "scene_route": config["scene_route"],
            "extra_routes": dict(config.get("extra_routes", {})),
            "api_key_required": bool(headers),
        },
        "provenance": {
            "configured_inputs": _load_tracker_input_summary(),
            "scene_response_meta": scene_payload.get("meta", {}) if isinstance(scene_payload, dict) else {},
        },
        "review_notes": list(config["review_notes"]),
        "scene_payload_sha256": _hash_payload(scene_payload),
        "scene_payload": scene_payload,
    }
    if "news_cache" in config:
        envelope["provenance"]["news_cache"] = _load_news_cache_summary(Path(config["news_cache"]))
    for payload_key, payload in payloads.items():
        if payload_key == "scene_payload":
            continue
        envelope[f"{payload_key}_sha256"] = _hash_payload(payload)
        envelope[payload_key] = payload
        envelope["provenance"][f"{payload_key}_meta"] = (
            payload.get("meta", {}) if isinstance(payload, dict) else {}
        )

    destination.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a provenance-backed globe test fixture from the real FastAPI app."
    )
    parser.add_argument(
        "--scene",
        choices=sorted(SCENE_CAPTURE_CONFIG.keys()),
        default="intel",
        help="Scene fixture to capture.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Defaults to the reviewed test-fixture location.",
    )
    args = parser.parse_args()
    try:
        output_path = capture_fixture(scene=args.scene, output_path=args.output)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Captured {args.scene} globe fixture -> {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
