# AI Assistant Plan (Draft)

## Current Status
- API route `/api/assistant/query` accepts JSON payloads and returns structured responses (answer/sources/warnings/meta plus reserved nullable confidence compatibility) from a rules-based summarizer.
- Unsupported modes or questions return explicit "not implemented" payloads with a 501 status and `meta` warnings.
- Web chat drawer and CLI assistant module are implemented; persistence is still planned.
- Assistant history exports strip unsupported confidence labels and preserve support through methodology, warnings, and source lineage.

## Goals
- Provide a deterministic insight layer on top of existing analytics, news, and client data.
- Keep all calculations source-driven (no simulations, no example math).
- Support optional local model integrations without changing core outputs.

## Scope
- Summarize existing analytics (risk/regime/patterns/diagnostics) and news coverage.
- Answer questions using user data with clear citations to data sources.
- Offer explanations of metrics and anomalies without inventing values.

## Data Contracts
- Read-only access to:
  - `/api/clients`, `/api/clients/{id}`, `/api/clients/{id}/accounts/{id}`
  - `/api/intel/summary`, `/api/intel/weather`, `/api/intel/conflict`, `/api/intel/news`
  - `/api/trackers/snapshot`
  - `/api/tools/diagnostics`, `/api/settings`
- Only use JSON-ready view-models already exposed by the API.
- Do not compute new values unless backed by documented formulas in code.

## Interaction Model
- UI: floating chat drawer anchored in the top nav, expandable from any page (planned).
- CLI: shared "Ask Lotbook" command with context flags (client, account, region) (planned).
- API: `/api/assistant/query` endpoint (auth gated) that accepts:
  - `question` (string)
  - `context` (optional selectors: client_id, account_id, region, industry)
  - `sources` (optional list for news filtering)
  - `mode` (summary | explain | compare | timeline)

## Behavior Rules
- Always return structured output with:
  - `answer` (string)
  - `sources` (list of data refs + timestamps)
  - `confidence` (`null` unless a documented model or scoring contract exists)
  - `warnings` (missing data, stale cache, or blocked sources)
- No hallucinated numbers or placeholder examples.
- If inputs are missing, return "Unavailable" with a reason.
- Until the assistant is fully wired, unsupported queries return a 501 response with empty sources and explicit warnings.

## Model Options
- Default: rules-based summarizer and templated narratives over deterministic data.
- Optional: local model integration (e.g., via Ollama) for language polish only.
- Never allow the model to change numeric values, only rephrase.

## Implementation Plan
1) Add shared prompt context builder for analytics + news payloads (started).
2) Harden the API endpoint with strict schema validation and rate limits.
3) Add UI chat drawer with history + export (done; persistence planned).
4) Add CLI command that mirrors API payloads (done).
5) Add tests for schema validation and deterministic output constraints.

Lotbook is not a general multi-agent reasoning framework. Assistant behavior
stays a deterministic insight layer over existing analytics, news, and client
data. Local `AGENTS.md` / `agents/` helpers, when present, are ignored git
state. Independent verification of plans and code uses
[docs/inspection_verification.md](inspection_verification.md).
