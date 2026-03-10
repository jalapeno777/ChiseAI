---
name: "chise-skill-trigger-optimize"
description: "ChiseAI: run trigger eval + iterative description optimization loop for a skill."
disable-model-invocation: true
---

Use this to optimize skill triggering quality (false negatives/false positives).

Inputs:
- `<skill_name>`: e.g. `my-skill`
- `<claude_model_id>`: model used for description improvement

1. Run optimization loop
   - Run from `scripts/ops/skill_creator` so module imports resolve:
     ```bash
     repo_root="$(git rev-parse --show-toplevel)"
     cd "$repo_root/scripts/ops/skill_creator"
     python3 -m scripts.run_loop \
       --skill-path "$repo_root/.opencode/skills/<skill_name>" \
       --eval-set "$repo_root/.opencode/skills/<skill_name>/evals/evals.json" \
       --model <claude_model_id> \
       --results-dir "$repo_root/docs/tempmemories/skill-trigger-optimization/<skill_name>" \
       --max-iterations 5 \
       --runs-per-query 3 \
       --trigger-threshold 0.5 \
       --holdout 0.4 \
       --verbose
     ```

2. Validate resulting skill metadata
   - Run:
     ```bash
     python3 scripts/ops/skill_creator/scripts/quick_validate.py .opencode/skills/<skill_name>
     ```

3. Persist evidence
   - Store loop output JSON and HTML report under:
     - `docs/tempmemories/skill-trigger-optimization/`

Policy:
- Require holdout (`--holdout > 0`) to reduce overfitting.
- Do not promote based on one iteration; route final evidence through `chise-skill-promote` thresholds.
