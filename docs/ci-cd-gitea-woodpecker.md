---
title: "Gitea + Woodpecker CI/CD"
status: active
updated: 2026-02-08
---

# Gitea + Woodpecker CI/CD

## Overview
- **SCM (canonical):** Gitea
- **CI engine:** Woodpecker
- **Pipeline config:** `.woodpecker.yml`
- **Required status check context:** `ci/woodpecker/push/woodpecker`

GitHub is **deprecated** for ChiseAI unless explicitly re-enabled by a human. Use the `gitea` remote for pushes/PRs.

## Ports (host)
- Gitea UI/API: `http://localhost:3000`
- Gitea SSH: `localhost:2222`
- Woodpecker UI/API: `http://localhost:8012` (container port 8000)

## Container → host access (this agent environment)
Use `host.docker.internal` instead of `localhost`:
- Gitea API: `http://host.docker.internal:3000`
- Woodpecker UI: `http://host.docker.internal:8012`

## CI pipeline summary
The default pipeline runs:
1. **lint**: installs `black`, `ruff`, `mypy`, `pytest` and runs:
   - `black --check .`
   - `ruff check .`
   - `mypy src tests scripts`
   - `python scripts/validate_status_sync.py`
   - `python scripts/validate_iterloop_compliance.py`
2. **security-scan**: installs `bandit` and runs:
   - `bandit -q -r src`
2. **local-ci**: runs `scripts/local-ci-checks.sh` if present

## Required branch protections
Configure `main` to require:
- status context `ci/woodpecker/push/woodpecker`
- PRs for merge (no direct pushes to `main`)

## Debugging checklist
### CI not triggering
1. **Check Gitea webhook** (repo → Settings → Webhooks):
   - Expected hook target: `http://woodpecker-server:8000/api/hook?...`
2. **Check Woodpecker server logs**:
   - `docker logs --tail 200 woodpecker-server`
3. **Check pipeline records** (read-only):
   - `docker cp woodpecker-server:/var/lib/woodpecker /tmp/woodpecker-data`
   - Inspect `/tmp/woodpecker-data/woodpecker.sqlite` with `python3` + `sqlite3` module.

### Lint failures that look like “no files”
If `mypy .` fails with “There are no .py[i] files”, add a targeted `files = [...]` entry in `[tool.mypy]` to ensure at least one file is checked.

## Working with tokens (admin-only)
- Use short-lived PATs for API work.
- Create with: `gitea admin user generate-access-token --username <user> --token-name <name> --scopes all`
- Delete after use (Gitea DB):
  - `sqlite3 /data/gitea/gitea.db "delete from access_token where name='<name>';"`

## Merge flow (expected)
1. Push branch to Gitea: `git push gitea <branch>`
2. Open PR in Gitea.
3. Wait for `ci/woodpecker/push/woodpecker` to pass.
4. Merge via Gitea UI or API (auto-merge bot recommended).
