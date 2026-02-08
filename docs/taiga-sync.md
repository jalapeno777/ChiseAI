# Taiga <-> Repo Sync Policy (Strict Conflict)

## Canonical Source of Truth
- Repo is canonical for requirements, status, and acceptance criteria.
- Taiga is canonical for planning metadata (assignee, sprint, estimates, tags, comments).

## Tooling
- Sync script: `scripts/taiga_sync.py`
- Sync state (mapping + checksums): `docs/taiga/sync-state.yaml`

## Login Notes (Local Taiga)
- UI: `http://localhost:9001` (from your host machine)
- Login uses **username + password** (not email).
- If you try "Reset password" with an email that Taiga doesn't know, it will say you are not registered.
  - In that case, log in via username, or change your Taiga email in the UI/admin to your preferred address.

### Required Env Vars (Repo -> Taiga)
- `TAIGA_BASE_URL` (default: `http://host.docker.internal:9002`)
- `TAIGA_PROJECT_SLUG` (required)
- Auth (one of):
  - `TAIGA_TOKEN` (preferred)
  - `TAIGA_USERNAME` + `TAIGA_PASSWORD`
 - Optional (milestone creation requires dates):
   - `TAIGA_MILESTONE_START` (default: today, ISO date like `2026-02-08`)
   - `TAIGA_MILESTONE_FINISH` (default: today + 90 days)

### Safety Defaults
- Dry-run is the default.
- Applying changes requires `--apply`.
- If Taiga edits repo-canonical fields (title/status/AC), sync will flag conflicts unless `--force`.

### Common Commands
```bash
# Validate config + connectivity (fails fast if env vars missing)
python3 scripts/taiga_sync.py --validate

# Preview what would be created/updated in Taiga
python3 scripts/taiga_sync.py

# Apply repo -> Taiga updates and persist mapping state
python3 scripts/taiga_sync.py --apply
```

## Repo-Canonical Fields (Taiga edits create PR)
- Story ID
- Story title
- Acceptance criteria
- Story status (`docs/bmm-workflow-status.yaml`)
- Validation status (`docs/validation/validation-registry.yaml`)

## Taiga-Canonical Fields (Repo accepts direct sync)
- Assignee(s)
- Sprint/Milestone
- Estimates/Story Points
- Tags/Labels
- Comments/Discussion

## Conflict Rules
- If both sides changed a repo-canonical field since last sync: **hard conflict**, no auto-merge.
- Conflicts require manual resolution and a PR that updates repo files.
- If Taiga changes repo-canonical fields: **create PR**, do not auto-apply to main.

## Sync Flow
1) Pull repo state and compute canonical fields.
2) Pull Taiga state and compare last sync checksum.
3) Apply Taiga-canonical updates to repo sync metadata (if any).
4) If repo-canonical changes detected in Taiga, create PR with updates.
5) If conflicts detected, log and halt.

## PR Requirements
- PR must reference story ID(s).
- Include acceptance criteria changes explicitly.
- Must pass status sync and CI gates before merge.

## CI Automation (Optional)
Woodpecker may run `scripts/taiga_sync.py --validate` or `--apply` on `main` only when
explicitly enabled via CI secrets/env (so the repo stays buildable without Taiga creds).
