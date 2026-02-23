---
name: chiseai-branch-hygiene
description: Branch lifecycle management, cleanup standards, and hygiene monitoring for ChiseAI repository.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-branch-hygiene

## Goal

Keep the repository clean by managing branch lifecycle, identifying stale branches, and automating cleanup decisions.

## When To Use

- Creating new branches
- Weekly hygiene reviews
- Before major releases
- merlin PR sweep operations
- Cleaning up after sprint completion

## When Not To Use

- During active development on a branch
- Emergency hotfix creation (use safety branch naming instead)
- Local-only experimentation branches
- When branch is protected by active PR review

## Branch Naming Standards

### Feature Work
feature/<story-id>-<brief-description>
Examples:
- feature/ST-NS-001-neuro-evolution
- feature/ST-CI-007-fix-pipeline

### Emergency/Safety Work
safety/<reason>-<date>
Examples:
- safety/hotfix-20260216

### NEVER Use
- wip, temp, test (non-descriptive)
- feature-1, feature-2 (no story ID)
- Personal names: john-fix

## Branch Lifecycle

Create → Active Work → PR Open → Merged → Delete
    ↓         ↓           ↓         ↓        ↓
Feature  <7 days     Review    merlin   Auto-cleanup
Branch   Active     Period    merges   (or manual)

## Hygiene Rules

### Behind Main >7 Days
Status: WARNING
Action: Update branch or delete if abandoned
Redis: bmad:chiseai:branch_hygiene:warned:behind

### No Activity >30 Days
Status: REVIEW
Action: Archive or delete
Redis: bmad:chiseai:branch_hygiene:warned:inactive

### Already Merged
Status: DELETE
Action: Delete immediately
Redis: bmad:chiseai:branch_hygiene:deleted:merged

### Invalid Naming
Status: WARN
Action: Rename or delete
Redis: bmad:chiseai:branch_hygiene:warned:invalid-name

## Redis Tracking

```python
# Mark branch as warned
redis_state_hset(
    name="bmad:chiseai:branch_hygiene:warned:behind",
    key="feature/ST-NS-001-old",
    value='{"reason": "behind_main_7_days", "warned_at": "2026-02-16T10:00:00Z"}'
)

# Mark as cleaned up
redis_state_hset(
    name="bmad:chiseai:branch_hygiene:deleted:merged",
    key="feature/ST-NS-001-old",
    value='{"deleted_at": "2026-02-16T15:00:00Z", "pr_number": 123}'
)

# Daily summary
redis_state_hset(
    name="bmad:chiseai:branch_hygiene:summary:2026-02-16",
    key="report",
    value='{"total": 45, "active": 12, "stale": 8, "actions": ["warned:3", "deleted:2"]}'
)
```

## Cleanup Decision Matrix

| Branch State | Action | Owner |
|--------------|--------|-------|
| Merged to main + >7 days old | DELETE | merlin (auto) |
| Behind main + >7 days | WARN → Update or delete | Jarvis decides |
| No activity + >30 days | REVIEW → Archive or delete | Human decision |
| Invalid naming | WARN → Rename or delete | Jarvis decides |

## Exit Conditions

- Branch naming follows convention.
- Lifecycle state tracked in Redis.
- Cleanup actions documented.
- No orphaned branches remain after sweep.

## Troubleshooting/Safety

- **Accidental deletion**: Use git reflog to recover within 30 days; restore from backup if needed.
- **Protected branch**: Never delete main or release branches; check protection rules first.
- **Active PR branch**: Do not delete while PR is open; check PR status before cleanup.
- **Naming conflict**: Rename with valid convention before deleting duplicate.

## Related Skills

- `chiseai-git-workflow` - Defines branch creation and PR workflow
- `chiseai-validation` - Validates pre-merge state
- `chiseai-parallel-safety` - Manages parallel branch work

## Related Commands

- `.opencode/command/chise-branch-hygiene-check.md`
- `.opencode/command/chise-merlin-pr-sweep.md`
