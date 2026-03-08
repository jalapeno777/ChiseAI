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

2. Decide rollback
   - `decision: ROLLBACK | HOLD`
   - Identify target fallback version.

3. Execute rollback (if ROLLBACK)
   - Update registry preferred version to last known-good.
   - Mark degraded version as `on_hold`.

4. Persist and notify
   - Log to Redis promotion stream.
   - Create incident note and link evidence.

5. Follow-up
   - Open improvement cycle for degraded version.

Safety:
- Rollback can be automatic for severe regressions.
- Missing skills are not rollback events; they are coverage KPI events.

