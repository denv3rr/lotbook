# API Contracts

Advisory/valuation contracts: [banking_api.md](banking_api.md).

This document summarizes core API contracts and shared response expectations.

## Conventions
- JSON responses include a `meta` payload (route, source, timestamp, warnings).
- When `CLEAR_WEB_API_KEY` is set, `X-API-Key` is required.
- Payloads must be JSON-ready view-models (no SQLAlchemy objects).

## Core Routes
- `/api/clients` (list + create)
- `/api/clients/{id}` (detail)
- `/api/clients/{id}/accounts/{id}` (account detail)
- `/api/clients/{id}/positions` (recorded lots and cash)
- `/api/clients/{id}/accounts/{id}/transactions` (cash-flow events)
- `/api/banking/valuation/wacc` (assumption-driven WACC)
- `/api/tools/diagnostics` (system + feed health)
- `/api/settings` (configuration status)
- `/api/trackers/snapshot` (tracker health)
- `/api/intel/news` (news with filters)
- `/api/assistant/query` (assistant responses)

## Validation
- Enforce schema validation for write endpoints.
- Reject partial payloads where required fields are missing.
- Surface warnings in `meta` for stale or incomplete data.
