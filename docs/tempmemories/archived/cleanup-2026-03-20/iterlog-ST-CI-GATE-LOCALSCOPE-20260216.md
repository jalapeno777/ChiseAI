---
project: ChiseAI
scope: ci-cd
type: iterlog
story_id: ST-CI-GATE-LOCALSCOPE-20260216
story_title: "CI migration: local-ci scope + ci-gate root-cause unification"
phase: implementation
status: in_progress
started_at: "2026-02-16T00:00:00Z"
needs_manual_qdrant_import: true
---

## Acceptance Criteria

- AC1: `scripts/local-ci-checks.sh` defaults to full local checks and supports merged-files-only mode for CI.
- AC2: `.woodpecker.yml` `local-ci` step invokes merged-files-only mode while local command remains full.
- AC3: `ci-gate` emits structured root-cause details (`tool`, `message`, plus `file:line` or `rule` or `test`) on failure without separate `ci-root-cause-bundle` step.
- AC4: CI-targeted tests pass for updated scripts.

## Decisions

- Migrate root-cause bundle behavior into `scripts/ci/ci_gate.py` and remove standalone `ci-root-cause-bundle` pipeline step.
- Keep `scripts/local-ci-checks.sh` full by default; add `--merged-only` for CI usage.

## Learnings

- Existing `woodpecker_triage.py bundle` already returns structured root-cause artifacts that `ci-gate` can consume directly.
- File-scoped CI can be implemented safely by selecting changed tests and running syntax checks for changed source files without matching tests.

## Scope Ownership

- `.woodpecker.yml`
- `scripts/local-ci-checks.sh`
- `scripts/ci/ci_gate.py`
- `tests/test_ci/test_ci_gate.py`

## Incidents

- Iterloop validator required a docs fallback iterlog file even though Redis iterlog key existed.

## Evidence

- Redis scan: `redis-cli -h host.docker.internal -p 6380 -n 0 --scan --pattern 'bmad:chiseai:iterlog:*'`
- Qdrant context scan: `POST http://host.docker.internal:6334/collections/ChiseAI/points/scroll`
- Tests: `python3 -m pytest -q tests/test_ci/test_ci_gate.py tests/test_ci/test_woodpecker_triage.py tests/test_ci/test_ci_change_scope.py`
- Compliance: `python3 scripts/validate_iterloop_compliance.py --story-id=ST-CI-GATE-LOCALSCOPE-20260216`
