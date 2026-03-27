---
story_id: ST-ICT-020-PART-B
title: Live Paper Trading Data Collection - Time-Gated
epic_id: EP-ICT-006
status: in_progress
observation_start: "2026-03-25"
target_completion: "2026-04-22"
duration_weeks: 4
owner: operations
---

# Observation Checkpoint

## Schedule

| Checkpoint | Date       | Status      | Signals (Control) | Signals (Treatment) | p-value | Action            |
| ---------- | ---------- | ----------- | ----------------- | ------------------- | ------- | ----------------- |
| Start      | 2026-03-25 | ✅ Complete | 0                 | 0                   | N/A     | Begin collection  |
| Week 1     | 2026-04-01 | ⏳ Pending  | -                 | -                   | -       | Review interim    |
| Week 2     | 2026-04-08 | ⏳ Pending  | -                 | -                   | -       | Review interim    |
| Week 3     | 2026-04-15 | ⏳ Pending  | -                 | -                   | -       | Review interim    |
| Final      | 2026-04-22 | ⏳ Pending  | -                 | -                   | -       | Go/No-Go decision |

## Early Stopping Criteria

- p > 0.3 after 50 signals: Stop (futile)
- p < 0.05 with effect > 2%: Early confirm
- Minimum 100 signals per group required

## Signal Types

- **Control:** Non-ICT baseline (math-only signals)
- **Treatment:** ICT-enhanced (CVD, FVG, Order Block)
- **Excluded:** BOS/CHoCH per BL-BOS-CHOCH-001

## Current Metrics

_Last updated: 2026-03-27_

| Metric                  | Value |
| ----------------------- | ----- |
| Days elapsed            | 2     |
| Signals collected       | 0     |
| Control win rate        | N/A   |
| Treatment win rate      | N/A   |
| Effect size (Cohen's h) | N/A   |
| Current p-value         | N/A   |

### Status Notes

- **ICT feature flag flipped to `true`** as of 2026-03-27
- **Cron jobs restarted** and running
- **Signal pipeline now active** — treatment signal collection began 2026-03-27 (2 days after observation window opened on 2026-03-25)
- **Treatment signals (CVD, FVG, Order Block)** now flowing
- **BOS/CHoCH remains excluded** per BL-BOS-CHOCH-001

## Next Checkpoint

**Date:** 2026-04-01
**Owner:** Operations Team
**Action:** Review Week 1 data, check early stopping criteria
