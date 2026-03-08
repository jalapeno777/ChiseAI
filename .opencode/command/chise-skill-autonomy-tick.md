---
name: "chise-skill-autonomy-tick"
description: "ChiseAI: autonomous skills control-plane tick (coverage/effectiveness capture + weekly aggregation) with runtime safeguards."
disable-model-invocation: true
---

Use this as the single entry point for skills autonomy operations.

1. Per-story tick (start/close)
   - Run:
     ```bash
     python3 scripts/ops/skill_autonomy_tick.py \
       --mode=start \
       --story-id=<story_id> \
       --task-class=<task_class_or_unclassified>
     ```
   - At close, include metrics if available:
     ```bash
     python3 scripts/ops/skill_autonomy_tick.py \
       --mode=close \
       --story-id=<story_id> \
       --task-class=<task_class_or_unclassified> \
       --quality-score=<0.0-1.0> \
       --cycle-time-minutes=<int> \
       --skill-name=<active_skill_if_any> \
       --skill-version=<version_if_any>
     ```

2. Weekly tick
   - Run:
     ```bash
     python3 scripts/ops/skill_autonomy_tick.py --mode=weekly
     ```
   - Then ingest candidates into canonical backlog:
     ```bash
     python3 scripts/ops/ingest_skill_backlog_candidates.py
     ```
   - This can emit:
     - weekly KPI artifact in `docs/tempmemories/`
     - backlog candidates in `docs/backlog/` (threshold-based)
     - Redis queue items in `bmad:chiseai:skills:backlog:candidates`

3. Combined tick
   - Run both eval and weekly aggregation in one call:
     ```bash
     python3 scripts/ops/skill_autonomy_tick.py --mode=all --story-id=<story_id> --task-class=<task_class_or_unclassified>
     ```

4. Performance safeguards
   - Config file: `config/skill_autonomy.yaml`
   - Uses runtime budget, command timeout, and sampling.
   - Uses a lock file to avoid duplicate concurrent ticks.
   - If budget is exceeded, the tick degrades gracefully and warns.

5. Policy
   - Missing skills are KPI signals and never execution blockers.
   - Keep quality/safety gates (tests/CI/risk constraints) unchanged.
