---
name: chiseai-risk-audit
description: Enforce POC-mode risk constraints for grid strategy recommendations (risk cap, leverage cap, confidence, no-degen, data-first).
metadata:
  version: "1.0"
  opencode_min_version: "1.1.48"
---

# chiseai-risk-audit

## Goal

Prevent unsafe recommendations and ensure every strategy output has explicit, bounded risk.

## When To Use

- Any time a grid strategy recommendation is produced.
- Before posting anything to Discord.
- Before marking a strategy story as completed.

## Checklist

- Recommendation-only (no live execution).
- Leverage <= 3x if futures are involved.
- Worst-case per grid <= 2% (state assumptions).
- Confidence gating for Discord posting.
- No-degen constraints (no unbounded averaging or exposure growth).
- Data-first: Phase 0 data foundation completed for the token/timeframe used.

## Command

Run `.opencode/command/chise-risk-audit.md` and record pass/fail evidence in the story iterlog.

