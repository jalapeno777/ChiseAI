# LINK Signal Burn-in Test and Checkpoint Gate Audit Report

**Story ID:** LINK-BURNIN-001  
**Agent:** senior-dev  
**Date:** 2026-03-10  
**Branch:** feature/LINK-BURNIN-001-signal-validation

---

## Executive Summary

Successfully diagnosed and fixed the missing LINK signal issue. LINK signals are now being generated and stored in Redis alongside BTC, ETH, SOL, and BNB.

---

## Initial Baseline (Before Burn-in)

| Token | Signal Count |
|-------|--------------|
| BTC   | 8 signals    |
| ETH   | 8 signals    |
| SOL   | 8 signals    |
| **LINK** | **0 signals** ⚠️ |
| BNB   | 8 signals    |

**Total paper signals:** 32

---

## Burn-in Execution

**Duration:** 10 minutes  
**Interval:** 30 seconds  
**Command:** `python3 scripts/continuous_signal_generator.py --duration 10 --interval 30`

### Burn-in Results (Initial - Before Fix)

During the initial burn-in, LINK signals were consistently blocked with the error:
```
WARNING - Signal generation blocked: stale data for LINK/USDT 1h
```

All other tokens (BTC, ETH, SOL, BNB) generated signals normally.

---

## Root Cause Analysis

### Problem
The `create_mock_ohlcv()` function in `scripts/continuous_signal_generator.py` was creating mock OHLCV data with fixed price offsets:
- `open_price = price - 50`
- `low_price = price - 100`

For LINK with a base price of $15.0, this resulted in negative prices:
- `open_price = 15 - 50 = -35` ❌
- `low_price = 15 - 100 = -85` ❌

The data validator rejected these invalid prices, causing the signal to be marked as STALE_DATA.

### Why Other Tokens Worked

| Token | Base Price | Low Price | Open Price | Valid? |
|-------|------------|-----------|------------|--------|
| BTC   | $50,000    | $49,900   | $49,950    | ✅     |
| ETH   | $3,000     | $2,900    | $2,950     | ✅     |
| SOL   | $150       | $50       | $100       | ✅     |
| **LINK** | **$15**  | **-$85**  | **-$35**   | ❌     |
| BNB   | $600       | $500      | $550       | ✅     |

---

## Fix Applied

**File:** `scripts/continuous_signal_generator.py`  
**Function:** `create_mock_ohlcv()`

### Change
Modified the price offset calculation to be proportional to the base price, ensuring no negative prices:

```python
# Calculate safe offset to avoid negative prices for low-value tokens like LINK
# Ensure low_price (price - 100) is always positive
price_offset = min(50, base_price * 0.1)  # Use 10% of base price or 50, whichever is smaller
low_offset = min(100, base_price * 0.2)   # Use 20% of base price or 100, whichever is smaller

# In the data loop:
open_price=max(0.01, price - price_offset),
low_price=max(0.01, price - low_offset),
```

### Rationale
- **Non-destructive:** Only affects mock data generation, not production signal logic
- **Proportional:** Offsets scale with token price to maintain realistic OHLCV relationships
- **Safe:** `max(0.01, ...)` ensures prices are always positive

---

## Verification After Fix

### Quick Burn-in Test (2 minutes)

LINK signals now generated successfully:
```
INFO - Actionable signal: LINK/USDT [LONG] confidence=86.0%
INFO - Signal stored: paper:signal:20260311031302:LINK/USDT:9409fdbd-2d5c-46e1-8e5b-a3e74f04b0e0
```

### Final Signal Counts

| Token | Signal Count | Change |
|-------|--------------|--------|
| BTC   | 56 signals   | +48    |
| ETH   | 56 signals   | +48    |
| SOL   | 56 signals   | +48    |
| **LINK** | **8 signals** | **+8** ✅ |
| BNB   | 56 signals   | +48    |

**Total paper signals:** 232 (+200 since start)

---

## Checkpoint Gate Audit G1-G8

| Gate | Status | Detail |
|------|--------|--------|
| **G1** | ✅ PASS | Heartbeat 6s ago |
| **G2** | ✅ PASS | 232 paper signals in Redis |
| **G3** | ✅ PASS | 3 outcomes recorded |
| **G4** | ✅ PASS | Armed and ready (enabled=1, triggered=0) |
| **G5** | ⚠️ CHECK | Cron evidence module not available in this context |
| **G6** | ✅ PASS | Bybit API reachable |
| **G7** | ✅ PASS | Redis OK, 1640 keys, 324h uptime |
| **G8** | ✅ PASS | Burn-in verdict: GO |

### G4 (Kill Switch) Details
- **Status:** Armed and ready ✅
- **enabled:** 1
- **triggered:** 0

### G5 (Cron Cadence) Details
- **Status:** CHECK ⚠️
- **Note:** Cron evidence module requires additional dependencies not available in this execution context. Manual verification recommended.

---

## Files Changed

| File | Change Type | Lines |
|------|-------------|-------|
| `scripts/continuous_signal_generator.py` | Modified | +8/-4 |

---

## Evidence

### Redis LINK Signal Keys
```
paper:signal:20260311031426:LINK/USDT:622d1266-4ae4-4c29-8b63-9d3f1ea3d164
paper:signal:20260311031302:LINK/USDT:9409fdbd-2d5c-46e1-8e5b-a3e74f04b0e0
paper:signal:20260311031358:LINK/USDT:51b4dc24-863e-45d5-87fa-ecf88b1fbe23
paper:signal:20260311031330:LINK/USDT:f831fef6-2dc2-475b-9640-fae1b864cfea
paper:signal:20260311031426:LINK/USDT:ee832698-5549-4cbf-bcae-94a46a6dbec4
...
```

### Burn-in Log Excerpt
See: `/tmp/worktrees/LINK-BURNIN-001-senior-dev/burnin_output.log`

---

## Conclusion

✅ **LINK signals are now being generated and stored correctly**  
✅ **All 5 configured tokens (BTC, ETH, SOL, LINK, BNB) have signals in Redis**  
✅ **Checkpoint gates G1-G8 show healthy system status**  
✅ **G4 (Kill Switch) is armed and ready**  
⚠️ **G5 (Cron Cadence) requires manual verification**

---

## Recommendations

1. **Monitor LINK signals** over the next few hours to ensure continued generation
2. **Verify G5 cron cadence** manually or in a context with the cron_evidence module
3. **Consider adding data validation warnings** to the signal generator logs to make similar issues more visible in the future
