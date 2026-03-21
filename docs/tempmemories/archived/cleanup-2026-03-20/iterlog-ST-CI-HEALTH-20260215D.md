---
project: ChiseAI
scope: git-governance
type: iterlog
story_id: ST-CI-HEALTH-20260215D
story_title: "Swarm merge authority + anti-drift + CI command hardening"
phase: implementation
status: completed
started_at: "2026-02-15T00:00:00Z"
completed_at: "2026-02-15T13:00:04Z"
needs_manual_qdrant_import: true
---

## Acceptance Criteria
- Enforce jarvis as merge authority for main merge operations
- Add Redis merge lock for main merge serialization
- Add session close anti-drift checks (ahead-of-main + no PR guard)
- Update opencode CI/session commands + executor agent docs to reflect enforced flow
- Validate parser/command behavior locally

## Decisions
- Use `scripts/swarm/session.py` as enforcement point to avoid bypass via ad-hoc git commands.
- Keep `CANONICAL_STATUS_LOCK` advisory-only, but add explicit main-merge enforcement and anti-drift checks.

## Evidence
- MEM-SCAN completed against root AGENTS.md for all touched files.
- Redis iterlog initialized for ST-CI-HEALTH-20260215D.
- Qdrant query performed via REST scroll; MCP store unavailable in this environment, so manual promotion note retained.

## Scope Ownership
- scripts:swarm:session.py: ST-CI-HEALTH-20260215D/codex/2026-02-15T00:00:00Z
- opencode:command: ST-CI-HEALTH-20260215D/codex/2026-02-15T00:00:00Z
- opencode:agent: ST-CI-HEALTH-20260215D/codex/2026-02-15T00:00:00Z
- AGENTS.md: ST-CI-HEALTH-20260215D/codex/2026-02-15T00:00:00Z

## Incidents
- None so far.
