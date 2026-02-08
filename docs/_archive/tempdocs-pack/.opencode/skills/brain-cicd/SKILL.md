---
name: brain-cicd
description: Run Brain CI/CD: version, evaluate, shadow-test, and propose upgrades to the agent brain with human approval gating.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: meta
---

## What I do
I define how the system can propose **upgraded brains** safely:
- Brain registry + BrainSpec artifacts
- BrainEval KPIs (paper carryover, false positives, time-to-improvement, compute)
- Shadow mode comparisons (vNext generates candidates only)
- Human approval required to activate vNext

## When to use me
- Any time you want to improve the orchestrator’s planning/reasoning policies
- On a fixed cadence (every 3 days initially)

## BrainEval KPIs (score brains on R&D quality)
- paper_carryover_rate (primary)
- false_positive_rate (backtest wins that die in paper)
- time_to_improvement (experiments to beat champion)
- turnover_bias_alignment (does it prefer low trades/day when profit within 3%?)
- compute_cost (tokens / runs per useful win)
- safety_compliance (never violates caps; never touches live)

## Cadence policy (starting point)
- Attempt every **3 days**
- Generate ≤ 2 candidate brains per attempt
- Promote only on clear KPI wins + human approval
- Transition to weekly/monthly when stable; snap-back to rapid on drift/carryover drops

## Root of trust (do not self-modify)
- Risk caps + invariants
- Promotion gate logic
- Audit log append-only pipeline
- Emergency rollback path
