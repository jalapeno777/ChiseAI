---
name: "chise-rd-iteration"
description: "ChiseAI: run one end-to-end strategy R&D iteration (candidate -> backtest -> rank -> paper canary plan)."
disable-model-invocation: true
---
Run a full R&D iteration for the trading system.

Context:
- Follow the V1 spec at `docs/planning/neuro-symbolic-ai-evolution/agentic_neurosymbolic_trading_rd_v1_spec.md`.
- Use the rules in the `chiseai-strategy-cicd-gates` skill.

Steps:
1) Identify current champion strategy version and recent paper performance.
2) Propose 1-2 candidate strategy mutations (parameter and/or structure) inside the Strategy DSL.
3) Run walk-forward + stress + fee/slippage sensitivity backtests (use existing project tooling).
4) Rank candidates vs champion using ε=3% profit-close logic; apply turnover ceilings.
5) If a candidate qualifies, produce a paper canary deployment plan (no live changes).
6) Output: candidate summary, backtest artifacts list, and next actions.

If $ARGUMENTS is provided, treat it as the target symbol(s) or strategy family to focus on.
