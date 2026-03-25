# BOS/CHoCH Validation Remediation - Deferred Backlog Item

**Backlog ID:** BL-BOS-CHOCH-001  
**Related Epic:** EP-ICT-004 (Component Validation)  
**Related Story:** ST-ICT-013 (Validation Framework)  
**Status:** Deferred to Phase 5 (EP-ICT-007)  
**Priority:** P2  
**Created:** 2026-03-25  
**Target Sprint:** ICT-S9 (Weeks 15-18) / EP-ICT-007

---

## Problem Statement

The BOS/CHoCH (Break of Structure / Change of Character) signal detector achieved **15.38% directional accuracy** during EP-ICT-004 validation, falling significantly below the **40% No-Go threshold** and far from the **60% Go threshold**.

This represents a **critical finding** that blocks BOS/CHoCH from Phase 2 integration (EP-ICT-005) but does not block the overall ICT/SMC initiative.

---

## Observed Evidence

### Validation Results (ST-ICT-013)

| Signal        | Accuracy   | Decision     | Threshold Status |
| ------------- | ---------- | ------------ | ---------------- |
| CVD           | 100%       | ✅ GO        | Exceeds 60%      |
| FVG           | 100%       | ✅ GO        | Exceeds 60%      |
| Order Block   | 80.77%     | ✅ GO        | Exceeds 60%      |
| **BOS/CHoCH** | **15.38%** | ❌ **NO-GO** | Below 40%        |

### Test Details

- **Scenarios Tested:** 52 synthetic OHLCV scenarios
- **Tests Passed:** 8/15 (53.3% test pass rate)
- **Directional Accuracy:** 15.38% (8 correct direction predictions out of 52)
- **Bearish Detection Sub-component:** 33.33% (below 40% sub-threshold)
- **Validation Date:** 2026-03-25

---

## Root-Cause Hypotheses

### Hypothesis 1: Test Design Issue (Most Likely)

**Description:** Synthetic OHLCV data may not produce the correct pivot structures required for BOS/CHoCH detection.

**Evidence:**

- BOS/CHoCH detection relies on swing pivot identification
- Synthetic data may lack the necessary price action patterns
- Detector may be working correctly but test data is inappropriate

**Validation Path:** Test with real market data from paper trading

### Hypothesis 2: Algorithm Implementation Gap

**Description:** The BOS/CHoCH classifier + SwingPivotDetector pipeline may have implementation gaps for certain market conditions.

**Evidence:**

- Bearish detection at 33.33% suggests asymmetric performance
- May fail on specific trend patterns (ranging, low volatility)

**Validation Path:** Code review + targeted unit tests

### Hypothesis 3: Integration Issue

**Description:** The pipeline from raw OHLCV → SwingPivotDetector → BOSCHoCHClassifier may have integration issues.

**Evidence:**

- Data format mismatches
- Timing/sequencing issues
- Configuration parameter misalignment

**Validation Path:** End-to-end integration testing

---

## Risk Impact Assessment

### Without Remediation

| Risk                                               | Severity | Impact                         |
| -------------------------------------------------- | -------- | ------------------------------ |
| False BOS/CHoCH signals degrade confluence scoring | Medium   | Reduced signal quality         |
| Capital exposure to incorrect directional bias     | High     | Potential PnL degradation      |
| ML feedback loop contamination                     | Medium   | Model training on wrong labels |

### Risk Mitigation (Current)

- ✅ BOS/CHoCH excluded from EP-ICT-005 (Phase 2 integration)
- ✅ Feature flag ready for future enablement
- ✅ 3/4 ICT signals (CVD, FVG, Order Block) operational
- ✅ Validation framework in place for re-testing

---

## Why Deferred Now

