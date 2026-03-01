# Brain CI/CD KPI Table - BRAIN-CICD-2026-03-01-RERUN

**Story ID:** BRAIN-CICD-2026-03-01-RERUN  
**Generated:** 2026-03-01  
**Status:** NO CHANGE (Primary KPIs unmeasurable)  

## KPI Status Overview

| KPI | Value | Type | Measurable | Notes |
|-----|-------|------|------------|-------|
| **paper_carryover_rate** | 0.0 | 🔴 PLACEHOLDER | ❌ NO | No paper trading history |
| **false_positive_rate** | 0.0 | 🔴 PLACEHOLDER | ❌ NO | Requires backtest/paper comparison |
| **time_to_improvement** | 0.0 | 🔴 PLACEHOLDER | ❌ NO | No experiment tracking data |
| **safety_compliance** | 1.0 | 🟢 MEASURED | ✅ YES | Default - no violations |

## Detailed KPI Analysis

### 1. paper_carryover_rate (PRIMARY KPI)

**Current Value:** 0.0 (placeholder)  
**Target:** > 0.40 (40% of backtest winners carry over to paper)  
**Status:** 🔴 CANNOT MEASURE  

**Why It's a Placeholder:**
- No paper trading has been conducted
- No correlation data between backtest and paper results
- Requires at least 30 days of paper trading data for statistical significance

**What Would Be Needed:**
1. Implement paper trading mode
2. Run strategies in paper mode for 30+ days
3. Compare backtest winners vs paper winners
4. Calculate: `paper_winners / backtest_winners`

**Decision Impact:**
- Cannot evaluate if vNext improves carryover
- Cannot validate if brain changes improve real-world performance
- DEFAULT TO NO CHANGE per decision policy

---

### 2. false_positive_rate

**Current Value:** 0.0 (placeholder)  
**Target:** < 0.30 (30% of backtest wins fail in paper)  
**Status:** 🔴 CANNOT MEASURE  

**Why It's a Placeholder:**
- Requires comparison between backtest and paper results
- No historical data on strategies that passed backtest but failed paper

**What Would Be Needed:**
1. Track all strategies that pass backtest gates
2. Run each in paper trading mode
3. Record which ones fail paper validation
4. Calculate: `failed_paper / total_backtest_passes`

**Decision Impact:**
- Cannot measure if brain reduces false positives
- Cannot validate improved filtering logic

---

### 3. time_to_improvement

**Current Value:** 0.0 (placeholder)  
**Target:** < 10 experiments per champion beat  
**Status:** 🔴 CANNOT MEASURE  

**Why It's a Placeholder:**
- No experiment tracking infrastructure in place
- No historical record of experiments per improvement cycle
- vNext-B proposes this tracking but hasn't been implemented

**What Would Be Needed:**
1. Implement experiment tracking in Redis iterlog
2. Track experiment count per improvement cycle
3. Record when champion is beaten
4. Calculate: `experiments_since_last_champion_beat`

**Decision Impact:**
- Cannot measure R&D efficiency
- Cannot validate if vNext-B improves experimentation

---

### 4. safety_compliance

**Current Value:** 1.0 (measured)  
**Target:** = 1.0 (100% compliance)  
**Status:** 🟢 MEASURABLE  

**Why It's Measured:**
- Binary metric: either compliant or not
- No violations detected in current cycle
- Default to 1.0 when no violations found

**How It's Calculated:**
- Check for risk cap violations: 0 found
- Check for live trading modifications: 0 found
- Check for promotion gate changes: 0 found
- Result: 1.0 (fully compliant)

**Decision Impact:**
- Only measurable KPI shows compliance
- Not sufficient alone to justify promotion

---

## Proxy vs Measured Values

### Measured Values (Real Data)

| Metric | Value | Source |
|--------|-------|--------|
| safety_compliance | 1.0 | Violation scan |
| Redis availability | True | Connection test |
| Existing artifacts | 6 files | File system |
| BrainSpec count | 1 | docs/brain/ |

### Proxy Values (Estimates/Simulations)

| Metric | Value | Source | Confidence |
|--------|-------|--------|------------|
| paper_carryover_proxy (from previous cycle) | 0.463 | correlation estimate | LOW |
| false_positive_rate (previous cycle) | 0.25 | simulated | LOW |

### Placeholder Values (No Data)

| Metric | Value | Reason |
|--------|-------|--------|
| paper_carryover_rate | 0.0 | No paper trading |
| false_positive_rate | 0.0 | No comparison data |
| time_to_improvement | 0.0 | No tracking history |

---

## Decision Framework Application

### Policy: Decision on Unmeasurable Primary KPI

**Rule:** If primary KPI (paper_carryover_rate) cannot be measured with real evidence → default to NO CHANGE

**Application:**
1. ✅ Primary KPI is unmeasurable (placeholder)
2. ✅ No real evidence exists for comparison
3. ✅ Decision: NO CHANGE

### Why NO CHANGE is Correct

1. **No Baseline:** Cannot establish vCurrent performance without measurements
2. **No Comparison:** Cannot evaluate if vNext-B improves upon vCurrent
3. **Speculative Changes:** Any BrainSpec changes would be theoretical
4. **Risk Mitigation:** Better to maintain current state than make unvalidated changes

### What Would Enable CHANGE Decision

1. **30 days of paper trading data**
   - Would enable paper_carryover_rate measurement
   - Would enable false_positive_rate measurement

2. **Experiment tracking implementation**
   - Would enable time_to_improvement measurement
   - Would validate vNext-B's core proposal

3. **Measurable improvement threshold**
   - paper_carryover_rate improvement > 5%
   - false_positive_rate reduction > 10%
   - time_to_improvement < 10 experiments

---

## Recommendations for Next Cycle

### Immediate (Next 7 Days)

1. **Implement experiment tracking**
   - Add Redis keys for experiment logging
   - Update iterlog structure
   - Begin tracking hypothesis and outcomes

2. **Set up paper trading mode**
   - Configure paper trading environment
   - Begin running strategies in paper mode
   - Start collecting carryover data

### Short-term (Next 30 Days)

3. **Collect measurement data**
   - Run 30 days of paper trading
   - Track 20+ experiments
   - Build baseline metrics

4. **Validate infrastructure**
   - Ensure Redis tracking is working
   - Verify paper trading logs are complete
   - Test metric calculation pipelines

### Medium-term (Next Cycle)

5. **Re-run Brain CI/CD**
   - With 30 days of real data
   - Evaluate vNext-B against measured baseline
   - Make data-driven promotion decision

---

## Summary

**Current State:** 3 of 4 KPIs are placeholders  
**Measurable KPIs:** 1 of 4 (safety_compliance only)  
**Decision:** NO CHANGE (insufficient evidence)  
**Path Forward:** Implement measurement infrastructure, collect data, re-evaluate  

**Key Insight:** The Brain CI/CD process correctly identified that promotion without measurement would be premature. The infrastructure exists, but the data foundation needs to be built before meaningful evaluation can occur.

