# ST-AI-COG-006: Verifier-Driven Reasoning

- Story ID: `ST-AI-COG-006`
- Priority: `P1`
- Default execution mode: `autonomous`
- Dependencies: `ST-AI-COG-002`, `ST-AI-COG-010`

## Owned Scope

- reasoning trace and verifier interfaces
- `tests/test_brain/test_evaluation.py`
- `tests/test_evaluation/test_mini_brain_eval.py`
- `tests/test_ci/test_brain_evaluation.py`

## Acceptance Evidence

- reasoning trace format landed
- verifier artifacts emitted
- disagreement logging present
- blocking verifier path in high-impact flows

## Validation Commands

```bash
pytest -q tests/test_brain/test_evaluation.py
pytest -q tests/test_evaluation/test_mini_brain_eval.py
pytest -q tests/test_ci/test_brain_evaluation.py
```

## Human Approval Gate

Bypass of blocking verifier checks requires approval.
