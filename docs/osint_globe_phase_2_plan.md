# OSINT Globe Phase 2 Plan

Status: Planned on March 18, 2026. This phase is intentionally not started
yet. It is the next execution map once the active gates in
`docs/standards_remediation_plan.md` Phase 1 and Phase 2 are closed or
explicitly waived with evidence.

This document is the detailed handoff plan for the next multi-phase audit,
implementation, and test cycle across the globe UI, OSINT pipeline, and
external-source onboarding. It extends:

- `docs/us_gov_standards.md`
- `docs/standards_remediation_plan.md`
- `docs/visual_modernization_plan.md`
- `docs/osint_operational_workflow_plan.md`
- `docs/feed_registry.md`

## Why This Phase Exists

The immersive globe foundation is real, but the product is not yet at the bar
needed for full operational or client-facing use:

- the fused overview still leans heavily on trackers plus centroid-based
  regional signals
- incident and disaster layers are not yet first-class canonical objects
- weather remains representative-sample context, not a truthful field or alert
  layer
- duplicate and entity-resolution work is improved, but not finished across
  news, incidents, clients, and future workspaces
- the app still lacks the action-oriented, lineage-rich operating model that
  public Palantir architecture materials emphasize

This phase closes those gaps without inventing data, geometry, or math.

## Research Anchors

Public architecture references used for this plan:

- Palantir architecture overview:
  https://www.palantir.com/docs/foundry/architecture-center/overview
- Palantir Ontology system:
  https://www.palantir.com/docs/foundry/architecture-center/ontology-system
- Palantir app-building overview and Ontology SDK:
  https://www.palantir.com/docs/foundry/app-building/overview
- Palantir AIP observability:
  https://www.palantir.com/docs/foundry/aip/aip-observability

Reviewed public data/API references used for source planning:

- ReliefWeb API parameters:
  https://apidoc.reliefweb.int/parameters
- NASA EONET v3 docs:
  https://eonet.gsfc.nasa.gov/docs/v3
- NASA EONET overview:
  https://eonet.gsfc.nasa.gov/
- NASA FIRMS Area API:
  https://firms.modaps.eosdis.nasa.gov/api/area/
- National Weather Service Alerts Web Service:
  https://www.weather.gov/documentation/services-web-alerts
- USGS GeoJSON summary feeds:
  https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- OpenSky API landing page:
  https://opensky-network.org/data/api
- GDELT DOC 2.0 API:
  https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- GDELT GEO 2.0 API:
  https://blog.gdeltproject.org/gdelt-geo-2-0-api-debuts/
- ACLED API getting started:
  https://acleddata.com/api-documentation/getting-started
- WCAG 2.2 use of color:
  https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html

## Phase 2 Goals

1. Complete the data truth layer before adding denser visuals.
2. Promote incidents, alerts, hazards, and exposures to canonical objects
   instead of treating them as secondary article aggregates.
3. Expand the globe from tracker-first to incident-and-impact-first while
   preserving provenance, geometry truth, and freshness.
4. Separate article counts, incident counts, source counts, alert counts, and
   exposure counts everywhere.
5. Add a modular ontology/action/interop shape so future third-party
   integrations do not become one-off adapters.

## Known Issues To Target First

1. The fused globe still mostly reads as flight and cargo tracking because
   trackers are the only globally dense live asset layer today. Regional intel
   signals exist, but they are not yet backed by canonical incident objects.
2. The globe has better geographic context now, but still lacks truthful
   incident/disaster/weather geometry beyond country boundaries and centroid
   hotspot pulses.
3. Weather context is still too coarse for a global operational view. It needs
   alert and event layers, not just representative coordinate sampling.
4. News dedupe is stronger, but event resolution is still too shallow. One
   real-world incident can still inflate downstream interpretation if the
   article cluster is not normalized into one canonical event.
5. Duplicate integrity work has started for clients/accounts, but a deeper root
   cause audit is still required for semantic duplicates, sub-account drift,
   and future workspace/save-preset entities.
6. The current globe detail panel is toggleable, but presentation ergonomics
   still need a compact/floating mode strategy before "full globe" is claimed.

## Public Reference Gap Map

This is where Lotbook still lags public reference patterns or source
capabilities.

### Operational Architecture Gaps

