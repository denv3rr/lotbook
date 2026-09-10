# U.S. Government Standards Baseline

This document is the mandatory engineering baseline for Clear. It maps repo
rules to official U.S. government standards and guidance and turns them into
enforceable project requirements.

This is not a claim of formal FedRAMP, DoD, Section 508, or other government
certification. It is the minimum bar we choose to follow internally. If a
change cannot satisfy this baseline, stop and redesign it before shipping.

## Mandatory Rule

Before any non-trivial update to code, tests, data flows, visuals, reports,
analytics, prompts, or deployment behavior, re-skim this file and the directly
implicated source documents listed below.

## Source Baseline

The repo baseline is anchored to these official U.S. government publications:

1. NIST SP 800-218, Secure Software Development Framework (SSDF), Version 1.1
   - https://csrc.nist.gov/pubs/sp/800/218/final
2. NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations, catalog release 5.2.0
   - https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
3. NIST SP 800-160 Volume 1 Rev. 1, Engineering Trustworthy Secure Systems
   - https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final
4. NIST AI Risk Management Framework (AI RMF 1.0)
   - https://www.nist.gov/itl/ai-risk-management-framework
5. Revised Section 508 Standards for Information and Communication Technology
   - https://www.access-board.gov/ict/
6. DoD MIL-STD-882E with Change 1 (September 27, 2023), Department of Defense Standard Practice: System Safety
   - https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027

## What This Means In Practice

Source review: September 9, 2026. The [reference register](reference_register.json)
and [coverage record](reference_coverage.md) distinguish partial implementation
from compliance. SSDF 1.1 remains the published final baseline; NIST lists
SSDF 1.2 as a draft. AI RMF 1.0 remains the baseline while revision is in
progress. Do not silently treat drafts or reference links as adopted controls.
SP 800-53 release 5.2.0 adds/updates development, integrity and software-update
controls; organizational tailoring and evidence remain release work.
Revised Section 508 incorporates WCAG 2.0 A/AA with applicable exceptions;
newer WCAG targets do not by themselves establish Section 508 conformance.

These source documents drive the repo rules below:

- SSDF means secure development, reviewed changes, verified dependencies,
  explicit defect handling, and traceable release hygiene.
- NIST 800-53 means least privilege, validated inputs, explicit logging,
  configuration control, safe defaults, and no silent trust expansion.
- NIST 800-160 means substantiated trustworthiness, evidence-backed decisions,
  and rigor proportional to the damage a failure could cause.
- AI RMF means AI-assisted behavior must be valid, reliable, explainable,
  measurable, and tied to real evidence.
- Section 508 means accessibility is a build requirement, not a cleanup task.
- MIL-STD-882E means safety hazards must be identified early and reduced by
  design, not accepted by accident.

## Repo Enforcement Rules

### 1. No Fabricated Data

- Do not use mock, demo, synthetic, invented, placeholder, or example data in
  runtime behavior, user-facing demos, reports, screenshots, globe scenes,
  heatmaps, analytics, or visual baselines.
- Positive-path tests must use live local data or captured real fixtures with
  recorded provenance, source, and timestamp.
- Negative-path validation tests may construct deliberately invalid payloads
  only to prove rejection, containment, and fail-safe behavior. They must never
  appear as valid analytics or business data.
- Never hide missing data behind fabricated fill values, invented centroids,
  dummy scores, fake news points, or synthetic activity layers.

### 2. No Invented Math

- Every metric, score, ranking, heatmap, alert, or surface must declare its
  inputs, formula, units, time window, and source.
- No placeholder confidence values, static filler series, random walks,
  simulated curves, hand-waved weights, or fabricated derived fields.
- If the data needed for a calculation is missing, return an explicit warning
  or an unavailable state. Do not guess.
- If a formula is too weak to defend to a customer, auditor, or engineering
  peer, it is not ready to ship.

### 3. Fail Safe And Fail Closed

- On auth failure, schema mismatch, provenance gap, stale data, or dependency
  failure, default to the safer state.
- Never silently weaken authentication, permissions, validation, freshness
  checks, or integrity checks to keep a screen alive.
- Prefer explicit degraded states, warnings, disabled actions, and last-known
  good read-only views over silent corruption or invented continuity.
- Destructive behavior must require explicit confirmation and documented
  safeguards.

### 4. Provenance, Integrity, And Traceability

- Every shared payload should carry source, timestamp, warnings, and enough
  lineage to explain where it came from.
- External inputs are untrusted until validated.
- If two systems disagree, surface the mismatch and stop the unsafe path rather
  than silently choosing one.
- Reports, exports, and assistant responses must preserve methodology and
  provenance rather than stripping them away for presentation.

### 5. Measured Optimization Only

- No undocumented hacks, magic constants, silent bypasses, or speculative
  "optimizations."
- Performance claims must be backed by measurement such as bundle size, frame
  time, memory use, API latency, render cost, or query cost.
- Before adding heavier visuals, animations, or data layers, set or update
  budgets and verify the change against them.
- Reduced-motion behavior, accessibility, and fail-safe degradation are part of
  optimization. Fast but unsafe or inaccessible is a failure.

### 6. No Hacks In Production Paths

- Do not ship monkey patches, hidden fallback branches, fake data shims,
  "temporary" auth bypasses, or code that only works because a bug is being
  ignored.
- If emergency containment is unavoidable, document the reason, owner, tests,
  expiry, and removal plan in the same change set.
- Convenience cannot outrank correctness, provenance, safety, or reviewability.

### 7. Accessibility Is Mandatory

- UI work must satisfy Revised Section 508 expectations for keyboard access,
  focus visibility, labeling, contrast, assistive-technology compatibility, and
  reduced-motion handling.
- Visual polish cannot depend on motion alone.
- Canvas-heavy experiences must expose stable non-canvas controls and state so
  they remain operable and testable.

### 8. AI And Assistant Guardrails

- No fabricated citations, sources, confidence, or claims of certainty.
- AI-assisted summaries must be grounded in deterministic system data or cited
  external sources with preserved provenance.
- If the model cannot support a statement with real evidence, it must say so.
- AI output must never override validated system data or silently invent
  analytics.

### 9. Release And Test Discipline

- Run the affected automated tests before closing work.
- For visuals, verify settled states, not animation guesswork.
- Do not keep demo-only switches, fabricated fixture loaders, or mock-path
  shortcuts in the main product path.
- Treat "works on my machine" without evidence as a failing state.

### 10. Git And Change Control

- Git workflow must follow [docs/agent_git_standards.md](agent_git_standards.md).
- Use branch names that reflect the real work type and keep branch scope narrow.
- Review staged diffs before commit or push and verify sensitive files remain
  excluded.
- Do not rewrite shared history or discard user work unless explicitly directed.

## Static enforcement

Independent inspectors and the whole-repo guardrail scanner are defined in
[docs/inspection_verification.md](inspection_verification.md). They verify
these rules; they do not replace them. Known remaining violations are
ratcheted in `tests/guardrail_baseline.json`.

## Change Gate

Before closing any substantial update, confirm all of the following:

1. The change uses real data or explicitly rejects missing data.
2. The math is documented, deterministic, and traceable.
3. The safer default is in place for failure conditions.
4. The performance claim is measured, not assumed.
5. Accessibility and reduced-motion paths still work.
6. Tests prove the affected behavior without relying on invented positive-path data.

## Conflict Rule

If another local note, old plan, or convenience helper conflicts with this
document, this document wins. Update the older material so the repo says one
thing.
