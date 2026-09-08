# Launcher Behavior

This document summarizes launcher behavior to keep startup/stop flows reliable and non-interactive.

## Commands
- `clear` is the preferred interactive command after the one-time PowerShell
  setup documented in the root README. With no arguments it starts API + UI in
  the foreground and opens the browser.
- `.\clear` is the no-setup PowerShell form from the repository directory.
- `clear stop` stops background services and verifies port release.
- `clear cli` launches the CLI.
- `python clear_bootstrap.py start` is the explicit automation/CI form when
  automatic verified dependency bootstrap is desired.

Running `clear_bootstrap.py` without a subcommand is equivalent to `start`. The
standard-library bootstrap changes to the repository root before importing the
application and installs approved runtime dependencies from the hash-verified
`requirements-web.lock` only when they are missing. Startup flags can be passed
without repeating the subcommand, such as `clear --detach --no-open`;
`--no-install` makes missing dependencies a hard stop instead. Normal starts
reuse the existing environment, and Vite compiles changed frontend modules
incrementally. No manual production build is required for local use.

`requirements-web.in` is the reviewed direct-pin source for the launcher lock.
After an approved runtime pin change, regenerate it with
`python -m piptools compile --generate-hashes --resolver=backtracking
--strip-extras --output-file requirements-web.lock requirements-web.in`; the
test suite checks that these pins remain aligned with `requirements.txt`.

PowerShell reserves `clear` as a built-in terminal-clearing alias. The explicit
`.\clear.ps1 install-command` setup replaces that alias in the current-user
profile with the Clear launcher. `Clear-Host` and `cls` remain available, and
the command can be run from any working directory. The setup can be rerun
safely to refresh the checkout path.

## Startup Guarantees
- Startup performs API health checks and fails fast if the API cannot come up.
- UI launch waits for API health before opening the UI.
- Startup cleans stale PID files and attempts to clear occupied ports.
- `.env` is loaded for API credentials and feed detection.

## Shutdown Guarantees
- Stop attempts to terminate process trees and verify port release.
- Shutdown handlers keep running on Ctrl+C to prevent orphan processes.

### Dashboard Close app

Restart through the updated launcher (without `--reload`) to enable Close app.
The confirmation requires local access, API authentication when configured,
an explicit confirmation payload/header and the current UI origin. Unmanaged
or reload-mode servers fail closed rather than killing ports indiscriminately.
Uvicorn drains active requests (10-second ASGI grace period) before its owned
UI tree is stopped. Slow in-flight provider/worker work can take longer than
an idle shutdown; the UI reports a request, not an unverified completed close.
Tracker refresh runs off the event loop so it cannot block that request.

Per-launch records under `data/runtime/stack-*.json` bind API/UI PIDs and
creation times and retain observed descendants for orphan cleanup. The
foreground launcher yields to managed cleanup rather than racing it. Failure
is recorded and produces a nonzero server exit. Browser tabs are not forcibly
closed; saved records stay on disk. Never kill unrelated processes by port.

Acceptance: from `web`, run `npx playwright test --config playwright.advisory.config.ts`.
This uses ports 18080/15173, refuses occupied ports, invokes the real foreground
launcher and stores disposable databases under ignored `test_runtime`.
The default browser suite excludes these mutating tests. No operator database
is used. Test runtime artifacts are retained locally for diagnosis.

## Diagnostics
- `clear status` reports health and running processes.
- `clear doctor` validates deps, ports, and health checks.
