---
project: ChiseAI
scope: git-governance
type: summary
story_id: CH-GIT-MERLIN-PR-001
phase: implementation
tags: [git, gitea, woodpecker, governance, merlin]
---

## Promotion Candidates

1. Decision: PR authority must be single-owner (`merlin`) to prevent branch/PR drift and conflicting merge behavior.
2. Pattern: Worker lifecycle is `local CI -> push -> report to Jarvis`; PR handling is centralized in Merlin.
3. Pattern: For multi-PR systemic CI failures, consolidate unique commits into one remediation branch and merge that first.
4. Safety Rule: Branch pruning is allowed only after merge reachability/supersession is verified to prevent data loss.
