---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-PB-001
story_title: "Create canonical product brief; enforce story IDs in PR titles"
phase: implementation
status: completed
started_at: "2026-02-08T20:09:21Z"
completed_at: "2026-02-08T20:12:46Z"
mem_scan:
  - AGENTS.md
  - docs/prd.md
  - docs/bmm-workflow-status.yaml
  - .opencode/command/chise-pr-automerge.md
  - scripts/gitea_pr_automerge.py
acceptance_criteria:
  - "AC1: Add canonical product brief at docs/product-brief.md and reference it from docs/prd.md."
  - "AC2: Enforce story_id in PR titles by updating scripts/gitea_pr_automerge.py and .opencode/command/chise-pr-automerge.md."
  - "AC3: Update AGENTS.md to require story_id in PR titles for all autonomous merges."
  - "AC4: CI remains green; changes merged to main via PR+Woodpecker auto-merge; branch pruned."
---

## Decisions
- Created canonical product brief at `docs/product-brief.md` and linked it from `docs/prd.md`.
- Enforced story IDs in PR titles by requiring `--story-id` in `scripts/gitea_pr_automerge.py` and documenting it in `.opencode/command/chise-pr-automerge.md`.

## Learnings
- Enforcing story IDs at the PR automation layer prevents unlabeled merges and improves traceability.

## Scope Ownership

- TBD

## Incidents

- TBD


## Evidence
- PR #9 merged with title prefix `CH-PB-001` after Woodpecker context `ci/woodpecker/push/woodpecker` was green.
