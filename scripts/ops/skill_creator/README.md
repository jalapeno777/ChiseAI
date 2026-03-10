# Skill Creator Ops Bundle

This directory provides a tracked, repo-local copy of the skill creation and evaluation tooling used by ChiseAI commands:

- `chise-skill-create`
- `chise-skill-trigger-optimize`
- `chise-skill-benchmark`
- `chise-skill-benchmark-run`
- `chise-skill-lifecycle`

Run module-based commands from this directory:

```bash
cd scripts/ops/skill_creator
python3 -m scripts.run_loop --help
python3 -m scripts.run_eval --help
python3 -m scripts.aggregate_benchmark --help
python3 scripts/run_benchmark_suite.py --help
python3 scripts/skill_lifecycle_orchestrator.py --help
```

Reference schema:
- `references/schemas.md`
