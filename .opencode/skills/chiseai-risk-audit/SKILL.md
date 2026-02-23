---
name: chiseai-risk-audit
description: Enforce POC-mode risk constraints for grid strategy recommendations (risk cap, leverage cap, confidence, no-degen, data-first).
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-risk-audit

## Goal

Prevent unsafe recommendations and ensure every strategy output has explicit, bounded risk.

## When To Use

- Any time a grid strategy recommendation is produced.
- Before posting anything to Discord.
- Before marking a strategy story as completed.
- When validating backtest or paper trading results.

## When Not To Use

- Pure infrastructure changes with no trading logic.
- Documentation updates.
- Test-only changes that don't affect strategy behavior.
- Non-trading features (dashboard, reporting, etc.).

## Checklist

- Execution mode awareness:
  - Backtesting is always-on and must not be halted.
  - Paper/live execution must be gated and kill-switch controlled per PRD/Product Brief.
- Leverage <= 3x if futures are involved.
- Worst-case per grid <= 2% (state assumptions).
- Confidence gating for Discord posting.
- No-degen constraints (no unbounded averaging or exposure growth).
- Data-first: Phase 0 data foundation completed for the token/timeframe used.

## Exit Conditions

- All checklist items verified.
- Risk audit command executed with pass result.
- Evidence recorded in story iterlog.
- Any violations flagged and escalated to Jarvis.

## Troubleshooting/Safety

- **Leverage exceeds cap**: Reduce position size or adjust strategy parameters.
- **Worst-case exceeds 2%**: Tighten stops, reduce grid density, or lower notional.
- **Missing data foundation**: Block and require Phase 0 completion before proceeding.
- **Confidence too low for Discord**: Hold posting, document reasoning in iterlog.
- **Unbounded exposure detected**: Reject strategy, require explicit bounds.

## Related Skills

- `chiseai-data-first` - Validates data foundation before risk audit
- `chiseai-strategy-cicd-gates` - Defines promotion gates that include risk checks
- `chiseai-promotion-packet` - Packages risk evidence for human approval

## Related Commands

- `.opencode/command/chise-risk-audit.md` - Run risk audit and record evidence
