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
| POST `/api/banking/valuation/wacc` | Operator-supplied weights and rates; after-tax cost of debt and WACC |
| POST `/api/banking/valuation/capital-structure` | Net debt and optional enterprise value from supplied cash, debt and equity |
| POST `/api/banking/valuation/debt-schedule` | Linked beginning/ending balances, interest, paydowns and cash sweeps |
| POST `/api/banking/valuation/statements` | Linked income, cash flow and balance sheet; unbalanced sheets fail closed |
| POST `/api/banking/valuation/merger` | Pro forma EPS and accretion/dilution from supplied NI, shares and synergies |
| POST `/api/banking/valuation/lbo` | MOIC and XIRR from sponsor equity and exit equity |
| POST `/api/banking/valuation/precedent` | Transaction multiples with coverage; no invented premiums |
| POST `/api/banking/valuation/bond` | Price, Macaulay/modified duration and convexity for whole coupon periods |
| POST `/api/banking/valuation/option` | European BSM plus zero-tenor and zero-vol boundaries |
| POST `/api/banking/intake` | Statement/peer/precedent intake with source document, period, currency, units, restatement and review status |
| POST `/api/banking/parties` | Deal party; NDA status never grants document access |
| POST `/api/banking/bids` | Party bid on the same deal and client |
| POST `/api/banking/documents` | Version metadata only; no file blob in this release |
| POST `/api/banking/approvals` | Pending/approved/rejected decision record |
| POST `/api/banking/valuations` | Immutable snapshot: name, client, owner, source, model_kind, original inputs; optional deal and same-client/type supersedes_id |
| GET `/api/clients/{id}/positions` | Recorded lots and cash; no market fetch |
| PUT `/api/clients/{id}/accounts/{id}/positions` | Single-ticker lot/quantity/delete with revision compare-and-swap |
| PUT `/api/clients/{id}/accounts/{id}/cash` | Recorded cash correction |
| POST `/api/clients/{id}/accounts/{id}/transactions` | Buy/sell/deposit/withdrawal/fee/transfer/dividend/split |
| POST `/api/clients/{id}/accounts/{id}/transactions/import` | Preview unless `confirm=true` |
| GET `/api/clients/{id}/accounts/{id}/performance` | Realized P&L and fees from the ledger; TWR/XIRR unavailable without an ending market value |
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
