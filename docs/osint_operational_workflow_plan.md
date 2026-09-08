# OSINT Operational Workflow Plan

September 2026: OSINT supports the primary advisory/client-management
workbench. World is available from Workspace > Open World; it does not launch
on the application landing page. Existing source/provenance gates remain.

Status: Active on March 18, 2026. This plan extends
`docs/visual_modernization_plan.md` and is gated by
`docs/us_gov_standards.md` plus `docs/standards_remediation_plan.md`.

## Purpose

Turn the globe, intel, tracker, and related report pipelines into one operational workflow instead of separate read-only screens.

This plan is "Palantir-inspired" only in the public, architectural sense:

- canonical object and action models
- closed-loop operational writeback
- workflow lineage, observability, and permissions
- workspace-oriented execution instead of dashboard sprawl

This is an inference from Palantir's public docs, not a claim that Clear should copy proprietary internals.

## What Landed In The Current Pass

- Added a fused overview scene at `/api/osint/scene/overview` so trackers and regional intel can coexist on the same globe contract.
- Added a scene switcher in the globe overlay so operators can move between `World`, `Trackers`, and `Signals` without leaving the immersive surface.
- Made the Overview page launch the fused `World` globe by default so the product opens on the operational canvas instead of a tracker-only subview.
- Added first-class layer visibility controls for tracker points, tracker trails, regional signals, and conflict pulses, with persisted operator state and a reset path.
- Added a toggleable right-side detail stack and reduced panel/tooltip opacity so the globe can stay presentation-first when needed.
- Moved the primary OSINT workspace into the Overview page below the existing
  overview panels, with the workspace visible by default so operators can keep
  the globe and client/account context together while still expanding trackers,
  signals, and news in place.
- Added client/account summary context into the World globe HUD and promoted
  source-backed conflict signals in sorting, red accent styling, and raised
  peaks without hardcoding any region as active conflict.
- Enabled the fused overview globe from the Overview route and simplified the
  top navigation so OSINT is no longer a permanent top-level menu item; the
  `/osint` route remains available as a deep link.
- Added payload-derived signal-density strips, selected-feature provenance
  rows, expandable warnings, and safer centroid-highlight terminology in the
  globe overlay.
- Corrected theater matching to use word boundaries, isolated conflict pulse
  placement/headlines to conflict evidence, and made pulse highlights directly
  selectable through the globe and keyboard-accessible Browse list.
- Fixed collector-boundary duplicate news handling by deduping across feed/source overlaps using canonical URL first and content fallback second, while preserving a `sources` list for provenance.
- Fixed client/account write-path duplicate drift by adding normalized client/account keys, store-level duplicate rejection, API `409` responses, and stronger duplicate tests.
- Expanded diagnostics to surface duplicate client names and duplicate raw news cache entries, and routed report/news reads through the same deduped cache loader.
- Added schema support for normalized client/account key columns plus indexes to support future cleanup and stricter enforcement.

## Public Architecture Mapping

Primary public references:

- Palantir AIP architecture:
  https://www.palantir.com/docs/foundry/architecture-center/aip-architecture
- Palantir Ontology system:
  https://www.palantir.com/docs/foundry/architecture-center/ontology-system/
- Palantir operational applications:
  https://www.palantir.com/docs/foundry/app-building/operational-apps/
- Palantir AIP observability:
  https://www.palantir.com/docs/foundry/aip/aip-observability
- Palantir AI FDE overview:
  https://www.palantir.com/docs/foundry/ai-fde/overview

Operational mapping for Clear:

1. Ontology-style core
- Clear should treat trackers, articles, incidents, regions, industries, clients, accounts, ports, airports, routes, and alerts as canonical objects with stable IDs and explicit lineage.
- Actions should be first-class too: triage, suppress duplicate, acknowledge alert, export report pack, tag client relevance, save globe preset, and dispatch follow-up workflow.

