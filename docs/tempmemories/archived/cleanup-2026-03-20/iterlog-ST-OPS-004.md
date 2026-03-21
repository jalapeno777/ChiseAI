---
story_id: ST-OPS-004
story_title: "Taiga Integration (Repo<->Taiga Sync)"
phase: implementation
status: completed
started_at: "2026-02-08T20:49:14Z"
completed_at: "2026-02-08T21:27:30Z"
acceptance_criteria:
  - "AC1: `python3 scripts/taiga_sync.py --dry-run` runs without network creds and exits 0, showing planned changes."
  - "AC2: With `TAIGA_BASE_URL`, `TAIGA_TOKEN`, and `TAIGA_PROJECT_SLUG` set, `python3 scripts/taiga_sync.py --apply` creates/updates Taiga milestones and user stories for non-deprecated repo stories."
  - "AC3: Sync writes/updates `docs/taiga/sync-state.yaml` mapping repo story ids to Taiga ids/refs and stores checksums for conflict detection."
  - "AC4: `python3 scripts/taiga_sync.py --validate` fails fast with a clear message when required Taiga config is missing or Taiga API is unreachable."
  - "AC5: CI includes a safe Taiga validation gate that defaults to skip unless explicitly enabled by env/secrets."
  - "AC6: Unit tests cover YAML parsing, checksum generation, and conflict detection logic."
key_decisions:
  - "Dry-run is the default; applying changes requires explicit `--apply`."
  - "Repo remains canonical for story id/title/status/acceptance criteria; Taiga remains canonical for assignee/sprint/points/tags/comments."
  - "Conflicts on repo-canonical fields in Taiga are detected and reported; updates require `--force`."
learnings: []
---

Working notes for ST-OPS-004.

- Taiga milestone creation requires `estimated_start` and `estimated_finish`; sync uses defaults (today..+90d) and allows overrides via `TAIGA_MILESTONE_START`/`TAIGA_MILESTONE_FINISH`.

## Scope Ownership

- TBD

## Incidents

- TBD
