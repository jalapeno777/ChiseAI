---
project: ChiseAI
scope: infra
type: iterlog
story_id: CH-INFRA-WOODPECKER-PG-001
story_title: "Migrate Woodpecker DB to Postgres; Enable Taiga Auto-Sync; Rotate Taiga Secret Key"
phase: implementation
status: in_progress
started_at: "2026-02-08T23:00:00Z"
mem_scan:
  - AGENTS.md
  - .woodpecker.yml
  - scripts/taiga_sync.py
  - infrastructure/terraform/main.tf
  - infrastructure/terraform/variables.tf
  - infrastructure/terraform/README.md
  - .env
acceptance_criteria:
  - "AC1: Woodpecker server uses Postgres (not sqlite) and no longer logs sqlite lock errors under normal load."
  - "AC2: Existing repo + required secrets (clone + taiga sync) are present after migration so pipelines continue to work."
  - \"AC3: Taiga sync runs automatically on merges to main (gated by repo secrets) and updates Taiga state.\"
  - \"AC4: Taiga secret key is rotated via Terraform and taiga services remain healthy.\"
notes:
  - "Redis/Qdrant tools not available in this runtime; using docs/tempmemories fallback per AGENTS.md."
completed_at: "2026-02-08T23:06:00Z"
---

## Decisions
- Woodpecker persistence migrated from sqlite to Postgres to eliminate sqlite locking under concurrency.
- Taiga secret key rotated via Terraform; expect Taiga sessions/tokens to be invalidated (normal).
- Taiga auto-sync is enabled via Woodpecker repo secrets and runs on `main` when `TAIGA_SYNC_APPLY=1`.

## Scope Ownership

- TBD

## Incidents

- TBD


## Evidence
- Terraform applied with `WOODPECKER_DATABASE_DRIVER=postgres` and `WOODPECKER_DATABASE_DATASOURCE=...` (`infrastructure/terraform/main.tf`).
- Created Postgres role/db: `woodpecker` / `woodpecker` on `chiseai-postgres:5434`.
- Migrated Woodpecker state (forges/orgs/users/repos/secrets) from sqlite to Postgres using `scripts/woodpecker_sqlite_to_postgres.py` (via a /tmp sqlite export).
- Verified Woodpecker HTTP is up: `curl http://localhost:8012` returns 200.
- Verified Taiga API/Front up after secret rotation: `curl http://localhost:9002/api/v1/` returns 200 and `curl http://localhost:9001/` returns 200.
- Verified Taiga sync works with bot creds: `python3 scripts/taiga_sync.py --apply` reports no changes needed.