2. Operational app behavior
- The globe should not be a passive visualization.
- Every major layer should support action: inspect, pivot, filter, attach to a client/account/report, export, save as preset, or hand off to another workspace.
- The app should favor closed-loop workflows where a decision changes system state and that writeback remains auditable.
- Operators must be able to suppress visual domains without changing upstream counts; visibility toggles are presentation state, not data mutation.

3. Workflow lineage and observability
- Every scene load, layer derivation, alert trigger, and export should retain route, sources, timestamps, warnings, filter state, and execution metadata.
- Globe/report/assistant flows should eventually have one shared workflow lineage trail: request -> sources -> transforms -> scene/report/export.

4. Permission-aware AI and workflow tooling
- Assistant behavior should be grounded in the same canonical objects and filters as the globe and reports.
- Suggested actions should be permission-aware and bounded by page/workspace context.
- No assistant summary should bypass deterministic scene/report data or fabricate evidence.

## Canonical Object Model For Clear

Phase target object families:

- `GeoEntity`
  - region, airport, port, corridor, country, facility
- `LiveAsset`
  - aircraft, vessel, cargo flow, convoy, weather node
- `IntelItem`
  - article, event, source item, classified incident, shortage/disaster/strike tag set
- `OperationalImpact`
  - impacted market, industry, route, client exposure, alert severity
- `WorkflowAction`
  - export, acknowledge, assign, suppress duplicate, save preset, attach evidence
- `WorkspaceState`
  - globe preset, filters, time window, focus selection, active report pack

Each object must preserve:

- stable identifier
- source system
- source timestamp
- freshness state
- warnings
- methodology or derivation note when computed

## Specialist Designation

Standards lead
- Re-skims `docs/us_gov_standards.md` and blocks fabricated data, weak math, or fail-open behavior.

Geo scene architect
- Owns `GeoScenePayload`, fused scene composition, globe controls, camera model, and scene-state contracts.

OSINT taxonomy engineer
- Owns event/channel/emotion taxonomy expansion, dedupe rules, relevance filtering, and provenance-backed fixtures for article classification drift.

Geospatial truth engineer
- Owns reviewed source onboarding for polygons, wildfire/disaster geometry, country/worldview context, and display caveats.

Workflow/ontology engineer
- Owns canonical object IDs, state transitions, action contracts, export hooks, and saved workspace/preset flow.

Observability engineer
- Owns execution metadata, timing, trace IDs, lineage payloads, alert telemetry, and budget measurements.

Browser verification engineer
- Owns Playwright smoke/visual coverage, captured real fixtures, reduced-motion baselines, and settled-state visual review.

Accessibility and motion engineer
- Owns keyboard/focus parity, reduced-motion behavior, non-canvas controls, and overlay usability on laptops/presentation screens.

## Current Gaps To Close Before "Full Globe" Claim

1. Geometry truth
- Country boundary context is integrated.
- Conflict overlays are still centroid pulses, not incident or polygon truth.
- Weather is still representative-coordinate sampling, not a gridded global weather field.

2. Canonical event flow
- News dedupe is now fixed at ingestion, but broader event normalization still needs deeper work so one real-world incident can connect article clusters, regional hotspots, impacted markets, and later client exposures.

3. Workflow depth
- The globe can inspect and filter, but saved presets, alert actions, evidence bundles, and report writeback still need full implementation.

4. Client/workspace linkage
- The fused globe does not yet attach incident or route impact directly to client/account exposure views.

## Next Phase Planning Note

The detailed next-phase handoff now lives in
`docs/osint_globe_phase_2_plan.md`.

That document is the current source of truth for:

- reviewed public source onboarding priorities
- canonical incident/exposure/workflow object design
- specialist roles and contract-based branch shapes
- Palantir-inspired modularization ideas grounded in public architecture docs
- the exact sequence for turning the current tracker-plus-regional globe into a
  richer operational surface without inventing geometry or math

Do not start that phase from this file alone. Use this file for the long-range
workflow direction and `docs/osint_globe_phase_2_plan.md` for the next batch's
execution detail.

## Execution Phases

### Phase A: Integrity Foundation

Objective:
- keep counts, categories, and entities trustworthy before adding denser visuals

