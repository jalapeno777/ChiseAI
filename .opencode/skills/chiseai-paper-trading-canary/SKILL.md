---
name: chiseai-paper-trading-canary
description: Run paper canary→paper full validation with trade-budget enforcement and produce a promotion packet.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-paper-trading-canary

## Goal

Define how to run **paper trading validation** safely through staged deployment with trade budgeter enforcement.

## When To Use

- Any time a strategy passes backtest and is ready for paper
- Any time paper results need to be summarized for approval
- Validating backtest-to-paper carryover
- Preparing strategy for live deployment

## When Not To Use

- Backtesting only (no paper deployment)
- Live trading (requires human approval first)
- Strategy development (use backtest environment)
- Emergency fixes (use safety procedures instead)

## Paper Stages

### Paper Canary
- Small notional / limited symbols / limited risk
- Goal: verify backtest→paper carryover and execution realism

### Paper Full
- Broader symbol set / longer horizon
- Goal: validate stability across conditions

## Paper Gate Checklist

Must report:
- Net profit after costs
- Turnover: avg/p95/max trades/day
- Execution realism: fill rate, slippage, rejects
- Drift alerts (inputs and performance)

Pass criteria should follow the selection policy in `strategy-cicd-gates`.

## Promotion Packet Template (Minimum Sections)

- Executive summary (pass/fail, recommendation)
- Champion vs candidate metrics (paper first)
- Turnover + budgeter behavior
- Worst day / worst regime snapshot
- Operational notes (spike days, symbols involved)
- Risks + rollback plan

## Exit Conditions

- Paper canary completed with documented results.
- Trade budgeter enforced throughout.
- Promotion packet prepared if passing.
- Failures documented with root cause analysis.

## Troubleshooting/Safety

- **Canary fails**: Do not proceed to paper full; diagnose and fix strategy.
- **Budgeter exhausted**: Document behavior, consider tightening entries.
- **Execution drift**: Investigate slippage and fill rate issues before promotion.
- **Unexpected losses**: Halt paper trading, review strategy parameters.

## Related Skills

- `chiseai-strategy-cicd-gates` - Defines pass/fail criteria
- `chiseai-promotion-packet` - Formats promotion evidence
- `chiseai-turnover-metrics` - Calculates trades/day metrics
- `chiseai-risk-audit` - Validates risk constraints

## Related Commands

- `.opencode/command/chise-risk-audit.md` - Validate before promotion
