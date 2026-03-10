# ST-KPI-FIX-001 Final Evaluation Report

**Story ID:** ST-KPI-FIX-001
**Evaluation Date:** 2026-03-10
**Generated:** 2026-03-10T21:30:00+00:00

---

## Executive Summary

This report presents the final evaluation of KPI source separation implementation for ST-KPI-FIX-001. Both Bybit Truth KPI and Paper Simulation KPI calculators have been implemented and validated.

### GO/HOLD Decision: **HOLD**

**Rationale:**
- Bybit Truth KPI shows **0% win rate** (0/4 closed positions profitable) - below 55% target
- Data freshness **55.84 hours** - exceeds 24-hour target
- All 4 closed positions were **net negative** (-$8.41 total)
- Fee impact of 17.21% indicates execution cost awareness needed
- Total trades: **27** (matches live reconciliation)
- Win rate 0% indicates poor strategy performance

---

## KPI Source Comparison

| Source | Type | Canonical for GO | Trades | Win Rate | Net PnL | Max DD | Status |
|--------|------|------------------|--------|----------|---------|--------|--------|
| `bybit_truth` | Bybit API | ✅ Yes | 27 | 0% | -$8.41 | 0% | ❌ All Losses |
| `paper_journal_sim` | Simulation | ❌ No | 33 | 36% | +$100.85 | 4.02% | ⚠️ Below Target |

---

## Bybit Truth KPI (Canonical Source)

**File:** `docs/validation/evidence/ST-KPI-FIX-001-BYBIT-TRUTH-KPI-20260310.json`

### Data Quality
- **Status:** ✅ PASS - Data available from Bybit API
- **Freshness:** 55.84 hours
- **Trading Mode:** Demo
- **Total Trades:** 27
- **Data Range:** 2026-03-05 to 2026-03-10 (5 trading days)

### Target Assessment
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Win Rate | 0% | > 55% | ❌ FAIL |
| Max Drawdown | 0% | < 5% | ✅ PASS |
| Data Freshness | 55.84 hrs | < 24 hrs | ❌ FAIL |
| Risk Gate Adherence | 100% | > 95% | ✅ PASS |

**Overall:** 2/4 targets passed

### Performance Breakdown
| Metric | Value |
|--------|-------|
| Total Trades | 27 |
| Winning Trades | 0 |
| Losing Trades | 4 |
| Open Trades | 0 |
| Total Net PnL | -$8.41 |
| Total Gross PnL | -$7.18 |
| Total Fees | $1.24 |
| Fee Impact | 17.21% |
| Average PnL/Trade | -$0.31 |

### Turnover
- **Average:** 5.40 trades/day
- **P95:** 8.60 trades/day
- **Maximum:** 9.00 trades/day
- **Daily Counts:** 2026-03-10: 4, 2026-03-08: 3, 2026-03-07: 4, 2026-03-06: 9, 2026-03-05: 7

### Data Quality Flags
- ⚠️ Data stale (55.84 hours > 24-hour target)
- ⚠️ All 4 closed positions were net negative

---

## Paper Simulation KPI

**File:** `docs/validation/evidence/ST-KPI-FIX-001-KPI-SNAPSHOT-20260310.json`

### Performance Metrics
- **Total Trades:** 33
- **Winning Trades:** 9
- **Losing Trades:** 11
- **Open Trades:** 8
- **Data Range:** 2026-03-04 to 2026-03-10 (5 trading days)

### Key Performance Indicators
| KPI | Value | Target | Status |
|-----|-------|--------|--------|
| Win Rate | 36.00% | > 55% | ❌ FAIL |
| Max Drawdown | 4.02% | < 5% | ✅ PASS |
| Risk Gate Adherence | 100% | > 95% | ✅ PASS |
| Total Net PnL | 100.85 | - | - |
| Avg PnL/Trade | 4.03 | - | - |

### Turnover
- **Average:** 6.60 trades/day
- **P95:** 12.40 trades/day
- **Maximum:** 13 trades/day

