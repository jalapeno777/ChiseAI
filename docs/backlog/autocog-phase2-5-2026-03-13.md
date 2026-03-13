# AutoCog Phase 2-5 Backlog (2026-03-13)

## Goal
Complete the remaining autonomous cognition phases:
- Phase 2 belief graph + contradiction resolution
- Phase 3 strategy/portfolio improvement loop
- Phase 4 neuro-symbolic runtime integration
- Phase 5 autonomy tuning + constitution audit

## Delivered
1. `AUTOCOG-201` Belief system
- Added belief models, store, consistency checker, revision engine, and explanations.
- Contradictions and revisions are detectable and traceable.

2. `AUTOCOG-301` Improvement engine
- Added hypothesis generator, portfolio policy lab, and champion-challenger evaluator.
- Promotions and rejections are gated and eventable.

3. `AUTOCOG-401` Runtime integration
- Added neuro-symbolic runtime integration wrapper with shadow-mode safe fallback and divergence metrics.

4. `AUTOCOG-501` Governance tuning
- Added autonomy tuner and automated constitution audit engine.

5. `AUTOCOG-599` End-to-end orchestration
- Added full-cycle orchestrator (`src/autonomous_cognition/full_cycle.py`).
- Added operational runner script (`scripts/ops/run_autonomous_full_cycle.py`).
- Added E2E coverage and registry jobs for autonomous cadence.

## Technical Debt - Scheduled Maintenance

### Item: Datetime Deprecation Warnings Cleanup
- **Added:** 2026-03-13
- **Severity:** Low
- **Due Date:** 2026-03-27
- **Owner:** engineering
- **Action ID:** AA-20260313-002

**Description:**
Approximately 20 deprecation warnings related to `datetime.utcnow()` usage detected during autonomous cognition daily run regression tests. These warnings indicate use of deprecated APIs that may become errors in future Python versions.

**Impact:**
- No current functional impact (all 12 tests pass)
- Future Python compatibility risk
- Warning noise in test output

**Resolution:**
Replace deprecated `datetime.utcnow()` with `datetime.now(datetime.UTC)` or equivalent modern patterns across the codebase.

**Evidence:**
- Run ID: `autocog-20260313-144824-c95f4f`
- Test output shows: "DeprecationWarning: datetime.datetime.utcnow() is deprecated"
- Location: Various files in autonomous_cognition module and potentially others

**Command to find occurrences:**
```bash
grep -r "datetime.utcnow" --include="*.py" . 2>/dev/null
```

