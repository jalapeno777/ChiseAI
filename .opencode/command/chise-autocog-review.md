---
name: "chise-autocog-review"
description: "Aria review pass over backend autonomous cognition outputs with severity classification and action proposals."
disable-model-invocation: true
---

Aria review protocol:

1. Read latest cycle artifact in `_bmad-output/autocog/cycles/`.
2. Read latest self-assessment artifact in `docs/governance/self_assessments/`.
3. Build `AUTOCog_REVIEW_PACKET`:
   - `run_id`
   - `top_findings[]` with:
     - `severity`: `low|medium|high|critical`
     - `summary`
     - `evidence`
     - `recommended_action`
     - `layman_alert`:
       - `title`
       - `why_this_happened`
       - `intended_resolution`
       - `expected_improvement`
       - `result_status`
       - `evidence_reasoning[]`
4. Severity policy:
   - low/medium -> mark as `auto_action_candidate=true`
   - high/critical -> mark as `escalation_required=true`
5. Include explicit recommendation list (ordered):
   - immediate
   - near-term
   - deferred
