# Add notification routing and severity matrix

## Objective
Route governance and belief events either to daily digest or immediate alerts using one severity model.

## Why this matters
Discord notification support exists, but event completeness and severity guarantees are not yet reliable.

## Scope
- add policy-driven event router
- map events to low/medium/high/critical
- send immediate alerts for high/critical and approval requests
- stage daily digest builder for 8 PM America/Toronto

## Deliverables
- router implementation
- severity mapper
- digest builder skeleton
- tests for routing decisions

## Acceptance criteria
- high/critical events route immediately
- approval requests route immediately
- medium/low events enter digest
- timezone handling uses America/Toronto

## Notes
Hook into existing Discord notifier if already present.
