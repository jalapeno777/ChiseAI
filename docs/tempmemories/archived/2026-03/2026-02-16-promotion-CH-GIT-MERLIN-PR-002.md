---
project: ChiseAI
scope: git-governance
type: summary
story_id: CH-GIT-MERLIN-PR-002
phase: implementation
tags: [git, gitea, woodpecker, governance, merlin, automation]
---

## Promotion Candidates

1. Pattern: Run `scripts/ops/merlin_pr_sweep.py` as the canonical Merlin batch/sprint reconciliation entrypoint.
2. Decision: Keep explicit branch-to-story mappings in `docs/operations/merlin-branch-story-map.json`; use regex only as fallback.
3. Safety Rule: Consolidation mode must include supersession-link comments for every replaced PR (`--consolidation-mode --supersession-pr --supersede-pr ...`).
