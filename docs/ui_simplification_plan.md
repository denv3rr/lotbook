# UI Simplification And Progressive Disclosure Plan

Status: Active on August 27, 2026. This is a presentation and interaction
refactor. It does not authorize new data sources, analytical formulas, globe
layers, or changes to API contracts.

## Product Rule

Lotbook should be simple by default and powerful on demand.

Every major screen should establish three levels:

1. Primary workspace: the globe, portfolio, record, chart, or table the user
   came to use.
2. Contextual controls: actions and filters for the current selection or task.
3. Secondary detail: methodology, provenance, diagnostics, configuration, and
   advanced analysis disclosed only when needed.

New controls must not automatically become permanent UI. Place each control in
the primary workflow, contextual UI, or advanced settings according to when it
is needed.

## Audit Inventory

The August 27 source and interaction-architecture audit found these highest
priority density problems:

- The World overlay surrounds the globe with several simultaneous left panels
  and a multi-panel right stack. Scene, layers, filters, camera, status, focus
  browsing, selected-object detail, aggregates, legends, and client context all
  compete with the canvas.
- Globe selection already works directly on points, but the permanent focus
  list makes the sidebar appear to be the primary interaction path.
- Client analytics defaults almost every section open. Portfolio history,
  risk, distribution, regime, pattern surfaces, holdings, lots, diagnostics,
  and manual assets therefore arrive with equal visual weight.
- The transition surface has no axis contract. Pattern surfaces have technical
  axes, but their labels and hover behavior do not explain the decision each
  chart supports.
- Portfolio history hides both axes. Distribution tooltips expose generic data
  keys instead of plain-language financial labels.
- Risk metric labels use unexplained shorthand such as Sharpe, Sortino, beta,
  alpha, VaR, CVaR, entropy, permutation entropy, and Hurst.
- Several empty states report only absence instead of teaching the next action.
- Overview repeats World entry and supporting dashboards while auto-opening
  the globe, which makes the page beneath compete with the active workspace.

## Information Architecture

### World

- The globe is the dominant canvas.
- A compact command bar owns scene selection, close, and entry to layer/view
  controls.
- Layer, lens, tracker scope, camera, and filters live in one disclosed control
  surface. Safety warnings remain immediately discoverable.
- Selecting a globe object opens a bottom inspector that keeps the globe
  visible. The inspector has a compact summary first and expandable evidence,
  methodology, aggregates, legend, and client context below it.
- A keyboard-operable Browse items control preserves non-canvas access without
  making the focus list permanent.

### Client Portfolio

- The selected client and portfolio summary are primary.
- Interval and account scope stay visible because they change every downstream
  view.
- Client/account editing moves behind one Manage menu.
- Portfolio history, core risk, and holdings are the initial analysis path.
- Return distribution, market-regime analysis, pattern analysis, lots,
  diagnostics, and manual assets remain available but default closed.

### Technical Visualizations

Every significant chart or surface must provide:

- a human-readable title;
- visible X, Y, and Z labels where applicable;
- units;
- plain-language hover labels;
- a concise statement of what the visualization shows;
- an optional How to read this disclosure for technical detail;
- an explicit unavailable state that tells the user what data is missing or
  what to do next.

Technical notation may appear after the plain-language label. It must not be
the only explanation.

## Implementation Sequence

1. Replace the dual-sided World HUD with a compact command bar and contextual
   bottom inspector.
2. Consolidate layer/view/filter/camera controls behind one disclosure without
   removing them.
3. Add shared visualization guidance, axis titles, units, and readable hover
   labels.
4. Rebalance client defaults and group advanced analytics.
5. Improve empty-state instructions and primary-action copy across the touched
   routes.
6. Validate desktop, laptop, and narrow layouts; keyboard/focus behavior;
   reduced motion; bundle limits; and existing analytical contracts.

## Guardrails

- Do not change calculations for presentation reasons.
- Do not add fabricated data or geometry to make a screen look complete.
- Do not hide warnings, freshness, uncertainty, or provenance.
- Do not make the globe canvas the only way to select or inspect an object.
- Do not replace one collection of permanent panels with one enormous drawer.
- Do not add unexplained icon-only controls.
- Do not make advanced/admin functions top-level navigation unless they are a
  primary workflow.
- Persisted filters or hidden-layer choices must not make available scene data
  look absent. Version stored UI state when defaults or disclosure patterns
  change, and expose contextual recovery actions beside an empty summary.

## Verification Evidence

The implementation must include:

- focused component and Playwright assertions for globe control disclosure,
  selection inspection, and keyboard access;
- chart/surface contract assertions for readable axis labels and descriptions;
- frontend build and bundle guardrail checks;
- affected Python tests to confirm payload and calculation semantics remain
  unchanged;
- independent frontend-accessibility, analytics-integrity, and visual-systems
  inspection records against origin/main...HEAD.
