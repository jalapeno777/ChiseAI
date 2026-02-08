---
name: turnover-metrics
description: Compute and report turnover as trades/day (avg/p95/max) using filled orders aggregated per order_id and UTC day buckets.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: metrics
---

## What I do
I define the exact turnover metric implementation so backtest, paper, and live are comparable.

## Definition
- A “trade” is a **filled order aggregated per unique order_id** (partial fills do not add trades)
- Bucket by **UTC calendar day**
- Compute per window:
  - avg_trades_per_day
  - p95_trades_per_day
  - max_trades_per_day

## Implementation notes
- Ensure days count equals the number of UTC days with valid market data in the evaluation window
- Report spike days separately (top 5 busiest days) to diagnose ops risk
- Use the same calculation in backtest and paper logs

## Output template
- Window: start/end UTC
- Total trades, days, avg/p95/max
- Top 5 busiest days (date + trade count)
- Whether the candidate violates turnover ceilings