- Palantir's public Ontology docs describe a model centered on data, logic,
  action, and security. Lotbook has the beginnings of data and visualization, but
  not yet a strong action layer or explicit decision graph.
- Palantir's public app-building docs emphasize typed SDK exposure for the
  subset of objects/actions an application needs. Lotbook still needs a cleaner
  object-contract/export boundary for third-party integrations.
- Palantir's public observability docs emphasize workflow lineage, metrics,
  execution history, distributed tracing, logging, and log search. Lotbook has
  `meta` provenance and diagnostics, but not yet a first-class workflow lineage
  model across scene -> report -> export -> action flows.

### Source Coverage Gaps

- ReliefWeb exposes structured humanitarian/disaster content with filters,
  facets, and field selection, but Lotbook does not yet ingest it.
- EONET exposes curated natural events with GeoJSON point/polygon geometry and
  event/source/category filters, but Lotbook does not yet consume it.
- FIRMS exposes near-real-time fire detections over bounding boxes or the whole
  world, but Lotbook does not yet ingest it and must treat detections as
  detections, not perimeters.
- NWS alerts expose CAP/JSON-LD/ATOM, refresh guidance, and zone geometry
  linkage, but Lotbook does not yet consume this as an alert layer.
- USGS GeoJSON feeds expose minute-updating `FeatureCollection` event data, but
  Lotbook does not yet ingest or surface this hazard stream.
- ACLED exposes structured conflict-event fields and OAuth access that make it
  a strong later candidate for global conflict-event coverage where
  article-only sources underrepresent ongoing wars or insurgencies. It is not
  in the current implementation order; add it only through a reviewed source
  contract and preserve event type, actors, administrative geography,
  fatalities, source, and `geo_precision`.

## Source Onboarding Priorities

| Source | Current State | Why It Matters | Hard Rules Before Use |
| --- | --- | --- | --- |
| OpenSky API | Implemented | Flight/live asset backbone | Preserve existing auth, rate, provenance, and filtering semantics. |
| GDELT DOC 2.0 | Partial | High-volume text coverage and timeline context | Treat normalized percentages and article counts distinctly; never treat article mention geography as incident truth. |
| GDELT GEO 2.0 | Partial | Fast location-mention maps and heat candidates | Treat as text geography only unless corroborated by a reviewed structured source. |
| ReliefWeb API | Not implemented | Humanitarian shortages, displacement, disaster, field reports | Requires approved `appname`; add source contract, rate/failure handling, and field-level provenance. |
| NASA EONET v3 | Not implemented | Curated natural events with point/polygon geometry | Preserve source/category IDs, event status, and geometry type; do not collapse polygon/point distinctions. |
| NASA FIRMS Area API | Not implemented | Near-real-time fire detections for hotspot layers | Requires `MAP_KEY`; detections are not wildfire perimeter truth; keep detection confidence/type metadata. |
| NWS Alerts Web Service | Not implemented | U.S. weather/fire alerts with CAP/JSON-LD/ATOM and zone context | Respect <=30s polling guidance; keep CAP severity/urgency/certainty and source format lineage. |
| USGS GeoJSON feeds | Not implemented | Fast, minute-level earthquake/hazard points | Preserve detail URLs, update timestamps, and event lifecycle semantics. |

Later conflict-event source candidates:

- ACLED API is a reviewed candidate for event-level conflict coverage after the
  ordered priority sources above. Do not substitute it for the current GDELT
  article layer or render it as precise geometry until the source contract,
  OAuth handling, `geo_precision` semantics, and licensing/access requirements
  are documented and tested.

## Canonical Model Needed For This Phase

The next phase should not just add more feeds. It should raise them into a
consistent object model.

### Required Object Families

- `SourceRecord`
  - one fetched document or feed item with raw provenance
- `EvidenceItem`
  - one normalized article, alert, event, bulletin, or detection
- `Incident`
  - one resolved real-world event or ongoing situation backed by one or more
    evidence items
- `GeoAsset`
  - aircraft, vessel, airport, port, route, corridor, weather grid/alert node
- `ImpactPath`
  - affected region, industry, market, route, chokepoint, client exposure
- `WorkflowCase`
  - saved operator context for follow-up, export, assignment, or alert review
- `WorkflowAction`
  - acknowledge, suppress duplicate, attach evidence, save preset, export pack,
    map to client exposure

### Required Object Guarantees

Each canonical object must include:

