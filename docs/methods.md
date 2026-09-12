# Deterministic Methods

See [banking_valuation.md](banking_valuation.md) for DCF and comparable-company
methods and [advisory_math_verification.md](advisory_math_verification.md) for
the September 2026 portfolio-history/undefined-metric corrections.

This is the formula sheet for shared analytics in
`modules/client_mgr/calculations.py` and the Markov snapshot in
`modules/client_mgr/regime.py`. Core risk fields and Hurst use unavailable
states for undefined values, not betas of 1.0 or Hurst values of 0.5. Some
legacy descriptive entropy paths still return zero for insufficient inputs;
that is an open limitation, not evidence of low uncertainty. See
[reference coverage](reference_coverage.md) for source review and remaining gaps.

## Returns and annualization

- Inputs are simple period returns `r_t`.
- Price return is `P_t / P_(t-1) - 1`, implemented with pandas fractional
  `pct_change`; it is not a percent until multiplied by 100. Current-holdings
  reconstruction is not cash-flow-adjusted historical client performance.
- GIPS-style TWR geometrically links sub-period returns
  `r = (EMV - CF) / BMV - 1`. XIRR is Newton-Raphson on dated external cash
  flows plus ending market value. Both stay unavailable without valued
  sub-periods. These are formula implementations, not a GIPS verification.
- Annualization `A` is `seconds_per_year / mean(positive timestamp deltas)`
  when a DatetimeIndex is present, otherwise `252`.
- Mean annual return is `mean(r) * A`.
- Annualized volatility is `std(r, ddof=1) * sqrt(A)`.
- Sample volatility requires at least two observations. Calendar-spacing
  annualization is not an exchange trading calendar; square-root-time scaling
  does not adjust for serial correlation. Arithmetic annual mean is not CAGR.

## Sharpe and Sortino

- Sharpe: `((mean(r) - r_f / A) / std(r, ddof=1)) * sqrt(A)`.
- Lightweight summary paths may set `r_f = 0` and record that in the payload.
- Sortino uses the full-sample downside deviation
  `sqrt(mean(min(r - r_f/A, 0)^2))`, not the standard deviation of the
  negative subset.

References: [Sharpe 1994](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm),
[pandas fractional changes](https://pandas.pydata.org/docs/reference/api/pandas.Series.pct_change.html).

## Beta, alpha, tracking

- Series are inner-joined and dropped for missing dates before any covariance.
- Beta uses sample covariance and sample variance (`ddof=1`).
- If market variance is 0, beta is omitted.
- Jensen/alpha, tracking error, information ratio, and M² use the same
  aligned window.

Reference: [Sharpe 1964](https://doi.org/10.2307/2977928).

## Drawdown and tails

- Max drawdown is `min((V_t - peak_t) / peak_t)` on `V = cumprod(1+r)`,
  with `peak_t = max(1, V_1,...,V_t)` to include the opening capital.
- Historical VaR is the left-tail return quantile `quantile(r, 1-q)`.
- CVaR is the inclusive mean of returns at or below that quantile, **not**
  `mean(r <= quantile)`, which would average booleans. Pandas uses linear
  quantile interpolation; all ties at the cutoff count in the tail mean.
- Require `0 < q < 1` and finite observations; invalid inputs are unavailable.
- These are return units, not positive loss amounts.

Background: [RiskMetrics 1996](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document).
The inclusive empirical tail convention is not a fractional-tail-weighted ES
estimator. Lotbook's 95%/99% period-return summaries do **not** implement
[Basel MAR33](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/33/inforce/2023-01-01/published/2020-06-05):
that framework requires 97.5% regulatory ES, stress calibration, liquidity
horizons, model approval and other controls. Do not use this output for capital
requirements or imply Basel compliance.

## EWMA

- Recursion: `var_t = 0.94 * var_{t-1} + 0.06 * r_t^2`.
- One-step forecast is `sqrt(var_t)`.
- Horizon `h` uses RiskMetrics random-walk scaling `σ * sqrt(h)`.
  Variance is not decayed toward zero.

Reference: [1996 RiskMetrics Technical Document](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document).

## Hurst, entropy, CUSUM

- Hurst is the R/S log-log slope. Short series return unavailable, not 0.5.
  There is no calibration offset. This implementation clips the estimated
  slope to [0,1], uses disjoint blocks and population standard deviation;
  it is a descriptive estimator, not proof of predictability.
- Shannon and permutation entropy are descriptive complexity measures.
  Insufficient inputs return unavailable (`None`), not zero. A defined zero
  remains possible for a constant series with enough observations.
- CUSUM is two-sided, with `k=0.5*s` and `h=threshold*s` (default threshold 5),
  resetting after a signal. Its mean and sample standard deviation use the
  entire input window, so this is retrospective detection, not online trading
  or a calibrated false-alarm probability.

References: [Hurst 1951](https://doi.org/10.1061/TACEAT.0006518),
[permutation entropy](https://doi.org/10.1103/PhysRevLett.88.174102),
[NIST CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm).

## Markov regime snapshot

- Returns are discretized into five quantile bins and treated as a Markov
  chain.
- `stay_probability` is the projected probability of remaining in the current
  bin at the requested horizon. It is not statistical confidence.
- Reports label this as current-state probability.

## Tax estimates

- Unrealized tax uses lot quantity, lot basis, and an available price snapshot;
  the application does not establish a licensed live quote stream.
- Unknown timestamps are excluded from term-specific tax and remain in
  total unrealized gain.
- There is no FIFO/LIFO realization or wash-sale engine.

## HHI

- Diagnostics HHI is the sum of squared **sector** shares of priced securities,
  using fractional weights (0–1), not DOJ's percentage-share 0–10,000 scale.
  It excludes manual assets and does not establish complete portfolio coverage
  when quotes are missing. Zero with no priced assets is a legacy sentinel,
  not evidence of diversification. DOJ merger thresholds do not classify a
  client's investment suitability or portfolio risk.
  Reference: [DOJ HHI](https://www.justice.gov/atr/herfindahl-hirschman-index).
