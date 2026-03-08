---
story_id: ST-CONF-001
story_title: ECE Calculation per Strategy/Signal Type
phase: implementation
status: completed
started_at: 2026-02-14T00:00:00Z
completed_at: 2026-02-14T00:00:00Z
acceptance_criteria:
  - ECE calculations use correct binning (10 bins: 0-10%, 10-20%, etc.)
  - ECE is calculated per signal type (entry, exit, SL, TP)
  - Historical ECE values are tracked and trended over time
  - ECE calculations are verified against ground truth labels
  - ECE is queryable per strategy via API for calibration decisions
  - ECE updates daily with new prediction-outcome pairs
---

## Summary

Implemented ECE (Expected Calibration Error) calculation module with:
- ECECalculator with 10-bin binning
- Per-signal-type calculation
- ECEHistoryTracker for trending
- API endpoint for querying ECE per strategy
- Daily scheduler for automatic ECE updates

## Key Decisions

1. Used 10 equal-width bins (0-10%, 10-20%, ..., 90-100%) per AC
2. Implemented SignalType enum for type-safe signal classification
3. Used InfluxDB for persistent ECE history storage
4. Created FastAPI router with 4 endpoints for ECE queries
5. Implemented asyncio-based scheduler for daily updates

## Files Created

- src/confidence/ece.py - ECECalculator, ECEBin, ECEResult
- src/confidence/ece_tracker.py - ECEHistoryTracker
- src/api/ece_router.py - FastAPI router for ECE queries
- src/confidence/ece_scheduler.py - Daily ECE update scheduler
- tests/test_confidence/test_ece.py - ECE calculation tests
- tests/test_confidence/test_ece_tracker.py - Tracker tests
- tests/test_api/test_ece_router.py - API endpoint tests
- tests/test_confidence/test_ece_scheduler.py - Scheduler tests

## Scope Ownership

- src/confidence/: ST-CONF-001/jarvis/COMPLETED
- src/api/: ST-CONF-001/dev/2026-02-14

## Incidents

None.
