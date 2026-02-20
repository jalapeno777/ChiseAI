# Pre-Sprint Cleanup Routine - Documentation

## Overview

The **Pre-Sprint Cleanup Routine** is a comprehensive repository hygiene system designed to ensure the ChiseAI codebase is clean, synchronized, and ready for new sprint work. It automates the detection and resolution of common repository issues while maintaining safety through dry-run capabilities and explicit action gates.

## System Components

### 1. Main Cleanup Script
**File:** `scripts/ops/sprint_cleanup.py`

The core cleanup orchestrator that performs all checks and executes safe fixes.

**Key Capabilities:**
- Working tree cleanliness verification
- Branch hygiene analysis
- Main branch synchronization
- PR status verification
- Canonical file integrity checks
- Automated cleanup actions

### 2. Command Definition
**File:** `.opencode/command/chise-sprint-cleanup.md`

Agent-facing documentation and usage instructions.

### 3. History Query Tool
**File:** `scripts/ops/cleanup_history.py`

Query and report on cleanup history stored in Redis.

### 4. Cron Automation
**File:** `scripts/cron/weekly_cleanup.sh`

Automated weekly cleanup execution.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Sprint Cleanup Routine                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ GitHelper    │   │ GiteaHelper  │   │ RedisHelper  │    │
│  │              │   │              │   │              │    │
│  │ - Branches   │   │ - PRs        │   │ - State      │    │
│  │ - Worktrees  │   │ - Status     │   │ - Logs       │    │
│  │ - Commits    │   │ - Mergeable  │   │ - History    │    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            ▼                                │
│                   ┌─────────────────┐                       │
│                   │ SprintCleanup   │                       │
│                   │                 │                       │
│                   │ - Orchestrate   │                       │
│                   │ - Report        │                       │
│                   │ - Execute       │                       │
│                   └────────┬────────┘                       │
│                            │                                │
│         ┌──────────────────┼──────────────────┐            │
│         ▼                  ▼                  ▼            │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ Console      │   │ JSON         │   │ Discord      │    │
│  │ Report       │   │ Output       │   │ Summary      │    │
│  └──────────────┘   └──────────────┘   └──────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Check Categories

### 1. Working Tree Cleanliness

**What it checks:**
- Uncommitted changes in any worktree
- Untracked files
- Stale agent sessions (>3 days)

**Severity:**
- Uncommitted changes → CRITICAL
- Untracked files → WARNING
- Stale sessions → WARNING

**Auto-fixable:** No (manual intervention required)

### 2. Branch Hygiene

**What it checks:**
- Already merged to main (safe to delete)
- Behind main >7 commits (needs rebase)
- Stale branches (>30 days no activity)
- Invalid branch naming

**Severity:**
- Merged branches → INFO
- Behind main → WARNING
- Stale branches → WARNING
- Invalid naming → WARNING

**Auto-fixable:**
- Merged branches → Yes
- Behind main with no local commits → Yes
- Others → No

### 3. Main Branch Synchronization

**What it checks:**
- Local main == Remote main
- No diverged commits
- Clean fast-forward possible

**Severity:**
- Any sync issue → CRITICAL

**Auto-fixable:**
- Local behind remote → Yes (pull)
- Diverged → No (manual resolution)

### 4. PR Status Verification

**What it checks:**
- Open PRs with merge conflicts
- Stuck PRs (no mergeable status)

**Severity:**
- Merge conflicts → WARNING
- Stuck state → WARNING

**Auto-fixable:** No

### 5. Canonical File Integrity

**What it checks:**
- `docs/bmm-workflow-status.yaml` exists and valid
- `docs/validation/validation-registry.yaml` exists and valid

**Severity:**
- Missing or invalid → CRITICAL

**Auto-fixable:** No

## Redis Schema

### State Tracking
```
Key: bmad:chiseai:sprint_cleanup:state
Type: Hash
Purpose: Track current cleanup state

Fields:
  current: JSON {
    "state": "started|completed",
    "timestamp": "ISO8601",
    "data": {...}
  }
```

