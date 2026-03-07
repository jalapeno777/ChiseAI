---
name: "chise-metacog-close"
description: "ChiseAI: close metacognitive loop with predicted-vs-actual outcome, calibration delta, and prevention-rule promotion."
disable-model-invocation: true
---

Run at story close, before/with `chise-iterloop-close`.

1. Outcome card
   - Required fields:
     - `story_id`
     - `actual_outcome`
     - `actual_metrics`
     - `misses` (where prediction was wrong)
     - `wins` (where prediction was right)
     - `new_prevention_rules` (if any)
   - Record in iterlog under `## Metacognitive Outcomes`.

2. Calibration card
   - Required fields:
     - `predicted_confidence`
     - `observed_result` (`success|partial|failure`)
     - `calibration_delta` (absolute error or equivalent)
     - `confidence_adjustment_recommendation`
   - Record in iterlog under `## Metacognitive Calibration`.

3. Redis writes (DB 0)
   - Write outcome card to `bmad:chiseai:metacog:outcome:story:<story_id>`
   - Update weekly agent calibration key:
     - `bmad:chiseai:metacog:calibration:agent:<agent>:weekly:<yyyy-Www>`
   - Upsert any prevention rules into:
     - `bmad:chiseai:metacog:prevention_rules`

4. Qdrant promotion
   - Promote durable lessons to `ChiseAI_metacognition`.
   - If unavailable, write fallback markdown in `docs/tempmemories/` with:
     - `needs_manual_qdrant_import: true`

5. Compliance check
   - Run:
     - `python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict`

