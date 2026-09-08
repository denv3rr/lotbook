# Security Verification

This document records the defensive security checks used in this repo. It is
an internal engineering record, not a certification package.

**This is not a formal penetration test.** It does not authorize offensive
testing, exploit development, or claims of FedRAMP, DoD, PCI, or third-party
audit status. Findings here are fail-closed contract checks, dependency
hygiene, and documented GitHub Dependabot remediations.

## Scope

In scope:

- API key comparison and HTTP/WebSocket rejection when
  `CLEAR_WEB_API_KEY` is set
- Localhost-only CORS
- Assistant filesystem/path and entry-scope guards
- Destructive maintenance and duplicate-cleanup confirm gates
- The 36 GitHub Dependabot alerts targeted by the current pip/npm pins

CodeQL follow-up on PRs 14 and 31:

- Browser API-key values are encrypted before session/local storage. A
  non-extractable AES-GCM key is stored through IndexedDB so an operator's
  selected persistence scope survives navigation and reloads; legacy
  clear-text browser values are discarded and must be re-entered. There is no
  server-side token vault, and this is storage-at-rest hardening rather than a
  defense against already-authorized same-origin script execution.
- HTTP requests and the WebSocket subprotocol await key recovery before they
  connect. This corrects the merged PR 31 regression where the asynchronous
  decrypt operation could be coerced into an invalid header or protocol value.
- First-use key creation is atomic within one IndexedDB read/write transaction,
  so concurrent tabs cannot overwrite one another's encryption key. Persistent
  storage failures are shown to the operator and do not close the settings
  dialog. Session-only entry can fall back to page memory with an explicit
  warning when encrypted browser storage is unavailable.
- Route handlers no longer interpolate exception objects into API warnings.
  Failures are logged server-side and the client sees a generic unavailable
  message.

Out of scope:

- Offensive scanning, exploit proof-of-concepts, or payload construction
- Remote or third-party systems
- Formal residual-risk scoring or authority-to-operate evidence
- Runtime secrets, `.env` values, or live operator data

## Methodology

1. Re-skim `docs/us_gov_standards.md` and `docs/agent_git_standards.md`.
2. Exercise negative-path tests only. Invalid or incomplete credentials,
   confirm flags, origins, and assistant questions are used solely to prove
   rejection. No fabricated successful business data is introduced.
3. Prefer isolated unit/route checks (`web_api.auth._keys_match`, FastAPI
   `TestClient`, summarizer guards). Client write paths are not used unless a
   later test requires the isolated temp-DB pattern in
   `tests/test_web_api_clients.py`.
4. Record dependency remediations from GitHub Dependabot alert numbers and
   the versions actually pinned in `requirements.txt` and `web/package.json`.
5. Do not invent secrets, CVE narratives, or unreviewed advisory IDs.

The automated suite is:

```pwsh
python -m pytest tests/test_security.py
cd web
npm run typecheck
```

That file covers:

- `hmac.compare_digest` through `web_api.auth._keys_match` (match, mismatch,
  empty/missing)
- `/api/health` and `/api/clients` return 401 when the key is missing, empty,
  or wrong
- `/ws/trackers` rejects a missing subprotocol and does not accept
  `?api_key=`
- CORS allows `http://127.0.0.1:5173` and does not reflect
  `https://evil.example`
- Assistant queries that name `/etc/passwd` or `C:/Windows` are denied
- Clients entry with region-only context is not a scope denial; dashboard
  entry with `client_id` is denied
- Maintenance and `/api/clients/duplicates/cleanup` reject `confirm=false`

## NIST Mapping

This verification implements the repo's internal baseline. It does not claim
that the product is assessed against these publications.

| Practice | Source | Repo evidence |
| --- | --- | --- |
| Review and update dependencies; track known defects | NIST SP 800-218 SSDF PW.4, PW.7, RV.1 | Dependabot config, 36-alert pin list below, `docs/repo_automation.md` |
| Verify software with automated tests before release | NIST SP 800-218 SSDF PW.8, PW.7 | `tests/test_security.py`, `.github/workflows/ci.yml` |
| Authenticator management and least privilege | NIST SP 800-53 IA-5, AC-3, AC-6 | `CLEAR_WEB_API_KEY` fail-closed HTTP/WebSocket checks |
| Transmission confidentiality and origin restriction | NIST SP 800-53 SC-8, SC-7, AC-4 | Localhost CORS regex; non-local origin not reflected |
| Input validation and information-flow control | NIST SP 800-53 SI-10, AC-4 | Assistant path and entry-scope guards |
| Least functionality / fail-safe defaults | NIST SP 800-53 CM-7, SI-17, CP-12 | Confirm payloads required before destructive routes |
| Flaw remediation and monitoring | NIST SP 800-53 SI-2, RA-5, CA-7 | Dependabot + CodeQL + Security tab review |

Related baseline documents: `docs/us_gov_standards.md`,
`docs/standards_remediation_plan.md`, `SECURITY.md`.

## 36 Dependabot Remediations

GitHub listed 36 open Dependabot alerts against `denv3rr/clear` at the start
of this audit. They are targeted by the pins below. GitHub will not mark an
alert fixed until the remediating commit is on the default branch.

Direct pins:

