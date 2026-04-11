# Paper Canary TTL Policy

**Story**: PAPER-RECON-005  
**Date**: 2026-04-11  
**Decision**: AD-PAPER-RECON-001-20260411T123500Z-ttl14

## Current Policy

| Setting                    | Value                                   | Notes             |
| -------------------------- | --------------------------------------- | ----------------- |
| Redis `paper:*` key TTL    | 14 days (extended 2026-04-11)           | Previously 7 days |
| Index TTL (paper:index:\*) | 14 days                                 | Same as keys      |
| Postgres sync              | Enabled via `enable_postgres_sync=True` | Durable store     |

## Rationale for 14-day Interim Extension

- Redis is treated as **operational/realtime** store only
- Postgres is the **durable** store for canary trade data
- 14-day window provides safety buffer while Postgres mirror is stabilized
- After Postgres durability is proven (2+ weeks of clean sync), TTL may be reduced to 7 days again

## Rollback Plan

- If Postgres sync proves reliable: reduce TTL back to 7 days (remove interim extension)
- If Redis data loss observed: investigate and extend further if needed
- Decision debt tracked: DEBT-PAPER-TTL-ROLLBACK-001 (due 2026-04-29)

## What Happens at TTL Expiry

- Redis keys are deleted when TTL expires
- Index entries (sorted sets) are NOT automatically deleted when TTL expires — the index entries reference keys that are gone
- Postgres `signal_outcomes` is unaffected by Redis TTL

## Oracle for TTL Decisions

| Condition                                      | Action                                              |
| ---------------------------------------------- | --------------------------------------------------- |
| Postgres sync stable for 14 days               | Consider reducing TTL to 7 days                     |
| Postgres row count drops to 0                  | Immediately disable TTL reduction, investigate sync |
| Redis fill count diverges from Postgres by >10 | Extend TTL, investigate backfill                    |

## Approved By

- Aria: Decision AD-PAPER-RECON-001-20260411T123500Z-ttl14
- Craig: Endorsed via Aria delegation (implicit)
