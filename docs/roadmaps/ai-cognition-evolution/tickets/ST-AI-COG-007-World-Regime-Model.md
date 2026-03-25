# ST-AI-COG-007: World / Regime Model

- Story ID: `ST-AI-COG-007`
- Priority: `P1`
- Default execution mode: `autonomous`
- Dependencies: `ST-AI-COG-010`

## Owned Scope

- regime classification and transition modeling
- `tests/fixtures/ohlcv_generators.py`
- `tests/integration/test_venue_provenance_e2e.py`
- `tests/test_ml/test_evaluation/test_integration.py`

## Acceptance Evidence

- regime model emits confidence and `UNKNOWN`
- transition and counterfactual artifacts logged
- slice scorecards produced

## Validation Commands

```bash
pytest -q tests/integration/test_venue_provenance_e2e.py
pytest -q tests/test_ml/test_evaluation/test_integration.py
pytest -q tests/test_evaluation/test_issue_ingestion.py
```

## Human Approval Gate

Implementation is autonomous unless it changes protected live policy behavior.