1. **Phase 2 Priority:** EP-ICT-005 integration can proceed with 3 validated signals
2. **Resource Allocation:** Fixing BOS/CHoCH would delay Phase 2 by estimated 2-3 sprints
3. **Risk Acceptable:** With proper feature flagging, BOS/CHoCH can be safely excluded
4. **Better Validation:** Real market data from Phase 3 (EP-ICT-006) will provide better test scenarios
5. **Parallel Track:** Remediation work can proceed in parallel with Phase 2/3/4

---

## Acceptance Criteria for Future Fix

- [ ] BOS/CHoCH directional accuracy >= 60% on real market data (not synthetic)
- [ ] Bearish detection accuracy >= 50% (above No-Go threshold)
- [ ] All 52 validation scenarios pass OR scenarios updated to reflect realistic market conditions
- [ ] Integration tests pass with EP-ICT-005 confluence scorer
- [ ] Feature flag can be safely enabled
- [ ] No regression in CVD, FVG, or Order Block performance

---

## Validation Plan for Re-Test

### Phase A: Real Data Collection (EP-ICT-006)

1. Collect BOS/CHoCH signals from paper trading during Phase 3
2. Capture outcomes for 100+ signals
3. Calculate actual directional accuracy in live markets

### Phase B: Algorithm Review (EP-ICT-007)

1. Code review of BOSCHoCHClassifier + SwingPivotDetector
2. Identify edge cases and failure modes
3. Implement fixes with unit tests

### Phase C: Re-Validation

1. Re-run validation framework with updated scenarios
2. Validate on both synthetic AND real data
3. Confirm >= 60% accuracy before Phase 5 integration

---

## Owner Recommendation

**Primary Owner:** ML/Signal Engineering Team  
**Secondary Owner:** Market Analysis Team (for algorithm expertise)  
**Target Phase:** EP-ICT-007 (Phase 5 - Post-Validation Expansion)  
**Estimated Story Points:** 5 SP (algorithm refinement + re-validation)

---

## Dependencies and Interactions

### Blocks

- None (BOS/CHoCH is excluded from downstream dependencies)

### Blocked By

- EP-ICT-006 completion (need real market data for better validation)
- EP-ICT-007 kickoff (Phase 5 expansion)

### Interacts With

- EP-ICT-005: Must ensure feature flag prevents BOS/CHoCH integration
- ST-ICT-014 through ST-ICT-018: Confluence v2 integration stories must exclude BOS/CHoCH
- EP-ICT-007: Will be primary epic for BOS/CHoCH remediation

### Risk Note for EP-ICT-005

**CRITICAL:** EP-ICT-005 (Confluence v2 Integration) must:

1. Explicitly exclude BOS/CHoCH from signal registration
2. Implement feature flag `ict:bos_choch:enabled` (default: false)
3. Document that BOS/CHoCH is deferred pending Phase 5 remediation
4. Ensure confluence scorer handles missing BOS/CHoCH gracefully

---

## References

- EP-ICT-004 Validation Report: `docs/validation/ict-component-validation-report.md`
- Validation Framework: `tests/validation/ict/test_bos_choch.py`
- Source Code: `src/market_analysis/structure/bos_choch.py`
- Swing Pivot Detector: `src/market_analysis/structure/swing_pivot.py`
- Related Stories: ST-ICT-009 (BOS/CHoCH implementation)

---

## Decision Log

| Date       | Decision                     | Rationale                                                           | Decision Maker |
| ---------- | ---------------------------- | ------------------------------------------------------------------- | -------------- |
| 2026-03-25 | Defer BOS/CHoCH to Phase 5   | 15.38% accuracy below threshold; Phase 2 can proceed with 3 signals | Jarvis/Aria    |
| 2026-03-25 | Document as BL-BOS-CHOCH-001 | Formal backlog tracking for remediation                             | Jarvis         |

---

## Success Criteria for Closure

This backlog item can be closed when:

1. BOS/CHoCH achieves >= 60% directional accuracy on validation
2. Successfully integrated into confluence scorer
3. Feature flag enabled in production
4. No material regression in system performance

---

_Document Version: 1.0_  
_Last Updated: 2026-03-25_
