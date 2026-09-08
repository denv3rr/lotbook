# Deterministic Methods

See [banking_valuation.md](banking_valuation.md) for DCF and comparable-company
methods and [advisory_math_verification.md](advisory_math_verification.md) for
the September 2026 portfolio-history/undefined-metric corrections.

This is the formula sheet for shared analytics in
`modules/client_mgr/calculations.py` and the Markov snapshot in
`modules/client_mgr/regime.py`. Empty or insufficient inputs return an
unavailable state. They do not invent zeros, betas of 1.0, or Hurst values of
0.5.

## Returns and annualization

- Inputs are simple period returns `r_t`.
- Annualization `A` is `seconds_per_year / mean(positive timestamp deltas)`
  when a DatetimeIndex is present, otherwise `252`.
- Mean annual return is `mean(r) * A`.
- Annualized volatility is `std(r, ddof=1) * sqrt(A)`.

## Sharpe and Sortino

- Sharpe: `((mean(r) - r_f / A) / std(r, ddof=1)) * sqrt(A)`.
- Lightweight summary paths may set `r_f = 0` and record that in the payload.
- Sortino uses the full-sample downside deviation
  `sqrt(mean(min(r - r_f/A, 0)^2))`, not the standard deviation of the
  negative subset.

References: [Investor.gov Sharpe](https://www.investor.gov/introduction-investing/investing-basics/terms-and-definitions/sharpe-ratio).

## Beta, alpha, tracking

- Series are inner-joined and dropped for missing dates before any covariance.
- Beta uses sample covariance and sample variance (`ddof=1`).
- If market variance is 0, beta is omitted.
- Jensen/alpha, tracking error, information ratio, and M² use the same
  aligned window.

Reference: [Sharpe 1964](https://doi.org/10.2307/2977928).

## Drawdown and tails

- Max drawdown is `min((V_t - peak_t) / peak_t)` on `V = cumprod(1+r)`.
- Historical VaR is the left-tail return quantile `quantile(r, 1-q)`.
- CVaR is the mean of returns at or below that quantile.
- These are return units, not positive loss amounts.

Reference: [Investor.gov VaR](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/understanding-value-risk).

## EWMA

- Recursion: `var_t = 0.94 * var_{t-1} + 0.06 * r_t^2`.
- One-step forecast is `sqrt(var_t)`.
- Horizon `h` uses RiskMetrics random-walk scaling `σ * sqrt(h)`.
  Variance is not decayed toward zero.

Reference: [1996 RiskMetrics Technical Document](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document).

## Hurst, entropy, CUSUM

- Hurst is the R/S log-log slope. Short series return unavailable, not 0.5.
  There is no calibration offset.
- Shannon and permutation entropy are descriptive complexity measures.
- CUSUM change points are a two-sided classical detector, not a forecast.

References: [Hurst 1951](https://doi.org/10.1098/rspa.1951.0001),
[permutation entropy](https://doi.org/10.1103/PhysRevLett.88.174102),
[NIST CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm).

## Markov regime snapshot

- Returns are discretized into five quantile bins and treated as a Markov
  chain.
- `stay_probability` is the projected probability of remaining in the current
  bin at the requested horizon. It is not statistical confidence.
- Reports label this as current-state probability.

## Tax estimates

- Unrealized tax uses lot quantity, lot basis, and a live price.
- Unknown timestamps are excluded from term-specific tax and remain in
  total unrealized gain.
- There is no FIFO/LIFO realization or wash-sale engine.

## HHI

- Diagnostics HHI is the sum of squared portfolio weights.
  Reference: [DOJ HHI](https://www.justice.gov/atr/herfindahl-hirschman-index).
