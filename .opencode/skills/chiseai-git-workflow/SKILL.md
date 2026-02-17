---
name: chiseai-git-workflow
description: Standard Git workflows for ChiseAI agent swarm operations (branching, PR handoff, merge authority).
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
---

# chiseai-git-workflow

## Goal

Ensure all agent swarm operations follow consistent, safe Git practices that maintain repository integrity.

## When To Use

- Starting any new story/feature work
- Preparing to hand off to PR review
- Any merge/rebase operations
- Emergency hotfix procedures

## Branch Strategy

### Standard Branches
- `main` - Stable, protected, human-approved merges only
- `feature/<story-id>-<slug>` - Story implementation
- `safety/<reason>-<date>` - Emergency work when tree is dirty

### Pre-Edit Checklist
- [ ] Run `git status -sb`
- [ ] Run `git branch --show-current`
- [ ] If on `main`, create feature branch immediately
- [ ] Verify working tree is clean before switching

## PR Workflow

### Worker Completion Protocol
1. Run local CI (via `chise-precommit-gates.md`)
2. Run status sync validation (via command)
3. Push branch to Gitea
4. Ensure handoff includes canonical `story_id` token for PR title gating:
   - Accepted: `ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*` (must include a digit)
5. Report handoff to Jarvis (DO NOT open PR)
6. Jarvis delegates merlin for PR sweep

### Required Handoff Information
- story_id
- branch name
- head SHA
- CI result
- status-sync result
- blockers (if any)

## Merge Authority

### Only Merlin May:
- Open/update/close PRs
- Merge to `main`
- Run branch cleanup

### Emergency Override
See `.opencode/command/chise-emergency-merge-override.md` for documented bypass procedure.

## Session Isolation

Use `scripts/swarm/session.py` for isolated worktree sessions:
- `start` before any git work
- `verify` before git actions  
- `close` when done

## Related Commands
- `.opencode/command/chise-precommit-gates.md` - Pre-PR validation
- `.opencode/command/chise-merlin-pr-sweep.md` - PR batch processing
- `.opencode/command/chise-swarm-session.md` - Session management
