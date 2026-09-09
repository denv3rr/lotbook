# World map reference and implementation gates

Research checkpoint: September 8, 2026. World remains a secondary Workspace
action; advisory and client management stay the landing workflow.

## Reference reviewed

[God's Eye View](https://github.com/bilawalsidhu/gods-eye-view) is the requested
reference. Its [current README](https://raw.githubusercontent.com/bilawalsidhu/gods-eye-view/main/README.md)
describes navigable imagery/terrain, modular layers, selectable tracked objects
with metadata and trails, and shareable camera/layer state. It also explicitly
identifies simulated traffic and estimated camera poses/launch trajectories.
Those are not evidence suitable for Clear's operational layers.

The useful direction is geographic navigation and source-backed map context,
not its tactical styling. Its keyless setup and optional photorealistic 3D
have distinct provider terms. Personal/non-commercial offers must not be
assumed eligible for an advisory firm's deployment. No source code, dependency,
imagery subscription, API key or billable service was added by this research.

## Next bounded implementation

1. Compare the existing MapLibre surface with a globe-capable tiled-map engine
   such as Cesium, using the same canonical scene contracts. Record projection,
   terrain/imagery attribution, commercial rights, credential restrictions,
   network/cache behavior and offline failure states before selecting providers.
   Optional [Google 3D Tiles](https://developers.google.com/maps/documentation/tile/3d-tiles)
   require their own provider and deployment review; code licensing is not a
   license to redistribute map content.
2. Implement a navigable basemap with geographic search, fit/reset, scale and
   coordinates, accessible layer controls and a source/freshness inspector.
   Persist camera/layers without putting client identifiers or private notes
   into publicly shareable URLs. Lazy-load World and retain a usable fallback.
3. Add saved areas of interest with explicit geometry type and basis:
   operator-drawn research boundaries are not observed event extents; reviewed
   source polygons retain their original provenance, dates and precision.
   Existing regional centroids must remain labeled approximate. A more detailed
   basemap does not make the underlying signal location more accurate.

## Acceptance and sequencing

- Preserve the source order and incident-resolution prerequisites in
  `osint_globe_phase_2_plan.md`; this reference does not onboard additional feeds.
- Apply `standards_remediation_plan.md` and `feed_registry.md` before new dense
  overlays or presentation baselines. Provider review must include actual terms,
  not just an upstream project's description of them.
- Verify coordinate/projection and antimeridian behavior, source attribution,
  unavailable/offline states, saved-view fidelity, keyboard operation, reduced
  motion, mobile layout, memory/frame and initial-bundle budgets.
- Use reviewed real-source artifacts for loaded-state evidence. Do not import
  simulated movements, guessed incident polygons or synthetic market data.

## September 9 implementation

World now uses the existing MapLibre integration, upgraded to 6.8.0, with globe
and Mercator projections. The retired Three renderer and its unused packages
are removed. The same scene contracts, source inspector, Browse list, layer
filters and approximate regional signals remain. This is geographic context,
not an implementation of the reference project's simulations or 3D buildings.

The basemap is NASA GIBS `BlueMarble_ShadedRelief_Bathymetry`, a non-temporal
historical composite, **not live satellite imagery**. The actual
[WMTS capabilities](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml)
were checked: EPSG:3857, JPEG, 256-pixel tiles, GoogleMapsCompatible_Level8,
native maximum zoom 8, latitude coverage +/-85.051129 degrees. Higher camera
zoom only enlarges existing imagery; it does not provide street-level detail.
No terrain elevations, precise incident polygons or new hazard feeds were added.

NASA requests are direct from the browser, keyless, without Clear client IDs,
notes or API keys. Viewport tile coordinates and the browser's IP reach NASA.
Only the NASA GIBS host was added to CSP. No bulk tile download or offline tile
cache is implemented. Availability is external; failures show incomplete
imagery and retain local reviewed Natural Earth land/borders and the Browse list.
WebGL 2 is required for World; unsupported devices retain non-canvas browsing.
Natural Earth borders remain de facto context, not a legal boundary authority.

Visible attribution acknowledges NASA EOSDIS GIBS and Natural Earth. The
[NASA data-use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy)
was reviewed for this NASA informational layer: acknowledge the source, do not
imply endorsement, and do not infer rights to unrelated third-party content.
No paid provider or account was connected. Deployment-specific licensing review
is still required if providers, caching, resale or imagery layers change.

Country search fits the reviewed country geometry (including overseas parts),
not a guessed national center. Scale, center coordinates and native navigation
controls are available. Research areas are named viewport rectangles stored in
this browser, limited to 20, removable, and explicitly operator-defined. They are
not observed event extents. Antimeridian areas split into two polygons; invalid
stored data is not overwritten. Browser storage is not shared, centrally backed
up or an encrypted place for confidential notes. Camera/layer sharing and drawn
polygons remain future work.

MapLibre's [v6 migration guide](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/)
and [Vite installation](https://maplibre.org/maplibre-gl-js/docs/)
informed the ESM loader and bundled same-origin worker. Tracker integration uses
the same loader; Leaflet remains its fallback. Surface charts use the map-free
Plotly GL3D 3.3.1 distribution. The unused Plotly source-package map dependency
is overridden to the same patched MapLibre version; this does not claim support
for Plotly map charts. The resolved npm tree reports no known vulnerabilities
at this checkpoint, not a security certification.

Evidence: isolated launcher browser tests received actual NASA tile responses,
used the existing captured intel fixture with provenance, navigated country /
projection / zoom controls and saved operator bounds. Geometry assertions are
unit evidence only. No new presentation baseline was created. Provider outage,
hardware, accessibility conformance and production load remain separate gates.
