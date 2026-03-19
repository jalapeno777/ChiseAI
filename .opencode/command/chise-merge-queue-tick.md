---
name: "chise-merge-queue-tick"
description: "ChiseAI: process a bounded merge-queue tick for PRs waiting on required Woodpecker status."
disable-model-invocation: true
---

Use this command for a non-destructive reconciliation tick (no merge) or merge tick (with `--allow-merge`).
Merge-enabled ticks require Merlin authority because main-merge lock acquisition is Merlin-only.

Prereqs:
- `GITEA_TOKEN` must be set.
- In containerized agent environments, use `GITEA_BASE_URL=http://host.docker.internal:3000`.
- Run from a clean control worktree.

Dry-run style tick (requeue/pending/fail classification only):

```bash
python3 scripts/ops/merge_reconciler.py queue-tick \
  --owner "merlin/queue" \
  --max-items 3 \
  --required-context "ci/woodpecker/pr/ci"
```

Merge-enabled tick (Merlin only):

```bash
python3 scripts/swarm/session.py verify \
  --story-id "${STORY_ID}" \
  --branch "${BRANCH}" \
  --worktree-path "${WORKTREE_PATH}" \
  --check-canonical \
  --require-main-merge-authority \
  --acquire-main-merge-lock

python3 scripts/ops/merge_reconciler.py queue-tick \
  --owner "merlin/queue" \
  --max-items 3 \
  --required-context "ci/woodpecker/pr/ci" \
  --allow-merge
```

Runtime enforcement:
- `AGENT_ID` must be `merlin` (unless explicit override env is set).
- A valid Redis main-merge lock must exist at `bmad:chiseai:merge-lock:main`.
