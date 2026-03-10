---
name: "chise-skill-eval"
description: "ChiseAI: evaluate skill coverage/effectiveness for a story and log KPI gaps without blocking execution when skills are missing."
disable-model-invocation: true
---

Run at iteration start (coverage) and/or close (effectiveness).

1. Resolve task context
   - Identify `story_id`.
   - Identify `task_class` (use `unclassified` if unknown).

2. Determine recommended skills (advisory)
   - Load `docs/metrics/skill-task-map.yaml`.
   - Load `docs/metrics/skill-stacks.yaml` and expand any stack references.
   - Read recommended list for `task_class`.

3. Detect available skills
   - Scan `.opencode/skills/*/SKILL.md`.
   - Build `available_skills` set from directory names.

4. Compute coverage (NON-BLOCKING)
   - `missing_skills = recommended - available`.
   - `coverage_status = full|partial|none`.
   - If missing exists:
     - continue execution
     - record KPI gap event
     - include fallback plan in story notes

5. Persist KPI event
   - Run:
     ```bash
     python3 scripts/validation/validate_skill_autonomy.py \
       --story-id=<story_id> \
       --task-class=<task_class> \
       --impact-estimate=<none|low|medium|high>
     ```

6. Optional effectiveness snapshot (at close)
   - Include objective fields if known:
     - `--quality-score=<0.0-1.0>`
     - `--cycle-time-minutes=<int>`
     - `--rework-flag`
     - `--regression-flag`
     - `--skill-name=<active_skill_if_any>`
     - `--skill-version=<version_if_known>`

7. Output contract
   - Emit summary with:
     - `recommended_skills`
     - `recommended_stacks`
     - `available_skills`
     - `missing_skills`
     - `coverage_status`
     - `fallback_used`
     - `next_skill_candidate` (if repeated gap)

Gate behavior:
- Missing skills: warning only, never a blocker.
- Script/tool failure: warning only unless explicitly configured otherwise.
