---
project: ChiseAI
scope: ci-governance
type: iterlog
story_id: ST-CI-HEALTH-20260215G
story_title: "CI fast-gate and non-intrusive throughput hardening"
phase: testing
status: completed
started_at: "2026-02-15T00:00:00Z"
completed_at: "2026-02-15T20:05:00Z"
---

## Acceptance Criteria
- AC1: Add fast-required gate and keep heavy checks non-intrusive
- AC2: Add docs/opencode path-aware heavy-test skip logic
- AC3: Expand PR-title validation to accept active story IDs used in practice
- AC4: Add watchdog script for stuck pipeline detection and wire it into CI

## Decisions
- Use dynamic CI gate requirements: fast checks for PRs, full gate for push to `main`.
- Make lint path-aware (changed Python files only) to avoid unrelated legacy style drift blocking merges.
- Skip heavy `local-ci` for docs/opencode-only changes while preserving required security/status checks.
- Add watchdog signal for likely-stuck Woodpecker pipelines without making it blocking.

## Scope Ownership
- .woodpecker.yml: ST-CI-HEALTH-20260215G/codex/2026-02-15T00:00:00Z
- scripts/ci: ST-CI-HEALTH-20260215G/codex/2026-02-15T00:00:00Z
- scripts/README.md: ST-CI-HEALTH-20260215G/codex/2026-02-15T00:00:00Z

## Incidents
- None.

## Learnings
- PR-title validation needed regex expansion for real-world IDs like `ST-CI-HEALTH-20260215F`.
- Non-intrusive CI requires separating "required fast checks" from heavyweight confidence checks.

## Validation
- `python3 -m pytest -q tests/test_ci/test_validate_pr_title.py tests/test_ci/test_ci_change_scope.py tests/test_ci/test_check_woodpecker_stuck_pipelines.py`
- `python3 scripts/validate_status_sync.py`
- `python3 scripts/validate_iterloop_compliance.py --story-id=ST-CI-HEALTH-20260215G`
- `bash scripts/local-ci-checks.sh`
