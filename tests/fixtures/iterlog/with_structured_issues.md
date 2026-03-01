---
story_id: TEST-STRUCTURED-001
story_title: Test Structured Issues Only
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
Test iterlog with structured issues for structured parsing tests.

This file should be parsed first before regex patterns.

## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "missing dependency in requirements.txt"
    fix_applied: "added pytest-asyncio>=0.21.0 to requirements.txt"
    time_lost_minutes: 45
    recurrence_hint: "check deps before commit"
    impact_area: "efficiency"
    resolved: true
