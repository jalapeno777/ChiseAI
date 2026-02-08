---
name: paper-trading-canary
description: Run paper canary→paper full validation with trade-budget enforcement and produce a promotion packet.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: paper
---

## What I do
I define how to run **paper trading validation** safely:
- Canary deployment (limited scope)
- Full paper expansion (if canary passes)
- Enforce **trade budgeter**
- Collect paper metrics and compare vs champion
- Produce a human-readable **promotion packet** (paper→live)

## When to use me
- Any time a strategy passes backtest and is ready for paper
- Any time paper results need to be summarized for approval

## Paper stages
### Paper Canary
- Small notional / limited symbols / limited risk
- Goal: verify backtest→paper carryover and execution realism

### Paper Full
- Broader symbol set / longer horizon
- Goal: validate stability across conditions

## Paper gate checklist
Must report:
- Net profit after costs
- Turnover: avg/p95/max trades/day
- Execution realism: fill rate, slippage, rejects
- Drift alerts (inputs and performance)

Pass criteria should follow the selection policy in `strategy-cicd-gates`.

## Promotion packet template (minimum sections)
- Executive summary (pass/fail, recommendation)
- Champion vs candidate metrics (paper first)
- Turnover + budgeter behavior
- Worst day / worst regime snapshot
- Operational notes (spike days, symbols involved)
- Risks + rollback plan
