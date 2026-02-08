---
name: chiseai-promotion-packet
description: Generate a concise human-approval promotion packet for strategy or brain changes, including evidence, risks, and rollback plan.
license: MIT
compatibility: opencode
metadata:
  audience: trading-system
  scope: approval
---

## What I do
I produce the human-facing approval doc for:
- strategy promotions (paper → live)
- brain promotions (vNext brain activation)

## When to use me
- When a candidate passes paper gates and is ready for human decision
- When a brain candidate beats current brain on BrainEval and shadow results

## Promotion packet sections (required)
1) Executive summary (recommend approve/reject)
2) What changed (diff summary)
3) Evidence:
   - Paper results (primary)
   - Backtest robustness (supporting)
4) Turnover (avg/p95/max trades/day) and budgeter behavior
5) Risks and known failure modes
6) Rollback plan (champion restore steps)
7) Monitoring plan (what alerts to watch after promotion)

## Decision language
Be explicit:
- “Approve” → exact version id to activate
- “Reject” → exact reasons + what to improve next
