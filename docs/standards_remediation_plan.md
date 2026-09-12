# Standards Remediation Plan

September 9 reference checkpoint: all README standards and methods references
are versioned and mapped in `reference_register.json` / `reference_coverage.md`.
This corrects source/title drift and bounded undefined-statistic defects; it
does not close the repo-wide standards gate. Individual authorization, model
review, operational acceptance, accessibility conformance and remaining
descriptive-analytics coverage/availability gaps stay open.

September 2026 bounded progress: advisory route acceptance now uses actual
isolated SQLite writes; `playwright.advisory.config.ts` launches the real
foreground launcher with disposable data for client/deal/task and close-app
workflows. The default browser suite explicitly excludes these mutating tests.
This does not migrate all older positive-path stubs or close the repo-wide gate.
See `advisory_product_plan.md`, `banking_valuation.md` and
`advisory_math_verification.md` for the bounded scope and remaining limitations.

This plan is the mandatory gate before the next major visual modernization
phase. `docs/us_gov_standards.md` remains the binding baseline; this document
turns the audit findings into ordered engineering work, owners, and exit
criteria.

## Audit Snapshot

Audit date: 2026-03-18

Closed in the current pass:
- Removed runtime/demo mock plumbing from the web data layer and tracker stream.
- Removed browser `?demo=` happy paths and moved Playwright to the real local
  API/UI stack.
- Rebased globe visual regression on fail-safe unavailable states instead of
  fabricated scene content.
- Added a captured-fixture format and capture workflow for positive-path intel
  globe visuals, with provenance recorded from the real FastAPI route contract
  and local news cache.
- Added a loaded-state Playwright globe visual baseline driven by the reviewed
  captured intel fixture instead of invented route bodies.
- Added a reviewed geospatial source audit for country boundaries, wildfire
  perimeters, fire detections, and U.S. alert polygons, with explicit limits on
  what can and cannot be shown as precise geometry.
- Added collector-boundary news dedupe that collapses cross-feed duplicate
  articles while preserving contributing source provenance.
- Routed reporting-engine cached news reads through the same deduping loader so
  report packs do not bypass collector/cache duplicate controls.
- Added normalized client/account duplicate guards on the write path so
  semantic duplicates fail closed instead of inflating downstream counts.
- Expanded diagnostics visibility for duplicate client names and duplicate raw
  news cache entries so existing drift is detectable before it biases counts.
- Moved the OSINT workspace into the Overview route behind a collapsible lazy
  mount while keeping the globe as the primary entry point and preserving
  `/osint` as a deep link.
- Renamed the user-facing fused globe to World, auto-opens it on Overview,
  keeps the World workspace visible by default, and embeds client/account
  context in the globe HUD.
- Added truthfulness-oriented globe copy and selected-feature provenance rows
  for source, layer, display scope, coverage, warnings, and display notes when
  present in the payload.
- Added a compact globe signal-density strip and scene surface peaks derived
  only from visible real payload values; no missing values, geometry, or
  positive-path visuals are fabricated.
- Promoted source-backed conflict signals in region sorting, red globe accents,
  and raised peaks without hardcoding regions as hot when source evidence is
  absent.
- Extended frontend bundle guardrails to fail on heavy async visual
  preloads/styles in `index.html`, and moved MapLibre/Leaflet styles behind
  their lazy loaders.
- Removed heuristic assistant confidence values from runtime assistant output
  and exports, including stripping old history payload labels at the export
  normalization boundary with an explicit warning.
- Removed heuristic confidence labels from weather/conflict/combined intel
  reports; those reports now expose support/availability instead of invented
  certainty labels.
- Replaced the Yahoo macro snapshot `fake_ts` shortcut with an explicit
  empty-result backoff window.
- Removed the tracker map demo-tile fallback and restored MapLibre as the
  primary tracker map path with explicit failure behavior.
- Renamed the aggregate portfolio history helper so it no longer mislabels
  real-data reconstruction as "synthetic."
- Replaced random-data unit tests with deterministic sequences for regime and
  financial calculations.
- Replaced a silent startup schema failure with explicit logging plus startup
  failure, and made `.env` load issues visible in logs.
