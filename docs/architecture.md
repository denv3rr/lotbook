# Architecture Standards

These standards keep CLI, API, and web UI modular and future-proof.

## Product boundary

Clear is a local-first advisory, client-management, portfolio, analytics, and OSINT platform with a
rules-based assistant surface. It is not a general multi-agent reasoning
framework, model-training system, or autonomous dispatcher.

September 2026: advisory workflow contracts and immutable valuation snapshots
live in `modules/banking`, with thin routes in `web_api/routes/banking.py`.
The dashboard is the primary workbench; CLI feature parity is deferred by
explicit product direction. Additive SQLite tables share existing client IDs.
The managed web server owns safe application-requested shutdown; per-launch
PID/creation-time records constrain cleanup to its own process identities.

Governed agent work is seeded by:

- [docs/agent_git_standards.md](agent_git_standards.md)
- assistant constraints in [docs/us_gov_standards.md](us_gov_standards.md)
  and [docs/ai_assistant.md](ai_assistant.md)
- independent inspection in [docs/inspection_verification.md](inspection_verification.md)

The ignored `agents/` directory is local helper state. It is not a product
runtime and must not be committed.

## Core Principles
- Single source of truth for business logic and view-models.
- Web UI and CLI render the same view-model payloads.
- API is modularized by domain (routers) and shares auth dependencies.
- Design system is tokenized and components are reusable across pages.
- Analytics renderers should live in dedicated view modules (e.g., patterns/risk/regime) rather than monolithic toolkits.
- Diagnostics and system info should be sourced from shared modules (SystemHost, DbClientStore, feed registry) to avoid drift.

## API Layout
- `web_api/routes/*` contains domain routers (trackers, intel, clients, reports, settings, tools).
- `web_api/auth.py` provides shared API key auth dependency.
- `web_api/app.py` only composes routers + middleware.

## UI Layout
- `web/src/design/tokens.ts` defines theme tokens and base colors.
- `web/src/components/ui/*` includes reusable primitives (Card, SectionHeader, etc).
- `web/src/components/layout/*` hosts global layout components (Sidebar, AppShell).
- `web/src/config/*` hosts navigation and shared UI config.
- `web/src/lib/api.ts` hosts the shared API client, caching, and hooks.
- `web/src/lib/stream.ts` hosts WebSocket hooks for live data.
- `web/src/pages/*` contains feature pages; pages must use shared components and `useApi`.

## Diagnostics + Registry
- Feed registry lives in `modules/market_data/registry.py` and powers API/CLI/UI summaries.
- System info should use `utils/system.py` to normalize CPU/memory/host data.
- Diagnostics endpoints should surface provenance (source, timestamp, warnings) via `meta`.

## Extension Checklist
- Add a view-model and/or shared helper in `modules/*`.
- Add an API endpoint in `web_api/routes/<domain>.py`.
- Add or reuse UI components in `web/src/components`.
- Add tests for new view-models + API routes.
- Update `AGENTS.md` if system design changes.
