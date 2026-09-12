# Feed Registry

This document describes the feed registry, source-onboarding rules, and health
signals used across CLI, API, and web UI.

It is intentionally broader than the currently implemented sources so the next
OSINT/globe phase can onboard reviewed public feeds without inventing a new
registry model later.

## Registry Principles

- Every source must have a stable source ID, category, provenance note, and
  health signal.
- Every source must document whether it provides raw observations, structured
  events, curated incidents, text mentions, polygons, points, or derived
  aggregates.
- Every source must document auth or access prerequisites before
  implementation.
- Every source must document geometry truth level so the globe does not render
  detections, mentions, and polygons as if they meant the same thing.

## Current Implemented Sources

- Market data: Finnhub, Yahoo Finance
- Trackers: OpenSky, flight URLs/files, shipping feeds
- Intel: Open-Meteo, GDELT
- News: RSS collectors

### World basemap context (not an incident feed)

`nasa-gibs-blue-marble` is the historical NASA Blue Marble shaded relief and
bathymetry composite, served directly as EPSG:3857 raster tiles through GIBS.
It is non-temporal, keyless background context with native maximum zoom 8 and
approximately +/-85.05-degree latitude coverage, not current ground conditions.

`esri-world-imagery` is the keyless ArcGIS Online World Imagery mosaic used
through zoom 19. `osm-raster` is an operator-selected street map, not an
automatic fallback. Neither is a live feed. Attribution is required. World
shows incomplete-imagery failures and retains reviewed Natural Earth context.
Terms, geometry, network and evidence details are in
[the World implementation record](world_map_reference_plan.md).
This does not advance or reorder the unimplemented hazard-source priorities.

## Reviewed Priority Sources Not Yet Implemented

| Source | Type | Value To Lotbook | Notes |
| --- | --- | --- | --- |
| ReliefWeb API | Structured humanitarian/disaster reports | Better coverage of shortages, displacement, crisis operations, and field reporting | Requires approved `appname` as of November 1, 2025. |
| NASA EONET v3 | Curated natural event metadata | Gives event IDs plus point/polygon GeoJSON and source/category filters | Good bridge between narrative intel and reviewed natural-event objects. |
| NASA FIRMS Area API | Fire detections | Useful for global fire hotspot overlays | Requires `MAP_KEY`; detections are not perimeter truth. |
| NWS Alerts Web Service | CAP/JSON-LD/ATOM alerts | Strong U.S. weather and hazard alert coverage with zone context | Recommended refresh no more than every 30 seconds. |
| USGS GeoJSON feeds | Structured hazard events | Fast earthquake and related hazard points | GeoJSON `FeatureCollection`, updated every minute for key feeds. |

## Reviewed Candidate Sources For Later Conflict Depth

These sources are not part of the current source-onboarding order and must not
be implemented ahead of ReliefWeb/EONET/FIRMS/NWS/USGS without updating
`docs/osint_globe_phase_2_plan.md`.

| Source | Type | Value To Lotbook | Notes |
| --- | --- | --- | --- |
| ACLED API | Structured political violence, demonstration, and strategic-development events | Better event-level conflict coverage for Myanmar, Ukraine, Sahel, Middle East, and other active theaters than article mentions alone | Requires myACLED account plus OAuth for programmatic access; preserve event date, event type, actors, admin fields, fatalities, source, and `geo_precision`. |

## Health Status

- `ok`: last fetch successful and freshness within source policy
- `degraded`: failures observed or source data missing key fields
- `backoff`: temporary cooldown after repeated failures
- `stale`: last known good data exists but freshness is outside policy
- `unavailable`: source is configured but unusable due to auth, quota, or
  upstream failure
- `unknown`: no recent health signal

## Source Onboarding Requirements

Before any new source moves from reviewed to implemented:

1. Document access requirements, licensing, app name, API key, or rate limit.
2. Define the normalization contract and required provenance fields.
3. Define geometry truth level:
   - text mention
   - sampled coordinate
   - detection point
   - reviewed point event
   - polygon
   - derived aggregation
4. Define freshness expectations and failure behavior.
5. Add diagnostics visibility and tests.

## Registry Output

- `sources`: array of sources with `id`, `label`, `category`, `configured`,
  `implemented`, `notes`, and optional `health/status`.
- `summary`: total/configured counts, per-category counts, `health_counts`, and
  warnings.
- `lineage`: optional execution metadata for source refreshes, retries, and
  degraded reads.

## Usage

- API diagnostics includes registry + summary in `feeds`.
- CLI diagnostics displays summary counts and warnings.
- Web System page shows registry counts and issues.
- The next OSINT/globe phase should also use the registry to decide which globe
  layers can render truthfully in the current environment.

## Public References For Next Source Intake

- ReliefWeb API docs: https://apidoc.reliefweb.int/parameters
- NASA EONET docs: https://eonet.gsfc.nasa.gov/docs/v3
- NASA FIRMS Area API: https://firms.modaps.eosdis.nasa.gov/api/area/
- NWS alerts docs: https://www.weather.gov/documentation/services-web-alerts
- USGS GeoJSON feeds: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- ACLED API docs: https://acleddata.com/api-documentation/getting-started
