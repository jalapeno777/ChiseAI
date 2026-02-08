---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-OPS-AUTOMERGE-CMD-001
story_title: "Add Opencode command for standardized PR+CI+auto-merge flow"
phase: implementation
status: in_progress
started_at: "$(date -u +%FT%TZ)"
mem_scan:
  - AGENTS.md
  - .opencode/command/*
  - scripts/gitea_pr_automerge.py
  - docs/ci-cd-gitea-woodpecker.md
acceptance_criteria:
  - "AC1: Add .opencode/command/chise-pr-automerge.md that runs gates, pushes to gitea, opens PR, and enables merge-when-checks-succeed (or merges once green)."
  - "AC2: Update AGENTS.md to reference the command and mandate its use for autonomous convergence."
  - "AC3: Validate flow end-to-end by pushing branch, auto-merging to main on green CI, and pruning branch."
---

## Decisions
- TBD

## Learnings
- TBD

## Evidence
- TBD
