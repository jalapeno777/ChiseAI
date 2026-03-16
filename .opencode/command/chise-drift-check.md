---
name: "chise-drift-check"
description: "ChiseAI: lightweight drift detection for branch/main divergence, worktree leaks, and ownership orphans"
disable-model-invocation: true
---

## When to Run

- **Periodic checks**: Run daily/weekly to catch drift early
- **Before batch work**: Verify clean state before starting parallel execution
- **When suspicious**: Unexpected CI failures, merge conflicts, or "weird" git behavior
- **Post-incident**: After resolving conflicts to ensure no lingering issues

## Quick Check (30 seconds)

### 1. Active Sessions
```bash
git worktree list
find . -type f -name ".swarm-session.json" -not -path "*/.git/*"
```
Shows: Active worktrees, their branches, and story associations.

### 2. Branch Hygiene
```bash
python3 scripts/swarm/branch_hygiene_check.py --report
```
Shows: Merged branches, stale branches, worktree leaks.

### 3. Ownership Orphans
```bash
# Via iterlog_ops.py (if available)
python3 scripts/iterlog_ops.py check-ownership --all 2>/dev/null || \
# Fallback: direct Redis query
redis-cli HGETALL bmad:chiseai:ownership
```
Shows: Active ownership claims that may be stale.

## Full Report

Run all checks together:

```bash
echo "=== ACTIVE SESSIONS ==="
git worktree list 2>/dev/null || echo "git worktree not available"
find . -type f -name ".swarm-session.json" -not -path "*/.git/*" 2>/dev/null || echo "no swarm session files found"

echo -e "\n=== BRANCH HYGIENE ==="
python3 scripts/swarm/branch_hygiene_check.py --report 2>/dev/null || echo "branch_hygiene_check.py not available"

echo -e "\n=== OWNERSHIP ORPHANS ==="
# Check for ownership entries older than 7 days
python3 scripts/iterlog_ops.py check-ownership --all 2>/dev/null || \
  redis-cli HGETALL bmad:chiseai:ownership | head -20

echo -e "\n=== GIT STATUS ==="
git status -sb
git log --oneline -5

echo -e "\n=== MAIN DRIFT ==="
git fetch origin main
git log --oneline HEAD..origin/main 2>/dev/null | head -5 || echo "Already up to date with main"
```

## Drift Detection Criteria

| Check | Drift Signal | Severity |
|-------|--------------|----------|
| Session without matching branch | Worktree leak | Medium |
| Branch merged but not deleted | Stale branch | Low |
| Ownership > 7 days old | Orphaned claim | High |
| Local commits behind main | Merge risk | Medium |
| Protected branch modified | Governance breach | Critical |

## Remediation

### Worktree Leaks
```bash
# List all worktrees
git worktree list

# Remove stale worktree
git worktree remove /tmp/worktrees/STORY-ID-branch-name
rm -rf /tmp/worktrees/STORY-ID-branch-name
```

### Stale Branches
```bash
# Safe cleanup (dry-run first)
python3 scripts/swarm/branch_hygiene_check.py --dry-run

# Auto-clean safe branches
python3 scripts/swarm/branch_hygiene_check.py --auto-clean
```

### Ownership Orphans
```bash
# Release specific ownership
redis-cli HDEL bmad:chiseai:ownership <path_slug>

# Or use iterlog_ops
python3 scripts/iterlog_ops.py release-ownership --path-slug=<path_slug>
```

### Main Drift
```bash
# Rebase onto main
git fetch origin main
git rebase origin/main

# Or merge main
git merge origin/main
```

## Exit Codes

When used in scripts:
- `0`: No drift detected
- `1`: Minor drift (stale branches)
- `2`: Major drift (worktree leaks, ownership orphans)
- `3`: Critical drift (protected branch issues)

## Related Commands

- `chise-claim-ownership` - Claim scope before parallel work
- `chise-check-ownership` - Verify ownership before edits
- `chise-branch-hygiene-check` - Deep branch cleanup
- `chise-append-incident` - Log drift-related incidents
