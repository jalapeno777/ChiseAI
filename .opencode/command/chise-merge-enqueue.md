---
name: "chise-merge-enqueue"
description: "ChiseAI: enqueue a PR for Jarvis-managed merge reconciliation so workers can continue development."
disable-model-invocation: true
---

Use this command after opening/updating a PR when you want Jarvis to merge on green CI without blocking ongoing branch work.

Prereqs:
- `GITEA_TOKEN` must be set.
- `STORY_ID`, `BRANCH`, `PR_NUMBER`, `HEAD_SHA`, `AGENT_ID` must be set.

Run:

```bash
python3 scripts/ops/merge_reconciler.py enqueue \
  --story-id "${STORY_ID}" \
  --branch "${BRANCH}" \
  --pr-number "${PR_NUMBER}" \
  --head-sha "${HEAD_SHA}" \
  --queued-by "${AGENT_ID:-jarvis}"
```

Verification:

```bash
python3 scripts/ops/merge_reconciler.py queue-status
```
