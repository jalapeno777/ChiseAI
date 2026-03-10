---
name: "chise-skill-promote"
description: "ChiseAI: evaluate whether a skill version should be promoted based on rolling effectiveness evidence."
disable-model-invocation: true
---

Run weekly or after benchmark cycles.

1. Gather evidence
   - Pull latest effectiveness events for `<skill_name>`.
   - Compare candidate version vs incumbent.
   - If benchmark artifact exists, run:
     ```bash
     python3 scripts/ops/skill_promote_from_benchmark.py \
       --skill-name <skill_name> \
       --candidate-version <candidate_version> \
       --incumbent-version <incumbent_version_or_blank> \
       --benchmark-json <path_to_benchmark.json> \
       --apply-registry-update
     ```
   - This writes:
     - decision artifact under `docs/tempmemories/`
     - Redis promotion event in `bmad:chiseai:skills:promotions`

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
   - Include benchmark evidence refs when available.

5. Apply routing update (if promoted)
   - Update skill registry entry for preferred version.
   - Canonical registry path: `docs/metrics/skill-versions.yaml`.

Safety:
- If evidence is insufficient, choose `HOLD`.
- Never promote based on a single anecdotal run.
