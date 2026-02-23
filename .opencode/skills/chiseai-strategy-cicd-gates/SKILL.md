---
name: chiseai-strategy-cicd-gates
description: Define strategy selection, turnover (trades/day), gates, and promotion rules for backtest→paper→human-approved live.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-strategy-cicd-gates

## Goal

Provide the **source of truth** for strategy evaluation, selection, and promotion gates.

## When To Use

- Implementing candidate evaluation, ranking, or gating.
- Writing promotion logic (paper to live).
- Validating metrics and report outputs.
- Setting up backtest or paper trading pipelines.

## When Not To Use

- Non-strategy code changes.
- Infrastructure setup with no trading logic.
- Documentation-only updates.
- Single strategy debugging (use specific debugging tools).

## Source of Truth

- Lexicographic objective: **profit after costs** → **turnover (if enabled)** → **DD (within caps)**
- Profit-close rule: **ε = 3%**
- Turnover definition: **trades/day** (filled orders per order_id, UTC buckets)
- Turnover ceilings: avg ≤ 20, p95 ≤ 30, max ≤ 45
- Trade Budgeter: **20 tokens/day**
- Promotion gates: Backtest → Paper Canary → Paper Full → Human approval → Live

## Decision Rules (Copy/Paste Friendly)

### Constraints (must pass)
- Enforce existing hard risk caps (DD, daily loss, exposure/leverage, etc.)

### Primary objective
- Maximize **net profit after costs** (fees + modeled slippage)

### Profit-close band (ε=3%)
Candidate is "close" if:
- P_candidate ≥ P_best * (1 - 0.03)

### Tie-breaks (apply on paper first)
If profit is close:
1) minimize avg_trades_per_day
2) minimize p95_trades_per_day
3) minimize max_trades_per_day
4) minimize ops_complexity_score (if tracked)
5) minimize DD (still within caps)

## Turnover Metric Spec

- trade_count = number of **filled orders aggregated per unique order_id** (partial fills do not inflate)
- bucket by **UTC day**
- required stats: avg/p95/max trades/day

## Trade Budgeter (Enforcement)

- 20 daily tokens, 1 token per filled order_id
- low tokens: tighten entries
- zero tokens: block new entries, allow exits

## Outputs Required from Evaluators

- Strategy Card (profit after costs, DD, turnover avg/p95/max, complexity)
- Diff vs champion
- Robustness report (walk-forward + stress + cost sensitivity)
- Paper report (execution stats + turnover + profit)

## Exit Conditions

- Strategy ranked against champion using defined objective.
- Turnover metrics calculated and compared to ceilings.
- Trade budgeter state evaluated.
- Promotion recommendation documented with evidence.

## Troubleshooting/Safety

- **Tie-break ambiguity**: Follow tie-break order exactly; document reasoning.
- **Turnover ceiling exceeded**: Reject candidate or require justification.
- **Budgeter exhausted**: Block new entries, document in report.
- **Missing metrics**: Block evaluation until all required outputs available.

## Related Skills

- `chiseai-turnover-metrics` - Calculates trades/day metrics
- `chiseai-paper-trading-canary` - Runs paper validation gates
- `chiseai-promotion-packet` - Packages evaluation for human approval
- `chiseai-risk-audit` - Validates risk constraints

## Related Commands

- `.opencode/command/chise-risk-audit.md` - Validate risk before promotion
