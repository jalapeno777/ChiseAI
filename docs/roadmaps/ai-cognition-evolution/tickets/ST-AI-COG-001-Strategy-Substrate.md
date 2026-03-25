# ST-AI-COG-001: Strategy Substrate

- Story ID: `ST-AI-COG-001`
- Priority: `P0`
- Default execution mode: `autonomous`
- Dependencies: none

## Owned Scope

- `src/strategy/engine.py`
- `src/strategy/registry.py`
- `src/strategy/contracts.py`
- `src/strategy/validator.py`
- `src/strategy/executors/`
- `tests/test_backtesting_candidate/`

## Acceptance Evidence

- strategy registry and contracts landed
- validation and provenance packets emitted
- replay determinism demonstrated
- rollback target exists for promotable candidates

## Validation Commands

```bash
pytest -q tests/test_backtesting_candidate/test_registry.py
pytest -q tests/test_backtesting_candidate/test_integration.py
pytest -q tests/test_backtesting_candidate/test_pipeline.py
```

## Human Approval Gate

Implementation is autonomous. Live promotion remains approval-gated.
