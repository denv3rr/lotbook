# Geospatial Source Audit

Status: March 18, 2026. This audit defines the reviewed source track that must
be followed before country fills, wildfire/disaster polygons, or other
non-centroid globe overlays expand further.

This document works with:

- [docs/us_gov_standards.md](us_gov_standards.md)
- [docs/standards_remediation_plan.md](standards_remediation_plan.md)
- [docs/visual_modernization_plan.md](visual_modernization_plan.md)

## Decision Summary

Approved direction:

- Keep the current Natural Earth physical land/coast context for the immersive
  base globe.
- Use Natural Earth admin boundaries only for reviewed country/background
  overlays, with explicit worldview/disputed-boundary caveats.
- Use official NIFC wildfire perimeter services for U.S. fire polygons.
- Use NASA FIRMS for fire detections and heat/activity points, not perimeter
  polygons.
- Use NOAA/NWS alerts for U.S. alert polygons and zone-aware severe-weather
  overlays.
- Keep GDELT GEO 2.0 as an approximate text-geography layer only, never as a
  precise incident polygon source.

Not approved:

- presenting GDELT article geography as ground-truth conflict polygons
- presenting FIRMS detections as wildfire perimeters
- presenting Natural Earth boundaries as de jure legal truth without worldview
  or disputed-boundary caveats
- inventing polygons or buffered extents for food, water, strike, or attack
  events when the upstream source is only text mentions

## Reviewed Sources

### 1. Global Base Geography And Country Fills

Primary source:

- Natural Earth admin 0 countries:
  https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/
- Natural Earth admin 0 boundary lines:
  https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-boundary-lines/

What the source says:

- Natural Earth says its countries and boundary lines are de facto by default,
  not de jure.
- It also notes that disputed areas and worldview variants may need separate
  treatment.

Approved use in Lotbook:

- base country outlines
- background country fills
- low-resolution country-level choropleths with explicit provenance

Current status:

- The immersive globe base context now includes reviewed 110m admin-0 country
  geometry from Natural Earth, rendered as de facto country-border context on
  top of the existing land/coast texture.
- This pass does not yet ship separate boundary-line assets or worldview
  variants; those remain future refinements if presentation requirements demand
  them.

Not approved:

- legal/sovereignty claims
- client-facing disputed-border visuals without an explicit worldview policy

Repo integration targets:

- [natural-earth-110m.json](/C:/Users/denve/code/clear/web/public/globe-data/natural-earth-110m.json)
- [natural-earth-110m-source.json](/C:/Users/denve/code/clear/web/public/globe-data/natural-earth-110m-source.json)
- [build_natural_earth_globe_context.py](/C:/Users/denve/code/clear/scripts/build_natural_earth_globe_context.py)
- [globeGeography.ts](/C:/Users/denve/code/clear/web/src/lib/globeGeography.ts)
- future reviewed country-polygon asset under `web/public/globe-data/`

### 2. U.S. Wildfire Perimeters

Primary official trail:

- USGS wildfire perimeter FAQ:
  https://www.usgs.gov/faqs/where-can-i-find-wildfire-perimeter-data
- NIFC information technology page:
  https://www.nifc.gov/programs/information-technology

What the sources say:

- USGS says GeoMAC was retired and wildfire perimeter responsibility moved to
  NIFC Open Data.
- NIFC says Wildland Fire Open Data is the public fire perimeter source and the
  go-to source for perimeter maps.

Approved use in Lotbook:

- reviewed U.S. wildfire perimeter polygons
- perimeter timeline playback when source timestamps are preserved

Not approved:

- implying global wildfire-perimeter coverage from NIFC alone
- mixing NIFC U.S. perimeter truth with non-U.S. inferred fire extents without
  visibly different semantics

Repo integration targets:

- future perimeter adapter in `modules/market_data`
- [scene_payloads.py](/C:/Users/denve/code/clear/modules/market_data/scene_payloads.py)
- [scene.py](/C:/Users/denve/code/clear/web_api/routes/scene.py)
- reviewed polygon asset/cache manifest under `data/` or `web/public/` only if
  provenance and licensing are recorded

### 3. Fire Detections And Heat Activity

Primary official source:

- NASA FIRMS Area API:
  https://firms.modaps.eosdis.nasa.gov/api/area/

What the source says:

