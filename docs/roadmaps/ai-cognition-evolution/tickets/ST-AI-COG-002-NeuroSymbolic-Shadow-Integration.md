# ST-AI-COG-002: Neuro-Symbolic Shadow Integration

- Story ID: `ST-AI-COG-002`
- Priority: `P0`
- Default execution mode: `autonomous`
- Dependencies: `ST-AI-COG-001`, `ST-AI-COG-005`, `ST-AI-COG-010`

## Owned Scope

- `src/signal_generation/signal_generator.py`
- `src/autonomous_cognition/runtime_integration.py`
- `src/neuro_symbolic/orchestrator/orchestrator.py`
- `tests/unit/autonomous_cognition/test_runtime_and_tuning.py`
- `tests/test_brain/test_shadow_testing.py`

## Acceptance Evidence

- legacy path remains authoritative
- divergence records emitted
- shadow latency visible
- divergence report or dashboard produced

## Validation Commands

```bash
pytest -q tests/unit/autonomous_cognition/test_runtime_and_tuning.py
pytest -q tests/test_brain/test_shadow_testing.py
pytest -q tests/test_brain/test_shadow_tester.py
```

## Human Approval Gate

Shadow mode is autonomous. Live influence is not.
