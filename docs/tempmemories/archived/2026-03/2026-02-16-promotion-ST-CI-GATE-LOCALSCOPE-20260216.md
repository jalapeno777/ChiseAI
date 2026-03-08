---
project: ChiseAI
scope: ci-cd
type: summary
story_id: ST-CI-GATE-LOCALSCOPE-20260216
tags: [ci, woodpecker, gitea, ci-gate, local-ci]
phase: implementation
---

Promotion payload prepared for Qdrant manual import because `qdrant_qdrant-store` MCP tooling is unavailable in this runtime.

Summary:
- `scripts/local-ci-checks.sh` now supports `--merged-only`; default behavior remains full local pytest with coverage enforcement.
- `.woodpecker.yml` `local-ci` now runs `./scripts/local-ci-checks.sh --merged-only`.
- Removed standalone `ci-root-cause-bundle` pipeline step.
- `scripts/ci/ci_gate.py` now runs bundle diagnostics directly, writes `_bmad-output/ci/root-cause.log`, and prints structured root-cause lines (`tool`, `message`, plus `file/rule/test` fields when available).
- Added tests: `tests/test_ci/test_ci_gate.py`.

Validation:
- `python3 -m pytest -q tests/test_ci/test_ci_gate.py tests/test_ci/test_woodpecker_triage.py tests/test_ci/test_ci_change_scope.py` => passed.
- `bash scripts/local-ci-checks.sh --merged-only` => passed.
- `python3 scripts/validate_status_sync.py` => passed.
- `python3 scripts/validate_iterloop_compliance.py --story-id=ST-CI-GATE-LOCALSCOPE-20260216` => passed (warnings only on legacy tempmemory files).
