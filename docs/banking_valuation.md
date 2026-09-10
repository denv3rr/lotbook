# Valuation methods and limits

These are assumption-driven screening calculators. Formula tests do not
validate company evidence, peer suitability, forecasts or investment advice.
All inputs, source notes, date, currency and methodology travel with exports
and saved model snapshots. No market financials are invented or prefilled.
Use whole currency units and actual diluted shares, not millions.

## Annual FCFF DCF

For years t=1..N, PV(t) = FCFF(t)/(1+WACC)^t. N is 1..20.
Terminal value at N = FCFF(N) × (1+g)/(WACC-g). Enterprise value is the
sum of annual PVs plus terminal value discounted N years. WACC must be
positive and exceed g; rates are decimals in the API and percent in the UI.
Negative forecast cash flow and equity residuals remain visible with warnings.
The terminal period needs a defensible normalized cash flow.

Equity residual = EV + cash + non-operating assets - debt - other claims.
Value per diluted share requires a positive supplied share count. A negative
residual is not the limited-liability market value of common equity.
Sensitivity recalculates EV at explicit WACC/g grid coordinates; invalid
cells stay unavailable. No hidden midyear convention or premium applies.

Method reference: [Damodaran, FCFF valuation](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcff.html).

## Trading comparable companies

Each peer's multiple = supplied EV / supplied revenue or EBITDA. Missing,
zero or negative denominators are excluded for that multiple. Coverage is
separate for EV/revenue and EV/EBITDA. Duplicate normalized peer names fail
validation. No automatic peer selection, exclusion of outliers or premium.

Minimum, quartiles, median and maximum use sorted individual multiples and
linear interpolation at (n-1)×p; they are not ratios of aggregate financials.
Target financial metric × multiple = implied EV, followed by the same equity
bridge. Nonpositive/missing target denominators leave implied values unavailable.

All peers and target must use a consistent observation date, LTM/NTM period
basis, currency units and accounting/EV adjustments. Exact financial period
ends and sources belong in the required source notes. This consistency is an
operator review requirement, not independently established by text labels.
Small peer sets and differences in risk, margins and growth limit comparability.

Method references: [Value/EBITDA](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/vebitnote.html)
and [The Anatomy of a Multiple](https://people.stern.nyu.edu/adamodar/New_Home_Page/lectures/multintr.htm).

## Evidence and outstanding coverage

`test_banking_valuation.py` and `test_banking_comparables.py` exercise known
arithmetic, missing inputs, domain boundaries and finite output checks.
`test_banking_api.py` uses isolated actual SQLite writes and protects immutable
versions and same-client links. These are not verified market-data examples.
WACC, capital structure, debt schedules, three-statement linkage, precedent
screens, merger accretion/dilution, LBO MOIC/IRR and bond/option boundary
calculators are now assumption-driven screening endpoints. They do not close
reviewed financial intake or independent model approval. GIPS TWR linking and
Damodaran cost-of-capital notes are methodological references, not compliance
claims. TWR/XIRR stay unavailable on the performance route until an ending
market value is independently recorded.
