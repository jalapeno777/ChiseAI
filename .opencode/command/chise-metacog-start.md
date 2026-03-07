---
name: "chise-metacog-start"
description: "ChiseAI: initialize metacognitive prediction artifacts for a story (before implementation/execution)."
disable-model-invocation: true
---

Run at story start, after `chise-iterloop-start`.

1. Create prediction card
   - Required fields:
     - `story_id`
     - `owner_agent` (`aria|jarvis|worker`)
     - `predicted_outcome`
     - `predicted_risks` (1-3)
     - `confidence` (0.0-1.0)
     - `verification_plan`
     - `expected_metrics` (at least one measurable metric)
   - Record in iterlog under `## Metacognitive Predictions`.

2. Persist to Redis (DB 0)
   - Write to `bmad:chiseai:metacog:prediction:story:<story_id>`:
     - `created_at`, `owner_agent`, `confidence`, `predicted_outcome`, `predicted_risks`, `expected_metrics`, `verification_plan`
   - Set TTL to 5 days (`EXPIRE 432000`).

3. Fetch relevant semantic memory (Qdrant)
   - Query prior related prevention rules/failed predictions for similar scope.
   - If unavailable, add fallback note in `docs/tempmemories/`.

4. Inject into planning handoff
   - Ensure Jarvis task contract includes:
     - prediction assumptions
     - known risk signatures
     - prevention rules to apply

5. Gate
   - Do not mark story execution ready unless prediction card exists and is measurable.

