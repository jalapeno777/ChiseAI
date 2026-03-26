# ICT Hypothesis Framework

**Story ID:** ST-ICT-019  
**Epic:** EP-ICT-006  
**Date:** 2026-03-25  
**Status:** Implemented

## Overview

This document defines the hypothesis testing framework for validating whether ICT signals provide statistically significant alpha over a non-ICT baseline strategy.

## Hypotheses

### Null Hypothesis (H0)

**ICT signals do NOT add statistically significant alpha.**

Formally: The mean return of ICT-enhanced signals is less than or equal to the mean return of non-ICT baseline signals.

```
H0: μ_treatment ≤ μ_control
```

### Alternative Hypothesis (H1)

**ICT signals add alpha with p<0.05 and effect size >2%.**

```
H1: μ_treatment > μ_control
   AND effect_size > 2%
   AND p_value < 0.05
```

## Study Design

### Control Group

Non-ICT baseline signals using:

- Random entry timing
- Fixed rules without ICT components
- Time-based entries as benchmark

### Treatment Group

ICT-enhanced signals using:

- **CVD (Clustered Volume Delta):** Volume imbalance detection
- **FVG (Fair Value Gap):** Price gap identification
- **Order Block:** Institutional order zone detection

Note: BOS/CHoCH signals are excluded per BL-BOS-CHOCH-001.

### Assignment

Each signal is independently classified as:

- **Positive outcome:** Return exceeds threshold (e.g., 0% = breakeven)
- **Negative outcome:** Return does not exceed threshold

## Power Analysis

### Sample Size Determination

Using normal approximation for comparing two proportions:

```
n = 2 * ((z_α + z_β) / h)²
```

Where:

- `z_α = 1.96` (two-tailed at α=0.05)
- `z_β = 0.84` (80% power)
- `h = 0.50` (Cohen's h medium effect size)

**Minimum signals required: 100 per group**

### Effect Size Thresholds

| Category   | Cohen's h   | Interpretation                  |
| ---------- | ----------- | ------------------------------- |
| Negligible | < 0.02      | Below 2% practical significance |
| Small      | 0.02 - 0.10 | Marginal improvement            |
| Medium     | 0.10 - 0.25 | Meaningful alpha                |
| Large      | 0.25 - 0.40 | Strong alpha                    |
| Very Large | ≥ 0.40      | Exceptional alpha               |

## Statistical Methods

### Two-Proportion Z-Test

Tests whether the success rate differs significantly between treatment and control.

```python
z = (p1 - p2) / √(p_pooled * (1 - p_pooled) * (1/n1 + 1/n2))
```

### Effect Size (Cohen's h)

```python
h = 2 * arcsin(√p1) - 2 * arcsin(√p2)
```

### Confidence Intervals

95% CI for the difference in means:

```
CI = (μ_treatment - μ_control) ± 1.96 * SE
SE = √(σ²_treatment/n_treatment + σ²_control/n_control)
```

## Early Stopping Rules

### Trigger Conditions

**Early stopping is triggered when ALL of the following are true:**

1. At least 50 signals have been analyzed
2. p-value > 0.30 (no significance trending)
3. Evidence strongly suggests H0 cannot be rejected

### Rationale

A p-value > 0.30 after 50 signals indicates:

- Weak or no treatment effect
- Continued sampling is unlikely to反转 the conclusion
- Resources can be allocated elsewhere

### Post-Stop Actions

1. Document findings and accumulate evidence
2. Do NOT claim "ICT doesn't work" - only "insufficient evidence"
3. Consider alternative signal combinations or timeframes

## Decision Criteria

### Continue Collecting

- Signals analyzed < 100
- p-value between 0.05 and 0.30
- Effect size trending positive

### Accept H0 (ICT adds no alpha)

- Signals ≥ 100
- p-value ≥ 0.05
- Effect size < 2% (negligible)

### Reject H0 (ICT adds alpha)

- Signals ≥ 100
- p-value < 0.05
- Effect size ≥ 2% (Cohen's h ≥ 0.02)
- Power achieved ≥ 80%

### Inconclusive

- p-value < 0.05
- BUT effect size < 2%
- Statistical significance without practical significance

## Implementation

### Module

`src/validation/statistical/hypothesis_framework.py`

### Key Classes

| Class                    | Purpose                               |
| ------------------------ | ------------------------------------- |
| `ICTHypothesisFramework` | Main framework orchestrator           |
| `TestParameters`         | Configurable test parameters          |
| `EffectSizeThresholds`   | Effect size interpretation thresholds |
| `SignalResult`           | Single signal evaluation result       |
| `HypothesisTestResult`   | Aggregated test results               |

### Key Functions

| Function                          | Purpose                    |
| --------------------------------- | -------------------------- |
| `calculate_minimum_sample_size()` | Power analysis             |
| `cohens_h()`                      | Effect size calculation    |
| `two_proportion_z_test()`         | Hypothesis test            |
| `check_early_stopping()`          | Early stop evaluation      |
| `effect_size_interpretation()`    | Human-readable effect size |

## Validation Requirements

### Pre-Collection

- [ ] Define success metric (return threshold)
- [ ] Document control group strategy
- [ ] Confirm 100 signal minimum budget
- [ ] Establish data collection pipeline

### During Collection

- [ ] Track signals in real-time
- [ ] Evaluate at 50 signals (early stop check)
- [ ] Re-evaluate at 75 signals
- [ ] Final evaluation at 100+ signals

### Post-Collection

- [ ] Report power achieved
- [ ] Report confidence intervals
- [ ] Document effect size interpretation
- [ ] Provide actionable recommendation

## Related Documents

- [EP-ICT-006: ICT Statistical Validation](../epics/EP-ICT-006-statistical-validation.md)
- [BL-BOS-CHOCH-001: BOS/CHoCH Exclusion](../decisions/BL-BOS-CHOCH-001-bos-choch-exclusion.md)
- [ICT Component Validation Report](./ict-component-validation-report.md)

## Changelog

| Date       | Change                           |
| ---------- | -------------------------------- |
| 2026-03-25 | Initial framework implementation |
