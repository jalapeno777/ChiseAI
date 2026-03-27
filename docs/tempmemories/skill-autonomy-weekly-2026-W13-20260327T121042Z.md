---
week_id: 2026-W13
generated_at_utc: '2026-03-27T12:10:42Z'
events_analyzed: 3
needs_manual_qdrant_import: true
---

## Skill Autonomy Weekly

week_id: 2026-W13
generated_at_utc: '2026-03-27T12:10:42Z'
lookback_days: 14
events_analyzed: 3
coverage_distribution:
  none: 3
missing_skill_rate_by_task_class:
  remediation: 0.0
  unclassified: 0.0
top_missing_skills: []
stack_coverage_summary: {}
skill_effectiveness_summary: {}
promotion_decisions_summary:
  counts:
    PROMOTE: 7
  latest_by_skill:
    chiseai-worker-contracts:
      decision: PROMOTE
      generated_at_utc: '2026-03-10T19:39:03Z'
      artifact: docs/tempmemories/skill-promotion-chiseai-worker-contracts-20260310T193903Z.md
    chiseai-validation:
      decision: PROMOTE
      generated_at_utc: '2026-03-10T19:39:00Z'
      artifact: docs/tempmemories/skill-promotion-chiseai-validation-20260310T193900Z.md
    chiseai-skill-autonomy:
      decision: PROMOTE
      generated_at_utc: '2026-03-10T19:39:01Z'
      artifact: docs/tempmemories/skill-promotion-chiseai-skill-autonomy-20260310T193901Z.md
    chiseai-metacognition-ops:
      decision: PROMOTE
      generated_at_utc: '2026-03-10T22:49:58Z'
      artifact: docs/tempmemories/skill-promotion-chiseai-metacognition-ops-20260310T224958Z.md
    chiseai-git-workflow:
      decision: PROMOTE
      generated_at_utc: '2026-03-10T22:49:56Z'
      artifact: docs/tempmemories/skill-promotion-chiseai-git-workflow-20260310T224956Z.md
rollback_decisions_summary:
  counts: {}
  latest_by_skill: {}
version_registry_snapshot:
  skills_tracked: 5
  preferred_versions:
    chiseai-git-workflow: '1.1'
    chiseai-validation: '1.1'
    chiseai-skill-autonomy: '1.1'
    chiseai-worker-contracts: '1.1'
    chiseai-metacognition-ops: '1.1'
recommended_actions:
- Prioritize hardening skills with highest rework/regression rates.
- Only add new skills when missing-skill patterns are repeated over time.
- Monitor newly promoted skill versions for regression canaries.
backlog_candidates: []