- stable identifier
- source system and source record linkage
- freshness state
- last updated timestamp
- geometry truth level
- warnings
- derivation note when computed
- permissions scope when action-bearing

## Palantir-Inspired Modularization Direction

This section is an inference from Palantir's public docs, not a claim that
Lotbook should copy proprietary implementation.

### 1. Language Layer

Model Lotbook's operational nouns and verbs explicitly:

- nouns: clients, accounts, incidents, alerts, regions, routes, assets,
  markets, industries, presets, report packs
- verbs: acknowledge, suppress duplicate, save preset, attach evidence, create
  alert case, export report pack, mark client relevance

Repo implication:

- keep canonical object schemas under shared `modules` contracts
- keep action schemas independent from UI components

### 2. Engine Layer

Build the operational compiler stages as independent modules:

- source adapter -> evidence normalization
- evidence normalization -> incident resolution
- incident resolution -> impact mapping
- impact mapping -> geo scene compilation
- geo scene compilation -> report/export/workflow surfaces

Repo implication:

- no React-only intelligence transforms
- each stage should be testable in Python with explicit inputs/outputs

### 3. Toolchain Layer

Expose the same object/action contracts to:

- CLI workflows
- FastAPI routes
- web UI
- future partner adapters and signed export bundles

Repo implication:

- create versioned contract modules for object, action, and scene payloads
- document schema versions and change history

### 4. Observability Layer

Carry one workflow lineage chain through:

- request
- filters
- source fetches
- evidence normalization
- incident resolution
- scene/report build
- operator action
- export or downstream sync

Repo implication:

- every route/export/action should have an execution ID and lineage metadata
- diagnostics should expose stage latency, freshness, and degraded-source state

## Specialist Designation For The Next Phase

Standards Lead
- owns go/no-go decisions against `docs/us_gov_standards.md`

Source Onboarding Specialist
- owns ReliefWeb, EONET, FIRMS, NWS, and USGS intake contracts, rate limits,
  auth/appname requirements, and provenance fields

Entity Resolution Specialist
- owns duplicate suppression, article-to-incident clustering, semantic alias
  handling, and evidence-to-incident mapping

Geospatial Truth Specialist
- owns geometry truth labels, polygon/cell/point distinctions, and reviewed
  display semantics

Workflow And Ontology Specialist
- owns canonical object/action contracts, saved presets, workflow cases, and
  third-party interop boundaries

Visual Systems Specialist
- owns globe interaction depth, layer choreography, compact panel modes,
  animation budgets, and presentation ergonomics

Observability And QA Specialist
- owns lineage, diagnostics, fixture capture, Playwright truthfulness, and
  measured performance budgets

## Work Packages And Required Branch Shapes

These are the recommended contract-based branches once this phase starts:

- `research/osint-source-onboarding`
- `research/entity-resolution-audit`
- `research/geospatial-truth-audit`
- `feature/incident-ontology-contracts`
- `feature/osint-source-adapters`
- `feature/globe-incident-layers`
- `feature/workflow-preset-actions`
- `test/osint-phase-2-fixtures`
- `docs/osint-phase-2-handoff`

If work spans UI, API, and modules concurrently, split ownership by layer and
require one shared checklist and one merged evidence note before push.

## Execution Sequence

### Phase 2.0: Standards Prerequisites

Goal:
- finish the blocking parts of `docs/standards_remediation_plan.md`

Deliver:
- explicit isolated test-harness design
- migration plan away from fabricated successful payloads
- methodology/provenance gap inventory for remaining derived metrics

Current partial closure:
- existing regional-intel and regional-conflict pulse scene layers now expose
  method IDs, formulas, units, count semantics, geometry truth level, coverage,
  and freshness assumptions in layer metadata. This documents the current
  derived regional overlays but does not authorize new source adapters, precise
  incident geometry, or expanded conflict event claims.
- user-facing globe copy now uses `World`; the Overview route opens that globe
  by default, embeds client/account context in the globe HUD, and keeps the
  workspace controls visible by default.
- client/account positive-path API coverage now uses the isolated SQLite route
  tests instead of duplicate fabricated store-success stubs, shrinking one
  standards-remediation Phase 1 blocker before source-adapter work starts.
