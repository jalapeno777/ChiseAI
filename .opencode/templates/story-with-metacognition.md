---
type: story_template
version: "1.0"
metacognition_required: true
template_id: story-with-metacognition
---

# Story Template with Metacognition

Use this template for all new stories to ensure metacognitive tracking is captured from the start.

---

## Story Header (Required)

```yaml
---
story_id: "[STORY-PREFIX]-[NUMBER]"  # e.g., ST-001, CH-042
status: "[draft|in_progress|completed|archived]"
priority: "[P0|P1|P2|P3]"
created_date: "YYYY-MM-DD"
author: "[agent_name]"
---
```

---

## Story Description

### Title
[Brief, descriptive title]

### Background
[Context and motivation for this story. Why are we doing this?]

### Goals
1. [Specific, measurable goal 1]
2. [Specific, measurable goal 2]
3. [Specific, measurable goal 3]

### Scope
**In Scope:**
- [Item 1]
- [Item 2]

**Out of Scope:**
- [Item 1]
- [Item 2]

---

## Acceptance Criteria

- [ ] Criterion 1: [Specific, testable condition]
- [ ] Criterion 2: [Specific, testable condition]
- [ ] Criterion 3: [Specific, testable condition]

---

## Metacognitive Predictions (Fill at story start)

> **Purpose**: Capture what you expect to happen before execution begins.
> This enables calibration learning by comparing predictions to actual outcomes.

