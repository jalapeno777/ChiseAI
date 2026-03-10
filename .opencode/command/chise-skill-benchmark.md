---
name: "chise-skill-benchmark"
description: "ChiseAI: aggregate A/B skill benchmark results (with_skill vs baseline/old_skill) into benchmark artifacts."
disable-model-invocation: true
---

Use this after benchmark runs are captured in workspace layout.

Expected layout:
- `<workspace>/iteration-N/eval-*/with_skill/run-*/grading.json`
- `<workspace>/iteration-N/eval-*/without_skill/run-*/grading.json`
  or `<workspace>/iteration-N/eval-*/old_skill/run-*/grading.json`

1. Aggregate benchmark
   - Run:
     ```bash
     repo_root="$(git rev-parse --show-toplevel)"
     cd "$repo_root/scripts/ops/skill_creator"
     python3 -m scripts.aggregate_benchmark \
       "$repo_root/<workspace>/iteration-N" \
       --skill-name <skill_name> \
       --skill-path "$repo_root/.opencode/skills/<skill_name>"
     ```

2. Verify outputs
   - Confirm files exist:
     - `<workspace>/iteration-N/benchmark.json`
     - `<workspace>/iteration-N/benchmark.md`

3. Feed control-plane decisions
   - Use benchmark deltas for promotion/rollback review:
     - pass rate delta
     - time delta
     - token delta

Policy:
- Benchmark decisions are evidence inputs, not automatic deploy signals.
- Apply existing promotion/rollback guardrails before changing preferred skill versions.
