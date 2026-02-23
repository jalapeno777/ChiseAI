---
name: chiseai-promotion-packet
description: Generate a concise human-approval promotion packet for strategy or brain changes, including evidence, risks, and rollback plan.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-promotion-packet

## Goal

Produce the human-facing approval document for strategy or brain promotions with all required evidence.

## When To Use

- When a candidate passes paper gates and is ready for human decision
- When a brain candidate beats current brain on BrainEval and shadow results
- Preparing live deployment documentation
- Documenting upgrade decisions for audit trail

## When Not To Use

- Backtest-only results (not ready for promotion)
- Failed paper validation (do not create packet)
- Non-promotion documentation
- Internal technical notes (use iterlog instead)

## Promotion Packet Sections (Required)

1. **Executive summary** (recommend approve/reject)
2. **What changed** (diff summary)
3. **Evidence**:
   - Paper results (primary)
   - Backtest robustness (supporting)
4. **Turnover** (avg/p95/max trades/day) and budgeter behavior
5. **Risks and known failure modes**
6. **Rollback plan** (champion restore steps)
7. **Monitoring plan** (what alerts to watch after promotion)

## Decision Language

Be explicit:
- "Approve" → exact version id to activate
- "Reject" → exact reasons + what to improve next

## Exit Conditions

- All required sections completed.
- Evidence includes both paper and backtest results.
- Rollback steps are testable and documented.
- Monitoring plan specifies exact alerts to watch.

## Troubleshooting/Safety

- **Missing evidence**: Do not submit packet; gather required data first.
- **Ambiguous recommendation**: Clarify approve/reject with specific reasoning.
- **Rollback untested**: Test rollback procedure before submitting packet.
- **Monitoring gaps**: Define specific alerts; generic "monitor closely" is insufficient.

## Related Skills

- `chiseai-paper-trading-canary` - Generates paper results evidence
- `chiseai-strategy-cicd-gates` - Provides evaluation criteria
- `chiseai-brain-cicd` - Brain promotion workflow
- `chiseai-risk-audit` - Risk evidence for packet

## Related Commands

- `.opencode/command/chise-risk-audit.md` - Include audit results in packet
