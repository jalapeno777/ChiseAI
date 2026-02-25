---
name: "chise-reconcile-tick"
description: "ChiseAI: run queue processing + git hygiene reconciliation to detect branch/main drift early."
disable-model-invocation: true
---

## When to Use
- **Periodic maintenance**: Run on a timer/cadence (Jarvis cleanup loop) every 15-30 minutes
- **Early drift detection**: Prevent local-only branch drift and main divergence before it accumulates
- **Pre-batch cleanup**: Before starting parallel batch work, ensure clean state
- **Post-incident recovery**: After resolving conflicts, run to verify no lingering issues

## Do Not Use
- **As a merge queue**: Use `chise-merge-queue-process` for actual merge queue operations
- **For intake triage**: Use `chise-intake-triage` for processing incoming work items
- **For PR creation**: This is not for creating PRs; use Gitea CLI or web interface
- **During active work**: Do not run while workers are actively editing (will cause interference)

Use this command on a timer/cadence (Jarvis cleanup loop) to prevent local-only branch drift and main divergence.

Prereqs:
- `GITEA_TOKEN` must be set.
- In containerized agent environments, use `GITEA_BASE_URL=http://host.docker.internal:3000`.
- Run in an isolated control worktree.

Command:

```bash
python3 scripts/ops/merge_reconciler.py reconcile-tick \
  --owner "jarvis/reconcile" \
  --max-items 3 \
  --required-context "ci/woodpecker/pr/ci" \
  --allow-merge
```

Follow-up:
1. Check incidents:
   - `python3 scripts/ops/merge_reconciler.py intake-incidents --limit 100`
2. Route incidents:
   - `kind=ci_not_green|merge_conflict|merge_api_error` -> `merlin`
   - `kind=main_unsynced|local_branch_ahead_main|pr_closed_unmerged` -> `jarvis`
