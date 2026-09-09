# Production readiness and local recovery

Status: September 9, 2026. **Not approved as a fully production-ready banking
platform.** This pass provides a navigable World map and local database recovery
capabilities; it does not establish multiuser identity, firm isolation or a
complete transaction-modeling and execution product.

## Release boundary

The intended first deployment still needs confirmation: one-operator desktop,
self-hosted team server, or hosted multi-firm service. Current optional shared
API-key access and operator-entered names are not individual identity or client
authorization. Do not expose this build to an untrusted network or treat local
activity history as tamper-proof audit evidence.

| Area | Implemented evidence / remaining release gate |
| --- | --- |
| Advisory | Client, contacts, mandates, tasks, revisions and activity workflows; party-level bids, NDA/access responsibilities, documents and approvals remain incomplete. |
| Valuation | Annual FCFF DCF, comparables, sensitivity and immutable saved assumptions; verified financial intake, precedents, merger/sponsor/capital structure models and independent model approvals remain incomplete. Formula tests are not data verification or investment advice. |
| Loading | Profile reuse, request cancellation and deferred patterns; no provider latency SLA or licensed live quote streaming. |
| World | Navigable historical basemap, reviewed country context and operator viewport AOIs; no precise incident geometry, live imagery or simulated observations. |
| Safe Close | Real isolated launcher test checks owned process identities, descendants, listeners and stopped control state; active-work drain and hardware performance need deployment-specific evidence. |
| Recovery | Encrypted canonical SQLite snapshot and verified new-file restore; a production-sized activation drill, backup schedule, retention, off-device storage and owner remain required. |
| Security / operations | Existing API-key and source gates retained. Individual roles, per-client/firm authorization, TLS deployment, protected secrets/audit, incident response, retention and operations acceptance remain release blockers. |

## Create an encrypted backup

1. Run the local managed launcher and configure `CLEAR_WEB_API_KEY` and the UI
   key. Open System, then **Download encrypted backup**.
2. Supply and repeat a unique 12-128 character passphrase, then confirm. Store
   it separately: there is no passphrase recovery service.
3. Protect the downloaded `.clearbackup` file and verify a recovery candidate
   before relying on it. A download starting is not proof of durable storage.

The API is `POST /api/application/backup`, authenticated with `X-API-Key`,
explicit `X-Clear-Backup: confirm`, and JSON `{ "confirm": true, "passphrase":
"..." }`. It requires loopback access and a configured key even when other
local API routes are open. No caller-supplied database path is accepted. One
snapshot per process is allowed at a time; response caching is disabled.

The SQLite online backup API includes committed WAL content and checks database
and foreign-key integrity. Archive format 1 uses AES-256-GCM with a random
16-byte Scrypt salt (N=32768, r=8, p=1), 12-byte nonce and authenticated format
header; encrypted metadata includes timestamp, scope and database SHA-256.
Export is limited to 64 MiB with a bounded snapshot copy. It includes canonical
database tables only, not credentials, external document files, browser AOIs,
feed caches or deployment configuration. Temporary plaintext exists during
snapshot/recovery: use a protected local OS account, restrictive temp-directory
permissions and full-disk encryption. Cleanup is not secure erasure, and this
implementation is not a FIPS validation claim.

## Verify without replacing the running database

From the repository root, with dependencies installed:

```powershell
python scripts/stage_recovery.py C:\Backups\snapshot.clearbackup C:\Recovery\candidate.db
```

Use an existing protected destination directory and a **new** filename. The
passphrase is prompted without echo; do not put it in command arguments or logs.
The helper authenticates the archive, checks its digest and SQLite integrity,
then atomically creates the candidate without overwriting any existing path.
Hard-link creation requires a supporting local filesystem; failures leave the
destination unchanged. The recovered candidate is plaintext and needs the same
protection as the live database. This helper does not activate it.

Before any real activation, schedule downtime, use Close safely and verify all
owned processes stopped, preserve the original database **and WAL/SHM companions**,
verify candidate schema/app version and expected record counts, and perform a
documented restore drill in an isolated runtime. Never swap a running SQLite
file or blindly copy only its main file. Activation paths, rollback, retention
and recovery-time/data-loss objectives require an approved deployment runbook;
this release deliberately has no in-place restore endpoint.

## Verification scope

`tests/test_recovery.py` covers actual SQLite roundtrip, committed WAL, size and
foreign-key failures, tamper/wrong-passphrase rejection, non-overwrite and API
authentication/locality/confirmation gates. The disposable launcher browser
suite downloads an archive from System and decrypts/opens a new candidate.
Run browser mutations only with `web/playwright.advisory.config.ts`, never the
ordinary operator-data configuration. Screenshot inspection and automated
checks are not accessibility, security or financial-model certification.

Next bounded work: confirm deployment boundary; implement source-verified
financial intake plus versioned model review; complete transaction party /
document / approval workflows; then authorization and an operations recovery
drill appropriate to that deployment. Do not mark these gates complete from
map screenshots or passing unit tests.
