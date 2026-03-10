---
name: "chise-skill-rollback"
description: "ChiseAI: rollback a promoted skill version when regression evidence exceeds guardrails."
disable-model-invocation: true
---

Run when canary/shadow/live evidence shows regressions.

1. Trigger conditions
   - regression spike above threshold, or
   - sustained rework increase, or
   - repeated severe misses tied to recent promotion.
   - If benchmark/live evidence exists, run:
     ```bash
     python3 scripts/ops/skill_rollback_from_evidence.py \
       --skill-name <skill_name> \
       --degraded-version <degraded_version> \
       --fallback-version <last_known_good_or_blank> \
       --benchmark-json <path_to_benchmark.json_or_blank> \
       --regression-rate <0.0-1.0_if_known>
     ```

2. Decide rollback
   - `decision: ROLLBACK | HOLD`
   - Identify target fallback version.

3. Execute rollback (if ROLLBACK)
   - Update registry preferred version to last known-good.
   - Mark degraded version as `on_hold`.
   - Persist registry update in `docs/metrics/skill-versions.yaml`.

4. Persist and notify
   - Log to Redis promotion stream.
   - Create incident note and link evidence.

5. Follow-up
   - Open improvement cycle for degraded version.

Safety:
- Rollback can be automatic for severe regressions.
- Missing skills are not rollback events; they are coverage KPI events.
