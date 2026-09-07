# Portfolio math corrections - September 2026

This is bounded regression evidence, not a certification of all financial
analytics, provider data or suitability for a particular investment decision.

- Opening wealth participates in maximum drawdown; an initial loss is not zero.
- Undefined benchmark beta leaves alpha and R-squared unavailable. Aligned
  observations drive benchmark-relative annualized metrics.
- Constant series do not receive a fabricated Hurst exponent.
- A held benchmark security remains part of the portfolio. Missing holdings
  fail closed instead of silently shrinking the modeled portfolio.
- History aggregation intersects observed timestamps across all holdings;
  no positional date matching, partial-coverage values, or forward-filled
  prices. Fixed-current-holdings reconstruction is not actual account return.
- Purchase-inclusive lot value history is not used as a return series for
  regime analysis.
- Dashboard combined totals are unavailable for non-USD manual holdings
  without reviewed FX conversion. Native holding amounts remain visible.
- US long-term holding classification uses more than one calendar year,
  not an inclusive 365-day threshold. See [IRS Publication 550](https://www.irs.gov/publications/p550).

Deterministic arithmetic examples are unit evidence only. The full Python
suite passed 319 tests before subsequent advisory/shutdown additions; rerun
the suite for final release evidence.

Still open: reviewed market-price currency coverage, cash-flow-adjusted
account performance, comprehensive tax modeling and remaining legacy manual
asset/report aggregation paths. No claim of portfolio-wide math certification.
