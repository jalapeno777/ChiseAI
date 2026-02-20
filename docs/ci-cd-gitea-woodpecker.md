---
title: "Gitea + Woodpecker CI/CD"
status: active
updated: 2026-02-15
---

# Gitea + Woodpecker CI/CD

## Overview
- **SCM (canonical):** Gitea
- **CI engine:** Woodpecker
- **Pipeline config:** `.woodpecker.yml`
- **Required status check context:** `ci/woodpecker/pr/ci`

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
- status context `ci/woodpecker/pr/ci`
- PRs for merge (no direct pushes to `main`)

## CI Gate Override Procedure

### Overview
Overrides are **rare exceptions**, not the norm. The CI gates are designed to be non-bypassable by default. This section documents the formal process for temporarily disabling branch protection status checks in Gitea when absolutely necessary.

> **Important:** The CI pipeline itself contains no built-in bypass mechanism. All overrides require explicit human action in Gitea.

### 1. Override Definition
A CI gate override is the act of temporarily disabling or bypassing the `ci/woodpecker/pr/ci` status check requirement on a protected branch (typically `main`) to allow a merge that would otherwise be blocked by failing or incomplete CI checks.

### 2. Pre-Override Requirements
Before requesting or performing an override, **all** of the following must be satisfied:

| Requirement | Description |
|-------------|-------------|
| **Emergency Situation** | Clear justification demonstrating why the override is necessary (e.g., hotfix for production outage, critical security vulnerability) |
| **Maintainer Approval** | Written approval from project maintainer (Captain Craig or explicitly delegated delegate) |
| **Override Ticket** | Documentation of the override request in a dedicated issue or ticket with unique identifier |
| **Risk Assessment** | Completed assessment covering: impact of merging, risks of not merging, mitigation measures, rollback plan |

### 3. Override Process
Follow these steps to perform a CI gate override:

1. **Create Override Request Issue**
   - Create a new issue titled: `[OVERRIDE] CI Gate Override - <DATE> - <BRIEF_REASON>`
   - Include all pre-override requirements documentation

2. **Obtain Maintainer Approval**
   - Tag Captain Craig or delegate for review
   - Receive explicit approval comment (e.g., "Approved - proceed with override")

3. **Document in Override Ticket**
   - Record risk assessment, approval, and rationale in the issue
   - Reference any related PRs/branches

4. **Perform Override in Gitea**
   - Navigate to repository Settings → Protected Branches
   - Temporarily remove or modify the status check requirement
   - **Document exactly what was changed**

5. **Execute Merge**
   - Perform the merge while override is active
   - Monitor for any issues

6. **Restore Protection**
   - Immediately restore original branch protection settings
   - Confirm protection is active again

### 4. Audit Logging Requirements
After performing an override, the following must be logged in the override ticket:

| Field | Description |
|-------|-------------|
| **Override ID** | Unique identifier from override ticket |
| **Timestamp (UTC)** | Exact time override was applied and removed |
| **Performed By** | Human who executed the override |
| **Maintainer Approver** | Who approved the override |
| **Changes Made** | Exact branch protection changes made |
| **Before/After State** | Screenshots or documentation of protection settings |
| **Merge Commit** | SHA of merge that used override |
| **Duration** | How long override was active |

### 5. Post-Override Review
A post-override review **must** be completed within 24 hours:

- **Reviewer:** Project maintainer (Captain Craig or delegate)
- **Topics to Document:**
  - Was the override justified?
  - What were the actual outcomes?
  - Were there any issues caused by the override?
  - Lessons learned for future prevention
  - Recommendations for process improvement

The review must be added as a comment to the original override ticket with the `[POST-OVERRIDE-REVIEW]` prefix.

### 6. Non-Bypassable Guarantee
**Critical:** The CI pipeline configuration (`.woodpecker.yml`) contains **no built-in bypass mechanism**. There is no CLI flag, environment variable, or configuration option that can skip CI checks without human intervention in Gitea.

To bypass CI:
1. A human must explicitly modify branch protection settings in Gitea
2. This action is logged in Gitea's audit trail
3. The change must be manually reverted after use

This guarantee ensures that no automated system or script can circumvent CI gates without leaving an audit trail.

---

## Debugging checklist
### CI not triggering
1. **Check Gitea webhook** (repo → Settings → Webhooks):
   - Expected hook target: `http://woodpecker-server:8000/api/hook?...`
2. **Check Woodpecker server logs**:
   - `docker logs --tail 200 woodpecker-server`
3. **Check pipeline records** (read-only):
   - `docker cp woodpecker-server:/var/lib/woodpecker /tmp/woodpecker-data`
   - Inspect `/tmp/woodpecker-data/woodpecker.sqlite` with `python3` + `sqlite3` module.

### Pipelines fail before steps with forge/config errors
Symptoms:
- Pipelines immediately show `status=error` with `could not load config from forge: %!w(<nil>)`
- Woodpecker logs contain `user does not exist [uid: 0, name: ]`
- Gitea API with Woodpecker stored token returns `401 user does not exist [uid: 0, name: ]`

Checks:
1. Validate token drift and expiry health:
   - `python3 scripts/ci/check_woodpecker_forge_token_health.py --require-user craig`
2. Verify latest pipeline errors from DB:
   - `psql "$WOODPECKER_DATABASE_DATASOURCE" -c "select number,status,errors from pipelines order by id desc limit 10;"`
3. Confirm Woodpecker user token can read Gitea API:
   - `curl -H "Authorization: token <woodpecker_users_token>" http://localhost:3000/api/v1/user`

Recovery:
1. Refresh OAuth access token via Gitea `grant_type=refresh_token`.
2. Update Woodpecker `users.token`, `users.secret`, and `users.expiry` to the refreshed values.
3. Restart `woodpecker-server` and `woodpecker-agent`.
4. Trigger a new push/PR event and confirm steps execute.

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
3. Wait for `ci/woodpecker/pr/ci` to pass.
4. Merge via Gitea UI or API (auto-merge bot recommended).
