---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-OPS-AUTOMERGE-CMD-001
story_title: "Add Opencode command for standardized PR+CI+auto-merge flow"
phase: implementation
status: completed
started_at: "2026-02-08T20:01:04Z"
completed_at: "2026-02-08T20:03:21Z"
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
- Added `.opencode/command/chise-pr-automerge.md` to standardize push -> PR -> auto-merge (green CI only) for autonomous agents.
- Updated `AGENTS.md` to mandate the command for convergence.

## Learnings
- Gitea API may return 404 for private repo endpoints without auth; scripts should use `GITEA_TOKEN`.

## Evidence
- PR #7 merged via `scripts/gitea_pr_automerge.py` after Woodpecker status `ci/woodpecker/push/woodpecker` was green.
