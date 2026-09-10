# Reference currency and implementation coverage

Reviewed September 9, 2026. Scope is all 15 references in the
README's **Standards And Governance** and **Methods And Risk References**, not
a repository-wide conformance audit. [The register](reference_register.json)
records each version, URL, implementation, test evidence and limitation.

`tests/test_reference_contracts.py` checks that the README list and register
agree and that every listed implementation/test path exists. The same tests
exercise undefined sample statistics and the actual empirical tail convention.
This is an offline traceability guard, not a live-link or conformance checker.
The register and coverage record are also required inspection-corpus inputs.
Recheck source currency before releases or adopting a changed standard; dates
in the register are evidence checkpoints, not automatic update guarantees.

## Source corrections

- [NIST's SSDF publication list](https://csrc.nist.gov/Projects/ssdf/publications)
  still identifies 1.1 as final and 1.2 as a draft. Do not replace the adopted
  final baseline with an unlabeled draft.
- [SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
  includes catalog release 5.2.0, issued August 2025. The register explicitly
  retains tailoring, update governance and organizational evidence as gaps.
- [SP 800-160 Vol. 1 Rev. 1](https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final)
  is **Engineering Trustworthy Secure Systems**. The earlier baseline used a
  different publication title.
- [AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) lists 1.0 and
  an ongoing revision. Existing scope/provenance checks are not a full AI risk
  program. [Revised Section 508](https://www.access-board.gov/ict/) incorporates
  WCAG 2.0 A/AA with applicable exceptions; bounded browser tests do not prove
  assistive-technology compatibility or full conformance.
- [ASSIST](https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027)
  identifies MIL-STD-882 Revision E Change 1, September 27, 2023, as active.
- The old SEC exhibit and Investor.gov links could not be verified as formula
  authorities in this retrieval. They were replaced by the actual
  [fractional-change implementation](https://pandas.pydata.org/docs/reference/api/pandas.Series.pct_change.html),
  [Sharpe's own 1994 article](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm)
  and [RiskMetrics background](https://www.msci.com/research-and-insights/paper/1996-riskmetrics-technical-document).
  Retrieval failure alone is not proof that a page never existed.
- The old Hurst DOI `10.1098/rspa.1951.0001` identifies Chandrasekhar's
  *The invariant theory of isotropic turbulence in magneto-hydrodynamics*, not
  Hurst. Crossref publisher metadata confirms the corrected
  [Hurst 1951 DOI](https://doi.org/10.1061/TACEAT.0006518). Publisher full text
  was unavailable; no new estimator-validity claim is made.
- The 2013 Basel link was a consultation. It is replaced with current
  [MAR33](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/33/inforce/2023-01-01/published/2020-06-05).
  This is background only: Clear has no regulatory ES/capital implementation.

## Concrete code and evidence mapping

| Reference | Implementation / verification | Coverage boundary |
| --- | --- | --- |
| SSDF | CI, CodeQL, guardrail and inspection scripts; guardrail/inspection tests | Partial secure-development controls; no complete supplier/release assurance |
| 800-53 | HTTP/WS API-key checks, encrypted recovery; security/recovery tests | No individual identities, per-firm isolation or tailored control assessment |
| 800-160 | Owned launch/close and new-file recovery; launcher/recovery/browser tests | No complete lifecycle assurance case or production-sized recovery drill |
| AI RMF | Assistant scope/provenance and export boundaries; assistant tests | No complete AI governance/evaluation/monitoring program |
| Section 508 | Keyboard/labels/reduced-motion/non-canvas controls; isolated browser tests | No full conformance, screen-reader or document-export assessment |
| MIL-STD-882 | Owned-process and non-overwrite safeguards; launcher/recovery tests | No formal hazard log, safety acceptance or DoD certification |
| Fractional returns | Shared-date/current-holdings reconstruction; arithmetic regression tests | Not cash-flow-adjusted account performance |
| Sharpe | Shared calculations and dashboard payloads; toolkit/reference tests | Constant risk-free convention and scaling assumptions disclosed |
| RiskMetrics | EWMA and historical-tail helpers; financial/reference tests | Explicit Clear empirical-tail convention, not Basel ES |
| DOJ HHI | View-model sector-share squares; view-model tests | Fractional sector concentration, not firm competition or investment suitability |
| NIST CUSUM | Retrospective two-sided detector; financial tests | Full-window calibration, not a streaming forecasting engine |
| CAPM | Aligned covariance/variance, alpha and tracking metrics; financial tests | Historical estimates; undefined variance is unavailable |
| Permutation entropy | Ordinal-pattern counts in calculations/patterns; financial tests | Legacy tie/insufficient-input handling remains open |
| Hurst | Disjoint-block R/S in calculations/patterns; financial/regression tests | Clipped estimate, not proven predictability or an unbiased estimator |
| Basel MAR33 | Explicit exclusion in methods and code; empirical-tail tests | Background only; capital calculations are not implemented |

The source corrections also fix README math: `mean(r <= VaR)` would average a
boolean mask, whereas the code averages the selected returns. Drawdown includes
initial capital. HHI is sector-level on priced securities, with manual assets
excluded. Tax valuation uses a price snapshot, not an established live stream.

## Bounded corrections and remaining work

Reproduced before this patch: one observation produced NaN sample volatility
and Sharpe in the shared core path, and NaN volatility in risk summaries.
These are now unavailable (`None`/JSON null); the defined arithmetic mean is
retained. CAPM cannot bypass its two-observation minimum or emit a spurious
R-squared for a constant benchmark. The regime summary also preserves those
unavailable fields instead of crashing on `float(None)`, and its Sharpe uses
the requested risk-free rate consistently with alpha. Invalid tail confidence or nonfinite tail
inputs return unavailable, preserving the legitimate inclusive-tail convention.

Validation checkpoint: full local Python suite **356 passed**; focused
math/regime checks **45 passed**; final register/corpus checks **16 passed**.
Production web build and bundle budgets pass. Strict guardrails report 196
existing baseline findings, not zero findings. Independent inspection remains
pending; author-run tests and corpus checks do not satisfy that merge gate.
The paused holdings draft is excluded from this reference change.

Still release-blocking: deployment/authorization, verified intake and model
approval, complete transaction workflows, operations recovery acceptance,
remaining methodology/coverage gaps and full accessibility evidence. Existing
unit/stub tests are not promoted to real-provider integration proof. Legacy
descriptive entropy insufficient-input zeros and HHI no-data sentinels need
consumer-safe follow-up. Do not claim all standards are fully implemented.

Next bounded work: finish independent review of the map checkpoint; complete
individual holdings edits with lot/aggregate integrity; close descriptive
analytics availability/coverage semantics; then the deployment-specific gates
in [production readiness](production_readiness.md). Source revalidation and
registry path checks do not waive any gate.