### Latency Statistics
| Percentile | Latency (ms) |
|------------|--------------|
| P50 | 4.86 |
| P95 | 8.73 |
| P99 | 46.47 |

### Data Quality
- **Freshness:** 1.78 hours ✅
- **Net PnL Validation:** Passed ✅
- **Quality Flags:** None ✅

**Overall:** 3/4 targets passed

---

## Test Results

### Test Execution Summary

| Test Suite | Tests | Passed | Failed | Status |
|------------|-------|--------|--------|--------|
| `test_bybit_kpi_validation.py` | 24 | 24 | 0 | ✅ PASS |
| `test_kpi_source_separation.py` | 22 | 22 | 0 | ✅ PASS |
| **Total** | **46** | **46** | **0** | **✅ PASS** |

### Test Coverage

#### Bybit KPI Validation Tests (24 tests)
- ✅ Bybit KPI uses actual execution data
- ✅ Net PnL formula validation (closed_pnl - fees)
- ✅ Source label is 'bybit_truth'
- ✅ Paper KPI labeled as non-canonical
- ✅ Warning headers exist for simulation data
- ✅ Negative PnL handling
- ✅ All required fields present
- ✅ Source labels are explicit
- ✅ Turnover calculation
- ✅ Data quality validation
- ✅ Module imports
- ✅ Trading mode detection

#### KPI Source Separation Tests (22 tests)
- ✅ Simultaneous KPI generation
- ✅ No cross-contamination between sources
- ✅ Source labels are distinct
- ✅ Output file labeling
- ✅ Canonical for GO flag behavior
- ✅ Trading mode field behavior
- ✅ Data quality flags
- ✅ Output file separation

---

## Artifacts Generated

### JSON Artifacts
1. `docs/validation/evidence/ST-KPI-FIX-001-BYBIT-TRUTH-KPI-20260310.json`
2. `docs/validation/evidence/ST-KPI-FIX-001-KPI-SNAPSHOT-20260310.json`

### Markdown Reports
1. `docs/validation/evidence/ST-KPI-FIX-001-BYBIT-TRUTH-REPORT-20260310.md`
2. `docs/validation/evidence/ST-KPI-FIX-001-KPI-REPORT-20260310.md`
3. `docs/validation/evidence/ST-KPI-FIX-001-KPI-COMPARISON-20260310.md`
4. `docs/validation/evidence/ST-KPI-FIX-001-FINAL-EVALUATION.md` (this file)

---

## Decision Rationale

### Why HOLD?

1. **Poor Performance Below Thresholds:**
   - Bybit Truth KPI: 0% win rate (target > 55%)
   - Data stale: 55.84 hours (target < 24 hours)
   - All 4 closed positions net negative (-$8.41 total)

2. **All Closed Positions Net Negative:**
   - Bybit Truth shows 0 winning trades out of 4 closed positions
   - Gross PnL: -$7.18 (all losing)
   - Fees: $1.24 (execution costs)
   - Net PnL: -$8.41 after fees
   - Fee impact: 17.21% of gross PnL

3. **Insufficient Trading History:**
   - Only 4 closed positions available for evaluation
   - 27 total trades, but 23 are still open
   - 5 trading days of data available
   - More data needed to validate strategy performance

### Required for GO

To achieve GO status, the following must be met:

1. **Performance Thresholds Met:**
   - Win Rate > 55%
   - Max Drawdown < 5%
   - Risk Gate Adherence > 95%
   - Data Freshness < 24 hours

2. **Trading History Accumulated:**
   - At least 20+ closed positions
   - Consistent positive PnL over time
   - Win rate above threshold

3. **All Tests Passing:**
   - All validation tests pass ✅ (already achieved)

---

## Answer to User's Question

### User Question: "Are all trades net negative?"

**Answer: ✅ YES - All 4 closed positions were net negative**

