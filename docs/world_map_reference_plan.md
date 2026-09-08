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

This checkpoint records the design direction and source constraints; the new
tiled globe and precise AOI workflows are not implemented in the advisory pass.
