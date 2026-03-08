---
project: ChiseAI
scope: ci-workflow
type: iterlog
story_id: ST-CI-008
story_title: "Swarm worktree isolation phase1"
phase: implementation
status: in_progress
started_at: "2026-02-11T00:00:00Z"
needs_manual_qdrant_import: false
---

## Decisions

- Use isolated worktree sessions via `scripts/swarm/session.py` with explicit branch and Redis leases.
- Add `scripts/ci/validate_swarm_context.py` as a first CI/local gate.
- Enforce canonical status files as single-writer global-lock targets with explicit lock signal.

## Learnings

- CI-safe context validation must treat local preflight and CI builds differently to avoid false positives.

## Scope Ownership

- scripts:swarm:session.py: ST-CI-008/codex/2026-02-11T00:00:00Z
- scripts:ci:validate_swarm_context.py: ST-CI-008/codex/2026-02-11T00:00:00Z
- opencode:agent: ST-CI-008/codex/2026-02-11T00:00:00Z

## Incidents

- None

## Evidence

- `.woodpecker.yml` includes `swarm-context` status capture.
- `scripts/ci/ci_gate.py` now requires `swarm-context.status`.
- Agent/command docs updated for `BRANCH` + `WORKTREE_PATH` + session verification.
