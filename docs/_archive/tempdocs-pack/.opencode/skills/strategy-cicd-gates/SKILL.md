---
name: strategy-cicd-gates
description: Define strategy selection, turnover (trades/day), gates, and promotion rules for backtest→paper→human-approved live.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: gating
---

## What I do
I provide the **source of truth** for:
- Lexicographic objective: **profit after costs** → **turnover** → **DD (within caps)**
- Profit-close rule: **ε = 3%**
- Turnover definition: **trades/day** (filled orders per order_id, UTC buckets)
- Turnover ceilings: avg ≤ 20, p95 ≤ 30, max ≤ 45
- Trade Budgeter: **20 tokens/day**
- Promotion gates: Backtest → Paper Canary → Paper Full → Human approval → Live

## When to use me
Use this skill when you are:
- Implementing candidate evaluation, ranking, or gating
- Writing promotion logic (paper to live)
- Validating metrics and report outputs

## Decision rules (copy/paste friendly)
### Constraints (must pass)
- Enforce existing hard risk caps (DD, daily loss, exposure/leverage, etc.)

### Primary objective
- Maximize **net profit after costs** (fees + modeled slippage)

### Profit-close band (ε=3%)
Candidate is “close” if:
- P_candidate ≥ P_best * (1 - 0.03)

### Tie-breaks (apply on paper first)
If profit is close:
1) minimize avg_trades_per_day
2) minimize p95_trades_per_day
3) minimize max_trades_per_day
4) minimize ops_complexity_score (if tracked)
5) minimize DD (still within caps)

## Turnover metric spec
- trade_count = number of **filled orders aggregated per unique order_id** (partial fills do not inflate)
- bucket by **UTC day**
- required stats: avg/p95/max trades/day

## Trade Budgeter (enforcement)
- 20 daily tokens, 1 token per filled order_id
- low tokens: tighten entries
- zero tokens: block new entries, allow exits

## Outputs required from evaluators
- Strategy Card (profit after costs, DD, turnover avg/p95/max, complexity)
- Diff vs champion
- Robustness report (walk-forward + stress + cost sensitivity)
- Paper report (execution stats + turnover + profit)
