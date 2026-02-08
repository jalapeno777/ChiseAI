---
description: Compute trades/day turnover stats (avg/p95/max) for a given run or window.
agent: plan
subtask: true
---
Compute turnover as trades/day using the `turnover-metrics` skill definition.

Input:
- $ARGUMENTS may specify a date range (e.g., "2026-02-01..2026-02-07") or a run id.

Output:
- avg/p95/max trades/day
- top 5 busiest UTC days
- whether turnover ceilings were violated (avg≤20, p95≤30, max≤45)
