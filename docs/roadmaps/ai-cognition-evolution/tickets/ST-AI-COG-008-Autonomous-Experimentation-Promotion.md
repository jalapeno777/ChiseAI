# ST-AI-COG-008: Autonomous Experimentation & Promotion

- Story ID: `ST-AI-COG-008`
- Priority: `P1`
- Default execution mode: `autonomous` for backtest/shadow/paper, `approval-gated` for live promotion
- Dependencies: `ST-AI-COG-001`, `ST-AI-COG-004`, `ST-AI-COG-006`, `ST-AI-COG-010`

## Owned Scope

- `src/autonomous_cognition/experiments/champion_challenger.py`
- promotion packet and experiment manifest paths
- `tests/integration/test_training_flow.py`
- `tests/test_brain/test_promotion_packet.py`

## Acceptance Evidence

- experiment manifests include hypothesis, baseline, rollback
- comparison uses real metrics
- failed experiment artifacts retained
- promotion packet reviewable standalone

## Validation Commands

```bash
pytest -q tests/integration/test_training_flow.py
pytest -q tests/test_brain/test_promotion_packet.py
pytest -q tests/test_brain/integration/test_promotion_flow.py
```

## Human Approval Gate

Live-facing promotion and critical evolution decisions require approval.
