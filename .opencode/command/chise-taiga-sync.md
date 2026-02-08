---
name: "chise-taiga-sync"
description: "ChiseAI: sync repo stories to Taiga (dry-run by default; --apply to update Taiga)."
disable-model-invocation: true
---

Use this command to keep Taiga aligned with repo-canonical story metadata so you can monitor progress in Taiga without manually copying status/AC.

Prereqs (env vars):
- `TAIGA_BASE_URL` (default: `http://host.docker.internal:9002`)
- `TAIGA_PROJECT_SLUG` (required)
- Auth (one of):
  - `TAIGA_TOKEN` (preferred)
  - `TAIGA_USERNAME` + `TAIGA_PASSWORD`

1. Validate config + connectivity
   - `python3 scripts/taiga_sync.py --validate`

2. Dry-run preview (default)
   - `python3 scripts/taiga_sync.py`

3. Apply repo -> Taiga changes
   - `python3 scripts/taiga_sync.py --apply`

Notes:
- Sync state is stored in `docs/taiga/sync-state.yaml` (safe to commit; no secrets).
- Conflicts on repo-canonical fields in Taiga are reported unless `--force` is used.
