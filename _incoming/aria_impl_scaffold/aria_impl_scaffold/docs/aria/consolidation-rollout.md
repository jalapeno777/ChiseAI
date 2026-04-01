# Consolidation Rollout

## Objective
Enable the existing consolidation pipeline safely.

## Phase A — dry run
- keep destructive operations disabled
- emit candidate archive/promote decisions
- produce audit artifact
- measure volume, false positives, retention pressure

## Phase B — conservative live mode
- enable archive only for low-risk classes
- double default retention windows initially
- keep promote operations limited
- require audit log for every action

## Phase C — monitored expansion
- widen covered memory classes
- add alerts for abnormal growth or aggressive pruning
- track digest inclusion of archival summaries

## Rollback rule
Any unexpected identity loss, lesson disappearance, or significant recall degradation should revert consolidation to dry-run mode immediately.
