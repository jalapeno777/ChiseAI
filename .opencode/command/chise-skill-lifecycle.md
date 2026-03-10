---
name: "chise-skill-lifecycle"
description: "ChiseAI: single entrypoint for skill lifecycle (create, optimize triggers, benchmark, promote/rollback)."
disable-model-invocation: true
---

Use this to run end-to-end lifecycle orchestration from one command.

Example full flow:
```bash
python3 scripts/ops/skill_creator/scripts/skill_lifecycle_orchestrator.py \
  --skill-name <skill_name> \
  --create-skill \
  --run-trigger-opt \
  --trigger-model <claude_model_id> \
  --workspace _bmad-output/skill-benchmarks/<skill_name> \
  --iteration 1 \
  --executor-cmd-template '<executor_template>' \
  --grader-cmd-template '<grader_template>' \
  --promote-candidate-version <candidate_version> \
  --promote-incumbent-version <incumbent_version>
```

Rollback evaluation add-on:
```bash
python3 scripts/ops/skill_creator/scripts/skill_lifecycle_orchestrator.py \
  --skill-name <skill_name> \
  --workspace _bmad-output/skill-benchmarks/<skill_name> \
  --iteration 1 \
  --rollback-degraded-version <degraded_version> \
  --rollback-fallback-version <last_known_good> \
  --regression-rate <0.0-1.0>
```

Outputs:
- Benchmark artifacts under workspace iteration folder.
- Promotion/rollback artifacts under `docs/tempmemories/`.
- Version routing updates in `docs/metrics/skill-versions.yaml`.
