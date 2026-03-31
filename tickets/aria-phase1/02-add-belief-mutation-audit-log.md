# Add immutable belief mutation audit log

## Objective
Record every belief mutation as a structured event with evidence, severity, and approval metadata.

## Why this matters
The current belief system can mutate autonomously. Governance now requires auditable mutation history and notification hooks.

## Scope
- add event schema support
- write audit event on create/update/deprecate/promote/conflict resolution
- include evidence summary and approval flags
- ensure append-only semantics

## Deliverables
- schema integration
- writer utility
- tests for event creation and append-only behavior

## Acceptance criteria
- every belief mutation emits an audit event
- approval-required changes are flagged before apply
- notification mode can be derived from severity and approval status

## Notes
Prefer one canonical event model shared by digest and immediate alert routing.
