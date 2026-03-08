---
name: "chise-skill-promote"
description: "ChiseAI: evaluate whether a skill version should be promoted based on rolling effectiveness evidence."
disable-model-invocation: true
---

Run weekly or after benchmark cycles.

1. Gather evidence
   - Pull latest effectiveness events for `<skill_name>`.
   - Compare candidate version vs incumbent.

2. Apply promotion policy
   - Promote only if quality improves without harmful regressions.
   - Default thresholds:
     - quality/pass rate +10% OR
     - rework/regression rate -20%
     - cycle time degradation <=10%

3. Record decision
   - `decision: PROMOTE | HOLD`
   - Include metrics deltas and evidence refs.

4. Persist decision
   - Append to `bmad:chiseai:skills:promotions` (Redis).
   - Write markdown artifact under `docs/tempmemories/`.

5. Apply routing update (if promoted)
   - Update skill registry entry for preferred version.

Safety:
- If evidence is insufficient, choose `HOLD`.
- Never promote based on a single anecdotal run.

