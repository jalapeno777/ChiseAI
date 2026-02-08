---
story_id: ST-INFRA-001
story_title: "Infra finalize + CI trigger"
phase: implementation
status: in_progress
started_at: 2026-02-08
acceptance_criteria:
  - "AC1: Repo is committed on main and pushed to Gitea successfully."
  - "AC2: Woodpecker pipeline runs on the pushed commit and reports success."
  - "AC3: If CI fails, issues are fixed and pipeline is green."
notes:
  - "Redis/Qdrant unavailable; log decisions here for later import."
---

## Key decisions (log)
- Use temp memory files under docs/tempmemories in lieu of Redis/Qdrant.

## Work log
- Initialized iteration with acceptance criteria.
- Removed embedded Gitea PAT from `.woodpecker.yml`; clone now requires repo secrets `gitea_username` and `gitea_token`.
- Woodpecker clone failure: missing HTTP auth for Gitea (fatal: could not read Username).
- Woodpecker secret `events` must be JSON (e.g. `["push","manual"]`) to avoid UI/API errors.
- Gitea webhook delivery blocked until `GITEA__webhook__ALLOWED_HOST_LIST` includes `woodpecker-server`.
