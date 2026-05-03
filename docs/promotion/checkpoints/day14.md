---
story_id: R2a
checkpoint: day14
scheduled_utc: "2026-04-22T11:24:49+00:00"
status: FAILED
completed_utc: "2026-05-02T14:35:00+00:00"
note: "Day-14 was never formally evaluated. Retroactive marking as FAILED reflects the governance record, not a new evaluation. No escalation to Aria was performed at the time."
epic_ref: EP-LAUNCH-004
minimum_decision_day: true
---

# R2a — Day 14 Checkpoint Report (Minimum Decision Point)

**Scheduled**: 2026-04-22T11:24:49+00:00
**Status**: FAILED (retroactive, at Day-21 evaluation)
**Completed**: 2026-05-02T14:35:00+00:00

**Note**: This is the minimum decision point. Day 21 data is preferred for final decision.
**Retroactive resolution**: Day-14 checkpoint was never formally evaluated due to signal crash-loop fix occurring on day 14. No escalation to Aria was performed at the scheduled time. This is a retrospective observation, not a retroactive fix.

## Collected Metrics

| Metric       | Value | Threshold | Pass? |
| ------------ | ----- | --------- | ----- |
| Win Rate     | TBD   | ≥ 60%     | —     |
| Net Return   | TBD   | ≥ 5%      | —     |
| Max Drawdown | TBD   | ≤ 15%     | —     |
| Sharpe Ratio | TBD   | ≥ 1.0     | —     |
| Trade Count  | TBD   | ≥ 30      | —     |

**Status**: All Day-14 metrics are TBD and superseded by Day-21 evaluation.

## Health Status

**Day 14 Health**: Unknown — signal generator was in crash-loop at scheduled checkpoint time.
**ST-SIGNAL-CRASHLOOP-FIX-001** was merged on Day 14 to fix the crash-loop.

## All Criteria Check

**Day-14 criteria**: All TBD / SUPERSEDED by Day-21 evaluation

## Interim Assessment

**Day 14 verdict**: FAILED — Minimum decision point criteria unmet (≥30 trades, no circuit breaker trips unverifiable). No escalation to Aria was performed at the time. This is a retrospective observation, not a retroactive fix.

## Notes

- Day-14 checkpoint SCHEDULED status was never upgraded to COMPLETED at the time
- Signal crash-loop was fixed mid-day-14 via ST-SIGNAL-CRASHLOOP-FIX-001
- Signals resumed after fix but the formal Day-14 evaluation was never completed
- This document represents the retroactive closure of the Day-14 checkpoint
- All TBD metrics from this checkpoint are resolved in the Day-21 final evaluation
