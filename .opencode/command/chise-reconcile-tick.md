---
name: "chise-reconcile-tick"
description: "ChiseAI: run queue processing + git hygiene reconciliation to detect branch/main drift early."
disable-model-invocation: true
---

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
