# Lotbook
![GitHub Created At](https://img.shields.io/github/created-at/denv3rr/clear) ![GitHub repo size](https://img.shields.io/github/repo-size/denv3rr/clear)

A local-first advisory and client-management workspace with portfolio
analytics and supporting OSINT.

See [advisory/API guide](docs/banking_api.md), [valuation methods](docs/banking_valuation.md)
and [product readiness gates](docs/advisory_product_plan.md). This is not a
certified, hosted investment-banking platform; material production gates remain.

## Agents
This is not a general multi-agent reasoning framework. Agent git rules and
assistant constraints are the seed of governed helper work; independent
inspection is documented in
[docs/inspection_verification.md](docs/inspection_verification.md).

The dashboard opens on client relationships,
deal pipeline and next actions. It includes DCF, trading comparables and saved
valuation versions; World remains available from the Workspace menu.
Dashboard and API development take priority; new advisory CLI parity is deferred.

## Configuration and Quick Start

### Clone

```pwsh
git clone git@github.com:denv3rr/clear.git --depth 1
cd clear
```

### Configure `.env`

Copy `.env.example` to `.env`. The most common variables are below.

| Variable | Purpose |
| --- | --- |
| `LOTBOOK_WEB_API_KEY` | Enables API key auth for the web/API stack. |
| `FINNHUB_API_KEY` | Optional market symbol and quote lookups. |
| `OPENSKY_CLIENT_ID` | OpenSky OAuth client id for flight feeds. |
| `OPENSKY_CLIENT_SECRET` | OpenSky OAuth client secret for flight feeds. |
| `SHIPPING_DATA_URL` | Optional vessel/shipping feed endpoint. |
| `LOTBOOK_INCLUDE_COMMERCIAL` | Include commercial flights when set to `1`. |
| `LOTBOOK_INCLUDE_PRIVATE` | Include private flights when set to `1`. |

### Start with one command

From the repository directory:

```pwsh
.\lotbook
```

On Command Prompt, use `lotbook`. On macOS or Linux, use `./lotbook.sh`.

To launch from any directory, run this one-time setup from the repository
directory:

```pwsh
.\lotbook.ps1 install-command
```

Open a new PowerShell session, then the normal workflow is:

```pwsh
lotbook
lotbook status
lotbook stop
```

The setup installs a `lotbook` function in the current-user PowerShell profile
and leaves the terminal `clear` command unchanged. Rerun the setup command if
the checkout is moved. If an older Clear launcher was installed, this setup
removes it.

Optional startup flags can follow the command directly—for example,
`lotbook --detach --no-open`. Use `lotbook --no-install` when you want startup to
fail instead of installing a missing hashed/locked dependency.

The standard-library bootstrap installs missing approved web/API runtime
dependencies from the hash-verified `requirements-web.lock` only when needed,
starts the API and web UI, waits for health checks, and opens the application.
Vite compiles the frontend incrementally, so normal starts do not require a
manual `npm run build` or rebuild the application from scratch.

## What It Does

- Stores client, account, holding, and lot data in SQLite, with JSON kept for
  import/export.
- Delivers advisory workflows through the dashboard and FastAPI; existing
  portfolio analytics remain available in the CLI, with new CLI parity deferred.
- Runs OSINT workflows for trackers, news, and regional intel through the
  secondary Workspace menu and `/osint` deep link.
- Supports reports and exports with shared view-models and provenance metadata.
- Plans richer navigable World maps behind the active source and standards
  gates; advisory/client management remains the landing workspace.

## Stack

- Core runtime: Python, FastAPI, SQLAlchemy, Pandas, NumPy, Rich
- Web app: React, TypeScript, Vite, Tailwind
- Visualization: Three.js, React Three Fiber, MapLibre, Leaflet fallback,
  Plotly, Recharts
- Testing: pytest, Playwright

Notes:

- OpenSky is the only flight feed path right now.
- When `LOTBOOK_WEB_API_KEY` is set, the launcher forwards it to the web UI as
  `VITE_API_KEY` for local auth.
- Additional tracker/feed flags and OSINT notes live in
  [docs/osint.md](docs/osint.md).

## Common Commands

```pwsh
lotbook
lotbook status
lotbook stop
```

```pwsh
lotbook cli
lotbook doctor
lotbook logs
```

Without the optional PowerShell command setup, use the same arguments with
`.\lotbook`, for example `.\lotbook doctor`. Use `python lotbook_bootstrap.py start`
for automation that should retain the same verified dependency bootstrap.

## Testing

```pwsh
python -m pytest
```

```pwsh
cd web
npx playwright test
```

Browser-test policy:

- Positive-path browser tests must use the real local stack or captured real
  fixtures with provenance.
- Demo/mock/synthetic positive-path browser data is not allowed.

## Data Sources

| Source | Purpose |
| --- | --- |
| Finnhub | Optional symbol/quote lookups |
| Yahoo Finance | Historical pricing and macro snapshots |
| OpenSky | Flight tracking |
| Open-Meteo | Weather context for intel/reporting |
| GDELT | Conflict/news signal input |
| RSS feeds | Cached headlines for market and OSINT workflows |

Next-phase reviewed source intake is tracked in
[docs/feed_registry.md](docs/feed_registry.md) and
[docs/osint_globe_phase_2_plan.md](docs/osint_globe_phase_2_plan.md).

## Methods Snapshot

The core deterministic formulas are implemented in
[modules/client_mgr/calculations.py](modules/client_mgr/calculations.py).

| Metric | Formula used in code | Notes | Source |
| --- | --- | --- | --- |
| Annualization factor | `A = seconds_per_year / mean(delta_t)` or `252` fallback | Uses timestamp spacing when available. | [calculations.py](modules/client_mgr/calculations.py) |
| Mean annual return | `mean(r) * A` | Used in core and risk metrics. | [calculations.py](modules/client_mgr/calculations.py) |
| Annualized volatility | `std(r, ddof=1) * sqrt(A)` | Sample standard deviation; unavailable with fewer than two observations. | [Sharpe 1994](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm) |
| Sharpe ratio | `((mean(r) - r_f / A) / std(r)) * sqrt(A)` | Sample std (`ddof=1`). Lightweight paths may use `r_f = 0`; undefined variability is unavailable. | [Sharpe 1994](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm) |
| Sortino ratio | `(mean(r) - r_f / A) / downside_dev * sqrt(A)` | `downside_dev = sqrt(mean(min(r - r_f/A, 0)^2))` over all periods. | [calculations.py](modules/client_mgr/calculations.py) |
| Beta | `cov(r_p, r_m, ddof=1) / var(r_m, ddof=1)` | Aligned series only. Missing market variance is unavailable, not 1.0. | [Sharpe 1964 CAPM paper](https://doi.org/10.2307/2977928) |
| Max drawdown | `min((V_t - peak_t) / peak_t)`, `peak_t = max(1, V_1,...,V_t)` | Includes initial capital before the first return; empty is unavailable. | [calculations.py](modules/client_mgr/calculations.py) |
| Historical VaR / CVaR | `quantile(r, 1-q)` and `mean({r_t : r_t <= VaR_q})` | Inclusive left-tail *return* mean, not the mean of a boolean mask or Basel regulatory ES. | [methods and conventions](docs/methods.md) |
| EWMA volatility | `var_t = λ var_{t-1} + (1-λ) r_t^2` | `λ = 0.94`. Multi-step forecast is `σ * sqrt(h)`. | [1996 RiskMetrics Technical Document](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document) |

Additional deterministic methods in the same module include Black-Scholes,
Shannon entropy, permutation entropy, Hurst exponent, FFT spectrum, CUSUM
change points, motif similarity, and CAPM-derived metrics. Their validation
lives in the Python test suite rather than in the README.

## Docs

| Doc | Purpose |
| --- | --- |
| [docs/README.md](docs/README.md) | Full docs index |
| [docs/agent_git_standards.md](docs/agent_git_standards.md) | Branch, commit, merge, push, and sensitive-file rules for agents |
| [docs/inspection_verification.md](docs/inspection_verification.md) | Independent corpus-bound inspectors and whole-repo guardrail scan |
| [docs/us_gov_standards.md](docs/us_gov_standards.md) | Mandatory standards baseline |
| [docs/standards_remediation_plan.md](docs/standards_remediation_plan.md) | Active standards gate and phase plan |
| [docs/visual_modernization_plan.md](docs/visual_modernization_plan.md) | Advisory-first UX and secondary World roadmap |
| [docs/globe_layout_notes.md](docs/globe_layout_notes.md) | Researched HUD layout applied to the World globe |
| [docs/osint_globe_phase_2_plan.md](docs/osint_globe_phase_2_plan.md) | Detailed next-phase OSINT/globe execution plan |
| [docs/osint.md](docs/osint.md) | OSINT workspace and feed notes |
| [docs/assistant_usage.md](docs/assistant_usage.md) | Assistant usage across CLI/API/web |
| [docs/launchers.md](docs/launchers.md) | Startup and shutdown behavior |
| [docs/methods.md](docs/methods.md) | Shared deterministic formula sheet |
| [docs/security_verification.md](docs/security_verification.md) | Isolated security suite scope and Dependabot remediations |
| [docs/repo_automation.md](docs/repo_automation.md) | Dependabot, CI, CodeQL, and branch protection |

## Sources

### Standards And Governance

Reviewed September 9, 2026. [Reference coverage](docs/reference_coverage.md)
maps every item below to implementation, tests and remaining gaps. These are
engineering references, not certification or complete regulatory compliance.

- NIST SP 800-218, SSDF v1.1:
  https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-53 Rev. 5, including catalog release 5.2.0:
  https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-160 Vol. 1 Rev. 1, Engineering Trustworthy Secure Systems:
  https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final
- NIST AI RMF 1.0:
  https://www.nist.gov/itl/ai-risk-management-framework
- Revised Section 508 Standards:
  https://www.access-board.gov/ict/
- MIL-STD-882E with Change 1 (2023):
  https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027

### Methods And Risk References

- Fractional price-return implementation (pandas):
  https://pandas.pydata.org/docs/reference/api/pandas.Series.pct_change.html
- Sharpe ratio, William F. Sharpe (1994):
  https://web.stanford.edu/~wfsharpe/art/sr/SR.htm
- RiskMetrics (1996), historical VaR and EWMA background:
  https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document
- U.S. DOJ HHI overview:
  https://www.justice.gov/atr/herfindahl-hirschman-index
- NIST/SEMATECH CUSUM reference:
  https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm
- CAPM reference:
  https://doi.org/10.2307/2977928
- Permutation entropy reference:
  https://doi.org/10.1103/PhysRevLett.88.174102
- Hurst exponent reference:
  https://doi.org/10.1061/TACEAT.0006518
- Basel Framework MAR33, current regulatory ES background (not implemented):
  https://www.bis.org/committees/bcbs/basel-framework/standard/mar/33/inforce/2023-01-01/published/2020-06-05

### Data And Feeds

- Finnhub: https://finnhub.io/
- Yahoo Finance: https://finance.yahoo.com/
- OpenSky: https://opensky-network.org/about
- Open-Meteo: https://open-meteo.com/
- GDELT: https://www.gdeltproject.org/
- FRED: https://fred.stlouisfed.org/
- U.S. Treasury rates data:
  https://home.treasury.gov/resource-center/data-chart-center/interest-rates
- CFTC education:
  https://www.cftc.gov/LearnAndProtect

### Current Default News Sources

- CNBC: https://www.cnbc.com/
- MarketWatch: https://www.marketwatch.com/
- BBC Business: https://www.bbc.com/business

## Disclaimer

This project is for informational and operational analysis use. It does not
provide financial, legal, or tax advice, and no content here should be treated
as an offer to buy or sell securities.
