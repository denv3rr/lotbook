# Advisory dashboard and API

The default `/` workspace is advisory work: client-linked deals, contacts,
tasks and diligence records. `/clients` retains investment-account management.
`/valuation` provides DCF and `/comparables` provides trading comparables.
World is secondary: Workspace > Open World. It never opens on landing.
New advisory CLI commands are deliberately deferred.

## Local records

All routes below share existing API-key authentication. When configured,
send `X-API-Key`. This is local application access, not per-client multiuser
authorization. Do not expose this release as a hosted multiuser service.

| Route | Contract |
| --- | --- |
| GET `/api/banking/workspace` | Clients, deals, contacts, tasks, saved valuations, currency-specific summary and methodology |
| POST `/api/banking/deals` | Client, name, service, stage, owner, currency, source; optional financial estimates and target close |
| POST `/api/banking/contacts` | Client, person, relationship owner, source; optional contact information and notes |
| POST `/api/banking/tasks` | Client, title, owner, source; optional same-client deal, due date, workstream, status and notes |
| PATCH `/api/banking/{deals,contacts,tasks}/{id}` | Partial update plus required integer `expected_revision`; stale edits return 409 |
| GET `/api/banking/deals/{id}/activity` | Recorded before/after changes |
| POST `/api/banking/valuation/dcf` | Validated annual FCFF calculation, bridge, sensitivity and methodology |
| POST `/api/banking/valuation/comps` | Validated EV/revenue and EV/EBITDA peer multiples, coverage and implied value statistics |
| POST `/api/banking/valuations` | Immutable snapshot: name, client, owner, source, model_kind, original inputs; optional deal and same-client/type supersedes_id |
| GET `/api/banking/export` | Current workspace plus full activity records; includes sensitive client information |

Snapshot results are recalculated by the server. Callers cannot provide or
overwrite results. Updates and their history commit atomically. Records
cannot move between clients; linked deals and prior versions must belong to
the same client. All tables are additive in the existing SQLite database.
There is no record-deletion endpoint in this release.

Currency totals exclude closed, lost and on-hold deals. Missing values stay
unknown. Success fee = transaction value × fee_bps / 10000; weighted fee
multiplies this by the operator's close probability (decimal 0..1).
Coverage counts accompany each subtotal. These are estimates, not revenue.
Amounts accept up to 1e18 and twelve fractional decimal places, with Decimal
arithmetic and no intermediate currency rounding. UI rounds presentation.

Owner and source labels are operator-supplied. Activity history is not an
immutable compliance audit and an owner label is not an authenticated identity.
Saved models are not approved merely because they were saved.

See [valuation methods](banking_valuation.md) and
[release plan and open gates](advisory_product_plan.md).
