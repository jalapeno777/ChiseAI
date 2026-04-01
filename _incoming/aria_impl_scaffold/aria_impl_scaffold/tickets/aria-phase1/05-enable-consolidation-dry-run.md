# Enable consolidation in dry-run mode

## Objective
Safely activate the existing consolidation pipeline in dry-run mode with audit outputs.

## Why this matters
Consolidation exists but is disabled, which risks unbounded memory growth and uncontrolled tempmemory expansion.

## Scope
- enable dry-run schedule
- emit archive/promote candidates
- add visibility for growth pressure
- define rollback trigger

## Deliverables
- dry-run config change
- audit output artifact
- basic monitoring/summary report

## Acceptance criteria
- no destructive action occurs in dry run
- candidate decisions are inspectable
- growth trends are observable
- rollback path is documented

## Notes
Initial live phase should only archive low-risk classes with extended retention.
