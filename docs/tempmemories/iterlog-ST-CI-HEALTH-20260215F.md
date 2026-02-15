---
project: ChiseAI
scope: ci-governance
type: iterlog
story_id: ST-CI-HEALTH-20260215F
story_title: "Opencode merge-train + async reconcile implementation"
phase: testing
status: completed
started_at: "2026-02-15T00:00:00Z"
completed_at: "2026-02-15T19:28:40Z"
needs_manual_qdrant_import: true
---

## Acceptance Criteria
- Add Redis-backed merge queue operations for enqueue/list/pop/incident
- Add reconcile tick script with lock, bounded processing, and escalation payloads
- Add opencode commands for queue enqueue/tick/reconcile/intake
- Update docs for Jarvis/Aria usage and runtime cadence in container
- Add tests for queue/reconcile modules and run validation

## Decisions
- Implement bounded tick budgets to avoid starving active swarm workers in shared env.
- Keep reconciler deterministic and escalation-only for non-safe actions.

## Scope Ownership
- scripts:ops: ST-CI-HEALTH-20260215F/codex/2026-02-15T00:00:00Z
- opencode:command: ST-CI-HEALTH-20260215F/codex/2026-02-15T00:00:00Z
- opencode:agent: ST-CI-HEALTH-20260215F/codex/2026-02-15T00:00:00Z
- scripts:README.md: ST-CI-HEALTH-20260215F/codex/2026-02-15T00:00:00Z

## Incidents
- None yet.

## Learnings
- Queue-based merge reconciliation keeps worker throughput high while preserving serialized main integration.
- Bounded `--max-items` ticks are sufficient for drift prevention without monopolizing the shared environment.
- Enforcing `WOODPECKER_MAX_WORKFLOWS=3` at agent runtime provides explicit parallel pipeline capacity.

## Validation
- `python3 -m pytest -q tests/test_ops/test_merge_reconciler.py`
- `python3 -m pytest -q tests/test_ci/test_woodpecker_triage.py tests/test_gitea_pr_automerge.py`
- `python3 scripts/validate_iterloop_compliance.py --story-id=ST-CI-HEALTH-20260215F`
- `python3 scripts/validate_status_sync.py`
- `bash scripts/local-ci-checks.sh`