- FIRMS supports area queries and requires a MAP_KEY.
- RT and URT detections are removed when corresponding NRT detections are
  processed or after aging out.

Approved use in Lotbook:

- point detections
- heat/activity overlays
- near-real-time fire pulse layers

Not approved:

- treating FIRMS points as a perimeter polygon
- assuming RT/URT persistence

Repo integration targets:

- future fire-detection adapter in `modules/market_data`
- point/pulse layers in [scene_payloads.py](/C:/Users/denve/code/clear/modules/market_data/scene_payloads.py)
- legend/provenance controls in [GlobeOverlay.tsx](/C:/Users/denve/code/clear/web/src/components/scene/GlobeOverlay.tsx)

### 4. U.S. Severe Weather And Public Alert Polygons

Primary official sources:

- NOAA/NWS Alerts Web Service:
  https://www.weather.gov/documentation/services-web-alerts
- FEMA CAP background:
  https://www.fema.gov/emergency-managers/practitioners/integrated-public-alert-warning-system/technology-developers/common-alerting-protocol
- FEMA IPAWS All-Hazards feed:
  https://www.fema.gov/emergency-managers/practitioners/integrated-public-alert-warning-system/technology-developers/all-hazards-information-feed

What the sources say:

- NWS provides CAP/JSON-LD alert APIs and recommends respectful polling/rate
  behavior.
- NWS notes many alerts are forecast-zone based and points to official
  shapefiles for those zones.
- FEMA IPAWS is the broader U.S. all-hazards CAP distribution path, but feed
  access requires an MOA/onboarding path.

Approved use in Lotbook:

- U.S. alert polygons and zone-based overlays
- U.S. weather/disaster public warning layers

Not approved:

- claiming global alert-polygon coverage from NWS/IPAWS
- using IPAWS without completing the official access path

Repo integration targets:

- future U.S. alert adapter in `modules/market_data`
- polygon/area scene layers in [scene_payloads.py](/C:/Users/denve/code/clear/modules/market_data/scene_payloads.py)
- non-canvas filter controls in [GlobeOverlay.tsx](/C:/Users/denve/code/clear/web/src/components/scene/GlobeOverlay.tsx)

### 5. Conflict, Attack, Strike, Shortage, And Other Text-Driven Event Geography

Current reviewed contextual source:

- GDELT GEO 2.0 API:
  https://blog.gdeltproject.org/gdelt-geo-2-0-api-debuts/

What the source says:

- GDELT GEO 2.0 maps locations mentioned near a query and can output point,
  country, and ADM1-level geographic results.
- GDELT explicitly warns that large-scale automated georeferencing will always
  contain errors.

Approved use in Lotbook:

- contextual news geography
- supporting heat/cell/regional overlays
- corroborative signal for where coverage is concentrating

Not approved:

- precise incident polygons
- exact strike/attack footprints
- legal or operational ground truth

Repo integration targets:

- continue as supporting context in [intel.py](/C:/Users/denve/code/clear/modules/market_data/intel.py)
- continue as region/cell overlays in [scene_payloads.py](/C:/Users/denve/code/clear/modules/market_data/scene_payloads.py)

## Integration Order

1. Add reviewed country/background polygons from Natural Earth with explicit
   worldview caveats.
2. Add official U.S. wildfire perimeters from NIFC Open Data.
3. Add FIRMS fire detections as separate point/pulse overlays.
4. Add U.S. NWS alert polygons where official zones/polygons exist.
5. Keep non-U.S. conflict/disaster/scarcity overlays region- or cell-based
   until a reviewed structured geometry source is chosen.

## Repo Gates Before Polygon Work

- Every new geometry source must record source URL, capture method, timestamp,
  license/access terms, and display caveats.
- Every polygon-style layer must say whether it is:
  - source polygon truth
  - official zone polygon
  - reviewed country/admin boundary
  - inferred aggregate area
- If the source is inferred or text-derived, the UI must not render it with the
  same visual semantics as an official perimeter.
- Positive-path visual tests for new polygon layers must use captured real
  fixtures with provenance.

## Current Honest Gap

Lotbook does not yet have a reviewed structured global source for precise
conflict polygons, strike footprints, food-shortage extents, or water-shortage
areas. Until that changes, those overlays should remain regional, cell-based,
or explicitly inferred.
