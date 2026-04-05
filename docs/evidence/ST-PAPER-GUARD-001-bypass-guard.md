# ST-PAPER-GUARD-001: Burn-in Bypass Guard - Evidence

## Summary

Successfully audited and guarded burn-in bypass behaviors. The burn-in testing bypass in `orchestrator.py` is now gated behind `POC_MODE=true` instead of the generic `ENABLE_BURN_IN_TESTING` flag.

## Audit Findings

### 1. Burn-in Bypass Flag Location

- **File**: `src/execution/paper/orchestrator.py`
- **Lines**: 755-763
- **Previous behavior**: Position time-based close (burn-in) was controlled by `ENABLE_BURN_IN_TESTING` env var
- **Issue**: `ENABLE_BURN_IN_TESTING` is a generic test flag that could be accidentally enabled in production

### 2. Change Applied

- **Before**: `os.getenv("ENABLE_BURN_IN_TESTING", "false").lower() == "true"`
- **After**: `os.getenv("POC_MODE", "false").lower() == "true"`
- **Impact**: Only `POC_MODE=true` allows the burn-in bypass; production (POC_MODE=false or unset) blocks the bypass

## Tests Added/Modified

### Modified: `test_time_based_position_close`

- Updated to set `POC_MODE=true` before testing burn-in bypass
- Verifies that when `POC_MODE=true` and position > 60s old, `close_position` is called

### Added: `test_time_based_position_close_blocked_when_poc_mode_disabled`

- Verifies that when `POC_MODE=false`, burn-in bypass is BLOCKED
- `close_position` is NOT called for old positions when POC_MODE is disabled

### Added: `test_burn_in_bypass_unreachable_when_poc_mode_unset`

- Verifies that when `POC_MODE` is not set (default), burn-in bypass is BLOCKED
- `close_position` is NOT called for old positions when POC_MODE is unset

## Test Results

```
tests/test_execution/test_paper/test_orchestrator.py::TestPositionManagement::test_time_based_position_close PASSED
tests/test_execution/test_paper/test_orchestrator.py::TestPositionManagement::test_time_based_position_close_blocked_when_poc_mode_disabled PASSED
tests/test_execution/test_paper/test_orchestrator.py::TestPositionManagement::test_burn_in_bypass_unreachable_when_poc_mode_unset PASSED
```

## Acceptance Criteria Evidence

| Criterion                                                     | Status  | Evidence                                            |
| ------------------------------------------------------------- | ------- | --------------------------------------------------- |
| 1. Audit burn-in/test bypass flags                            | ✅ DONE | Found `ENABLE_BURN_IN_TESTING` in orchestrator.py   |
| 2. Remove bypass OR gate behind POC_MODE                      | ✅ DONE | Changed from `ENABLE_BURN_IN_TESTING` to `POC_MODE` |
| 3. Production config must not expose test bypass              | ✅ DONE | `POC_MODE` is the canonical production test mode    |
| 4. Add tests proving bypasses unreachable when POC_MODE=false | ✅ DONE | 3 new/modified tests passing                        |

## Files Changed

- `src/execution/paper/orchestrator.py` - Changed bypass gate from ENABLE_BURN_IN_TESTING to POC_MODE
- `tests/test_execution/test_paper/test_orchestrator.py` - Added/modified tests for burn-in bypass

## Conclusion

Burn-in bypass is now GUARDED behind `POC_MODE=true`. When `POC_MODE=false` or unset (production default), the burn-in bypass is unreachable. This ensures POC_MODE is the ONLY way to enable burn-in testing behavior.
