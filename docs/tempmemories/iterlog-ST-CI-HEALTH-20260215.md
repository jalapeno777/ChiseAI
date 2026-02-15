---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: ST-CI-HEALTH-20260215
story_title: "Repair Woodpecker CI health, validate pipeline execution, and add token-expiry hardening guard"
phase: implementation
status: in_progress
started_at: "2026-02-15T00:34:03Z"
acceptance_criteria:
  - "AC1: Woodpecker forge auth works again and new pipelines no longer fail with 'could not load config from forge'."
  - "AC2: At least one post-fix pipeline on main executes workflow steps (not pre-step error short-circuit)."
  - "AC3: Repo includes an automated token health check that detects JWT exp drift and near-expiry risk for Woodpecker forge users."
mem_scan:
  - AGENTS.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/workflow.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/steps/step-01-init.md
  - _bmad/bmm/workflows/chiseai-iteration-loop/steps/step-02-mem-scan.md
  - .woodpecker.yml
  - scripts/ci/woodpecker_triage.py
  - scripts/validate_iterloop_compliance.py
needs_manual_qdrant_import: true
notes:
  - "Redis/Qdrant MCP tools unavailable in this runtime. Using docs/tempmemories fallback per AGENTS.md and validate_iterloop_compliance policy."
---

## Decisions

- TBD

## Learnings

- TBD

## Scope Ownership

- scripts:ci: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- woodpecker.yml: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- docs:tempmemories: ST-CI-HEALTH-20260215/codex/2026-02-15T00:34:03Z
- TBD

## Incidents

- TBD

## Evidence

- TBD