Tasks:
- keep dedupe at collector/cache boundaries for news and source items
- keep duplicate rejection on client/account write paths
- add canonical IDs for article clusters, regional events, and future incident groups
- extend diagnostics so duplicate drift is visible in System/Diagnostics

Exit:
- counts are no longer inflated by feed overlap or duplicate accounts
- duplicate attempts fail closed with explicit operator feedback

### Phase B: Fused Globe Maturity

Objective:
- make the globe the real operating surface, not just two adjacent scenes

Tasks:
- mature `/api/osint/scene/overview`
- add saved scene presets and camera bookmarks
- keep detail stack toggleable and presentation-safe
- add layer visibility toggles by domain: trackers, regional intel, conflict hotspots, trails

Exit:
- operators can stay inside the overview scene for the primary walkthrough flow

### Phase C: Event And Market Impact Graph

Objective:
- connect article/event classification to concrete downstream market impact

Tasks:
- introduce canonical event clusters
- link events to impact channels, industries, chokepoints, and route disruptions
- show affected-market badges and report methodology directly from those canonical clusters
- separate article count, event count, and impacted-market count everywhere

Exit:
- one incident no longer looks like many incidents just because many articles mention it

### Phase D: Geospatial Truth Upgrade

Objective:
- move from centroid highlight to reviewed geometry where the source supports it

Tasks:
- onboard reviewed polygon/cell sources for wildfire, U.S. alert geometry, and future incident extents
- keep inferred vs direct geometry visually distinct
- add confidence/display-scope labels for every non-point area layer

Exit:
- no polygon/area overlay is shown without reviewed source semantics

### Phase E: Workspace And Action Layer

Objective:
- make the globe operational in the workflow sense

Tasks:
- add save preset, attach evidence, export report pack, and create alert actions
- add workspace-scoped object panels for region, route, asset, and client/account contexts
- add handoff between globe, Intel page, Reports, and client workspaces

Exit:
- users can move from seeing a problem to capturing a decision without leaving the platform

### Phase F: Observability And Lineage

Objective:
- make every critical scene/report/action flow traceable

Tasks:
- add execution IDs and source lineage through scene/report/export contracts
- record key metrics: scene build latency, source freshness, filter state, error rate, bundle/render budgets
- surface workflow lineage in diagnostics

Exit:
- support/debug/performance review can explain any scene or report from request to output

### Phase G: Client Exposure And Report Packs

Objective:
- connect OSINT globe state to client-facing outcomes

Tasks:
- map regions, industries, routes, and event clusters into client/account exposure summaries
- add report packs that preserve globe filters, selected nodes, warnings, and methodology
- add presentation mode presets for client meetings

Exit:
- the globe directly supports client and executive workflows instead of staying an analyst-only surface

## Data And Visual Rules For These Phases

- No scene or chart may count duplicate articles as separate evidence.
- Event counts, article counts, source counts, and impacted-market counts must remain separate metrics.
- Weather, conflict, and emotion overlays must state whether they are direct observation, derived signal, or inferred regional aggregation.
- Any pulsing area effect must declare its geometry truth level in payload metadata and UI copy.
- New visual layers must stay inside measured bundle/render budgets before they become default.

## Immediate Next Build Items

1. Add first-class layer visibility toggles in the globe overview.
2. Add diagnostics/API visibility for duplicate client names and duplicate account identities already present in stored data.
3. Add canonical incident clustering above deduped articles so one incident can drive one hotspot with many supporting articles.
4. Add provenance-backed captured fixtures for overview-scene visuals once the environment has a reviewed non-empty tracker contribution.
5. Add saved globe presets and report-pack export hooks.
6. Keep duplicate diagnostics visible in System/Diagnostics and add client-name remediation planning before any semantic DB uniqueness migration.

## Standards Note

This plan does not authorize shortcuts. Any later phase that needs:

- fabricated geometry
- invented weights
- duplicate-tolerant metrics
- silent merge behavior
- or inaccessible canvas-only controls

must stop and redesign before implementation.
