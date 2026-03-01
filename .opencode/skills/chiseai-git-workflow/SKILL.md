---
name: chiseai-git-workflow
description: Standard Git workflows for ChiseAI agent swarm operations (branching, PR handoff, merge authority).
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-git-workflow

## Goal

Ensure all agent swarm operations follow consistent, safe Git practices that maintain repository integrity.

## When To Use

- Starting any new story/feature work
- Preparing to hand off to PR review
- Any merge/rebase operations
- Emergency hotfix procedures
- Branch management and cleanup

## When Not To Use

- Non-git operations (file system, database, etc.)
- External repository work (forks, mirrors)
- Read-only operations that don't change state
- Documentation-only changes in non-repo locations

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

### Merge Authority Consistency (AGENTS.md Reference)
The merge authority rules here are consistent with `AGENTS.md` Git Safety Essentials:
- **Workers**: Push branches + handoff evidence only; workers do NOT open PRs or merge to main
- **Jarvis**: Orchestrates handoff to Merlin; coordinates worker completion
- **Merlin**: Sole merge authority to main and branch cleanup authority

## Command Selection Guide

### Reconcile Commands - Which to Use?
| Command | Purpose | When to Run |
|---------|---------|-------------|
| `chise-reconcile-tick` | Periodic drift detection | Every 15-30 mins via cron/loop |
| `chise-merge-queue-process` | Process merge queue items | When PRs are ready to merge |
| `chise-intake-triage` | Triage new work items | On new story/bug intake |

**Key Distinction**: `chise-reconcile-tick` is for **detection and hygiene**, not for **actual merging or intake processing**. Use the specific commands for those operations.

## Session Isolation

Use `scripts/swarm/session.py` for isolated worktree sessions:
- `start` before any git work
- `verify` before git actions (always pass `--worktree-path`)  
- `close` when done
- Before tests/lint/git commands, run `scripts/swarm/assert_session_context.py`
- Prefer `scripts/swarm/run_in_session.sh` for command execution

## Exit Conditions

- Changes committed to feature branch.
- Working tree is clean.
- Pre-commit gates passed.
- Handoff information complete for Jarvis.

## Troubleshooting/Safety

- **Dirty working tree**: Stash or commit changes before switching branches.
- **Merge conflict**: Do not force; resolve conflicts manually or escalate to Jarvis.
- **Main branch protection**: Never commit directly to main; always use feature branches.
- **Lost commits**: Use `git reflog` to recover; never force push shared branches.

## Related Skills

- `chiseai-branch-hygiene` - Branch cleanup and lifecycle
- `chiseai-validation` - Pre-commit and CI validation
- `chiseai-parallel-safety` - Safe parallel branch work

## Templates

### Template 1: Branch Creation Checklist

```markdown
# Branch Creation Checklist

## Pre-Creation
- [ ] `git status -sb` shows clean working tree
- [ ] `git branch --show-current` confirms current location
- [ ] Story ID confirmed: [ST-XXX]
- [ ] Branch name planned: feature/[ST-XXX]-[slug]

## Branch Creation
```bash
# From main
git checkout main
git pull origin main
git checkout -b feature/[ST-XXX]-[slug]

# Or from existing feature branch (for sub-feature)
git checkout -b feature/[ST-XXX]-[subfeature-slug]
```

## Post-Creation
- [ ] `git branch --show-current` shows new branch
- [ ] Branch pushed to origin: `git push -u origin [branch-name]`
- [ ] Ownership claimed in Redis

## Session Start
```bash
python3 scripts/swarm/session.py start \
  --story-id=[ST-XXX] \
  --agent=[agent-id] \
  --branch=feature/[ST-XXX]-[slug] \
  --worktree-root=.swarm-worktrees

# Set WORKTREE_PATH from the printed "- worktree: ..." value
export WORKTREE_PATH=/abs/path/from-session-start-output
python3 scripts/swarm/session.py verify --story-id=[ST-XXX] --branch=feature/[ST-XXX]-[slug] --worktree-path="$WORKTREE_PATH" --check-canonical
```
```

### Template 2: PR Handoff Document

