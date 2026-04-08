---
story_id: ST-WIRE-ERROR-RATE-TRACKER
title: Wire ErrorRateTracker into Execution Pipeline
status: planned
priority: P2
size_sp: 3
created: 2026-04-08
parent_epic: ""
assignee: ""
---

# Story: Wire ErrorRateTracker into Execution Pipeline

## Background

The error rate monitoring infrastructure (`src/execution/alerts/error_rate_integration.py`) exists and is monitored by `scripts/monitoring/error_rate_monitor.py`, but no execution code calls `ErrorRateTracker.record_operation()`. This means the monitor has no real data and can only fire false positives from stale/test data.

A producer-safety gate was added (commit b835f4ad) to suppress alerts when data is stale, but the tracker still needs to be wired into the actual execution pipeline.

## Acceptance Criteria

1. `ErrorRateTracker.record_operation()` is called on every execution attempt (both success and failure paths)
2. The EXECUTION category in Redis (`chise:paper:metrics:error_rate:EXECUTION:stats`) reflects real-time error rates
3. Discord alerts fire only when genuine error rate thresholds are exceeded
4. Existing tests pass + new unit tests cover the integration points
5. No performance degradation from the tracking overhead

## Implementation Notes

- Identify the execution connector code paths (order submit, cancel, modify)
- Add `record_operation(category="EXECUTION", success=bool, error_msg=str)` calls in try/except blocks
- Consider adding categories: SIGNAL_DELIVERY, ORDER_MANAGEMENT, DATA_PIPELINE
- Ensure thread-safety if execution runs in async/multi-threaded context

## Risk

- Low: Adding tracking calls is non-invasive; the safety gate prevents false alerts even if wiring is incomplete

## Dependencies

- None

## Evidence Required

- Diff showing record_operation() calls added to execution paths
- Redis state showing live error rate data after wiring
- Test results
