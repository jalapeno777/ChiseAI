---
story_id: SAFETY-RESCUE-001
story_title: CI Failure Incident Report
phase: implementation
status: completed
started_at: 2026-02-13T17:20:00Z
agent: dev
type: ci_failure
description: CI failing due to pre-existing lint errors in test files outside scope
---

# Incident Report: CI Failure on PR #75

## Summary
- **Task**: Push test fixes and merge PR #75
- **Scope**: `tests/grafana/test_dashboards.py`, `tests/test_signal_generation/test_signal_emitter.py`
- **Test Results**: ✅ All 4 target tests passing, 46/46 tests in modified files passing
- **CI Status**: ❌ Failed due to pre-existing lint errors in other test files

## Evidence

### Tests Passing (Local)
```
tests/grafana/test_dashboards.py::TestDashboardSchema::test_backtest_kpis_queries_use_correct_measurement PASSED
tests/grafana/test_dashboards.py::TestDashboardSchema::test_backtest_kpis_handles_all_strategy_selection PASSED
tests/test_signal_generation/test_signal_emitter.py::TestDiscordEmitter::test_bypass_confidence_filter_param PASSED
tests/test_signal_generation/test_signal_emitter.py::TestDiscordEmitter::test_bypass_confidence_filter_env_var PASSED
```

### Lint Status
- **Modified files**: No critical lint errors (E501 line too long in test strings is acceptable)
- **Other test files**: Multiple pre-existing lint errors (F401 unused imports, I001 import sorting, etc.)

### CI Failure Root Cause
The CI pipeline is failing on:
1. `ci_gate`: captured step failed - lint.status=1
2. Pre-existing lint errors in files NOT modified by this PR:
   - `tests/grafana/test_optimizer.py`
   - `tests/test_backtest_runner.py`
   - `tests/test_backtesting/test_dsl/*.py`
   - And many others

## Blocker
Cannot merge PR #75 because CI requires all checks to pass, but lint errors exist in test files outside the scope of this task.

## Options
1. **Fix all lint errors in tests/** (expands scope significantly)
2. **Request human override** to merge despite lint failures in unrelated files
3. **Update CI configuration** to exclude tests/ from lint checks (not recommended)

## Recommendation
Given that:
- The 4 specific failing tests mentioned in the task are now passing
- The test fixes are correct and verified
- Lint errors are pre-existing in files outside the task scope

Request human approval to merge PR #75 with the understanding that a separate cleanup task should address the test file lint errors.
