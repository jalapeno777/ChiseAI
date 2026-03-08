---
project: ChiseAI
scope: iteration-log
type: iterlog
story_id: ST-CI-HEALTH-20260215B
story_title: "Fix remediation-batch1 CI gate failures (fastapi dependency and security-scan issue)"
phase: implementation
status: in_progress
started_at: "2026-02-15T02:16:15Z"
acceptance_criteria:
  - "AC1: local-ci no longer fails with ModuleNotFoundError: No module named 'fastapi' for tests/test_api/test_ece_router.py."
  - "AC2: security-scan passes on remediation branch without introducing blanket ignores."
  - "AC3: branch pipeline reaches ci-gate success in Woodpecker."
mem_scan:
  - AGENTS.md
  - .woodpecker.yml
  - scripts/local-ci-checks.sh
  - src/api/ece_router.py
  - tests/test_api/test_ece_router.py
  - docs/tempmemories/iterlog-ST-CI-HEALTH-20260215B.md
notes:
  - "Redis/Qdrant MCP tools unavailable in this runtime; using docs/tempmemories fallback."
---

## Decisions

- Install `fastapi` in Woodpecker `local-ci` dependency bootstrap so API-router tests can import FastAPI modules.
- Replace `assert self.store is not None` in `src/confidence/ece_scheduler.py` with explicit runtime validation to satisfy Bandit (`B101`).

## Learnings

- The CI root-cause parser may label high-confidence findings as "high" even when Bandit severity is low; always confirm from raw Bandit output.
- Replay with the same dependency bootstrap used by `.woodpecker.yml` catches missing runtime test dependencies deterministically.

## Scope Ownership

- scripts:ci: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- scripts:local-ci-checks.sh: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- woodpecker.yml: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- src:api: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- tests:test_api: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- docs:tempmemories: ST-CI-HEALTH-20260215B/codex/2026-02-15T02:16:15Z
- TBD

## Incidents

- symptom: `local-ci` failed with `ModuleNotFoundError: No module named 'fastapi'` in `tests/test_api/test_ece_router.py`.
- root_cause: `local-ci` Woodpecker step did not install FastAPI while new API tests depend on it.
- fix: added `fastapi` to `.woodpecker.yml` `local-ci` pip install list.
- symptom: `security-scan` failed due Bandit finding in `src/confidence/ece_scheduler.py`.
- root_cause: use of `assert` in production code (`B101`).
- fix: replaced assert with explicit `RuntimeError` guard.

## Evidence

- `PYTHONPATH=src python3 -m pytest -q tests/test_api/test_ece_router.py` => `27 passed`.
- `bandit -q -r src -s B311,B107` => exit `0` after scheduler guard fix.
- Woodpecker-style local replay:
  - dependency bootstrap + `bandit` + `./scripts/local-ci-checks.sh` => `PASS`
  - pytest summary from replay: `3276 passed, 10 skipped` with coverage gate met.
