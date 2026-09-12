# Tests

Pytest suite for the core runtime, API, and analytics utilities.

## Run
```powershell
python -m pytest
```

Inspection and guardrail scan:

```powershell
python scripts/inspect_repo.py corpus
python scripts/inspect_repo.py scan
python scripts/check_guardrails.py --strict
```

## Coverage highlights
- Client store integrity and migrations (`test_client_store_*`).
- Analytics math and models (`test_financial_calculations.py`,
  `test_regime_models.py`).
- Launchers and startup behavior (`test_lotbookctl_startup.py`,
  `test_launcher_utils.py`).
- News/intel filtering and scoring (`test_intel_*`, `test_news_collectors.py`).
- Isolated positive-path API tests via `tests/harness.py`
  (`test_web_api_clients.py`, `test_web_api_maintenance.py`).
- Guardrail ratchet and inspection corpus (`test_guardrail_scan.py`,
  `test_inspect.py`).

## Evidence classes

- Live local data or the isolated SQLite/API harness for positive-path API
  tests. Do not point tests at operator `data/lotbook.db`.
- Captured real fixtures with provenance for globe loaded-state visuals.
- Negative-path tests may construct invalid payloads only to prove rejection.
- `*_stubbed` tests in `test_web_api.py` are contract-shape / filter wiring
  only. They are not positive-path evidence.

## Notes
- Add new tests alongside the feature they validate.
- Keep tests deterministic and data-driven (no randomization).
- New `except Exception` / silent `pass` / fabricated-data hits must update
  or shrink `tests/guardrail_baseline.json` with a classified reason.
