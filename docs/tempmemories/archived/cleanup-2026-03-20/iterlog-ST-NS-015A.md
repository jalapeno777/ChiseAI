---
story_id: ST-NS-015A
story_title: Correlation Calculation Engine
epic_id: EP-NS-003
phase: implementation
status: completed
started_at: "2026-02-10"
completed_at: "2026-02-10"
needs_manual_qdrant_import: true
---

## Summary
Split from parent story ST-NS-015 to comply with 5 SP policy. Implements the correlation calculation engine for portfolio positions.

## Key Decisions
- Story created as part of compliance split to reduce story points
- Rolling 30-day correlation window implemented for dynamic updates
- Unit tests validate calculation accuracy against known values

## Learnings
- Splitting large stories improves granularity and traceability
- Correlation calculations need careful handling of edge cases (zero volatility, missing data)

## Evidence
- Validation status: validated
- Story points: 4
- FR-015 is satisfied

## Incidents
None

## Scope Ownership
- Owner: main
- Status: Merged
