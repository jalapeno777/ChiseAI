# Backlog: Fix missing test dependencies (redis, qdrant_client)

## Background

CI integration-tests and e2e-tests fail with `ModuleNotFoundError: No module named 'redis'` and `No module named 'qdrant_client'`. These are pre-existing failures NOT introduced by Aria Phase 1 work — they exist in other test modules (e.g., `tests/integration/governance/`, `tests/integration/autonomous_cognition/`) that import redis/qdrant_client at module level without guards.

## Impact

- CI integration-tests step fails (exit 2)
- CI e2e-tests step fails (exit 2)
- Blocks clean CI green on any PR that touches these test directories

## Scope

- Audit all test files that import `redis` or `qdrant_client` without TYPE_CHECKING guards or try/except
- Either: (a) add the deps to the CI test image, or (b) add import guards + mock fallbacks
- Prefer option (a) if the tests genuinely need real Redis/Qdrant, option (b) if they only need mocks
- Ensure `pytest --co` (collect-only) passes on all test directories without live Redis/Qdrant

## Acceptance Criteria

- `pytest --co tests/integration/` succeeds without ModuleNotFoundError
- `pytest --co tests/e2e/` succeeds without ModuleNotFoundError
- CI lint + integration-tests + e2e-tests all pass green on a test PR

## Priority

P2 (non-blocking for Aria Phase 1 but degrades CI signal quality)

## Estimated Size

2-3SP

## Discovery References

- PR #890 CI triage: `rc-001` (redis ModuleNotFoundError), `rc-002` (qdrant_client ModuleNotFoundError)
- Affected test dirs: `tests/integration/governance/`, `tests/integration/autonomous_cognition/`
