# Build final context assembly boundary

## Objective
Create a deterministic module that selects, orders, filters, and budgets memory before prompt injection.

## Why this matters
The current system has retrieval tooling but no proven single context assembly module with deterministic budget enforcement.

## Scope
- define final assembler interface
- load core identity first
- apply stale/confidence filters
- enforce hard token budget
- emit inclusion audit trace

## Deliverables
- assembler module
- inclusion trace format
- tests for ordering and filtering

## Acceptance criteria
- ordering follows approved priority order
- low-confidence stale conflicting items are rejected by default
- hard budget is enforced
- inclusion reasons are auditable

## Notes
Implement as a boundary layer; avoid rewriting low-level stores first.
