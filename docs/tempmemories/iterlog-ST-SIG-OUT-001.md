---
story_id: ST-SIG-OUT-001
title: "signal_id correlation linkage"
status: completed
priority: P1
started_at: "2026-03-30T05:15:46Z"
completed_at: "2026-03-30T05:20:00Z"
branch: feature/ST-SIG-OUT-001-003-outcome-pipeline
head_sha: 54efa160dc1e3dce02eff190740fc40db0fc82b6
merged_to_main: false
needs_manual_qdrant_import: true
---

# Iterlog: ST-SIG-OUT-001 — signal_id correlation linkage

## Evidence

- **Commit**: `54efa160dc1e3dce02eff190740fc40db0fc82b6`
- **File changed**: `src/ml/feedback/signal_outcome_matcher.py` (+4/-5)
- **Branch**: `feature/ST-SIG-OUT-001-003-outcome-pipeline` (pushed to origin, not yet merged to main)
- **Test summary**: No new tests required; existing matcher tests pass with filter removal

## Key Decisions

- Removed `status='closed'` filter from signal_outcome_matcher query
- Closed positions were invisible to outcome linkage, causing correlation misses
- outcome_type classification added to integration pipeline for downstream consumers (ST-SIG-OUT-003 dependency)

## Learnings

- Signal-outcome matching must include closed positions in query scope
- Status filters can silently drop valid matches when lifecycle state changes after close
- Correlation linkage is prerequisite for outcome writer resume and outcome_type lifecycle

## Structured Issues

issues: []

## Metacognitive Predictions

- `predicted_outcome`: Remove status filter, enabling closed position matching in signal_outcome_matcher
- `predicted_risks`: Low risk; filter removal may increase result set size
- `confidence`: 0.85
- `verification_plan`: Verify matcher query returns closed positions after filter removal
- `expected_metrics`: 0 regression in existing tests

## Metacognitive Outcomes

- `actual_outcome`: Filter removed successfully; closed positions now visible to matcher
- `actual_metrics`: 0 test regressions; 1 file changed
- `wins`: Correct root cause identification (status filter exclusion)
- `misses`: None
- `new_prevention_rules`: Always include all position statuses in outcome matcher queries unless there is a documented reason to filter

## Metacognitive Calibration

- `predicted_confidence`: 0.85
- `observed_result`: success
- `calibration_delta`: 0.0
- `confidence_adjustment_recommendation`: maintain

## Thinking Partner Status

tp_mode: autonomous
no_issues_detected: true

## Insights Sent To Aria

NO_ISSUES_PACKET

- no_issues_packet_id: NIP-ST-SIG-OUT-001-001
- story_id: ST-SIG-OUT-001
- rationale: Straightforward filter removal with clear root cause; no ambiguity

## Aria Decisions

ARIA_DECISION

- aria_decision_id: AD-ST-SIG-OUT-001-001
- decision: PROCEED
- story_id: ST-SIG-OUT-001

Thinking Partner Proof: autonomous | ST-SIG-OUT-001 | IP:NIP-ST-SIG-OUT-001-001 | AD:AD-ST-SIG-OUT-001-001 | Risks:0
