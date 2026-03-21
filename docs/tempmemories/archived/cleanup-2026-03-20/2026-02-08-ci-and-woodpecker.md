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
- Removed custom clone step to rely on Woodpecker built-in Gitea clone (avoids secret lookup errors).
- Restored explicit clone plugin using `gitea:3000` to bypass Gitea ROOT_URL localhost clone URLs.
- Switched clone remote to host gateway `172.17.0.1:3000` because pipeline containers resolve default bridge, not `gitea`.
- Removed explicit username/password in clone; plan to rely on trusted clone credentials injection.
- Set clone remote to `from_secret: gitea_clone_url` to supply auth in URL (user-managed secret).
- Woodpecker OAuth client/secret still default `change-me`; server cannot load config from forge until real Gitea OAuth app creds are set and Woodpecker re-auths.
- Created Gitea OAuth app directly in `gitea.db` (client_id `54703d2c469ef2d15174d554aa822bbf`); set terraform tfvars locally and restarted woodpecker-server.
- Set `GITEA__server__HTTP_ADDR=0.0.0.0` to ensure host port 3000 is reachable (connection resets should stop).
- Recreated OAuth app via Gitea API using scoped admin token; updated local `terraform.tfvars` and restarted woodpecker-server.
- Set Gitea OAuth app `confidential_client=1` to avoid PKCE-required login errors.
- Created `chise-bot` user, granted repo access, and set Woodpecker `gitea_clone_url` to use bot PAT (no craig impact).
- Updated bot PAT scope to `all` and added `access` table entry for repo permissions.