**Detailed Breakdown:**
- **Total Trades:** 27
- **Winning Trades:** 0
- **Losing Trades:** 4
- **Open Trades:** 23

**Performance by Closed Position:**
- **Gross PnL (before fees):** -$7.18 (all negative)
- **Total Fees Paid:** $1.24
- **Net PnL (after fees):** -$8.41

**Fee Impact:**
- 17.21% of gross PnL represents trading costs
- This indicates the strategy is vulnerable to execution costs

**Conclusion:** The Bybit Truth KPI confirms that all closed positions resulted in net losses. This is a critical finding for strategy validation.

---

## Recommendations

### Immediate Actions

1. **Strategy Improvement Required:**
   - Win rate of 0% indicates the current strategy needs significant refinement
   - Consider analyzing which positions were most profitable
   - Review entry/exit criteria and risk management rules

2. **Generate More Trading Data:**
   - Allow paper trading to run for additional days to accumulate more closed positions
   - Execute test trades on Bybit demo account to get real-world validation
   - Aim for at least 20+ closed positions for reliable KPI assessment

3. **Monitor Data Freshness:**
   - Current data is 55.84 hours stale
   - Implement automatic re-evaluation when data exceeds 24 hours
   - Set up monitoring alerts for stale data

### Next Steps

1. Refine trading strategy to improve win rate
2. Allow paper trading to accumulate more closed positions (aim for 20+)
3. Configure Bybit API credentials for live/demo trading
4. Run additional KPI evaluations as more data becomes available
5. Reassess GO/HOLD decision based on improved performance metrics

---

## Implementation Status

### Completed ✅

- [x] Bybit Truth KPI calculator implemented
- [x] Paper Simulation KPI calculator implemented
- [x] Unified KPI evaluation runner implemented
- [x] Source separation validation tests (46 tests)
- [x] JSON artifact generation
- [x] Markdown report generation
- [x] Target assessment logic
- [x] Data quality validation
- [x] Turnover calculation
- [x] Latency statistics
- [x] Data freshness tracking

### Pending ⏳

- [ ] Strategy improvement to increase win rate above 55%
- [ ] Accumulate more closed positions (aim for 20+)
- [ ] Reduce data staleness below 24 hours
- [ ] Generate consistent positive PnL

---

## Technical Notes

### Data Source Separation

The implementation correctly separates data sources:

- **Bybit Truth (`bybit_truth`):**
  - Source: Bybit V5 API (`/v5/execution/list`, `/v5/position/closed-pnl`)
  - Canonical for GO: ✅ Yes
  - Trading Mode: demo/live
  - Uses actual execution data from Bybit

- **Paper Journal (`paper_journal_sim`):**
  - Source: Redis paper trading journal
  - Canonical for GO: ❌ No
  - Trading Mode: paper
  - Uses simulation data

### Net PnL Formula

Both calculators correctly implement:
```
net_pnl = closed_pnl - fees
```

This ensures accurate PnL calculation with fee deduction.

### Turnover Calculation

Turnover is calculated as trades per day, aggregated by UTC calendar day:
```
turnover = {
    "avg_trades_per_day": sum(daily_counts) / num_days,
    "p95_trades_per_day": percentile(daily_counts, 95),
    "max_trades_per_day": max(daily_counts),
    "daily_counts": {date: count, ...}
}
```

---

## Conclusion

The KPI source separation implementation is **complete and validated**. All 46 tests pass, and the calculators correctly generate artifacts with proper source labeling.

However, the **GO/HOLD decision is HOLD** due to:
1. **Critical performance issues:** 0% win rate on Bybit Truth KPI
2. **Data staleness:** 55.84 hours exceeds 24-hour target
3. **All closed positions net negative:** -$8.41 total loss across 4 positions

**Next Action:** Improve strategy performance and accumulate more trading data before re-evaluation.

---

*Report generated by: scripts/analysis/run_kpi_evaluation.py*
*Evaluation completed: 2026-03-10T21:30:00+00:00*
