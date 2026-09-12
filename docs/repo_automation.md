# Repo Automation

This document describes GitHub automation for a personal public clone of
Lotbook (`denv3rr/clear`). It is operator setup, not a claim that the remote
already has every control enabled.

Related files:

- `.github/dependabot.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/CODEOWNERS`
- `SECURITY.md`
- `docs/security_verification.md`

## Dependabot

`.github/dependabot.yml` runs weekly updates for:

- pip at `/`
- npm at `/web`
- github-actions at `/`

Security updates and version updates are grouped so one PR can carry a set of
related bumps. Open-PR limits are 8 for pip/npm and 4 for Actions.

Enable in the GitHub UI if the tab is empty:

1. Repository **Settings → Advanced Security** (or **Code security**).
2. Turn on **Dependabot alerts**.
3. Turn on **Dependabot security updates**.
4. Leave **Dependabot version updates** on once the YAML is on the default
   branch.

Do not put registry tokens or secrets in the YAML. Private feeds are out of
scope.

## CI

`.github/workflows/ci.yml` runs on push and pull request to `main`, and on
manual `workflow_dispatch`.

Jobs:

| Job | When | What |
| --- | --- | --- |
| `python` | every CI run | `pip install -r requirements.txt` then `python -m pytest` |
| `web` | every CI run | `npm ci` in `web/` then `npm run build:check` |
| `playwright` | workflow_dispatch only, when the Playwright input is true | browser suite |

Permissions are `contents: read`. Playwright stays opt-in because it needs
browsers and a live local stack.

## CodeQL

CI Python skips `PySide6` / `PySide6-WebEngine` because those desktop
wheels are not needed for pytest and are not reliably available on
`ubuntu-latest`. The web job runs `npm run build` before the bundle
budget check.

`.github/workflows/codeql.yml` analyzes `python` and
`javascript-typescript` on push/PR to `main`, weekly, and on
`workflow_dispatch`. It writes `security-events` only.

CodeQL results belong in the Security tab. Do not treat a green CodeQL job
as a pentest.

## Branch Protection (Personal Public Repo)

These rules are not stored in YAML. They were applied to `main` on
2026-08-18 via the GitHub API: pull-request reviews enabled with 0 required
approvals (solo owner is not deadlocked), stale reviews dismissed, force
pushes blocked, deletions blocked, admin enforcement off.

Tighten later in **Settings → Branches**:

1. Require the `python` and `web` CI jobs after they have run once.
2. Do not require the opt-in `playwright` job.
3. Optionally require conversation resolution and linear history.

If the UI shows names like `CI / python`, require those exact names.

## How To Read The GitHub Security Tab

Open **Security** on the repository.

| Panel | Use |
| --- | --- |
| Overview | Counts for Dependabot, code scanning, and secret scanning |
| Dependabot | Per-alert package, manifest, severity, GHSA, and state (`open`, `fixed`, `auto_dismissed`) |
| Code scanning | CodeQL findings; filter by language and severity |
| Secret scanning | Accidental credential detections |
| Advisories | Private vulnerability reports (`SECURITY.md`) |

When reviewing a Dependabot alert:

1. Open the alert and read the GHSA, not only the package name.
2. Confirm the remediating version is pinned in `requirements.txt` or
   `web/package.json` / `web/package-lock.json`.
3. Remember GitHub marks the alert **fixed** only after that pin is on the
   default branch.
4. Do not paste secrets, `.env` values, or exploit payloads into the alert
   thread.

The 36-alert target list lives in `docs/security_verification.md`.
