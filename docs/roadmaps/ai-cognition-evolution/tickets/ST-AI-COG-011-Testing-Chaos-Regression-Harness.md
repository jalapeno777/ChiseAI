# ST-AI-COG-011: Testing, Chaos, Regression Harness

- Story ID: `ST-AI-COG-011`
- Priority: `P1`
- Default execution mode: `autonomous`
- Dependencies: `ST-AI-COG-001` through `ST-AI-COG-010`

## Owned Scope

- `src/testing/chaos_engine.py`
- `src/testing/failure_injector.py`
- cognition replay harness and gold-set
- `tests/test_brain/`
- `tests/test_evaluation/`

## Acceptance Evidence

- replay harness exists
- chaos scenarios cover memory, retrieval, verifier, regime failures
- rollback and downgrade drills artifacted

## Validation Commands

```bash
pytest -q tests/test_brain
pytest -q tests/test_evaluation
pytest -q tests/contract/test_autocog_interfaces.py
```

## Human Approval Gate

Paper-mode and local chaos are autonomous. Protected live-system drills are not.
