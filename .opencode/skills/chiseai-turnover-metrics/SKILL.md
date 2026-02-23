---
name: chiseai-turnover-metrics
description: Compute and report turnover as trades/day (avg/p95/max) using filled orders aggregated per order_id and UTC day buckets.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-turnover-metrics

## Goal

Define the exact turnover metric implementation so backtest, paper, and live are comparable.

## When To Use

- Evaluating strategy candidates for selection.
- Generating paper or backtest reports.
- Comparing strategies for turnover-based tie-breaking.
- Validating trade budgeter compliance.

## When Not To Use

- Non-trading metrics (latency, uptime, etc.).
- Single-order analysis (not daily aggregation).
- Frontend display logic (this skill defines calculation, not presentation).

## Definition

- A "trade" is a **filled order aggregated per unique order_id** (partial fills do not add trades)
- Bucket by **UTC calendar day**
- Compute per window:
  - avg_trades_per_day
  - p95_trades_per_day
  - max_trades_per_day

## Implementation Notes

- Ensure days count equals the number of UTC days with valid market data in the evaluation window
- Report spike days separately (top 5 busiest days) to diagnose ops risk
- Use the same calculation in backtest and paper logs

## Output Template

- Window: start/end UTC
- Total trades, days, avg/p95/max
- Top 5 busiest days (date + trade count)
- Whether the candidate violates turnover ceilings

## Exit Conditions

- Turnover metrics calculated using UTC day buckets.
- Spike days identified and reported.
- Ceiling violation check completed.
- Results recorded in strategy card or report.

## Troubleshooting/Safety

- **Timezone confusion**: Always use UTC; document timezone in outputs.
- **Partial fills inflation**: Aggregate by order_id, not by fill event.
- **Missing days**: Exclude days with no market data from denominator.
- **Ceiling violations**: Flag immediately, require justification or strategy adjustment.

## Related Skills

- `chiseai-strategy-cicd-gates` - Uses turnover metrics for candidate selection
- `chiseai-paper-trading-canary` - Reports turnover in paper validation
- `chiseai-promotion-packet` - Includes turnover in promotion evidence

## Related Commands

- `.opencode/command/chise-risk-audit.md` - May include turnover validation
