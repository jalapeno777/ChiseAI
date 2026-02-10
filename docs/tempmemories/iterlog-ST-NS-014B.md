---
story_id: ST-NS-014B
story_title: Risk Exposure Calculation & Dashboard
epic_id: EP-NS-003
phase: implementation
status: completed
started_at: "2026-02-09T00:00:00Z"
completed_at: "2026-02-10T18:00:00Z"
acceptance_criteria:
  - Total portfolio exposure is calculated as sum of position notionals
  - Margin utilization percentage is displayed (used / total)
  - Portfolio heat map shows exposure by token and direction
  - Risk metrics update in real-time on dashboard (<5s latency)
  - Maximum exposure alerts trigger at configurable thresholds (default 80%)
  - Risk report is generated on-demand with current exposure breakdown
  - FR-014 is satisfied: Portfolio risk exposure monitoring
key_decisions:
  - Heat map visualization shows long/short by token for directional bias
  - Real-time updates with 5s latency threshold for dashboard
  - Configurable alert thresholds per exposure type
learnings:
  - Heat map provides quick visual for concentration risk
  - Real-time requires efficient calculation caching
  - On-demand reports complement always-on monitoring
---
