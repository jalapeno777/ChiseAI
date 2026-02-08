---
project: ChiseAI
scope: infra
type: iterlog
story_id: CH-TAIGA-DBPASS-001
story_title: "Rotate Taiga Postgres Password (Terraform + Running DB)"
phase: implementation
status: in_progress
started_at: "2026-02-08T22:40:00Z"
mem_scan:
  - AGENTS.md
  - infrastructure/terraform/main.tf
  - infrastructure/terraform/variables.tf
  - .env
acceptance_criteria:
  - "AC1: Taiga Postgres user password is rotated from the default value without data loss."
  - "AC2: Terraform is re-applied so taiga containers use the rotated password."
  - "AC3: `taiga-back` successfully connects to Postgres after rotation and Taiga API responds 200."
notes:
  - "Redis/Qdrant tools not available in this runtime; using docs/tempmemories fallback per AGENTS.md."
completed_at: "2026-02-08T22:45:00Z"
---

## Decisions
- Rotate Taiga DB password by first running `ALTER USER taiga WITH PASSWORD ...` (while old creds still work) and then re-applying Terraform to update container env.

## Evidence
- Postgres auth test: `docker exec -e PGPASSWORD=<new> taiga-postgres psql -U taiga -d taiga -c 'select 1;'`
- Django DB test: `docker exec taiga-back python manage.py shell -c "from django.db import connection; connection.ensure_connection()"`
- API health: `curl http://localhost:9002/api/v1/` returns 200