### Audit Log
```
Key: bmad:chiseai:sprint_cleanup:log
Type: List
Purpose: Immutable log of all cleanup actions

Entries:
  {
    "timestamp": "ISO8601",
    "action": "delete_merged_branch|rebase_branch|update_main|...",
    "details": JSON string
  }
```

### Daily Summaries
```
Key: bmad:chiseai:sprint_cleanup:summary:YYYY-MM-DD
Type: Hash
Purpose: Daily cleanup reports

Fields:
  report: JSON {
    "timestamp": "ISO8601",
    "dry_run": bool,
    "critical_count": int,
    "warning_count": int,
    "actions_taken": int,
    "actions_blocked": int
  }
```

### Sprint Boundaries
```
Key: bmad:chiseai:sprint:boundary
Type: List
Purpose: Track sprint start points

Entries:
  {
    "sprint_id": "SPRINT-YYYY-QX-NN",
    "started_at": "ISO8601",
    "cleanup_timestamp": "ISO8601",
    "issues_critical": int,
    "issues_warning": int,
    "repository_state": "ready|blocked"
  }
```

## Safety Mechanisms

### 1. Dry-Run by Default
- All checks are performed without making changes by default
- Must explicitly use `--execute` to modify state

### 2. Safe Fixes Only
- `--auto-fix-safe` only fixes clearly safe issues:
  - Merged branches (already in main)
  - Behind-main branches with no local commits
  - Main branch behind remote

### 3. No Interactive Prompts
- No blocking prompts
- Safety through explicit flags, not user interaction

### 4. Comprehensive Logging
- Every action logged to Redis
- Audit trail for compliance
- History available via `cleanup_history.py`

### 5. Exit Codes
- `0` = Ready (clean or warnings only)
- `1` = Ready with warnings
- `2` = Blocked (critical issues)
- Clear indication of required action

## Integration Points

### Agent Workflow Integration

**Before starting new sprint work:**
1. Run cleanup: `python3 scripts/ops/sprint_cleanup.py --check-all`
2. Review output
3. If blocked, resolve issues
4. Re-run cleanup
5. Mark sprint boundary if successful

**Weekly maintenance:**
```bash
# Automated via cron
0 6 * * 1 /home/tacopants/projects/ChiseAI/scripts/cron/weekly_cleanup.sh
```

### CI/CD Integration

```yaml
pre_sprint_check:
  script:
    - python3 scripts/ops/sprint_cleanup.py --check-all --json > report.json
  artifacts:
    reports:
      json: report.json
```

### Discord Notifications

The cleanup routine generates Discord-friendly summaries:

```bash
# Get Discord summary
cleanup_output=$(python3 scripts/ops/sprint_cleanup.py --check-all)

# Post to Discord (if configured)
echo "$cleanup_output" | python3 scripts/ci/post_ci_failure_discord.py
```

## Usage Examples

### Example 1: Pre-Sprint Check
```bash
# Check without making changes
python3 scripts/ops/sprint_cleanup.py --check-all

# Output:
# ============================================================
# Pre-Sprint Cleanup Report
# ============================================================
# ...
# SPRINT READINESS
# ----------------------------------------
# ⚠️  READY WITH WARNINGS - Review warnings before starting sprint
```

### Example 2: Execute Safe Fixes
```bash
# Auto-fix safe issues
python3 scripts/ops/sprint_cleanup.py --execute --auto-fix-safe

# Output shows actions taken:
# 🔧 Executing safe fixes...
#   ✓ Deleted merged branch: feature/ST-OLD-001-old-feature
#   ✓ Updated main branch from remote
```

### Example 3: Mark Sprint Boundary
```bash
# After successful cleanup, mark sprint start
python3 scripts/ops/sprint_cleanup.py \
  --execute --auto-fix-safe \
  --mark-sprint SPRINT-2026-Q1-01

# Stores in Redis: bmad:chiseai:sprint:boundary
```

### Example 4: Query History
```bash
# View recent cleanup trend
python3 scripts/ops/cleanup_history.py --trend 30

# View specific sprint
python3 scripts/ops/cleanup_history.py --sprint SPRINT-2026-Q1-01

# Export to file
python3 scripts/ops/cleanup_history.py --export cleanup-history.json --days 90
```

