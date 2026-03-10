---
skill_name: chiseai-skill-autonomy
candidate_version: '1.1'
decision: PROMOTE
generated_at_utc: '2026-03-10T19:39:01Z'
needs_manual_qdrant_import: true
---

## Skill Promotion Decision

benchmark_json: _bmad-output/skill-benchmarks/chiseai-skill-autonomy/iteration-1/benchmark.json
primary_config: with_skill
baseline_config: without_skill
pass_rate_delta: 0.206171
cycle_time_degradation: -0.134615
tokens_delta: -230.0
thresholds:
  promote_quality_gain_min: 0.1
  max_cycle_time_degradation: 0.1
evidence_refs:
- _bmad-output/skill-benchmarks/chiseai-skill-autonomy/iteration-1/benchmark.json
- _bmad-output/skill-benchmarks/chiseai-skill-autonomy/iteration-1/benchmark.md
reason: pass-rate delta meets threshold and time degradation is acceptable
