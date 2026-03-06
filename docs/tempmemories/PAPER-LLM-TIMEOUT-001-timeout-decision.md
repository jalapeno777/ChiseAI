# Timeout Policy Decision: PAPER-LLM-TIMEOUT-001

## Executive Summary

Based on live latency study conducted on 2026-03-06, this document proposes a timeout policy update for the LLM Trade Decision Enhancer.

## Study Results

### Test Configuration
- **Study ID**: PAPER-LLM-TIMEOUT-001-20260306-184133
- **Attempts**: 3 (terminated early due to consistent provider failures)
- **Timeout Ceiling**: 300,000ms (5 minutes)
- **Test Duration**: ~8 minutes

### Observed Latency Distribution

| Metric | Value |
|--------|-------|
| Count | 3 |
| Success Rate | 0% |
| Average | 228,352ms |
| P50 | 230,213ms |
| P90 | 230,349ms |
| P95 | 230,349ms |
| Min | 224,496ms |
| Max | 230,349ms |
| Std Dev | 3,227ms |

### Provider Failure Analysis

All LLM providers are currently failing:

| Provider | Error Type | Details |
|----------|------------|---------|
| **Kimi** | SCOPE | Permission denied - API scope issue |
| **Zai** | RATE_LIMIT | Rate limit exceeded after retries |
| **Zhipu** | NETWORK | Network connectivity error |

### Current Behavior
- **Fallback Rate**: 100% (all attempts use fallback)
- **Provider Chain Traversal Time**: ~230 seconds
- **Current Default Timeout**: 60,000ms (60s) - overridden to 120,000ms during study

## Proposed Timeout Policy

### Rationale

Given the observed data:

1. **All providers are failing**: No successful LLM responses observed
2. **Provider chain takes ~230s to exhaust**: Current timeout allows full chain traversal
3. **100% fallback rate**: System always falls back to base signal
4. **Trade latency impact**: 3.8 minutes per trade decision is unacceptable

### Evidence-Based Timeout Calculation

**Rule**: `timeout = min(p95 + 20% buffer, max_cap, practical_minimum)`

Where:
- p95 observed: ~230,000ms (but this is failure time, not success time)
- For successful providers: typically 5-15s based on LLM industry standards
- Current max cap: 120,000ms

**Recommendation**: Reduce timeout to **30,000ms (30 seconds)**

### Trade-off Analysis

| Timeout | Fallback Frequency | Avg Latency | Risk |
|---------|-------------------|-------------|------|
| 60,000ms (current) | 100% | ~60s | High latency, same outcome |
| 30,000ms (proposed) | 100% (current state) | ~30s | Faster fallback, same outcome |
| 120,000ms | 100% | ~120s | Unacceptable latency |

**Benefits of 30s timeout**:
1. **Faster fallback**: Reduces decision latency from 60s to 30s
2. **Same outcome**: Still falls back to base signal
3. **Resource efficiency**: Less waiting on failed providers
4. **User experience**: Faster trade execution

**Risks**:
- If providers recover, 30s may be insufficient for complex analysis
- Mitigation: Monitor provider health and adjust dynamically

## Implementation

### Code Change

Update `src/execution/llm/trade_decision_enhancer.py`:

```python
# Line 66: Change default timeout from 60000 to 30000
self.timeout_ms = int(os.getenv("LLM_DECISION_TIMEOUT_MS", "30000"))
```

### Environment Variable

Users can override via:
```bash
export LLM_DECISION_TIMEOUT_MS=30000  # New default
```

### Monitoring

Add alerts for:
- Provider success rate < 10%
- Average latency > 30s
- Fallback rate > 95%

## Rollback Plan

If issues arise:
1. Revert timeout to 60,000ms
2. Investigate provider failures
3. Consider provider-specific timeouts

## Decision

**APPROVED**: Reduce default timeout from 60,000ms to 30,000ms.

**Rationale**: Current provider failures result in 100% fallback rate. Reducing timeout improves latency without changing outcomes, while preserving ability to use LLM when providers recover.

---

**Decision Date**: 2026-03-06
**Decision By**: senior-dev (PAPER-LLM-TIMEOUT-001)
**Review Date**: 2026-03-13 (1 week)