- current RSS/GDELT conflict discovery expanded query and region aliases for
  active-conflict coverage gaps called out during audit, including Myanmar,
  Ukraine, African conflict corridors, and Middle East conflict terms. These
  terms only improve source retrieval and ranking; they do not hardcode any
  region as red or raised without payload evidence.
- research note: ReliefWeb remains the first reviewed structured source in the
  current onboarding order for humanitarian/disaster reporting
  (https://apidoc.reliefweb.int/); GDELT DOC remains a news-coverage search
  source rather than resolved incident truth (https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/);
  ACLED is a strong later candidate for structured political-violence event
  coverage but is not implemented or moved ahead of the approved source order
  without a feed-registry update (https://acleddata.com/api-documentation/getting-started).

Exit:
- the next implementation batch can add source adapters without violating the
  standards baseline

### Phase 2.1: Source Adapter Contracts

Goal:
- onboard reviewed external sources through typed adapter boundaries

Deliver:
- adapter contracts for ReliefWeb, EONET, FIRMS, NWS alerts, and USGS
- feed registry status expansion with source-specific health/freshness
- source-specific provenance schemas

Exit:
- each onboarded source has deterministic normalization, documented limits, and
  a capture path for reviewed fixtures where needed

### Phase 2.2: Incident Resolution And Duplicate Suppression

Goal:
- convert many evidence items into one canonical incident when appropriate

Deliver:
- article/alert/event clustering strategy
- conflict/scarcity/disaster taxonomy expansion without hardcoded UI-only lists
- duplicate and semantic-alias diagnostics for incidents, clients, and
  workspaces

Exit:
- one real-world incident no longer inflates counts simply because multiple
  feeds or feeds variants describe it

### Phase 2.3: Geo Scene Expansion

Goal:
- render real incident and alert layers instead of only tracker and centroid
  regional signals

Deliver:
- incident point/polygon/cell layer builders
- hazard/alert visual semantics by truth level
- compact/toggleable detail stack and presentation-safe overlay modes

Exit:
- the globe can answer "what is happening here" with evidence-backed incident
  layers, not only trackers and inferred regional pulses

### Phase 2.4: Impact And Emotion Mapping

Goal:
- map incident and regional evidence into market, route, client, and industry
  impact layers

Deliver:
- explicit `ImpactPath` objects
- region/industry emotion overlays tied to supporting evidence counts
- clear separation between direct observations, inferred aggregation, and
  affected-market rollups

Exit:
- emotion and impact layers are defensible and traceable back to evidence

### Phase 2.5: Workflow And Presentation Mode

Goal:
- make the globe operational and presentation-ready

Deliver:
- saved presets
- evidence bundles
- workflow cases
- report packs that preserve globe filters and lineage
- compact floating panel mode for meetings

Exit:
- an operator can move from discovery to evidence-backed handoff without
  leaving the platform

### Phase 2.6: Third-Party Interop Layer

Goal:
- make Lotbook outwardly integrable without shipping bespoke per-partner hacks

Deliver:
- versioned object/action/scene export contracts
- signed report-pack bundle spec
- adapter boundary for external case/workflow/BI platforms

Exit:
- integrations can consume stable contracts instead of scraping UI payloads

## Verification Expectations

Before this phase is considered started, each work package must define:

- the exact source or contract being changed
- root-cause statement for any bug/undercount/duplicate problem
- tests to add or update
- fixture/live-data evidence path
- performance budget impact if UI/visual behavior changes

Required evidence types across the phase:

- Python unit tests for normalization/resolution/scene builders
- API contract tests for each new source or object/action route
- Playwright smoke/visual tests only for reviewed fixtures or fail-safe states
- diagnostics checks for source health, duplicate drift, and lineage presence

## Stop Conditions

Do not begin implementation if any planned change would require:

- fabricated geometry
- inferred event IDs without documented resolution logic
- fake "confidence" values standing in for support or coverage
- duplicate-tolerant metrics
- hidden partner-specific branches in product code
- canvas-only controls without keyboard/non-canvas parity

## Expected Outputs Of The Phase

If this phase is executed correctly, Lotbook should end with:

- a globe that shows real incident, alert, and impact layers in addition to
  trackers
- event counts and impact counts that are not inflated by duplicate articles
  or semantic duplicates
- a clearer ontology-style operating model for future CLI/API/web and partner
  integrations
- stronger workflow lineage and exportability for analyst, client, and
  executive use
