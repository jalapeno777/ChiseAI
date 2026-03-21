---
story_id: CH-TAIGA-UI-001
story_title: "Taiga UI Login Fix (Front-end API URL)"
phase: implementation
status: completed
started_at: "2026-02-08T22:03:51Z"
completed_at: "2026-02-08T22:07:09Z"
acceptance_criteria:
  - "AC1: `taiga-front` serves `conf.json` with `api` pointing at `http://localhost:9002/api/v1/` (not :9001)."
  - "AC2: `taiga-front` serves `conf.json` with `eventsUrl` pointing at `ws://localhost:9003/events`."
  - "AC3: Human can log into Taiga UI at `http://localhost:9001` with valid Taiga credentials."
key_decisions:
  - "Fix is done by correcting `TAIGA_URL` and `TAIGA_WEBSOCKETS_URL` in Terraform for `taiga-front`."
learnings: []
---

Working notes for CH-TAIGA-UI-001.

## Scope Ownership

- TBD

## Incidents

- TBD
