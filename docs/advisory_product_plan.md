# Advisory and client management product plan

Updated September 8, 2026. Investment banking advisory is the primary
workspace; wealth and portfolio management remain alongside it. The web
dashboard and API are the delivery surfaces. New CLI parity is deferred.

The binding baseline remains `docs/us_gov_standards.md`. Existing OSINT
source and dense-visual gates remain in force. This plan changes the landing
workflow to advisory work; it does not close the older standards backlog.

## Current build

1. Establish an advisory workbench with client-linked mandates, contacts,
   next actions, diligence tasks, owners, deadlines, and change history.
2. Keep financial amounts currency-specific, preserve unknown values, label
   operator estimates, and protect updates against stale revisions.
3. Add an annual FCFF DCF workspace with explicit assumptions, an enterprise
   to equity bridge, sensitivity analysis, source notes, and JSON export.
   Trading-comparable EV/revenue and EV/EBITDA analysis and immutable saved
   model versions are now included. Snapshots link to clients and optionally deals.
4. Inspect existing financial calculations independently and correct verified
   defects with regression evidence. Formula tests prove arithmetic, not
   market-data quality or financial suitability.
5. Verify real database/API/browser workflows in an isolated runtime, improve
   keyboard-accessible forms and dialogs, and check frontend bundle budgets.

## Readiness gates

- The user can create a client, record a mandate and contact, assign work,
  update a stage, calculate a valuation, and export data from the dashboard.
- Failed validation and stale updates preserve saved records. Activity records
  retain changes; a local operator label is not an authenticated human identity.
- Financial results preserve assumptions, units, dates, formula, and source.
- API and browser verification do not write operator databases or return
  fabricated successful route responses.
- Independent inspectors review the final diff separately from its authors.

## Subsequent release work

Loading follow-through: client detail no longer reloads on account changes;
obsolete profile/dashboard/pattern requests are cancelled and ignored. Pattern
analysis and its 3D surfaces load only when expanded. Snapshot refresh is
explicitly labeled, not presented as live quotes. This reduces unnecessary work
but does not establish a market-provider latency guarantee. Next investigate
shared quote caching, request coalescing and provider-supported incremental
updates with observed timestamps, rate limits and subscription rights. Polling
and interpolated positions must not be labeled live market streaming.

World direction and the subsequent navigable NASA-basemap replacement are
captured in `world_map_reference_plan.md`. The dashboard remains the landing page.
Local encrypted database export and non-overwriting recovery staging are now
implemented; see `production_readiness.md` for scope, verification and release gates.

1. Expand modeling with reviewed financial statement and peer-data intake,
   precedent valuations, capital structure, merger and sponsor models, and
   versioned model review/approval. Do not imply these exist in the first build.
2. Extend execution with party-level bids, NDA/access tracking, diligence
   responses and document versioning, approval responsibilities, and report
   packs. Recording an NDA status must never grant document access.
3. Establish multiuser identity, role and client authorization, recovery-tested
   backups, deployment operations, retention, audit protections and onboarding
   appropriate to the intended organization before a hosted production release.

The product is not declared production-ready merely because this build passes
tests. Each release needs evidence for its actual deployment and workflows.

## This pass verification

- Python: 341 tests passed after integration with main; deterministic model
  tests are arithmetic evidence only.
- Real isolated browser: five acceptance flows passed, including saved DCF and
  comparable models, revision lineage, mobile no-overflow, keyboard dialogs,
  deferred pattern requests and profile reuse across account scopes.
- Idle close: API/UI listeners, recorded API/UI/launcher processes and observed
  descendants all exited; control record reported stopped in 1.149 seconds on
  the verified Windows run. Active work can require additional drain time.
- TypeScript, production build and bundle budgets passed. Existing async-heavy
  chunk size/circular-chunk and stale Browserslist warnings remain.
- Desktop and mobile screenshots inspected from the real isolated run; no new
  presentation fixture baseline. This is not accessibility conformance evidence.