```markdown
# PR Handoff Document

## Story Information
- **Story ID**: [ST-XXX]
- **Story Title**: [title]
- **Branch**: feature/[ST-XXX]-[slug]
- **Head SHA**: [commit-sha]

## Work Summary
[Brief description of what was implemented]

## Files Changed
| File | Change Type | Lines Changed |
|------|-------------|---------------|
| [path] | [added/modified/deleted] | [+N/-M] |

## Validation Results

### Local CI
- [x] `black --check src/`: PASS
- [x] `ruff check src/`: PASS
- [x] `pytest tests/`: PASS (N tests)

### Status Sync
- [x] `docs/bmm-workflow-status.yaml` updated
- [x] `python3 scripts/validate_status_sync.py`: PASS

## Testing Evidence
```
$ pytest tests/unit/test_[module].py -v
==================== 15 passed in 2.34s ====================
```

## Documentation
- [ ] Docstrings added/updated
- [ ] README updated (if applicable)
- [ ] Changelog entry (if applicable)

## Blockers
[List any blockers or "None"]

## Handoff To
- **From**: [worker-agent]
- **To**: Jarvis → merlin

## Suggested PR Title
`feat([scope]): [description] ([ST-XXX])`

## Suggested PR Body
```markdown
## Summary
- [bullet 1]
- [bullet 2]

## Test Plan
- [ ] [test step 1]
- [ ] [test step 2]

Closes #[issue-number] (if applicable)
```
```

### Template 3: Commit Message Format

```markdown
# Commit Message Format

## Standard Format
```
<type>(<scope>): <short summary> (<story-id>)

[optional body]

[optional footer]
```

## Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting (no code change)
- `refactor`: Code change without fix/feature
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

## Scopes (examples)
- `dsl`: Strategy DSL
- `evolution`: Neuro-symbolic evolution
- `validation`: Validation system
- `ci`: CI/CD changes
- `infra`: Infrastructure

## Examples

### Feature Commit
```
feat(dsl): add trailing_stop syntax support (ST-DSL-042)

- Add trailing_stop keyword to grammar
- Implement stop calculation logic
- Add unit tests for new syntax

Refs: ST-DSL-042
```

### Fix Commit
```
fix(evolution): correct fitness calculation edge case (ST-EV-015)

The fitness calculation was incorrectly handling zero-volatility
periods, causing division by zero. Added guard clause.

Fixes: #123
Refs: ST-EV-015
```

### Refactor Commit
```
refactor(validation): extract common validation logic (ST-VAL-008)

Move shared validation patterns into base class for reuse
across multiple validators. No behavior change.

Refs: ST-VAL-008
```
```

### Template 4: Merge Procedure

```markdown
# Merge Procedure (Merlin Only)

## Pre-Merge Checklist
- [ ] CI status: GREEN (all checks passed)
- [ ] PR review: APPROVED (if required)
- [ ] Status sync: VALIDATED
- [ ] Conflicts: RESOLVED (if any)
- [ ] Branch: UP TO DATE with main

## Merge Steps

### 1. Final Verification
```bash
# Check PR status
gh pr view [PR-NUMBER] --json statusCheckRollup,mergeable

# Verify status sync
python3 scripts/validate_status_sync.py --pr [PR-NUMBER]
```

### 2. Merge
```bash
# Squash merge (preferred for feature branches)
gh pr merge [PR-NUMBER] --squash --delete-branch

# Or regular merge (for release branches)
gh pr merge [PR-NUMBER] --merge --delete-branch
```

### 3. Post-Merge
```bash
# Update local main
git checkout main
git pull origin main

# Update story status
# Edit docs/bmm-workflow-status.yaml: status → "merged"

# Log completion
redis_state_hset(
    name="bmad:chiseai:iterlog:story:[ST-XXX]",
    key="merged_at",
    value=datetime.now().isoformat()
)
```

## Post-Merge Actions
- [ ] Branch deleted
- [ ] Story status updated
- [ ] Stakeholders notified
- [ ] Iterloop closed
```

## Examples

### Example 1: Starting a New Feature Branch

**Context**: Senior-dev starting work on ST-DSL-042

**Branch Creation**:

