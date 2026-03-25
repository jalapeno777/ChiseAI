# First Sprint Contract: ST-AI-COG-010

## Worker Slices

### Worker A

- ownership keys:
  - `scripts:evaluation:kpi`
  - `scripts:evaluation:cadence`
- scope globs:
  - `scripts/evaluation/kpi_scheduler.py`
  - `scripts/evaluation/validate_cadence.py`
  - `tests/test_evaluation/test_autonomy_cadence.py`

### Worker B

- ownership keys:
  - `scripts:evaluation:scorecards`
  - `bmad-output:brain-eval`
- scope globs:
  - `scripts/evaluation/run_daily_trends.py`
  - `scripts/evaluation/run_weekly_reflection.py`
  - `tests/integration/test_brain_eval_cadence.py`

### Worker C

- ownership keys:
  - `infra:grafana:cognition`
  - `docs:runbooks:ci-coverage`
- scope globs:
  - `infrastructure/grafana/**`
  - `docs/runbooks/ci-coverage-matrix.md`
  - `tests/test_ci/test_brain_evaluation.py`
