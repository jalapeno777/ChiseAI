# First Sprint Contract: ST-AI-COG-001

## Worker Slices

### Worker A

- ownership keys:
  - `src:strategy:contracts`
  - `src:strategy:registry`
- scope globs:
  - `src/strategy/contracts.py`
  - `src/strategy/registry.py`
  - `tests/test_backtesting_candidate/test_models.py`
  - `tests/test_backtesting_candidate/test_registry.py`

### Worker B

- ownership keys:
  - `src:strategy:engine`
  - `src:strategy:executors`
- scope globs:
  - `src/strategy/engine.py`
  - `src/strategy/executors/**`
  - `tests/test_backtesting_candidate/test_pipeline.py`
  - `tests/test_backtesting_candidate/test_integration.py`

### Worker C

- ownership keys:
  - `src:strategy:validator`
  - `bmad-output:strategy`
- scope globs:
  - `src/strategy/validator.py`
  - `_bmad-output/strategy/**`
  - `tests/test_backtesting_candidate/test_ranking.py`
  - `tests/test_backtesting_candidate/test_walk_forward.py`
