---
week_id: 2026-W11
generated_at_utc: 2026-03-10T19:43:30.090957Z
events_analyzed: 5
needs_manual_qdrant_import: true
---

## Skill Autonomy Weekly - ST-SKILL-EVAL-001

### Stack Coverage Summary
```yaml
core_engineering:
  coverage_rate: 1.0
  events: 2
  full_coverage_events: 2
  skills:
  - chiseai-git-workflow
parallel_coordination:
  coverage_rate: 1.0
  events: 1
  full_coverage_events: 1
  skills:
  - chiseai-worker-contracts
planning_ops:
  coverage_rate: 1.0
  events: 1
  full_coverage_events: 1
  skills:
  - chiseai-metacognition-ops
quality_gates:
  coverage_rate: 1.0
  events: 1
  full_coverage_events: 1
  skills:
  - chiseai-validation

```

### Promotion Decisions Summary
- **Total PROMOTE**: 5
- **Total HOLD**: 0

Skills promoted:
- chiseai-git-workflow: PROMOTE
- chiseai-metacognition-ops: PROMOTE
- chiseai-skill-autonomy: PROMOTE
- chiseai-validation: PROMOTE
- chiseai-worker-contracts: PROMOTE

### Version Registry Snapshot
- Skills tracked: 5
- Preferred versions: {'chiseai-git-workflow': '1.1', 'chiseai-validation': '1.1', 'chiseai-skill-autonomy': '1.1', 'chiseai-worker-contracts': '1.1', 'chiseai-metacognition-ops': '1.1'}

### Recommended Actions
- 5 skills promoted to v1.1 based on benchmark evidence
- All promotions showed >10% pass rate improvement
- Continue monitoring for regression signals
- Consider expanding benchmark coverage to remaining 26 skills
