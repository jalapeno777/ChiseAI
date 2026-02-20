---
name: "chise-sprint-cleanup"
description: "ChiseAI: comprehensive pre-sprint cleanup routine ensuring repository hygiene before starting new sprint work."
disable-model-invocation: true
---

Run the pre-sprint cleanup routine to ensure repository hygiene before starting new sprint work.

## Overview

The pre-sprint cleanup routine verifies and fixes:

1. **Working Tree Cleanliness** - No uncommitted changes, no untracked files, all sessions closed
2. **Branch Hygiene** - Delete merged branches, review stale branches, rebase behind-main branches
3. **Main Branch Synchronization** - Local main synced with remote
4. **PR Status Verification** - No stuck PRs, all PRs actionable
5. **Canonical File Integrity** - Status files valid and in sync
6. **Cleanup Actions** - Auto-delete safe branches, auto-rebase clean branches

## Usage

### Dry Run (Check Only)
```bash
python3 scripts/ops/sprint_cleanup.py --check-all
```

### Execute with Safe Auto-Fixes
```bash
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe
```

### Mark Sprint Boundary (After Cleanup)
```bash
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe --mark-sprint SPRINT-2026-Q1-01
```

### JSON Output (For Automation)
```bash
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe --json
```

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Repository ready for sprint | Proceed with sprint planning |
| 1 | Warnings present | Review warnings, then proceed |
| 2 | Critical issues | **BLOCKED** - Resolve before sprint start |
| 3 | Infrastructure unavailable | Check Redis/Gitea connectivity |

## What Gets Checked

### Working Trees
- ✅ Uncommitted changes (CRITICAL)
- ✅ Untracked files (WARNING)
- ✅ Stale sessions (>3 days old) (WARNING)

### Branches
- ✅ Already merged to main (INFO → auto-delete)
- ✅ Behind main >7 commits (WARNING → auto-rebase if clean)
- ✅ No activity >30 days (WARNING → review)
- ✅ Invalid naming (WARNING → rename or delete)

### Main Branch
- ✅ Local == Remote (CRITICAL if diverged)
- ✅ Clean fast-forward possible

### Pull Requests
- ✅ Open PRs with merge conflicts (WARNING)
- ✅ Stuck PRs without mergeable status (WARNING)

### Canonical Files
- ✅ `docs/bmm-workflow-status.yaml` exists and valid
- ✅ `docs/validation/validation-registry.yaml` exists and valid

## Auto-Fix Criteria

The following are considered **safe to auto-fix**:

1. **Merged branches** - Already merged to main, no unique commits
2. **Behind-main branches with no local commits** - Safe to rebase
3. **Main branch sync** - Pull from remote when local is behind

The following **require manual intervention**:

1. **Uncommitted changes** - Could lose work
2. **Stale sessions** - May indicate active work
3. **Stale branches (>30 days)** - Need human review
4. **Invalid branch names** - Need decision on rename vs delete
5. **PRs with conflicts** - Need conflict resolution

## Redis Schema

The cleanup routine stores data in Redis for tracking and audit:

### State Tracking
```
Key: bmad:chiseai:sprint_cleanup:state
Type: Hash
Fields:
  - current: JSON with state and timestamp
```

### Audit Log
```
Key: bmad:chiseai:sprint_cleanup:log
Type: List
Entries:
  - {"timestamp": "...", "action": "...", "details": "..."}
```

### Daily Summaries
```
Key: bmad:chiseai:sprint_cleanup:summary:YYYY-MM-DD
Type: Hash
Fields:
  - report: JSON summary of cleanup
```

### Sprint Boundaries
```
Key: bmad:chiseai:sprint:boundary
Type: List
Entries:
  - {"sprint_id": "...", "started_at": "...", "repository_state": "ready|blocked"}
```

## Integration with CI/CD

Add to your CI pipeline:

```yaml
pre_sprint_cleanup:
  script:
    - python3 scripts/ops/sprint_cleanup.py --check-all --json > cleanup_report.json
  artifacts:
    reports:
      json: cleanup_report.json
  allow_failure: true  # Don't block CI, just report
```

## Discord Integration

The cleanup routine generates a Discord-friendly summary. To post to Discord:

```bash
python3 scripts/ops/sprint_cleanup.py --check-all | \
  python3 scripts/ci/post_ci_failure_discord.py --channel dev-updates
```

## When To Run

| Scenario | Command | Frequency |
|----------|---------|-----------|
| Before sprint planning | `--check-all` | At sprint boundaries |
| Weekly maintenance | `--execute --auto-fix-safe` | Weekly (e.g., Monday morning) |
| After major releases | `--execute --auto-fix-safe` | Post-release |
| Emergency cleanup | `--execute` | On-demand |

## Safety Mechanisms

1. **Dry-run by default** - Must explicitly use `--execute` to make changes
2. **Safe fixes only** - `--auto-fix-safe` only fixes clearly safe issues
3. **Confirmation prompts** - None; safety through dry-run and explicit flags
4. **Audit trail** - All actions logged to Redis
5. **Exit codes** - Clear indication of readiness state

## Example Workflow

```bash
# 1. Check current state (dry run)
python3 scripts/ops/sprint_cleanup.py --check-all

# 2. Review output, then execute safe fixes
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe

# 3. Check again to verify
python3 scripts/ops/sprint_cleanup.py --check-all

# 4. If exit code is 0 or 1, mark sprint boundary
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe --mark-sprint SPRINT-2026-Q1-01

# 5. Proceed with sprint planning
```

## Related Commands

- `chise-branch-hygiene-check.md` - Focused branch hygiene check
- `chise-swarm-session.md` - Session management for worktrees
- `chise-merlin-pr-sweep.md` - PR cleanup automation
- `chise-precommit-gates.md` - Pre-PR validation gates

## Troubleshooting

### "Redis unavailable"
- Check Redis connection: `redis-cli -h host.docker.internal -p 6380 ping`
- Cleanup continues without Redis logging

### "Gitea token not set"
- Set `GITEA_TOKEN` environment variable
- PR checks will be skipped without token

### "Git command failed"
- Ensure you're in a git repository
- Check git configuration

### Exit code 2 (Critical issues)
- Review the report for critical issues
- Resolve manually
- Re-run cleanup
