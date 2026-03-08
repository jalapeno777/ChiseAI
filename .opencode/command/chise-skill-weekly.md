---
name: "chise-skill-weekly"
description: "ChiseAI: weekly autonomous skills report for coverage gaps, effectiveness trends, and promotion/rollback recommendations."
disable-model-invocation: true
---

Run weekly.

Preferred entry point:
- `.opencode/command/chise-skill-autonomy-tick.md` with `mode=weekly`.

1. Aggregate coverage KPIs
   - Missing-skill rate by task class.
   - Most frequent missing skill names.
   - Stories impacted by partial/none coverage.

2. Aggregate effectiveness KPIs
   - quality score trend by skill.
   - cycle time trend by skill.
   - rework/regression trend by skill.

3. Generate recommendations
   - Top skills to harden.
   - Top new skills to add (only if repeated gaps exceed thresholds).
   - Promotion and rollback candidates.

4. Emit machine-readable output
   - YAML with:
     - `week_id`
     - `missing_skill_rate_by_task_class`
     - `top_missing_skills`
     - `skill_effectiveness_summary`
     - `promotion_candidates`
     - `rollback_candidates`
     - `recommended_actions`

5. Persist
   - Write report to `docs/tempmemories/`.
   - Promote durable lessons to Qdrant if available.
   - Create backlog candidates automatically when repeated gap thresholds are met.
   - Queue candidates in Redis key: `bmad:chiseai:skills:backlog:candidates`.
   - Ingest queue into canonical backlog:
     - `.opencode/command/chise-skill-backlog-ingest.md`

Policy:
- Missing skills are signals, not blockers.
- Use weekly trends to decide where to invest in new skills.
- Repeated gaps become backlog candidates automatically (still non-blocking for execution).
