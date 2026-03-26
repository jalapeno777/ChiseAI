---
story_id: ICT-022
type: pattern
created: "2026-03-25T00:00:00"
tags:
  - ict
  - rollback
  - learnings
---

# ICT Rollback Learnings

## Redis Key Alignment (Critical Fix)

**Issue:** Initial runbook used wrong Redis key pattern.

**Old (Incorrect):**

- `chiseai:feature:ict_confluence:enabled`
- `chiseai:feature:ict_layer1:enabled`

**Correct (per ict_feature_flags.py):**

- `ict:feature_flags:integration` (master switch)
- `ict:feature_flags:cvd`
- `ict:feature_flags:fvg`
- `ict:feature_flags:order_block`
- `ict:feature_flags:bos_choch`

**Database:** 1 (REDIS_DB env var)
**TTL:** 3600 seconds (setex)
**Default:** true for integration, cvd, fvg, order_block; false for bos_choch

## Rollback Commands

```bash
# Quick rollback
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false

# Full rollback (all signals)
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:integration false
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:cvd false
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:fvg false
redis-cli -h host.docker.internal -p 6380 -n 1 SET ict:feature_flags:order_block false
```

## Testing

- 15 tests in scripts/validation/test_ict_rollback.py
- Tests verify actual ICTFeatureFlags consumer behavior
- All tests pass with correct keys
