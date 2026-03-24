---
name: chiseai-sprint-cleanup
description: Ensure repository hygiene before starting new sprint work through automated cleanup, branch hygiene checks, and main branch synchronization.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-sprint-cleanup

## Goal

Ensure repository hygiene before starting new sprint work through automated cleanup, branch hygiene checks, and main branch synchronization.

## When To Use

- **Before sprint planning** - Verify repository is clean and ready
- **Weekly maintenance** - Automated cleanup to prevent drift
- **Post-release** - Clean up after major deployments
- **Emergency cleanup** - On-demand repository health check

## Prerequisites

Required environment variables:

```bash
# Git/Gitea
export GITEA_TOKEN="your-gitea-token"
export GITEA_BASE_URL="http://host.docker.internal:3000"
export GITEA_OWNER="craig"  # defaults to "craig"

# Redis (optional but recommended)
export CHISE_REDIS_HOST="host.docker.internal"
export CHISE_REDIS_PORT="6380"
```

## Quick Start

### 1. Check Without Making Changes (Dry Run)

```bash
python3 scripts/ops/sprint_cleanup.py --check-all
```

### 2. Execute Safe Auto-Fixes

```bash
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe
```

### 3. Mark Sprint Boundary

```bash
python3 scripts/ops/sprint_cleanup.py \
  --execute --auto-fix-safe \
  --mark-sprint SPRINT-2026-Q1-01
```

## What Gets Checked

| Category        | Checks                                               | Severity         |
| --------------- | ---------------------------------------------------- | ---------------- |
| Working Trees   | Uncommitted changes, untracked files, stale sessions | Critical/Warning |
| Branches        | Merged, behind-main, stale (>30d), invalid naming    | Info/Warning     |
| Main Sync       | Local == Remote, no diverged commits                 | Critical         |
| PR Status       | Stuck PRs, merge conflicts                           | Warning          |
| Canonical Files | Status files exist and valid                         | Critical         |

## Auto-Fix Criteria

**Safe to auto-fix:**

- Merged branches (no unique commits)
- Behind-main branches with no local commits
- Main branch behind remote

**Require manual intervention:**

- Uncommitted changes
- Stale sessions (>3 days old)
- Stale branches (>30 days)
- Invalid branch names
- PRs with conflicts
- Diverged main branch

## Exit Codes

| Code | Meaning              | Action                         |
| ---- | -------------------- | ------------------------------ |
| 0    | Ready (clean)        | Proceed with sprint            |
| 1    | Ready with warnings  | Review then proceed            |
| 2    | Blocked (critical)   | **Must resolve before sprint** |
| 3    | Infrastructure error | Check Redis/Gitea              |

## Redis Schema

The cleanup routine stores data for audit and tracking:

```python
# Current state
bmad:chiseai:sprint_cleanup:state
  → Hash { "current": JSON }

# Action log (immutable)
bmad:chiseai:sprint_cleanup:log
  → List of { "timestamp": "...", "action": "...", "details": "..." }

# Daily summaries
bmad:chiseai:sprint_cleanup:summary:YYYY-MM-DD
  → Hash { "report": JSON }

# Sprint boundaries
bmad:chiseai:sprint:boundary
  → List of { "sprint_id": "...", "started_at": "...", "repository_state": "..." }
```

## Query Cleanup History

```bash
# Recent trend (last 30 days)
python3 scripts/ops/cleanup_history.py --trend 30

# Specific sprint
python3 scripts/ops/cleanup_history.py --sprint SPRINT-2026-Q1-01

# Recent log entries
python3 scripts/ops/cleanup_history.py --last 20

# Export to JSON
python3 scripts/ops/cleanup_history.py --export history.json --days 90
```

## Automated Execution

### Weekly Cron Job

```bash
# Add to crontab
0 6 * * 1 /home/tacopants/projects/ChiseAI/scripts/cron/weekly_cleanup.sh
```

The weekly cleanup:

1. Runs every Monday at 6 AM
2. Executes safe auto-fixes
3. Generates JSON and text reports
4. Saves logs to `logs/cleanup/`
5. Posts summary to Discord (if configured)