```bash
# Check current state
$ git status -sb
## main...origin/main

# Create feature branch
$ git checkout -b feature/ST-DSL-042-grammar-extensions
Switched to a new branch 'feature/ST-DSL-042-grammar-extensions'

# Verify branch
$ git branch --show-current
feature/ST-DSL-042-grammar-extensions

# Push to origin
$ git push -u origin feature/ST-DSL-042-grammar-extensions
```

**Ownership Claim**:

```python
redis_state_hset(
    name="bmad:chiseai:ownership",
    key="src:strategy:dsl",
    value="ST-DSL-042/senior-dev/2026-02-23T10:00:00Z",
    expire_seconds=432000
)
```

### Example 2: Completing Work and Handoff

**Context**: Senior-dev completed implementation

**Pre-Commit Validation**:

```bash
$ git status -sb
## feature/ST-DSL-042-grammar-extensions...origin/feature/ST-DSL-042-grammar-extensions
M src/strategy/dsl/grammar.py
A src/strategy/dsl/trailing_stop.py
A tests/unit/strategy/test_trailing_stop.py

$ black --check src/
All done! ✨ 🍰 ✨
5 files left unchanged.

$ ruff check src/
All checks passed!

$ pytest tests/unit/strategy/test_trailing_stop.py -v
==================== 12 passed in 1.23s ====================
```

**Handoff to Jarvis**:

```markdown
# PR Handoff

Story ID: ST-DSL-042
Branch: feature/ST-DSL-042-grammar-extensions
Head SHA: abc123def456

Files Changed:
- src/strategy/dsl/grammar.py (modified, +15/-3)
- src/strategy/dsl/trailing_stop.py (new, +120)
- tests/unit/strategy/test_trailing_stop.py (new, +80)

Validation: All passed
Blockers: None

Ready for merlin PR sweep.
```

### Example 3: Handling a Merge Conflict

**Context**: Rebase reveals conflict

**Conflict Resolution**:

```bash
# During rebase
$ git rebase main
CONFLICT (content): Merge conflict in src/strategy/dsl/grammar.py

# View conflict
$ git status
Unmerged paths:
  both modified:   src/strategy/dsl/grammar.py

# Resolve conflict manually or with tool
$ code src/strategy/dsl/grammar.py  # or preferred editor

# After resolving
$ git add src/strategy/dsl/grammar.py
$ git rebase --continue

# Verify resolution
$ pytest tests/unit/strategy/test_dsl.py -v
==================== 15 passed in 1.45s ====================

# Force push (required after rebase)
$ git push --force-with-lease origin feature/ST-DSL-042-grammar-extensions
```

## Quick Reference

### Git Command Cheat Sheet

```bash
# Start new work
git checkout main && git pull
git checkout -b feature/[ST-XXX]-[slug]

# Daily workflow
git status -sb                    # Check state
git add -p                        # Stage changes interactively
git commit -m "type(scope): msg"  # Commit with format

# Sync with main
git fetch origin
git rebase origin/main            # Rebase on latest main

# Push
git push -u origin [branch]       # First push
git push                          # Subsequent pushes
git push --force-with-lease       # After rebase

# Cleanup
git branch -d [branch]            # Delete local
git push origin --delete [branch] # Delete remote
```

### Branch Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/[ST-XXX]-[slug]` | `feature/ST-DSL-042-grammar-extensions` |
| Fix | `fix/[ST-XXX]-[slug]` | `fix/ST-EV-015-fitness-calc` |
| Safety | `safety/[reason]-[date]` | `safety/hotfix-2026-02-23` |
| Release | `release/[version]` | `release/v1.2.0` |

### PR Title Tokens (Required)

| Prefix | Meaning |
|--------|---------|
| `ST-*` | Story implementation |
| `CH-*` | Chore/maintenance |
| `FT-*` | Feature |
| `REWARD-*` | Reward system |
| `REPO-*` | Repository work |
| `SAFETY-*` | Safety-critical |
| `BRANCH-*` | Branch management |
| `PAPER-*` | Paper trading |
| `RECON-*` | Reconnaissance |

## Related Commands

- `.opencode/command/chise-precommit-gates.md` - Pre-PR validation
- `.opencode/command/chise-merlin-pr-sweep.md` - PR batch processing
- `.opencode/command/chise-swarm-session.md` - Session management