### Expected Outcomes
**predicted_outcome:** 
[Clear description of what you expect to achieve. Be specific and measurable.
Example: "Implement metacognition validator with 100% field coverage and 
pre-commit integration working within 4 hours."]

### Predicted Risks
**predicted_risks:**
1. **[Risk 1]**: [Description and likelihood. Example: "Ownership conflict 
   with existing validation scripts (30% likelihood) - may need to negotiate 
   scope or use different filename."]
2. **[Risk 2]**: [Description and likelihood]
3. **[Risk 3]**: [Description and likelihood]

### Confidence Level
**confidence:** [0.0-1.0]
[Your confidence level as a decimal between 0.0 (no confidence) and 1.0 
(absolute certainty). Example: 0.75 means 75% confident.]

**confidence_basis:**
[Why do you have this confidence level? What evidence supports it?
Example: "Similar validation scripts exist in codebase (validate_metacog_compliance.py), 
pre-commit hook pattern is well-established."]

### Verification Plan
**verification_plan:**
1. [Step 1: How will you verify success?]
2. [Step 2: How will you verify success?]
3. [Step 3: How will you verify success?]

### Expected Metrics
**expected_metrics:**
```yaml
- metric: "[name]"
  target: "[numeric target with units]"
  measurement_method: "[how measured]"
  
- metric: "code_coverage"
  target: ">= 80%"
  measurement_method: "pytest --cov"
  
- metric: "execution_time"
  target: "<= 4 hours"
  measurement_method: "wall clock from start to PR handoff"
```

---

## Metacognitive Outcomes (Fill at story completion)

> **Purpose**: Document what actually happened vs. what was predicted.
> Capture wins, misses, and new prevention rules for organizational learning.

### Actual Outcomes
**actual_outcome:**
[What actually happened? Compare directly to predicted_outcome.
Example: "Successfully implemented metacognition validator with field coverage 
and pre-commit integration. Took 5 hours instead of 4 due to ownership conflict 
resolution."]

### Actual Metrics
**actual_metrics:**
```yaml
- metric: "[name]"
  actual: "[actual value]"
  target: "[original target]"
  delta: "[+/- X% or absolute difference]"
  
- metric: "code_coverage"
  actual: "85%"
  target: ">= 80%"
  delta: "+5%"
  
- metric: "execution_time"
  actual: "5 hours"
  target: "<= 4 hours"
  delta: "+25%"
```

### Wins
**wins:**
1. **[Win 1]**: [What went better than expected? What worked well?
   Example: "Existing validate_metacog_compliance.py provided good reference 
   implementation, reducing development time."]
2. **[Win 2]**: [Description]

### Misses
**misses:**
1. **[Miss 1]**: [What went worse than expected? What was missed?
   Example: "Ownership conflict with HOURLY-HEALTH-004 caused 1 hour delay. 
   Should check ownership earlier in planning."]
2. **[Miss 2]**: [Description]

### New Prevention Rules
**new_prevention_rules:**
1. **[Rule 1]**: [Specific rule to prevent similar misses in future.
   Example: "Always run ownership check before claiming scope in Redis. 
   Use `chise-check-ownership` command before starting work."]
2. **[Rule 2]**: [Description]

---

## Metacognitive Calibration (Fill at story completion)

> **Purpose**: Measure and improve calibration accuracy over time.
> Compare predicted confidence to actual results.

### Predicted Confidence
**predicted_confidence:** [0.0-1.0]
[Copy from Metacognitive Predictions section above]

### Observed Result
**observed_result:** [success|partial|failure]
[Overall assessment of story outcome:
- **success**: Met or exceeded all acceptance criteria
- **partial**: Met some criteria, missed others
- **failure**: Missed most or all criteria]

### Calibration Delta
**calibration_delta:** [predicted_confidence - observed_success_as_decimal]
[Calculate: predicted_confidence minus actual success (1.0 for success, 
0.5 for partial, 0.0 for failure). 
Example: predicted 0.75, result was success → delta = 0.75 - 1.0 = -0.25 
(underestimated capability)]

### Confidence Adjustment Recommendation
**confidence_adjustment_recommendation:**
[Based on delta, how should you adjust future confidence estimates?
Example: "I tend to be conservative (underestimate). For similar validation 
script tasks, should use 0.85 confidence instead of 0.75."]

### Pattern Insights
**pattern_insights:**
[Any patterns noticed? How does this story compare to similar past stories?
Example: "Validation scripts consistently take 20% longer than estimated 
due to edge case handling. Future estimates should include 25% buffer."]

---

## Example: Complete Story with Metacognition

### Story Header
```yaml
---
story_id: "PROCESS-IMPROVEMENT-001"
status: "completed"
priority: "P1"
created_date: "2026-03-11"
author: "dev"
---
```

### Metacognitive Predictions Example
```yaml
predicted_outcome: "Create metacognition enforcement system with story template, 
validator script, pre-commit hook, and test examples."

predicted_risks:
  - "Ownership conflict with existing validation directory (30%)"
  - "Pre-commit hook integration complexity (20%)"
  - "Template adoption resistance from other agents (15%)"

confidence: 0.80
confidence_basis: "Clear requirements, existing validation patterns to reference, 
well-defined scope"

verification_plan:
  1. "Template passes schema validation"
  2. "Validator correctly identifies compliant/non-compliant stories"
  3. "Pre-commit hook blocks commits with missing metacog fields"
  4. "All tests pass"

expected_metrics:
  - metric: "field_coverage"
    target: "100%"
    measurement_method: "validator tests"
  - metric: "execution_time"
    target: "<= 3 hours"
    measurement_method: "wall clock"
```

### Metacognitive Outcomes Example
```yaml
actual_outcome: "Completed all deliverables. Ownership conflict caused 30 min delay. 
Template design took longer than expected due to example writing."

actual_metrics:
  - metric: "field_coverage"
    actual: "100%"
    target: "100%"
    delta: "0%"
  - metric: "execution_time"
    actual: "3.5 hours"
    target: "<= 3 hours"
    delta: "+17%"

wins:
  - "Existing validate_metacog_compliance.py provided excellent reference"
  - "Pre-commit hook integration was straightforward"

misses:
  - "Didn't account for template example writing time"
  - "Ownership check should happen earlier in process"

new_prevention_rules:
  - "Always check existing validators before creating new ones"
  - "Add 20% buffer for documentation/examples in estimates"
```

### Metacognitive Calibration Example
```yaml
predicted_confidence: 0.80
observed_result: "success"
calibration_delta: -0.20  # 0.80 - 1.0 = -0.20 (underestimated)

confidence_adjustment_recommendation: "For tooling/infrastructure stories with 
clear requirements, use 0.85-0.90 confidence. I'm consistently conservative."

pattern_insights: "Tooling stories have lower variance than feature stories. 
Existing patterns significantly reduce risk."
```

---

## Quick Reference

### Required Fields Checklist

**At Story Start (Prediction):**
- [ ] `predicted_outcome`
- [ ] `predicted_risks`
- [ ] `confidence` (0.0-1.0)
- [ ] `confidence_basis`
- [ ] `verification_plan`
- [ ] `expected_metrics`

**At Story Completion (Outcome):**
- [ ] `actual_outcome`
- [ ] `actual_metrics`
- [ ] `wins`
- [ ] `misses`
- [ ] `new_prevention_rules`

**At Story Completion (Calibration):**
- [ ] `predicted_confidence`
- [ ] `observed_result` (success/partial/failure)
- [ ] `calibration_delta`
- [ ] `confidence_adjustment_recommendation`

### Validation Commands

```bash
# Check if story file is compliant
python3 scripts/validation/metacog_validator.py --file story.md

# Auto-fix missing sections (adds templates)
python3 scripts/validation/metacog_validator.py --file story.md --fix

# Strict mode for CI (requires non-empty values)
python3 scripts/validation/metacog_validator.py --file story.md --strict
```

---

## Notes

- This template is enforced via pre-commit hooks
- P0/P1 stories require complete metacognition sections
- P2/P3 stories warn on missing sections but don't block
- Run `chise-metacog-start` at iteration start
- Run `chise-metacog-close` at iteration close
