# PAPER-LLM-DIAG-001 Fix Summary

**Date**: 2026-03-06
**Story ID**: PAPER-LLM-DIAG-001
**Status**: FIXED

## Root Cause
From BATCH 2 testing:
1. USE_LLM_TRADE_DECISIONS works when explicitly enabled
2. Unit tests all pass (55/55 for trade decision enhancer, 45/45 for provider chain)
3. Provider chain fallback works (Kimi → Zai → Zhipu)
4. Chain initialization showed: "Chain not initialized but enabled" - this was due to MiniMax provider issues causing initialization failures

## Changes Made

### 1. MiniMax Temporary Disablement
**File**: `src/llm/provider_chain.py`
**Change**: Removed MiniMax from DEFAULT_PROVIDER_ORDER
**Lines**: 268-279

```python
# TEMPORARY: MiniMax disabled due to PAPER-LLM-DIAG-001
# To re-enable: Add "minimax" back to the list
# Re-enable checklist:
# 1. Verify MINIMAX_API_KEY is configured
# 2. Set MINIMAX_ENABLED=true
# 3. Test with: python -m pytest tests/test_llm/test_provider_chain.py -v -k minimax
# 4. Monitor burn-in metrics for MiniMax success rate
self.provider_order = provider_order or [
    "kimi_compat",
    "kimi",
    "zai",
    "zhipu",
    # "minimax",  # Disabled per PAPER-LLM-DIAG-001
]
```

**Impact**: 
- MiniMax no longer included in provider chain
- Reduces provider order from 5 to 4 providers
- Chain initialization is more reliable

### 2. Debug Logging Added to Orchestrator
**File**: `src/execution/paper/orchestrator.py`
**Changes**: Added debug logging to show LLM enhancer status
**Lines**: 392-396, 399-402

```python
# Debug logging for LLM enhancer status
logger.debug(
    f"LLM enhancer status: enabled={self.decision_enhancer.enabled if self.decision_enhancer else False}, "
    f"chain_initialized={self.decision_enhancer._chain is not None if self.decision_enhancer else False}"
)

if self.decision_enhancer and self.decision_enhancer.enabled:
    logger.info(
        f"Calling LLM enhancer for signal {signal.token} - "
        f"chain_ready={self.decision_enhancer._chain is not None}"
    )
```

**Impact**: 
- Better visibility into LLM enhancer state
- Helps diagnose initialization issues
- Shows when LLM decision is being called

### 3. Enhanced Logging in TradeDecisionEnhancer
**File**: `src/execution/llm/trade_decision_enhancer.py`
**Changes**: 
1. Improved chain initialization logging (lines 78-93)
2. Added debug logging in enhance_decision (lines 105-111)

```python
# In _init_chain
self._chain = LLMProviderChain(enable_metrics=True)
logger.info(
    f"TradeDecisionEnhancer: LLM provider chain initialized successfully "
    f"(providers: {self._chain.provider_order})"
)

# In enhance_decision
logger.debug(
    f"enhance_decision called: enabled={self.enabled}, chain={self._chain is not None}"
)

if not self.enabled or self._chain is None:
    logger.info(
        f"LLM enhancement skipped: enabled={self.enabled}, chain_available={self._chain is not None}"
    )
```

**Impact**: 
- Shows which providers are in the chain
- Logs when enhancement is skipped
- Better observability for debugging

### 4. Test Updates
**File**: `tests/test_llm/test_provider_chain.py`
**Changes**: Updated 3 tests to reflect MiniMax disablement
**Lines**: 145-158, 545-576

```python
# test_default_provider_order
assert chain.provider_order == [
    "kimi_compat",
    "kimi",
    "zai",
    "zhipu",
    # "minimax",  # Disabled per PAPER-LLM-DIAG-001
]

# test_get_provider_status_all_available
assert "minimax" not in chain.provider_order

# test_get_provider_status_with_reasons
assert "minimax" not in status
```

**Impact**: 
- Tests now reflect the new provider order
- All 45 provider chain tests pass
- All 55 trade decision enhancer tests pass

## Test Results

### Provider Chain Tests
```bash
$ PYTHONPATH=/home/tacopants/projects/ChiseAI pytest tests/test_llm/test_provider_chain.py -v
============================= 45 passed in 1.57s ====================
```

### Trade Decision Enhancer Tests
```bash
$ PYTHONPATH=/home/tacopants/projects/ChiseAI pytest tests/execution/test_llm/test_trade_decision_enhancer.py -v
============================= 55 passed in 1.83s ====================
```

