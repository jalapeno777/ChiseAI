# ST-AI-COG-010: Telemetry, Evals, Decision Scorecards

- Story ID: `ST-AI-COG-010`
- Priority: `P0`
- Default execution mode: `autonomous`
- Dependencies: none

## Owned Scope

- KPI registry and scorecard generators
- `scripts/evaluation/kpi_scheduler.py`
- `scripts/evaluation/validate_cadence.py`
- `scripts/evaluation/autonomy_cadence_controller.py`
- `tests/test_evaluation/test_autonomy_cadence.py`
- `tests/integration/test_brain_eval_cadence.py`

## Acceptance Evidence

- KPI registry landed
- daily and weekly scorecards generated
- freshness and stale-data states visible
- autonomy thresholds tied to scorecards

## Validation Commands

```bash
pytest -q tests/test_evaluation/test_autonomy_cadence.py
pytest -q tests/integration/test_brain_eval_cadence.py
python3 scripts/evaluation/validate_cadence.py
```

## Human Approval Gate

Instrumentation is autonomous unless it directly changes protected live promotion logic.
