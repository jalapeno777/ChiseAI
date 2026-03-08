---
name: "chise-metacog-weekly"
description: "ChiseAI: run weekly metacognition rollup and calibration trend review."
disable-model-invocation: true
---

Run weekly (or manually during incident-heavy periods).

1. Generate reflection/rollup artifacts
   - `python3 scripts/evaluation/run_weekly_reflection.py`
   - If needed: `python3 scripts/ops/reflection_runner.py --type=macro --period=weekly`

2. Build metacognition KPI snapshot
   - Include:
     - confidence calibration trend (weekly)
     - repeated incident fingerprint rate
     - reopen/regression rate
     - median cycle time trend
     - prevention-rule hit rate

3. Decision output
   - Produce one of:
     - `NO_CHANGE`
     - `TIGHTEN_AUTONOMY_THRESHOLDS`
     - `EXPAND_AUTONOMY_ENVELOPE`
   - Include rationale + evidence links.
   - Emit machine-parseable YAML with:
     - `week_id`
     - `generated_at_utc`
     - `decision`
     - `kpis` (ece, repeat_fingerprint_rate, reopen_regression_rate, median_cycle_time_hours, prevention_rule_hit_rate, p0_p1_incident_count)
     - `baseline_comparison`
     - `evidence_links`
     - `recommended_actions`
     - `owner`

4. Executive digest payload (REQUIRED for Discord)
   - Include:
     - `tp_mode_overall` (`ACTIVE|DEGRADED|OFF`)
     - `tp_proof_coverage_percent`
     - `insight_packets_weekly`
     - `aria_decisions_weekly`
     - `overrides_weekly`
     - `decision_latency_median_minutes` (IP -> AD)
     - `top_risk_signatures` (max 3)
     - `craig_attention_item` (single highest-value pending decision)

5. Memory promotion
   - Store summary into Qdrant (`ChiseAI_metacognition`) with week metadata.
   - Fallback: write markdown artifact under `_bmad-output/brain-eval/reflections/weekly/`.

6. Escalation rule
   - If confidence is degrading while incident rate rises for 2 consecutive weeks:
     - route a `critical` insight packet to Aria before expanding any autonomy settings.
