---
story_id: "PROCESS-IMPROVEMENT-001"
status: "completed"
priority: "P1"
created_date: "2026-03-11"
author: "dev"
type: "example"
purpose: "Demonstrate complete metacognition fields for validator testing"
---

# Example Story: Complete Metacognition Fields

This is a test story demonstrating fully populated metacognition fields.
Use this as a reference for creating compliant stories.

## Story Description

### Title
Implement Metacognition Enforcement in Story Templates

### Background
The chiseai-metacognition-ops skill was promoted in ST-SKILL-EVAL-001, but
we lack enforcement mechanisms. Stories need to include metacognition fields
to enable organizational learning and calibration.

### Goals
1. Create story template with metacognition sections
2. Build validator script for compliance checking
3. Integrate validation into pre-commit hooks
4. Provide working examples for reference

---

## Acceptance Criteria

- [x] Story template created with metacognition fields
- [x] Metacognition validator script created and functional
- [x] Pre-commit hook updated with metacognition validation
- [x] Test story created with complete metacognition example
- [x] Validator passes for compliant stories
- [x] Validator fails for non-compliant stories (with clear errors)
- [x] Gate wiring verified (pre-commit runs on commit)

---

## Metacognitive Predictions

**predicted_outcome:**
Create metacognition enforcement system with story template, validator script,
pre-commit hook integration, and test examples. All components will be
functional and tested within the estimated timeframe.

**predicted_risks:**
1. **Ownership conflict (30% likelihood)**: The scripts/validation/ directory
   may be owned by another active story, requiring scope negotiation or delay.
2. **Template adoption resistance (20% likelihood)**: Other agents may find
   the new fields burdensome, slowing adoption.
3. **Pre-commit hook complexity (15% likelihood)**: Integration with existing
   hooks may require careful coordination to avoid conflicts.

**confidence:** 0.80

**confidence_basis:**
- Clear requirements from worker contract
- Existing validation patterns in codebase (validate_metacog_compliance.py)
- Well-defined scope with specific deliverables
- Prior art in tempmemory frontmatter validation

**verification_plan:**
1. Run validator against compliant test story → expect PASS
2. Run validator against incomplete story → expect FAIL with clear errors
3. Test pre-commit hook with sample commits → expect blocking behavior
4. Run validator with --strict flag → expect proper enforcement
5. Test --fix flag → expect auto-addition of missing sections

**expected_metrics:**
```yaml
- metric: "field_coverage"
  target: "100%"
  measurement_method: "validator tests on all required fields"
  
- metric: "execution_time"
  target: "<= 3 hours"
  measurement_method: "wall clock from task start to completion"
  
- metric: "test_pass_rate"
  target: "100%"
  measurement_method: "validator test suite"
```

---

## Metacognitive Outcomes

**actual_outcome:**
Successfully implemented all required components. Ownership conflict with
HOURLY-HEALTH-004 required 30 minutes of investigation before proceeding.
Template writing took longer than expected due to comprehensive example
creation. Pre-commit integration was straightforward due to existing patterns.

**actual_metrics:**
```yaml
- metric: "field_coverage"
  actual: "100%"
  target: "100%"
  delta: "0%"
  
- metric: "execution_time"
  actual: "3.5 hours"
  target: "<= 3 hours"
  delta: "+17%"
  
- metric: "test_pass_rate"
  actual: "100%"
  target: "100%"
  delta: "0%"
```

**wins:**
1. **Existing validator reference**: validate_metacog_compliance.py provided
   excellent patterns for field extraction and validation logic.
2. **Clear acceptance criteria**: The worker contract had very specific,
   measurable criteria that made validation straightforward.
3. **Template reuse**: Could leverage existing tempmemory frontmatter
   validation patterns for the pre-commit hook integration.

**misses:**
1. **Template writing time**: Did not account for the time needed to write
   comprehensive examples in the template. Added ~30 minutes.
2. **Ownership check timing**: Should have checked ownership before starting
   work, not after session initialization failed.
3. **Strict mode validation**: Initially underestimated complexity of
   validating field values vs just field presence.

**new_prevention_rules:**
1. **Early ownership check**: Always run ownership check before claiming scope
   in Redis. Use `chise-check-ownership` command during task planning phase.
2. **Buffer for documentation**: Add 25% time buffer for tasks involving
   template creation or extensive documentation writing.
3. **Reference existing validators**: Check for existing validation scripts
   before creating new ones - they often provide reusable patterns.
4. **Test both modes**: Always test validator in both normal and strict mode
to ensure proper CI integration.

---

## Metacognitive Calibration

**predicted_confidence:** 0.80

**observed_result:** success

**calibration_delta:** -0.20

**confidence_adjustment_recommendation:**
I was conservative in my confidence estimate. For tooling/infrastructure stories
with clear requirements and existing patterns, I should use 0.85-0.90 confidence
instead of 0.80. The ownership conflict was the main risk, but it was resolved
quickly without significant impact.

**pattern_insights:**
Tooling and infrastructure stories have lower variance than feature stories
when requirements are clear. Having existing patterns to reference significantly
reduces implementation risk. My confidence estimates tend to be conservative
for familiar task types - should calibrate upward for similar future tasks.

---

## Test Evidence

### Validator Test Results

```bash
# Test 1: Validate this compliant story
$ python3 scripts/validation/metacog_validator.py --file docs/tempmemories/test-story-metacog-example.md

============================================================
METACOGNITION VALIDATION RESULTS
============================================================

📄 docs/tempmemories/test-story-metacog-example.md
  ✅ Valid

============================================================
SUMMARY: 1/1 files valid
============================================================

# Test 2: Validate with strict mode
$ python3 scripts/validation/metacog_validator.py --file docs/tempmemories/test-story-metacog-example.md --strict
# Expected: PASS (all required fields present with values)

# Test 3: Validate with JSON output
$ python3 scripts/validation/metacog_validator.py --file docs/tempmemories/test-story-metacog-example.md --json
# Expected: JSON output with valid: true
```

### Pre-commit Hook Verification

```bash
# Test staging this file
$ git add docs/tempmemories/test-story-metacog-example.md
$ git commit -m "test: add compliant story example"
# Expected: Commit passes (story is compliant)
```

---

## References

- Template: `.opencode/templates/story-with-metacognition.md`
- Validator: `scripts/validation/metacog_validator.py`
- Related validator: `scripts/validation/validate_metacog_compliance.py`
- Skill: `chiseai-metacognition-ops`
