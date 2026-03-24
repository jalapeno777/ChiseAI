---
name: "chise-merge-enqueue"
description: "ChiseAI: enqueue a PR for Jarvis-managed merge reconciliation so workers can continue development."
disable-model-invocation: true
---

Use this command after opening/updating a PR when you want Jarvis to merge on green CI without blocking ongoing branch work.

Prereqs:

- `GITEA_TOKEN` must be set.
- In containerized agent environments, use `GITEA_BASE_URL=http://host.docker.internal:3000`.
- `GITEA_OWNER` defaults to `craig` if not set.
- `STORY_ID`, `BRANCH`, `PR_NUMBER`, `HEAD_SHA`, `AGENT_ID` must be set.
- `STORY_ID` must use accepted title-gate formats (`ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*`) and include a digit.

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
