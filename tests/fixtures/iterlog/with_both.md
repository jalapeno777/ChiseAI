---
story_id: TEST-BOTH-001
story_title: Test With Both Structured and Regex Issues
phase: implementation
status: completed
started_at: "2026-03-01T00:00:00Z"
completed_at: "2026-03-01T23:59:59Z"
---

## Incidents
None

## Scope Ownership
Scope: tests/fixtures/iterlog/

## Implementation Notes
This file has both structured issues and regex-detectable text.
The structured section should take precedence.

## Structured Issues

issues:
  - issue_type: "db_connectivity"
    root_cause: "Redis connection timeout"
    fix_applied: "incre connection pool size"
    time_lost_minutes: 15
    recurrence_hint: "monitor connection pool metrics"
    impact_area: "reliability"
    resolved: true

## Regex-detectable patterns
- Error: Connection refused to database at localhost:5432
- Warning: High memory usage detected at 85%
