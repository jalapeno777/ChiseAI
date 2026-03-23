# chise-post-branch-reconcile

## Purpose

Implements the Post-Branch Reconcile Loop defined in AGENTS.md "Post-Branch Reconcile Loop (REQUIRED)" section. Runs after each branch handoff/merge cycle before starting the next batch.

## When to Run

After completing a branch merge cycle, before starting new dependent work. This ensures:

1. Failed PRs are caught and routed for fixes before blocking dependent work
2. Merged commits are verified on main
3. Local main is synced to origin

## Command

```
chise-post-branch-reconcile
```

## Prerequisites

- Gitea CLI (`gh` or direct API access)
- Discord webhook configured (for notifications)
- Redis connection for notification channel

## 5-Step Procedure

### Step 1: Check Woodpecker Pipeline State

Check all recent PR/pipeline states for non-green pipelines.

```bash
# List recent PRs and their CI status
gh pr list --state all --limit 20 --json number,title,headRefName,statusCheckRollup,state

# Alternative: Use Gitea API directly
# GET /repos/{owner}/{repo}/pulls?state=all
```

Classify each PR:

- `running` / `pending` → In progress, monitor
- `failure` / `error` → Requires immediate routing for fixes
- `success` / `merged` → Clean, proceed

### Step 2: Route Failed/Error PRs for Fixes

For PRs with `failure` or `error` status:

1. Identify the PR owner/assignee
2. Post notification to #development channel
3. Block dependent work until resolved
4. Document in Redis: `bmad:chiseai:reconcile:blocking-prs`

```bash
# Example routing action
discord_send --channel "#development" --message "PR #<number> failed CI. Routing to <owner> for fixes. Blocking dependent work."
```

### Step 3: Verify Merged Commits on Main

Confirm that recently merged branches are actually on main using `git branch --contains`.

```bash
# For each merged PR, verify the merge commit is on main
git branch --contains <merge_commit_sha>

# Example:
# Merge commit from PR #599 was 560a9d9e
git branch --contains 560a9d9e
# Should output: * main (or show main in the list)
```

If the commit is NOT on main:

- STOP immediately
- Do not proceed with new work
- Report to orchestrator via BLOCKER_PACKET

### Step 4: Sync Local Main to Origin

Update local main branch to match origin.

```bash
git switch main
git fetch origin --prune
git pull --ff-only origin main
git status -sb
```

Expected output: `## main...origin/main` (no divergence)

### Step 5: Proceed with New Development

Only after all previous steps pass:

- Confirm local main is clean and up-to-date
- Verify no blocking PRs
- Begin new dependent work from refreshed main

## Notification Requirements

### Discord Notifications

Post status to #development:

- Start: "Starting post-branch reconcile loop"
- Step 2 failures: "Routing PR #X for fixes - blocking dependent work"
- Step 3 failure: "BLOCKER: Merge commit not on main!"
- Step 4 failure: "BLOCKER: Cannot sync main!"
- Completion: "Post-branch reconcile complete - local main synced"

### Redis State

Update reconcile state:

```
bmad:chiseai:reconcile:last_run = <timestamp>
bmad:chiseai:reconcile:status = <success|blocked>
bmad:chiseai:reconcile:blocking_prs = <comma-separated PR numbers or empty>
```

## Exit Conditions

| Condition                | Action                                |
| ------------------------ | ------------------------------------- |
| All steps pass           | Proceed with new work                 |
| PRs failing              | Route for fixes, block dependent work |
| Merge commit not on main | STOP, escalate via BLOCKER_PACKET     |
| Cannot sync main         | STOP, escalate via BLOCKER_PACKET     |

## Example Output

```
=== POST-BRANCH RECONCILE ===
[1/5] Checking Woodpecker pipelines...
  PR #599: success ✓
  PR #601: failure ✗ -> routing for fixes

[2/5] Routing failed PRs...
  PR #601 routed to @owner via Discord

[3/5] Verifying merged commits on main...
  Commit 560a9d9e: on main ✓

[4/5] Syncing local main...
  Fetched origin/main
  Fast-forward merge successful ✓

[5/5] Local main synced, no blocking PRs
=== RECONCILE COMPLETE ===
```

## Error Handling

If any step fails:

1. Do NOT proceed to next step
2. Log the failure to Redis: `bmad:chiseai:reconcile:errors`
3. Post error to Discord #development
4. If blocking (Step 3 or 4 failure): escalate via BLOCKER_PACKET to Aria

## Related Commands

- `chise-swarm-session` - Session management
- `chise-precommit-gates` - Pre-PR validation
