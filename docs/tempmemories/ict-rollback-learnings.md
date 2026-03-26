---
type: learnings
story_id: ST-ICT-022
created: 2026-03-25T00:00:00Z
tags:
  - ict
  - rollback
  - learnings
author: worker
priority: medium
---

# ICT Rollback Learnings

## Overview

Documented rollback procedures for ICT confluence feature (ST-ICT-022).

## Key Findings

### Feature Flag Location

- Redis key: `chiseai:feature:ict_confluence:enabled`
- Default state: `false` (disabled)
- Rollback command: `SET chiseai:feature:ict_confluence:enabled false`

### Rollback Triggers

1. **Validation Failure**: p-value > 0.05 after minimum signals
2. **Performance Degradation**: Win rate drop > 5%, latency > 500ms
3. **Safety Issue**: Exception in Layer 1 or confluence code

### Rollback Procedure

1. Execute: `redis-cli SET chiseai:feature:ict_confluence:enabled false`
2. Verify: `redis-cli GET chiseai:feature:ict_confluence:enabled` returns "false"
3. Confirm: System health check returns healthy
4. Document: File incident with metrics

## Recommendations

1. Always verify flag state after rollback
2. Monitor system stability for 5 minutes post-rollback
3. Capture logs before re-enabling
4. Complete root cause analysis before re-deployment

## Evidence

- Runbook: `docs/runbooks/ict-rollback-procedures.md`
- Test: `scripts/validation/test_ict_rollback.py`
