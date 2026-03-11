---
name: "chise-runtime-guardrail-canary"
description: "Run a safe canary for aria-runtime/jarvis-runtime with guardrail parity checks and rollback conditions."
disable-model-invocation: true
---

# Runtime Canary (Safe Rollout)

## Goal
Validate throughput improvements **without** guardrail or quality regression.

## Scope
- Use `aria-runtime` + `jarvis-runtime` for a bounded story slice only.
- Do not change merge authority or CI policy.

## Preconditions
1. Confirm canonical docs unchanged:
   - `AGENTS.md`
   - `.opencode/agent/Aria.md`
   - `.opencode/agent/Jarvis.md`
2. Confirm runtime profiles exist:
   - `.opencode/agent/AriaRuntime.md`
   - `.opencode/agent/JarvisRuntime.md`
3. Confirm question-routing guardrail:
   - `python3 scripts/validation/validate_question_routing_policy.py`
4. Capture baseline:
```bash
opencode stats --days 1 --models 20 --tools 20 --project ""
```

## Canary procedure
1. Select one low/medium-risk story.
2. Run that story with `aria-runtime` delegating to `jarvis-runtime`.
3. Require the same evidence bundle as normal:
   - AC mapping
   - test commands + results
   - live validation checks
   - incidents/blockers
   - quality sentinels all `true`:
     - `ac_coverage_complete`
     - `validation_evidence_present`
     - `risk_review_complete`
4. Track operational metrics:
   - time-to-first-plan
   - time-to-completion
   - rework count
   - escalation count

## Hard fail criteria (immediate rollback)
- Missing guardrail/compliance artifact required by canonical policy
- Increased hallucination/derailment compared to baseline
- Missing or weaker validation evidence
- Scope-lock/ownership/merge authority violations

## Success criteria
- Equal or better completion quality
- No guardrail violations
- Lower or equal cycle time
- Lower or equal rework/incident count

## Rollback
If any hard fail criterion is met:
1. stop runtime usage for that story
2. switch back to full `aria` + `jarvis`
3. log incident and prevention rule in iterlog

## Post-canary measurement
```bash
opencode stats --days 1 --models 20 --tools 20 --project ""
```
Compare against baseline for throughput and quality outcomes.
