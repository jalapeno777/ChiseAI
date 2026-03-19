---
name: chiseai-brain-cicd
description: "Run Brain CI/CD: version, evaluate, shadow-test, and propose upgrades to the agent brain with human approval gating."
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-brain-cicd

## Goal

Define how the system can propose **upgraded brains** safely through versioning, evaluation, and shadow testing.

## When To Use

- Any time you want to improve the orchestrator's planning/reasoning policies.
- On a fixed cadence (every 3 days initially).
- After observing degradation in brain performance metrics.
- When proposing new reasoning patterns or heuristics.

## When Not To Use

- Runtime agent operations (use current brain, don't modify).
- Emergency fixes (use hotfix procedures, not brain upgrade).
- Non-brain agent improvements (skills, commands, etc.).
- Single-story optimizations (don't generalize from one case).

## What It Does

- Brain registry + BrainSpec artifacts
- BrainEval KPIs (paper carryover, false positives, time-to-improvement, compute)
- Shadow mode comparisons (vNext generates candidates only)
- Human approval required to activate vNext

## BrainEval KPIs (Score Brains on R&D Quality)

- paper_carryover_rate (primary)
- false_positive_rate (backtest wins that die in paper)
- time_to_improvement (experiments to beat champion)
- turnover_bias_alignment (does it prefer low trades/day when profit within 3%?)
- compute_cost (tokens / runs per useful win)
- safety_compliance (never violates caps; never touches live)

## Cadence Policy (Starting Point)

- Attempt every **3 days**
- Generate ≤ 2 candidate brains per attempt
- Promote only on clear KPI wins + human approval
- Transition to weekly/monthly when stable; snap-back to rapid on drift/carryover drops

## Root of Trust (Do Not Self-Modify)

- Risk caps + invariants
- Promotion gate logic
- Audit log append-only pipeline
- Emergency rollback path

## Exit Conditions

- BrainEval KPIs calculated for vNext vs current.
- Shadow mode comparison completed.
- Promotion packet prepared if vNext wins.
- Human approval obtained before activation.

## Troubleshooting/Safety

- **vNext underperforms**: Do not promote; document learnings and iterate.
- **Safety violation detected**: Immediately disqualify vNext, investigate root cause.
- **KPI regression**: Require clear improvement before promotion.
- **Human rejection**: Document feedback, incorporate into next iteration.

## Related Skills

- `chiseai-promotion-packet` - Packages brain upgrade for approval
- `chiseai-strategy-cicd-gates` - Provides evaluation framework
- `chiseai-validation` - Validates brain changes

## Related Commands

- `.opencode/command/chise-iterloop-start.md` - Start brain evaluation iteration
- `.opencode/command/chise-iterloop-close.md` - Close with brain decision
