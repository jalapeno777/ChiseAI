---
name: "chise-autocog-daily-run"
description: "Run autonomous cognition backend evaluation cycle and collect evidence artifacts."
disable-model-invocation: true
---

Run backend autonomous cognition jobs and collect artifacts:

1. Execute self-assessment:
   - `python3 scripts/ops/run_autonomous_self_assessment.py --notify-discord`
2. Execute full cycle:
   - `python3 scripts/ops/run_autonomous_full_cycle.py --mode full --notify-discord`
3. Validate generated artifacts:
   - latest `_bmad-output/autocog/cycles/*.json`
   - latest `docs/governance/self_assessments/*.json`
4. Run regression checks:
   - `pytest -q tests/unit/autonomous_cognition tests/e2e/test_autonomous_cognition_full_cycle.py`
5. Capture summary:
   - `run_id`
   - cycle status
   - promotions/rejections
   - violation counts
   - discord send status evidence lines

