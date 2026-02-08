---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: CH-PB-001
story_title: "Create canonical product brief; enforce story IDs in PR titles"
phase: implementation
status: in_progress
started_at: "$(date -u +%FT%TZ)"
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
- TBD

## Learnings
- TBD

## Evidence
- TBD