| Ecosystem | Package | Remediation |
| --- | --- | --- |
| pip | cryptography | `50.0.0` |
| pip | requests | `2.33.0` |
| pip | python-dotenv | `1.2.2` |
| pip | pytest | `9.0.3` |
| npm | react-router-dom | `7.18.x` (lockfile `7.18.2`) |
| npm | vite | `7.3.5+` (lockfile `7.3.6`) |
| npm | postcss | `8.5.23+` (lockfile `8.5.26`) |
| npm | protocol-buffers-schema | override `3.6.1` |
| npm | picomatch | override `4.0.4` |
| npm | @babel/core | override `7.29.6` |

Alert inventory (advisory titles only; no exploit steps):

| # | Package | Severity | GHSA | Targeted by |
| --- | --- | --- | --- | --- |
| 1 | cryptography | high | GHSA-r6ph-v2qm-q3c2 | cryptography 50.0.0 |
| 2 | requests | medium | GHSA-gc5v-m9x4-r6x2 | requests 2.33.0 |
| 3 | cryptography | low | GHSA-m959-cc7f-wv43 | cryptography 50.0.0 |
| 4 | cryptography | medium | GHSA-p423-j2cm-9vmq | cryptography 50.0.0 |
| 5 | pytest | medium | GHSA-6w46-j5rx-g56g | pytest 9.0.3 |
| 6 | python-dotenv | medium | GHSA-mf9w-mj56-hr94 | python-dotenv 1.2.2 |
| 7 | cryptography | high | GHSA-537c-gmf6-5ccf | cryptography 50.0.0 |
| 8 | cryptography | high | GHSA-g6cj-pr64-35w5 | cryptography 50.0.0 |
| 9 | cryptography | high | GHSA-jwv3-5hgf-82ww | cryptography 50.0.0 |
| 10 | cryptography | medium | GHSA-m2h6-j472-rp4c | cryptography 50.0.0 |
| 11 | react-router | high | GHSA-8v8x-cx79-35w7 | react-router-dom 7.18.x |
| 12 | react-router | high | GHSA-2w69-qvjg-hvjx | react-router-dom 7.18.x |
| 13 | react-router | medium | GHSA-h5cw-625j-3rxh | react-router-dom 7.18.x |
| 16 | picomatch | medium | GHSA-3v7f-55p6-f55p | picomatch 4.0.4 |
| 17 | vite | high | GHSA-p9ff-h696-f583 | vite 7.3.5+ |
| 18 | vite | high | GHSA-v2wj-q39q-566r | vite 7.3.5+ |
| 19 | vite | medium | GHSA-4w7w-66w2-5vf9 | vite 7.3.5+ |
| 20 | protocol-buffers-schema | medium | GHSA-j452-xhg8-qg39 | protocol-buffers-schema 3.6.1 |
| 21 | postcss | medium | GHSA-qx2v-qp2m-jg93 | postcss 8.5.23+ |
| 22 | react-router | medium | GHSA-f22v-gfqf-p8f3 | react-router-dom 7.18.x |
| 23 | react-router | high | GHSA-8646-j5j9-6r62 | react-router-dom 7.18.x |
| 24 | react-router | medium | GHSA-2j2x-hqr9-3h42 | react-router-dom 7.18.x |
| 25 | react-router | high | GHSA-49rj-9fvp-4h2h | react-router-dom 7.18.x |
| 26 | react-router | high | GHSA-8x6r-g9mw-2r78 | react-router-dom 7.18.x |
| 27 | react-router | high | GHSA-rxv8-25v2-qmq8 | react-router-dom 7.18.x |
| 28 | @babel/core | low | GHSA-4x5r-pxfx-6jf8 | @babel/core 7.29.6 |
| 29 | vite | high | GHSA-fx2h-pf6j-xcff | vite 7.3.5+ |
| 30 | vite | medium | GHSA-v6wh-96g9-6wx3 | vite 7.3.5+ |
| 31 | postcss | high | GHSA-6g55-p6wh-862q | postcss 8.5.23+ |
| 32 | react-router | medium | GHSA-337j-9hxr-rhxg | react-router-dom 7.18.x |
| 33 | react-router | medium | GHSA-h8fp-f39c-q6mh | react-router-dom 7.18.x |
| 34 | react-router | medium | GHSA-jjmj-jmhj-qwj2 | react-router-dom 7.18.x |
| 35 | react-router | medium | GHSA-wrjc-x8rr-h8h6 | react-router-dom 7.18.x |
| 36 | react-router | high | GHSA-chx6-hx7r-mcp5 | react-router-dom 7.18.x |
| 37 | postcss | high | GHSA-r28c-9q8g-f849 | postcss 8.5.23+ |
| 38 | postcss | medium | GHSA-fxqj-rqcc-2cmp | postcss 8.5.23+ |

Adjacent GitHub states that are not part of the 36 open-alert target:

- #14 rollup already fixed
- #15 picomatch ReDoS auto-dismissed
- #40 and #41 nanoid auto-dismissed after the postcss/nanoid lift

## Residual Limits

- Alert closure is a GitHub default-branch event, not a local pytest result.
- Dev-server advisories (Vite, PostCSS source maps) mainly affect local
  `npm run dev`, not the production API.
- Assistant path guards are deny-lists for common filesystem tokens, not a
  sandbox.
- Auth is a shared API key when set. There is no per-user session model yet.
