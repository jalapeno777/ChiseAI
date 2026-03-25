# ST-AI-COG-012: Research Acceleration Program

- Story ID: `ST-AI-COG-012`
- Priority: `P2`
- Default execution mode: `autonomous`
- Dependencies: continuous sidecar

## Owned Scope

- research backlog and synthesis artifacts
- bounded experiment proposal packets
- `tests/test_skills/test_evaluations.py`

## Acceptance Evidence

- triage rubric and synthesis cadence established
- measurable ChiseAI problem mapped to each promoted item
- no roadmap mutation without bounded experiment proposal

## Validation Commands

```bash
python3 scripts/evaluation/run_daily_trends.py --help
python3 scripts/evaluation/run_weekly_reflection.py --help
pytest -q tests/test_skills/test_evaluations.py
```

## Human Approval Gate

Research and proposal work are autonomous. Critical evolution decisions are not.
