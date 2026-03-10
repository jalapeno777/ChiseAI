---
name: "chise-skill-benchmark-run"
description: "ChiseAI: run benchmark execution pipeline (with_skill vs baseline) and generate benchmark artifacts."
disable-model-invocation: true
---

Use this to run benchmark execution and grading with pluggable command templates.

1. Execute benchmark suite
   ```bash
   python3 scripts/ops/skill_creator/scripts/run_benchmark_suite.py \
     --skill-name <skill_name> \
     --skill-path .opencode/skills/<skill_name> \
     --eval-set .opencode/skills/<skill_name>/evals/evals.json \
     --workspace _bmad-output/skill-benchmarks/<skill_name> \
     --iteration <N> \
     --runs-per-configuration <k> \
     --configurations with_skill without_skill \
     --executor-cmd-template '<executor_template>' \
     --grader-cmd-template '<grader_template>'
   ```

2. Aggregate benchmark
   ```bash
   cd scripts/ops/skill_creator
   python3 -m scripts.aggregate_benchmark \
     "$(git rev-parse --show-toplevel)/_bmad-output/skill-benchmarks/<skill_name>/iteration-<N>" \
     --skill-name <skill_name> \
     --skill-path "$(git rev-parse --show-toplevel)/.opencode/skills/<skill_name>"
   ```

3. Promotion/rollback input
- Feed `benchmark.json` into:
  - `scripts/ops/skill_promote_from_benchmark.py`
  - `scripts/ops/skill_rollback_from_evidence.py`

Notes:
- The suite runner is runtime-agnostic; templates define how runs/graders are executed.
- By default, missing `grading.json` fails the suite unless `--allow-missing-grading` is set.
