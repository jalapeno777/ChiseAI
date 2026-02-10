---
story_id: ST-NS-012B
story_title: Position Sizing Integration & API
epic_id: EP-NS-003
phase: implementation
status: completed
started_at: "2026-02-09T00:00:00Z"
completed_at: "2026-02-10T18:00:00Z"
acceptance_criteria:
  - Position sizing recommendations are generated automatically with each signal
  - Current portfolio exposure is factored into sizing calculations
  - API endpoint `/api/v1/position-size` returns sizing recommendation for a given signal
  - Sizing recommendations include: suggested size, sizing method used, risk amount, max position check
  - Integration with signal detail breakdown (ST-NS-010) to display sizing
  - Sizing is recalculated when portfolio balance changes >5%
  - FR-012 is satisfied: Position sizing engine implementation
key_decisions:
  - Exposed sizing via API endpoint for dashboard consumption
  - Integrated with portfolio state for exposure-aware calculations
  - Used Kelly Criterion, fixed fractional, and volatility-based methods
learnings:
  - Portfolio exposure must be factored in to avoid over-leveraging
  - API design should be consistent with other endpoints
  - Recalculation triggers need careful threshold tuning
---
