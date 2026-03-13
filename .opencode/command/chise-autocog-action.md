---
name: "chise-autocog-action"
description: "Apply low/medium autocog improvements automatically and escalate high/critical items to Craig."
disable-model-invocation: true
---

Action routing protocol:

1. Input: latest `AUTOCog_REVIEW_PACKET`.
2. For each finding:
   - `low|medium`:
     - implement fix autonomously (within guardrails),
     - run targeted tests,
     - record evidence in iterlog/memory.
   - `high|critical`:
     - do not auto-implement silently,
     - prepare escalation to Craig with:
       - issue + impact,
       - recommended fix,
       - expected timeline/risk tradeoff,
       - default-safe interim mitigation.
3. Post Discord summary event with:
   - implemented low/medium actions count
   - escalated high/critical items count
   - artifact references
4. Ensure no action violates constitution/soul guardrails.

