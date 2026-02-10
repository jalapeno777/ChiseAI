---
story_id: ST-NS-009
story_title: Discord Alert Integration
phase: implementation
status: completed
started_at: "2026-02-10T00:00:00Z"
completed_at: "2026-02-10T00:30:00Z"
---

## Incidents
None

## Scope Ownership
Scope: src/discord_alerts/

## Implementation Notes
Send Discord alerts for high-confidence opportunities.

AC met: Internal actionable signals surfaced at ≥75% confidence (per FR-007); Discord message posted for signals meeting configured Discord posting threshold (default 40%); Discord alerts in 40-74% range posted as "watchlist" notifications; Each alert includes token, direction, confidence, key levels, and timestamp; Duplicate alerts within 15 minutes suppressed; FR-009 satisfied.
