---
name: "chise-ci-pr-status"
description: "ChiseAI: query Woodpecker PR pipeline status matrix (fast triage pre-check)."
disable-model-invocation: true
---

Use this command to quickly determine whether a PR has failing Woodpecker pipelines and which pipeline number to diagnose.

Prereqs:
- `WOODPECKER_TOKEN` must be set
- `GITEA_OWNER`/`GITEA_REPO` or `CI_REPO_OWNER`/`CI_REPO_NAME` must be set
- `PR_NUMBER` should be set for PR-targeted triage

Commands:

```bash
python3 scripts/ci/woodpecker_triage.py status --pr "${PR_NUMBER}" --format human
```

JSON output variant:

```bash
python3 scripts/ci/woodpecker_triage.py status --pr "${PR_NUMBER}" --format json
```
