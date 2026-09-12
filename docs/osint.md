# World + Trackers

## Overview
The user-facing workspace is labeled **World**. It groups trackers, regional
signals, and news into a single surface while keeping `/osint` as the technical
deep-link route.

Advisory/client management is the landing workspace. Open the fused globe
explicitly with **Workspace > Open World**, or use `/osint` for the detailed
OSINT panels. World does not open automatically on the advisory dashboard.
The map modernization direction and source gates are documented in
`world_map_reference_plan.md`.

The tracker module provides live aviation and maritime activity, but remains
opt-in for reports and should only surface when it matches account relevance
tags.

## Tracker Data Sources
- **OpenSky** (default fallback): used when no custom flight feed is configured.
- **Flight feeds**: use `FLIGHT_DATA_URL` or `FLIGHT_DATA_PATH` to point at JSON
  payloads (list or `{ "data": [] }`).
- **Shipping feeds**: set `SHIPPING_DATA_URL` to enable vessel tracking.

## Relevance Tags
Tracker notes render in reports only when account tags map to relevance rules
and cached tracker data exists. Supported tags:

- `shipping`, `logistics`, `freight`, `cargo`
- `aviation`, `airline`
- `defense`, `military`
- `energy`, `tanker`, `ports`

Add these tags on accounts to opt in to tracker relevance.

## Environment Variables
- `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET`: OAuth credentials for OpenSky.
- `OPENSKY_USERNAME` / `OPENSKY_PASSWORD`: legacy OpenSky basic auth.
- `OPENSKY_BBOX`, `OPENSKY_EXTENDED`, `OPENSKY_ICAO24`, `OPENSKY_TIME`: optional
  OpenSky query controls.
- `FLIGHT_DATA_URL`, `FLIGHT_DATA_PATH`: custom flight data sources.
- `SHIPPING_DATA_URL`: custom shipping feed.
- `LOTBOOK_INCLUDE_COMMERCIAL`: set to `1` to include commercial flights.
- `LOTBOOK_INCLUDE_PRIVATE`: set to `1` to include private flights.

## Report Integration
The weekly brief only includes aviation/maritime notes when:
1) Account tags match tracker relevance rules, and
2) Cached tracker data exists for those rules.

This keeps World/OSINT content out of unrelated portfolio reporting.
