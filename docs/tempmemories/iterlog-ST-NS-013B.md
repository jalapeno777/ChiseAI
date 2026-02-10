---
story_id: ST-NS-013B
story_title: Stop-Loss Integration & Signal Delivery
epic_id: EP-NS-003
phase: implementation
status: completed
started_at: "2026-02-09T00:00:00Z"
completed_at: "2026-02-10T18:00:00Z"
acceptance_criteria:
  - Stop-loss level is included in every generated signal
  - Stop-loss is displayed in signal detail breakdown panel
  - Discord alerts include stop-loss level when signal is actionable
  - Stop-loss updates dynamically if key levels change before entry
  - Trailing stop option is calculated and offered when trend is strong
  - Stop-loss hit tracking is implemented for outcome correlation
  - FR-013 is satisfied: Stop-loss recommendation system
key_decisions:
  - Trailing stop offered only when trend strength indicator is high
  - Dynamic SL updates triggered by significant level changes
  - Hit tracking integrated with outcome correlation system
learnings:
  - Dynamic SL updates require careful state management
  - Trailing stops work best in strong trending markets
  - Discord alerts need SL info for actionable signals
---
