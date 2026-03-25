# ST-AI-COG-003: Neuro-Symbolic Canary / Full Activation

- Story ID: `ST-AI-COG-003`
- Priority: `P1`
- Default execution mode: `autonomous` for shadow/paper/canary, `approval-gated` for full live activation
- Dependencies: `ST-AI-COG-002`, `ST-AI-COG-006`, `ST-AI-COG-007`, `ST-AI-COG-010`

## Owned Scope

- `src/signal_generation/signal_generator.py`
- `src/autonomous_cognition/runtime_integration.py`
- `tests/test_brain/test_promotion.py`
- `tests/test_brain/test_rollback.py`

## Acceptance Evidence

- canary segmentation implemented
- activation thresholds explicit
- rollback switch proven
- promotion packet artifact exists

## Validation Commands

```bash
pytest -q tests/test_brain/test_promotion.py
pytest -q tests/test_brain/test_rollback.py
pytest -q tests/test_brain/integration/test_promotion_flow.py
```

## Human Approval Gate

Any full live-facing activation requires approval.