## Safety Mechanisms

1. **Dry-run by default** - Must use `--execute` to modify
2. **Explicit auto-fix flag** - `--auto-fix-safe` required for automated fixes
3. **Comprehensive logging** - All actions logged to Redis
4. **No interactive prompts** - Safety through flags, not blocking questions
5. **Clear exit codes** - Know immediately if cleanup succeeded

## Integration with Workflow

### Pre-Sprint Checklist

```
□ Run cleanup: python3 scripts/ops/sprint_cleanup.py --check-all
□ Review output and resolve critical issues
□ Re-run until exit code 0 or 1
□ Execute safe fixes: --execute --auto-fix-safe
□ Mark sprint boundary: --mark-sprint SPRINT-XXX
□ Proceed with sprint planning
```

### Agent Workflow Integration

**Before starting new story work:**

```bash
# Verify repository state
python3 scripts/ops/sprint_cleanup.py --check-all

# If blocked (exit code 2), resolve or escalate
```

**Jarvis (Orchestrator) responsibilities:**

1. Schedule cleanup before sprint planning
2. Review cleanup reports
3. Assign agents to resolve blocked issues
4. Approve sprint start when cleanup passes

## Reporting Output

### Console Report

Detailed text report with:

- Summary statistics
- Categorized issues (critical/warning/info)
- Actions taken/blocked
- Sprint readiness status

### JSON Output

```bash
python3 scripts/ops/sprint_cleanup.py --check-all --json
```

Structure:

```json
{
  "timestamp": "2026-02-20T10:00:00Z",
  "dry_run": true,
  "critical_count": 0,
  "warning_count": 2,
  "issues": [...],
  "actions_taken": [...],
  "actions_blocked": [...],
  "ready": true
}
```

### Discord Summary

Copy-paste friendly format:

```
🟡 **Pre-Sprint Cleanup Report**

**Status:** Ready with warnings
**Critical:** 0
**Warnings:** 2
**Actions Taken:** 3

**Summary:**
⚠️ Review required before sprint start
```

## Troubleshooting

### Redis Unavailable

```bash
# Check connection
redis-cli -h host.docker.internal -p 6380 ping

# Cleanup continues without logging
# Check script output for details
```

### Gitea Token Issues

```bash
# Verify token is set
export GITEA_TOKEN="your-token"
export GITEA_OWNER="craig"  # defaults to "craig"

# PR checks will be skipped without token
```

### Permission Denied

```bash
# Ensure scripts are executable
chmod +x scripts/ops/sprint_cleanup.py
chmod +x scripts/ops/cleanup_history.py
```

## Related Commands

- `chise-branch-hygiene-check` - Focused branch cleanup
- `chise-swarm-session` - Session management
- `chise-merlin-pr-sweep` - PR batch processing
- `chise-precommit-gates` - Pre-PR validation

## Rollback Procedures

If cleanup causes issues:

1. **Check what was done:**

   ```bash
   python3 scripts/ops/cleanup_history.py --last 20
   ```

2. **Restore deleted branch:**

   ```bash
   git reflog | grep "feature/DELETED-BRANCH"
   git checkout -b feature/RESTORED <commit-sha>
   ```

3. **Undo rebase:**
   ```bash
   git reflog <branch>
   git reset --hard <pre-rebase-commit>
   ```

## File Locations

| Component       | Path                                        |
| --------------- | ------------------------------------------- |
| Main script     | `scripts/ops/sprint_cleanup.py`             |
| History query   | `scripts/ops/cleanup_history.py`            |
| Cron automation | `scripts/cron/weekly_cleanup.sh`            |
| Command docs    | `.opencode/command/chise-sprint-cleanup.md` |
| Full docs       | `docs/operations/pre-sprint-cleanup.md`     |

## Maintenance

**Weekly:**

- Review automated cleanup logs
- Verify Discord notifications sent

**Monthly:**

- Analyze trends via `cleanup_history.py --trend 30`
- Adjust thresholds if needed

**Quarterly:**

- Full history export
- Archive old logs
- Review safety criteria