### Live Validation
```bash
$ python3 scripts/validate_llm_fix.py
================================================================================
VALIDATION: LLM Enhancer with MiniMax Disabled
================================================================================

[TEST 1] Creating enhancer with enabled=True...
✓ Enhancer enabled: True
✓ Chain initialized: True
✓ Provider order: ['kimi_compat', 'kimi', 'zai', 'zhipu']
✓ MiniMax in provider_order: False

✓ Provider status:
  - kimi_compat: available=False
  - kimi: available=True
  - zai: available=True
  - zhipu: available=True

✓ Health check: {'enabled': True, 'chain_initialized': True, 'provider_chain_available': True, 'timeout_ms': 60000}

✓ VERIFIED: MiniMax is excluded from provider_order

[TEST 2] Creating enhancer with enabled=False...
✓ Enhancer enabled: False
✓ Chain initialized: False
✓ Returns safe default when disabled

================================================================================
ALL VALIDATIONS PASSED
================================================================================
```

## Files Changed

1. **src/llm/provider_chain.py** - MiniMax disablement with re-enable instructions
2. **src/execution/paper/orchestrator.py** - Debug logging for LLM enhancer status
3. **src/execution/llm/trade_decision_enhancer.py** - Enhanced chain initialization logging
4. **tests/test_llm/test_provider_chain.py** - Updated tests for MiniMax disablement
5. **scripts/validate_llm_fix.py** - Validation script (NEW)
6. **docs/fixes/PAPER-LLM-DIAG-001-fix-summary.md** - This summary document (NEW)

## MiniMax Re-Enable Instructions

To re-enable MiniMax provider:

### Step 1: Edit provider_chain.py
```python
# In src/llm/provider_chain.py, line 268-279
self.provider_order = provider_order or [
    "kimi_compat",
    "kimi",
    "zai",
    "zhipu",
    "minimax",  # Re-enable by uncommenting this line
]
```

### Step 2: Set Environment Variable
```bash
export MINIMAX_ENABLED=true
export MINIMAX_API_KEY=<your-api-key>
```

### Step 3: Run Tests
```bash
# Run MiniMax-specific tests
pytest tests/test_llm/test_provider_chain.py -v -k minimax

# Run all provider chain tests
pytest tests/test_llm/test_provider_chain.py -v

# Run trade decision enhancer tests
pytest tests/execution/test_llm/test_trade_decision_enhancer.py -v
```

### Step 4: Monitor Burn-in Metrics
```bash
# Check provider metrics in InfluxDB
# Look for:
# - minimax.success_rate
# - minimax.avg_latency_ms
# - minimax.error_rate
# - fallback_rate (should decrease if MiniMax is stable)
```

### Step 5: Update Tests
```python
# In tests/test_llm/test_provider_chain.py
# Revert the changes to:
# - test_default_provider_order (add "minimax" back)
# - test_get_provider_status_all_available (check for minimax)
# - test_get_provider_status_with_reasons (check for minimax)
```

## Validation Commands Run
```bash
# Unit tests
pytest tests/test_llm/test_provider_chain.py -v
pytest tests/execution/test_llm/test_trade_decision_enhancer.py -v

# Live validation
python3 scripts/validate_llm_fix.py

# With USE_LLM_TRADE_DECISIONS=true
USE_LLM_TRADE_DECISIONS=true python3 scripts/validate_llm_fix.py
```

## Next Steps
1. **Monitor**: Watch paper trading logs for LLM enhancer status messages
2. **Validate**: Run live paper trading session with USE_LLM_TRADE_DECISIONS=true
3. **Metrics**: Check InfluxDB for provider success rates and latency
4. **MiniMax**: When ready to re-enable, follow the re-enable checklist above
5. **Cleanup**: Remove this fix summary once MiniMax is re-enabled and stable

## Related Issues
- PAPER-LLM-DIAG-001: Initial diagnosis of LLM chain not initializing
- PAPER-EXEC-001: LLM-enhanced trade decisions with fallback

## Constraints Applied
- **No global-lock files modified**: Only touched src/llm/, src/execution/llm/, src/execution/paper/, tests/
- **Worker contracts**: All changes within SCOPE_GLOBS
- **Ownership**: PAPER-LLM-DIAG-001/dev confirmed before edits
- **Memory context**: Applied chiseai-git-workflow and chiseai-memory-ops skills
