# Independent Inspection Verification

This is the committed inspection process for Lotbook. It does not add a
general multi-agent reasoning product. It makes the specialist roles
already named in `docs/standards_remediation_plan.md` executable as
independent verifiers against the documentation corpus.

## Product boundary

Lotbook is a local-first portfolio, analytics, and OSINT platform with a
rules-based assistant surface. `docs/agent_git_standards.md` and the
assistant constraints in `docs/us_gov_standards.md` / `docs/ai_assistant.md`
are the seed of governed agent work. They are not an invitation to build a
standalone multi-agent framework, train models, or let agents mutate
runtime state without the documented git and standards gates.

The ignored `agents/` tree is local helper state. It is not product
capability and must not be committed.

## Why this exists

The standards baseline is binding, but most enforcement was documentation,
process, and targeted tests (`tests/test_security.py`, calculation tests,
`web/scripts/check-bundle.mjs`). Missing pieces were:

1. Dedicated inspectors bound to the documentation corpus, run separately
   from the authoring pass, against plans, generated code, or reasoning
   traces.
2. A whole-repo static scan for the guardrail classes in
   `docs/us_gov_standards.md`, not only security and math unit tests.

This directory plus `scripts/inspect_repo.py` and `scripts/check_guardrails.py`
close those gaps without inventing new workflow authorities.

## Corpus

Inspectors must load the files in `docs/inspection/corpus.json` before
judging work. The corpus is the source of requirements. Chat history is
not.

`python scripts/inspect_repo.py corpus` verifies that every corpus file exists
and prints its SHA-256. A missing corpus file is an inspection failure.

## Independent inspectors

Inspectors are role-specialized checklists, not a runtime agent mesh.
They correspond to the specialist roles already assigned in
`docs/standards_remediation_plan.md`.

| Role id | Specialist | Verifies |
| --- | --- | --- |
| `standards-lead` | Standards Lead | Baseline go/no-go, no invented workflow, stop/go against `docs/us_gov_standards.md` |
| `data-provenance` | Data Provenance Engineer | Source, timestamp, lineage, fixture capture, payload metadata |
| `backend-safety` | Backend Safety Engineer | Fail-closed behavior, exception handling, schema/startup guarantees |
| `frontend-accessibility` | Frontend Accessibility Engineer | Section 508, reduced-motion, keyboard/focus, non-canvas parity |
| `browser-verification` | Browser Verification Engineer | Real-data or provenance-backed fixtures; no fabricated happy paths |
| `analytics-integrity` | Analytics Integrity Engineer | Documented formulas, no heuristic certainty, methodology blocks |
| `visual-systems` | Visual Systems Engineer | Globe/UI only after the standards gate; bundle/render budgets |

Role checklists live in `docs/inspection/roles.md`.

An inspection is independent only when all of the following hold:

- it is a separate invocation from the authoring work
- it names the role that ran
- it loads the corpus (or fails)
- it records the artifact (plan path, diff range, code path, or trace)
- it includes `python scripts/check_guardrails.py` evidence
- it does not mark its own authoring work as verified

`python scripts/inspect_repo.py verify --role <id> --plan <file>`
`python scripts/inspect_repo.py verify --role <id> --diff <git-range>`
`python scripts/inspect_repo.py verify --role <id> --code <path>`
`python scripts/inspect_repo.py verify --role all --trace <file>`

The command prints a verification record. It does not merge, push, or
waive `docs/us_gov_standards.md`.

## Guardrail scanner

`scripts/check_guardrails.py` is the whole-repo checker for the
documented rule classes. It is not a pentest and not a substitute for
typed exception handling.

Classes scanned:

1. Fabricated / demo / mock / synthetic markers in runtime product code
2. Broad `except Exception` / bare `except` and silent `pass`
3. Invented `confidence` string literals in tests and runtime
4. Query-string API keys in web client code
5. Non-deterministic `random` use in analytics modules
6. Browser `?demo=` happy-path hooks

Known remaining findings are ratcheted in `tests/guardrail_baseline.json`.
New findings fail CI. Removing a finding requires shrinking the baseline
in the same change.

## Isolated positive-path harness

Phase 1 of `docs/standards_remediation_plan.md` requires an ephemeral
SQLite/API harness so destructive or workflow-heavy tests do not touch
operator data and do not fabricate successful business payloads.

Use `tests/harness.py`. Do not add new positive-path route stubs that
invent successful business data. Capture globe fixtures through
`scripts/capture_globe_fixture.py` with provenance.

Tracker loaded-state fixtures remain fail-closed until a real non-empty
tracker scene exists.

## Open remediation that this process tracks

These remain open until their phase exit criteria are met. Inspection
must not paper over them:

- Some Python tests still use in-memory or monkeypatched payloads instead
  of live local data or captured fixtures.
- Destructive browser happy paths still need the isolated Playwright
  harness.
- Tracker globe loaded-state visuals still need a reviewed non-empty
  capture.
- Broad exception handling still needs the Phase 2 fail-safe audit; the
  scanner inventory is the current evidence, not a completed audit.
- Globe Phase 2 source onboarding stays blocked until Phase 1 and Phase 2
  in `docs/standards_remediation_plan.md` have explicit evidence.
