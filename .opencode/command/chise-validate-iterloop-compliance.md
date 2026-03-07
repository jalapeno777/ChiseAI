---
name: "chise-validate-iterloop-compliance"
description: "ChiseAI: validate iteration loop compliance for a story (acceptance criteria, phase, Redis iterlog)."
disable-model-invocation: true
---

Validate that a story follows ChiseAI iteration loop requirements.

## Prerequisites
- scripts/validate_iterloop_compliance.py exists
- story_id known

## Execution

```bash
python3 scripts/validate_iterloop_compliance.py --story-id=<story_id>
python3 scripts/validation/validate_insight_governance.py --story-id=<story_id> --strict
python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict
```

## Checks Performed
- Acceptance criteria defined in Redis iterlog
- Proper phase tracking
- Required fields present
- No orphaned implementations
- Insight-governance fields present (`INSIGHT_PACKET` / `ARIA_DECISION` shape)
- No silent scope drift fields missing (`scope_impact`, `prd_scope_change`)
- Metacognition sections and required fields present (prediction/outcome/calibration)

## Success Criteria
- Exit code 0
- "✅ Iteration loop compliance validated"

## Failure Handling

If violations found:
1. Review specific issues in output
2. Fix missing acceptance criteria, phase, or fields
3. Re-run this command
4. Document any exceptions

## Pre-Commit Recommendation

Add to .git/hooks/pre-commit to catch violations early.