- Migrated client/account positive-path API evidence away from fabricated
  `DbClientStore` success stubs and onto the isolated SQLite route tests in
  `tests/test_web_api_clients.py`, now using a per-test temporary database.
- Restored GitHub Actions CI, CodeQL, and Dependabot YAML (2026-08-17):
  `.github/workflows/ci.yml`, `.github/workflows/codeql.yml`, and
  `.github/dependabot.yml`.
- Targeted 36 Dependabot alerts with the pip/npm pins recorded in
  `docs/security_verification.md`. This is dependency hygiene plus
  defensive route tests in `tests/test_security.py`, not a formal pentest.
- Added independent inspection: corpus-bound specialist verifiers in
  `docs/inspection_verification.md` / `scripts/inspect_repo.py`, and a whole-repo
  guardrail scanner in `scripts/check_guardrails.py` ratcheted by
  `tests/guardrail_baseline.json`. This is documentation-corpus inspection
  plus static analysis, not a trained multi-agent product.
- Shared isolated SQLite/API harness landed at `tests/harness.py` and is used
  by client and maintenance positive-path API tests. Operator runtime
  databases are out of bounds.
- Report synthesis tests no longer pass invented `confidence` strings.
- Startup `.env` load failures are typed (`ImportError`) or logged (`OSError`)
  instead of `except Exception: pass` in `lotbookctl.py` and `run_web.py`.

Still open:
- Several Python tests still rely on in-memory payloads or monkeypatched
  route internals instead of live local data or captured real fixtures with
  provenance. `tests/test_web_api.py` functions named `*_stubbed` remain
  contract-shape / negative-path evidence only.
- Positive-path browser mutation tests still need an isolated real-data
  Playwright harness so we can verify destructive flows without touching
  local operator data.
- Tracker globe positive-path visuals still need a reviewed capture path before
  fail-safe-only browser baselines should be replaced there.
- The tracker capture path now exists but correctly fails closed in environments
  that only return empty/degraded tracker scenes; a reviewed non-empty tracker
  source is still required before a loaded-state tracker fixture can be
  committed.
- Widespread `except Exception` and silent `pass` usage still needs the
  Phase 2 fail-safe audit across `modules/`, `web_api/`, and remaining startup
  code. The current inventory is `tests/guardrail_baseline.json`; new hits
  fail CI.
- The next implementation phase is now defined in
  `docs/osint_globe_phase_2_plan.md` and remains blocked until Phase 1 and
  Phase 2 in this document are explicitly advanced with evidence.

## Specialist Roles

- Standards Lead: owns interpretation of `docs/us_gov_standards.md`, blocks
  work that violates the baseline, and signs off on phase exits.
- Data Provenance Engineer: tracks source, timestamp, lineage, fixture capture,
  and payload metadata across API, CLI, and exports.
- Backend Safety Engineer: audits fail-open behavior, exception handling,
  schema validation, startup guarantees, and destructive-route safeguards.
- Frontend Accessibility Engineer: owns Section 508 behavior, reduced-motion,
  keyboard/focus paths, and non-canvas control parity for immersive views.
- Browser Verification Engineer: converts Playwright to real-data or
  provenance-backed fixtures, maintains visual baselines, and blocks fabricated
  happy paths.
- Analytics Integrity Engineer: removes heuristic confidence/math shortcuts,
  adds methodology blocks, and ensures deterministic formulas are documented.
- Visual Systems Engineer: advances the globe/UI work only after the standards
  gate stays green, and keeps bundle/render budgets measured.

## Phase 0: Standards Closure Gate

Objective: remove the most direct contradictions before new product surface
area is added.

Tasks:
- Remove demo/mock/synthetic runtime paths from shared product code.
- Eliminate browser demo query params and fabricated positive-path responses.
- Replace random-data unit tests with deterministic inputs.
- Replace silent startup/schema failures with explicit logging and safe stop
  behavior.
- Remove heuristic certainty labels where the app cannot defend them.

Exit criteria:
- No runtime product code depends on demo/mock data loaders.
- Playwright smoke/assistant/system/globe suites run against the real local
  stack or explicit negative-path failure checks only.
