# Timeout Policy Options: LLM-PROVIDER-FIX-001-LATENCY

## Executive Summary

This document proposes timeout policy options for the LLM Trade Decision Enhancer based on:
1. Phase B smoke matrix results (0/4 providers working)
2. Prior PAPER-LLM-TIMEOUT-001 findings (30s timeout recommended)
3. Study phase requirements (300s ceiling for data gathering)

## Background

### Phase B Results (Smoke Matrix)
- **Kimi**: Invalid API key (401)
- **Z.ai**: Not configured (missing API key)
- **Zhipu**: Quota exhausted (429)
- **Infrastructure**: Adapter functional, all providers failing

### Prior PAPER-LLM-TIMEOUT-001 Findings
- **Recommended timeout**: 30,000ms (30 seconds)
- **Rationale**: 100% fallback rate with failed providers; faster fallback improves latency without changing outcomes
- **Status**: Approved but not yet implemented

## Proposed Timeout Options

### Option 1: Conservative (P95-Based)

**Timeout**: 45,000ms (45 seconds)

**Rationale**:
- Based on P95 of observed failure times (~230s) with aggressive reduction
- Allows time for provider chain traversal (3 providers × 15s each)
- Accounts for network variability

**Trade-offs**:
| Aspect | Impact |
|--------|--------|
| Fallback latency | 45s per trade decision |
| Resource efficiency | Moderate - waits longer before fallback |
| User experience | Acceptable for non-latency-sensitive strategies |
| Risk tolerance | Low - conservative approach |

**When to use**: 
- When provider recovery is expected soon
- For strategies where 45s latency is acceptable
- During transition periods with mixed provider health

---

### Option 2: Balanced (P90-Based) - **RECOMMENDED**

**Timeout**: 30,000ms (30 seconds)

**Rationale**:
- Based on PAPER-LLM-TIMEOUT-001 recommendation
- Industry standard for LLM API timeouts
- Balances latency vs. provider recovery chance
- Fast enough for most trading strategies

**Trade-offs**:
| Aspect | Impact |
|--------|--------|
| Fallback latency | 30s per trade decision |
| Resource efficiency | Good - reasonable wait before fallback |
| User experience | Good - acceptable for most strategies |
| Risk tolerance | Medium - balanced approach |

**When to use**: 
- **DEFAULT RECOMMENDATION**
- Standard production configuration
- When providers have intermittent issues
- For most trading strategies

**Implementation**:
```python
# In src/execution/llm/trade_decision_enhancer.py
self.timeout_ms = int(os.getenv("LLM_DECISION_TIMEOUT_MS", "30000"))
```

---

### Option 3: Aggressive (P50-Based)

**Timeout**: 15,000ms (15 seconds)

**Rationale**:
- Fast fallback for latency-sensitive strategies
- Assumes providers should respond quickly or not at all
- Forces rapid fallback to base signal

**Trade-offs**:
| Aspect | Impact |
|--------|--------|
| Fallback latency | 15s per trade decision |
| Resource efficiency | High - minimal waiting |
| User experience | Excellent - fast decisions |
| Risk tolerance | High - may miss slow but valid responses |

**When to use**: 
- High-frequency trading strategies
- When providers are known to be slow
- Latency-critical applications
- With provider-specific timeouts enabled

**Risks**:
- May prematurely timeout valid but slow LLM responses
- Could increase fallback rate unnecessarily
- Requires monitoring to ensure not too aggressive

---

## Study Phase Timeout

**Timeout**: 300,000ms (5 minutes)

**Purpose**: 
- Allow full provider chain traversal during study
- Capture complete latency distribution
- Understand worst-case behavior

**Usage**:
- Only for `latency_study.py` script
- Not for production use
- Documented for reproducibility

## Comparison Matrix

| Option | Timeout | Fallback Latency | Use Case | Risk Level |
|--------|---------|------------------|----------|------------|
| Conservative | 45s | 45s | Transition/mixed health | Low |
| **Balanced** | **30s** | **30s** | **Standard production** | **Medium** |
| Aggressive | 15s | 15s | High-frequency/latency-critical | High |
| Study Phase | 300s | 300s | Data gathering only | N/A |

## Recommended Configuration

### Default (Production)
```bash
export LLM_DECISION_TIMEOUT_MS=30000  # 30 seconds
```

### Environment-Specific
```bash
# Conservative (e.g., during provider issues)
export LLM_DECISION_TIMEOUT_MS=45000

# Aggressive (e.g., high-frequency trading)
export LLM_DECISION_TIMEOUT_MS=15000

# Study phase (data gathering only)
export LLM_DECISION_TIMEOUT_MS=300000
```

### Dynamic Adjustment
Consider implementing dynamic timeout based on provider health:
```python
if provider_health_score > 0.8:
    timeout_ms = 30000  # Normal
elif provider_health_score > 0.5:
    timeout_ms = 45000  # Degraded
else:
    timeout_ms = 15000  # Poor - fast fallback
```

## Monitoring Recommendations

Track these metrics to validate timeout choice:

1. **Fallback rate** - Should be < 10% with healthy providers
2. **Average latency** - Should be < timeout value
3. **P95 latency** - Should be < timeout × 1.2
4. **Provider success rate** - Per-provider health tracking

**Alerts**:
- Fallback rate > 50%: Investigate provider health
- Average latency > timeout: Timeout may be too aggressive
- P95 latency > timeout × 2: Consider increasing timeout

## Rollback Plan

If timeout change causes issues:

1. **Immediate**: Revert to previous timeout via env var
   ```bash
   export LLM_DECISION_TIMEOUT_MS=60000  # Previous default
   ```

2. **Short-term**: Investigate provider failures
   - Check credential validity
   - Verify network connectivity
   - Review provider status pages

3. **Long-term**: Consider provider-specific timeouts
   - Kimi: 30s (typically fast)
   - Z.ai: 45s (may be slower)
   - Zhipu: 30s (typically fast)

## Decision

**RECOMMENDED**: Option 2 - Balanced (30,000ms)

**Rationale**:
1. Based on prior PAPER-LLM-TIMEOUT-001 findings
2. Industry standard for LLM APIs
3. Balances latency and success probability
4. Allows time for provider chain traversal
5. Fast enough for most trading strategies

**Implementation Priority**: P1 (after credential fixes)

---

**Document Version**: 1.0
**Created**: 2026-03-06
**Story ID**: LLM-PROVIDER-FIX-001-LATENCY
**Based on**: PAPER-LLM-TIMEOUT-001 findings