## Decision Matrix

| Issue Type | Severity | Auto-Fix | Action |
|------------|----------|----------|--------|
| Uncommitted changes | CRITICAL | No | Commit or stash manually |
| Untracked files | WARNING | No | Add to .gitignore or commit |
| Merged branch | INFO | Yes | Delete local and remote |
| Behind main, no local commits | WARNING | Yes | Rebase onto main |
| Behind main, has local commits | WARNING | No | Manual rebase with care |
| Stale branch (>30 days) | WARNING | No | Review and archive/delete |
| Invalid branch name | WARNING | No | Rename or delete |
| Main out of sync | CRITICAL | Sometimes | Pull if behind, manual if diverged |
| PR with conflicts | WARNING | No | Resolve conflicts |
| Stuck PR | WARNING | No | Investigate and escalate |
| Missing canonical file | CRITICAL | No | Restore from git |

## Rollback Procedures

### If Cleanup Causes Issues

1. **Check what was done:**
   ```bash
   python3 scripts/ops/cleanup_history.py --last 20
   ```

2. **For deleted branches:**
   ```bash
   # Restore from reflog
   git reflog | grep "feature/DELETED-BRANCH"
   git checkout -b feature/RESTORED <commit-sha>
   ```

3. **For rebased branches:**
   ```bash
   # Original commits are in reflog
   git reflog <branch-name>
   # Reset to pre-rebase state
   git reset --hard <pre-rebase-commit>
   ```

4. **For main sync issues:**
   ```bash
   # Check reflog for main
   git reflog main
   # Reset if needed
   git reset --hard <pre-sync-commit>
   ```

## Monitoring and Alerting

### Key Metrics

1. **Cleanup Frequency**
   - Track via Redis logs
   - Weekly automated runs

2. **Issue Trends**
   - Critical issues per sprint
   - Warning trends over time
   - Auto-fix success rate

3. **Repository Health Score**
   - Calculate: `100 - (critical * 10 + warnings * 2)`
   - Alert if score < 70

### Alerts

Configure alerts for:
- Cleanup blocked (exit code 2) for >2 consecutive runs
- Critical issues increasing week-over-week
- Failed auto-fixes

## Maintenance

### Monthly Tasks
1. Review cleanup logs for patterns
2. Adjust thresholds if needed
3. Update branch naming patterns
4. Verify Redis retention settings

### Quarterly Tasks
1. Full cleanup history export
2. Archive old logs (beyond 90 days)
3. Review and update safety criteria
4. Test rollback procedures

## Troubleshooting

### Redis Connection Failures
```bash
# Check Redis connectivity
redis-cli -h host.docker.internal -p 6380 ping

# Cleanup continues without Redis logging
# Check logs for details
```

### Git Permission Issues
```bash
# Ensure proper git config
git config user.email
git config user.name

# Check write permissions to repo
```

### Gitea API Failures
```bash
# Verify token
export GITEA_TOKEN="your-token"

# Check API connectivity
curl -H "Authorization: token $GITEA_TOKEN" \
  http://host.docker.internal:3000/api/v1/user
```

## Future Enhancements

1. **Web Dashboard**
   - Visual cleanup history
   - Repository health trends
   - Sprint boundary timeline

2. **Integration with Taiga**
   - Link cleanup to sprint planning
   - Auto-create tasks for blocked issues

3. **Machine Learning**
   - Predict stale branches
   - Recommend optimal cleanup timing
   - Detect abnormal patterns

4. **Slack/Discord Rich Notifications**
   - Interactive buttons for quick actions
   - Thread-based issue resolution
   - Scheduled cleanup reminders

## References

- **Command Reference:** `.opencode/command/chise-sprint-cleanup.md`
- **Branch Hygiene Skill:** `.opencode/skills/chiseai-branch-hygiene/SKILL.md`
- **Git Workflow:** `.opencode/skills/chiseai-git-workflow/SKILL.md`
- **Session Management:** `scripts/swarm/session.py`
- **PR Sweep:** `scripts/ops/merlin_pr_sweep.py`