- The affected Python and Playwright suites pass.

## Phase 1: Verified Test Data Infrastructure

Objective: give the repo a compliant way to test positive paths without
inventing business data.

Tasks:
- Build a captured-fixture format that stores source, timestamp, capture
  method, and schema version.
- Add an ephemeral SQLite/API harness for browser tests that need destructive
  or workflow-heavy positive paths.
- Split browser tests into:
  - real local data tests
  - captured real-fixture tests
  - negative-path validation tests
- Ban new positive-path route stubs that fabricate successful business data.

Exit criteria:
- System/browser mutation tests no longer need fabricated success bodies.
- New fixtures carry provenance metadata and are reviewable artifacts.
- Test docs explain when live local data vs captured fixtures are allowed.
- Globe/browser fixture coverage is expanded beyond intel as reviewed capture
  paths become available.

Current partial closure:
- `tests/harness.py` is the shared ephemeral SQLite/API harness for isolated
  positive-path Python tests.
- Independent inspection and the guardrail scanner exist; they inventory
  remaining debt and ratchet new violations, they do not close this phase.

## Phase 2: Fail-Safe And Silent-Failure Audit

Objective: remove quiet failure behavior that can hide corruption or weaken
guarantees.

Tasks:
- Audit `except Exception` and bare `pass` usage across startup, data loads,
  view models, feeds, and reporting.
- For each case, choose one of:
  - explicit log + safe degraded state
  - explicit log + startup failure
  - typed exception handling
  - removal of dead fallback branch
- Add tests for the corrected failure mode.

Exit criteria:
- Silent failures are documented exceptions, not defaults.
- Startup-critical paths fail closed when integrity checks fail.
- Degraded states are explicit in UI/API payloads.

Current partial closure:
- `scripts/check_guardrails.py` classifies broad/silent exception sites.
- `tests/guardrail_baseline.json` is the living exception-handling audit
  inventory. Completing this phase still requires classifying and correcting
  each remaining site.

## Phase 3: Analytics And Report Output Remediation

Objective: make user-facing analytics defensible to customers, auditors, and
internal reviewers.

Tasks:
- Remove or rename heuristic `confidence` outputs that are really coverage or
  source-availability signals.
- Add methodology blocks for derived metrics, risk scores, and report sections.
- Keep probability/confidence outputs only where the value is a real model
  output with documented inputs and units.
- Update report/export helpers and tests so they no longer normalize invented
  certainty labels by default.

Exit criteria:
- User-facing reports do not claim unsupported certainty.
- Every retained metric or probability has inputs, window, units, and source.
- Report/export tests align with the runtime contract.

## Phase 4: Visual Foundation Re-Entry

Objective: resume visual modernization on a compliant base.

Tasks:
- Keep globe/UI work behind measured bundle and render budgets.
- Require provenance/freshness badges for new immersive layers.
- Keep reduced-motion and non-canvas controls first-class.
- Expand visual regression only for settled, reviewable states.

Exit criteria:
- No new globe layer ships without provenance, freshness, and performance
  verification.
- Visual tests validate real or fail-safe states, not invented presentation
  scenes.

## Phase 5: Globe Expansion

Objective: continue the immersive roadmap without reintroducing standards
debt.

Tasks:
- Add cargo/logistics, weather, conflict, and news layers via the shared geo
  scene contract.
- Build saved scene/filter presets for presentation workflows.
- Add report/export parity for globe states.
- Keep fallbacks as resilience paths, not the default client surface.

Exit criteria:
- New layers consume canonical geo scene payloads.
- Presentation flows preserve provenance, warnings, and freshness.
- Bundle and frame budgets remain inside guardrails.

## Release Gate

Before any future visual phase is marked complete:
- The active specialists have re-skimmed `docs/us_gov_standards.md`.
- The touched phase checklist in this file is updated.
- The relevant Python and Playwright suites pass.
- No new fabricated positive-path data was added.
- Any remaining standards debt is listed explicitly in `AGENTS.md` and not
  hidden inside TODOs.
