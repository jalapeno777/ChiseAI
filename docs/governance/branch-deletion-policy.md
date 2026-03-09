# Branch Deletion Policy

## Overview

This document defines the branch deletion guardrail policy for the ChiseAI repository. The policy ensures that branches are only deleted when there is proper evidence of completion (merged PR or merge commit).

## Purpose

The branch deletion guardrail prevents accidental loss of work by:
1. Blocking deletion of branches without PR or merge evidence
2. Requiring explicit override for exceptional cases
3. Logging all deletion attempts for audit purposes
4. Integrating with existing branch hygiene workflows

## Guardrail Components

### 1. Pre-Delete Guard Hook

**Location:** `.git/hooks/pre-delete-guard`

The pre-delete guard is a Python script that intercepts branch deletion attempts and validates eligibility.

#### How It Works

1. When a branch deletion is attempted, the guard checks:
   - Is the branch merged to `main`? (`git branch --merged main`)
   - Is the branch commit an ancestor of `main`? (`git merge-base --is-ancestor`)
   - Does the branch have an open or merged PR in Gitea?

2. If any check passes, deletion is allowed
3. If all checks fail, deletion is blocked with instructions

#### Usage

```bash
# Check if a branch can be deleted (dry run)
.git/hooks/pre-delete-guard feature/my-branch --check-only

# Attempt deletion (will be blocked if no evidence)
git branch -d feature/my-branch

# Force deletion (bypass guard)
git branch -D feature/my-branch  # or use --force
```

### 2. Branch Hygiene Integration

**Location:** `scripts/swarm/branch_hygiene_check.py`

The branch hygiene checker includes deletion eligibility checking:

```bash
# Check if a specific branch can be deleted
python scripts/swarm/branch_hygiene_check.py --check-deletion feature/my-branch

# Output includes:
# - Eligibility status
# - Reason for decision
# - PR status
# - Merge status
```

### 3. Redis Logging

All deletion attempts are logged to Redis for audit:

- **Key:** `bmad:chiseai:branch_deletion:attempts`
- **Format:** JSON list of attempt records
- **Retention:** Last 1000 attempts

Blocked deletions are also logged separately:

- **Key:** `bmad:chiseai:branch_deletion:blocked`
- **Format:** Hash of blocked branch -> details

## Eligibility Criteria

A branch is eligible for deletion if ANY of the following are true:

| Criteria | Check Method | Evidence |
|----------|--------------|----------|
| Merged to main | `git branch --merged main` | Branch appears in merged list |
| Ancestor of main | `git merge-base --is-ancestor` | Commit is in main history |
| Has open PR | Gitea API | PR exists with state=open |
| Has merged PR | Gitea API | PR exists with merged=true |
| Force override | `--force` flag | Explicit user override |

## Override Procedures

### When to Override

Override should only be used in exceptional circumstances:
- Branch was created by mistake
- Work was abandoned and never pushed
- Emergency cleanup with team approval

### How to Override

```bash
# Method 1: Use force flag with guard
.git/hooks/pre-delete-guard feature/my-branch --force

# Method 2: Use git's force delete directly
git branch -D feature/my-branch

# Method 3: Bypass hook entirely
git branch -d feature/my-branch --no-verify  # if hook is in pre-commit
```

### Audit Trail

All force deletions are logged with:
- Branch name
- Timestamp
- User
- Force flag status
- Reason (if provided)

## Examples

### Example 1: Normal Workflow (Recommended)

```bash
# 1. Create feature branch
git checkout -b feature/ST-123-new-feature

# 2. Do work, commit, push
git add .
git commit -m "feat: add new feature (ST-123)"
git push -u origin feature/ST-123-new-feature

# 3. Create PR in Gitea and merge it

# 4. Clean up local branch (will succeed)
git checkout main
git pull origin main
git branch -d feature/ST-123-new-feature
# ✅ Deletion allowed: Branch is merged to main
```

### Example 2: Blocked Deletion

```bash
# Try to delete branch without PR
git branch -d feature/unmerged-work
# ❌ Deletion BLOCKED: feature/unmerged-work
#    Reason: No PR or merge evidence found
#
#    This branch does not have evidence of being merged or having a PR.
#    To delete anyway, use one of these methods:
#
#      1. Create and merge a PR for this branch first (recommended)
#      2. Use --force flag: git branch -D <branch> --force
#      3. Use direct git command: git branch -D <branch>
```

### Example 3: Force Override

```bash
# Branch was created by mistake, need to delete
git branch -D feature/wrong-branch
# ✅ Deletion allowed: Force override enabled
```

### Example 4: Check Before Delete

```bash
# Check eligibility before attempting deletion
python scripts/swarm/branch_hygiene_check.py --check-deletion feature/my-branch
# ✅ ELIGIBLE for deletion: feature/my-branch
#   Reason: open PR #42
#   Has PR: True
#   PR Detail: open PR #42
#   Is Merged: False
#   Has Merge Evidence: False
```

## Integration with CI/CD

### Woodpecker CI

The guard can be integrated into CI pipelines:

```yaml
# .woodpecker.yml
steps:
  - name: branch-cleanup-check
    image: python:3.11
    commands:
      - python scripts/swarm/branch_hygiene_check.py --check-deletion $CI_COMMIT_BRANCH
    when:
      event: [push, manual]
```

### Pre-Commit Hook

To install as a pre-commit hook:

```bash
# Copy to hooks directory
cp .git/hooks/pre-delete-guard .git/hooks/pre-commit
cp .git/hooks/pre-delete-guard .git/hooks/pre-push

# Make executable
chmod +x .git/hooks/pre-commit
chmod +x .git/hooks/pre-push
```

## Troubleshooting

### Issue: Guard blocks legitimate deletion

**Cause:** Branch was merged but guard doesn't detect it

**Solution:**
```bash
# Update local main
git checkout main
git pull origin main

# Retry deletion
git branch -d feature/my-branch
```

### Issue: Gitea API check fails

**Cause:** Missing environment variables

**Solution:**
```bash
export GITEA_TOKEN="your-token"
export GITEA_OWNER="chiseai"
export GITEA_REPO="chiseai"
export GITEA_BASE_URL="http://host.docker.internal:3000"
```

### Issue: Redis logging fails

**Cause:** Redis unavailable

**Solution:**
- Guard will still function without Redis
- Check Redis connection: `redis-cli -h host.docker.internal -p 6380 ping`
- Logs will be missing but deletions will still be protected

## Policy Compliance

### For Developers

- [ ] Always create a PR before deleting feature branches
- [ ] Use `--check-deletion` to verify eligibility
- [ ] Only use `--force` with team approval
- [ ] Document any force deletions in team chat

### For Maintainers

- [ ] Monitor `bmad:chiseai:branch_deletion:blocked` for patterns
- [ ] Review force deletion logs weekly
- [ ] Update policy based on team feedback
- [ ] Ensure CI integration is working

## Related Documentation

- [Branch Hygiene Check](../scripts/swarm/branch_hygiene_check.py)
- [Session Management](../scripts/swarm/session.py)
- [Git Workflow](../AGENTS.md#git-safety-essentials)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-09 | Initial policy implementation |

---

**Policy Owner:** ChiseAI Engineering Team  
**Last Updated:** 2026-03-09  
**Review Cycle:** Quarterly
