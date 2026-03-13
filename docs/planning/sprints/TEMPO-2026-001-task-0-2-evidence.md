# TEMPO-2026-001 Task 0.2 Evidence Document

**Task:** 0.2 - Design trace schema and sampling strategy  
**Story ID:** TEMPO-2026-001  
**Owner:** senior-dev  
**Date:** 2026-03-13  
**Status:** ✅ Complete

---

## Executive Summary

This document provides evidence and rationale for the trace schema design and sampling strategy decisions made for the ChiseAI OpenTelemetry integration. The design balances comprehensive observability with operational cost and performance considerations.

### Key Deliverables

1. ✅ Comprehensive trace schema design document (`docs/observability/trace-schema-design.md`)
2. ✅ Sampling strategy with head-based and tail-based rules
3. ✅ Service-specific instrumentation guidelines
4. ✅ Storage impact calculations
5. ✅ Migration plan

---

## Design Decisions

### Decision 1: OpenTelemetry Standard Compliance

**Decision:** Follow OpenTelemetry semantic conventions v1.20+ for all standard attributes.

**Rationale:**
- Ensures compatibility with Grafana Tempo and other OTel-compatible backends
- Reduces learning curve for developers familiar with OTel
- Enables use of standard instrumentation libraries
- Future-proofs the observability stack

**References:**
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- [Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/database/database-spans/)

**Trade-offs:**
- ✅ Standardized naming across services
- ✅ Rich ecosystem of tools and libraries
- ⚠️ May not cover all domain-specific needs (addressed via custom attributes)

---

### Decision 2: Custom Attribute Prefix

**Decision:** Use `chiseai.` prefix for all custom attributes.

**Rationale:**
- Prevents naming collisions with future OTel conventions
- Makes ChiseAI-specific attributes easily identifiable
- Enables custom dashboards and alerts in Grafana
- Follows OTel best practices for vendor-specific attributes

**Examples:**
- ✅ `chiseai.strategy.id`
- ✅ `chiseai.trade.symbol`
- ✅ `chiseai.performance.duration_ms`

**Trade-offs:**
- ✅ Clear namespace separation
- ✅ Easy to query and filter
- ⚠️ Slightly longer attribute names

---

### Decision 3: Head-Based Sampling by Environment

**Decision:** Implement environment-specific head-based sampling rates.

| Environment | Rate | Rationale |
|-------------|------|-----------|
| dev | 100% | Full visibility for debugging |
| staging | 50% | Balance visibility and cost |
| prod | 10% | Cost-effective statistical sample |

**Rationale:**
- Development requires complete visibility for debugging
- Staging balances testing needs with resource usage
- Production sampling keeps costs manageable while providing sufficient data
- 10% in production provides statistically significant samples for most analyses

**Storage Impact Calculation:**

```
Assumptions:
- 7 services instrumented
- Average 10 spans per trace
- Average span size: 2KB
- Production traffic: 1000 requests/second

At 100% sampling:
- Spans/second: 1000 requests × 10 spans = 10,000 spans/s
- Storage/day: 10,000 × 2KB × 86,400s = 1.73TB/day
- 7-day retention: 12.1TB

At 10% sampling:
- Spans/second: 1000 requests × 10 spans × 10% = 1,000 spans/s
- Storage/day: 1,000 × 2KB × 86,400s = 173GB/day
- 7-day retention: 1.2TB

Cost savings: ~90% reduction in storage
```

**Trade-offs:**
- ✅ Significant cost reduction
- ✅ Still captures representative samples
- ⚠️ May miss rare events (mitigated by tail-based sampling)

---

### Decision 4: Tail-Based Sampling Rules

**Decision:** Implement tail-based sampling to always capture important traces.

**Rules:**

1. **Always sample errors (5xx, exceptions)**
   - Priority: 1 (highest)
   - Condition: `status_code >= 500 OR exception.type exists`
   - Rate: 100%

2. **Always sample slow requests (>500ms)**
   - Priority: 2
   - Condition: `duration_ms > 500`
   - Rate: 100%
   - Thresholds vary by service

3. **Always sample enterprise users**
   - Priority: 3
   - Condition: `user.tier == "enterprise"`
   - Rate: 100%

4. **50% sample strategy executions**
   - Priority: 4
   - Condition: `chiseai.strategy.id exists`
   - Rate: 50%

5. **25% sample trade operations**
   - Priority: 5
   - Condition: `chiseai.trade.id exists`
   - Rate: 25%

**Rationale:**
- Errors are critical for debugging and must never be missed
- Slow requests indicate performance issues requiring investigation
- Enterprise users have SLA requirements requiring full visibility
- Strategy and trade operations are business-critical but high-volume

**References:**
- [Tempo Tail-Based Sampling](https://grafana.com/docs/tempo/latest/configuration/tail-based-sampling/)
- [OTel Collector Tail Sampling](https://opentelemetry.io/docs/collector/tail-sampling/)

**Trade-offs:**
- ✅ Critical traces always captured
- ✅ Better debugging experience
- ⚠️ Requires more memory for tail-based sampling buffer
- ⚠️ Slightly higher latency for trace export

---

### Decision 5: Service-Specific Slow Thresholds

**Decision:** Define different slow request thresholds per service.

| Service | Threshold | Rationale |
|---------|-----------|-----------|
| chiseai-api-final | 500ms | API response SLA |
| chiseai-brain-scheduler | 2000ms | Strategy computation |
| chiseai-ohlcv-ingestion | 10000ms | Batch processing |
| chiseai-kimi-adapter | 5000ms | LLM API latency |

**Rationale:**
- Different services have different performance characteristics
- API gateway needs low latency for user experience
- Strategy engine performs complex calculations
- Ingestion processes large batches
- LLM adapter depends on external API latency

**Trade-offs:**
- ✅ Accurate slow request detection per service
- ✅ Reduces noise from expected long-running operations
- ⚠️ Requires service-specific configuration

---

### Decision 6: Attribute Cardinality Limits

**Decision:** Limit attributes to maximum 50 per span and avoid high-cardinality values.

**Guidelines:**
- Maximum 50 attributes per span (including resource attributes)
- Avoid timestamps as attribute values
- Avoid UUIDs as attribute values (unless necessary)
- Use enums where possible
- Hash high-cardinality identifiers (user IDs)

**Rationale:**
- High cardinality impacts storage and query performance
- Tempo and other backends have cardinality limits
- Too many attributes make traces hard to read
- Enums enable efficient filtering and aggregation

**Examples:**

```python
# ❌ High cardinality - AVOID
span.set_attribute("chiseai.trade.timestamp", "2026-03-13T10:30:00.123456Z")
span.set_attribute("chiseai.trade.uuid", str(uuid.uuid4()))

# ✅ Low cardinality - PREFERRED
span.set_attribute("chiseai.trade.side", "buy")  # Enum
span.set_attribute("chiseai.trade.status", "filled")  # Enum
span.set_attribute("chiseai.user.id", hash_user_id(user_id))  # Hashed
```

**Trade-offs:**
- ✅ Better query performance
- ✅ Lower storage costs
- ✅ Faster dashboards
- ⚠️ Some loss of granularity (acceptable trade-off)

---

### Decision 7: Baggage Usage Constraints

**Decision:** Use baggage sparingly and only for critical context propagation.

**Allowed Baggage Keys:**
- `user.id` - User identification
- `user.tier` - User tier for routing decisions
- `request.id` - Request correlation
- `request.priority` - Priority for queue ordering
- `chiseai.strategy.id` - Strategy context
- `chiseai.execution.id` - Execution batch context
- `chiseai.trace.priority` - Sampling override

**Constraints:**
- Maximum 8192 bytes per baggage entry
- String values only
- No nested structures
- No sensitive data

**Rationale:**
- Baggage adds overhead to every request
- Excessive baggage impacts performance
- Some contexts are needed across service boundaries
- Security requires careful baggage management

**Trade-offs:**
- ✅ Context propagates to all downstream services
- ✅ Enables consistent sampling decisions
- ⚠️ Adds request header overhead
- ⚠️ Requires careful security review

---

### Decision 8: Database Statement Sanitization

**Decision:** Sanitize database statements to remove literal values.

**Example:**

```python
# ❌ Unsanitized - AVOID
span.set_attribute("db.statement", "SELECT * FROM trades WHERE id = 12345")

# ✅ Sanitized - PREFERRED
span.set_attribute("db.statement", "SELECT * FROM trades WHERE id = $1")
```

**Rationale:**
- Prevents sensitive data exposure in traces
- Reduces cardinality (each unique value creates new attribute combination)
- Still provides query structure for debugging
- Follows security best practices

**Trade-offs:**
- ✅ Improved security
- ✅ Lower cardinality
- ⚠️ Cannot see actual query parameters (acceptable for production)

---

### Decision 9: Error Classification System

**Decision:** Implement structured error classification with custom attributes.

**Error Types:**
- `validation` - Input validation errors
- `timeout` - Request timeouts
- `exchange_api` - External exchange API errors
- `database` - Database connection/query errors
- `cache` - Cache operation errors
- `authentication` - Auth/authorization errors
- `rate_limit` - Rate limiting errors
- `internal` - Internal service errors

**Error Severity:**
- `warning` - Non-critical, recoverable
- `error` - Operation failed, may be recoverable
- `critical` - System-level failure

**Rationale:**
- Enables targeted alerting by error type
- Supports error rate SLIs
- Facilitates root cause analysis
- Enables error trend analysis

**Trade-offs:**
- ✅ Better error analytics
- ✅ Targeted alerting
- ⚠️ Requires discipline in error classification

---

### Decision 10: Python OpenTelemetry SDK

**Decision:** Use Python OpenTelemetry SDK v1.20+ with auto-instrumentation.

**Instrumentation Libraries:**
- `opentelemetry-instrumentation-fastapi` - API framework
- `opentelemetry-instrumentation-redis` - Cache operations
- `opentelemetry-instrumentation-psycopg2` - PostgreSQL
- `opentelemetry-instrumentation-requests` - HTTP client
- `opentelemetry-instrumentation-logging` - Correlation

**Rationale:**
- Mature, well-supported libraries
- Minimal code changes required
- Automatic context propagation
- Comprehensive coverage of common operations

**References:**
- [Python OpenTelemetry](https://opentelemetry.io/docs/instrumentation/python/)
- [Auto-Instrumentation](https://opentelemetry.io/docs/instrumentation/python/automatic/)

**Trade-offs:**
- ✅ Quick implementation
- ✅ Broad coverage
- ✅ Community support
- ⚠️ May require customization for domain-specific spans

---

## Storage Impact Analysis

### Current State (No Tracing)

| Metric | Value |
|--------|-------|
| Trace storage | 0 GB |
| Trace-related compute | 0 |

### Projected State (With Tracing)

#### Development Environment

| Metric | Value |
|--------|-------|
| Sampling rate | 100% |
| Spans/second | ~1,000 (estimated dev traffic) |
| Daily storage | ~173 GB |
| 7-day retention | ~1.2 TB |

#### Staging Environment

| Metric | Value |
|--------|-------|
| Sampling rate | 50% |
| Spans/second | ~5,000 (estimated staging traffic) |
| Daily storage | ~432 GB |
| 7-day retention | ~3 TB |

#### Production Environment

| Metric | Value |
|--------|-------|
| Sampling rate | 10% (default) |
| Spans/second | ~10,000 (100k requests × 10% × 10 spans) |
| Daily storage | ~173 GB |
| 7-day retention | ~1.2 TB |
| Monthly storage | ~5 TB |

### Cost Comparison

| Scenario | Daily Storage | Monthly Storage | Relative Cost |
|----------|---------------|-----------------|---------------|
| No sampling (100%) | 1.73 TB | 52 TB | 10x |
| Prod default (10%) | 173 GB | 5 TB | 1x (baseline) |
| Aggressive (5%) | 87 GB | 2.6 TB | 0.5x |

**Recommendation:** Start with 10% sampling in production, adjust based on usage patterns.

---

## Performance Impact Analysis

### Overhead Estimation

| Component | Estimated Overhead | Mitigation |
|-----------|-------------------|------------|
| Span creation | ~1-5μs per span | Batch processing |
| Context propagation | ~10-50μs per request | Efficient serialization |
| Export (OTLP) | ~1-10ms per batch | Async export, batching |
| Memory (tail sampling) | ~100MB buffer | Configurable buffer size |

### Total Estimated Impact

| Service | Estimated Latency Impact | Memory Impact |
|---------|-------------------------|---------------|
| chiseai-api-final | +2-5ms per request | +50MB |
| chiseai-brain-scheduler | +5-10ms per execution | +100MB |
| chiseai-ohlcv-ingestion | +10-20ms per batch | +100MB |

**Acceptance Criteria:**
- Latency impact <5% of baseline
- Memory impact <10% of container limit
- CPU impact <5% of baseline

---

## References

### OpenTelemetry

1. [OpenTelemetry Specification v1.20](https://opentelemetry.io/docs/specs/otel/)
2. [Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
3. [OTLP Protocol](https://opentelemetry.io/docs/specs/otlp/)
4. [Python Instrumentation](https://opentelemetry.io/docs/instrumentation/python/)
5. [Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)

### Grafana Tempo

1. [Tempo Documentation](https://grafana.com/docs/tempo/)
2. [Tempo Configuration](https://grafana.com/docs/tempo/latest/configuration/)
3. [Tail-Based Sampling](https://grafana.com/docs/tempo/latest/configuration/tail-based-sampling/)
4. [Tempo Query](https://grafana.com/docs/tempo/latest/query/)

### Best Practices

1. [Distributed Tracing Best Practices](https://opentelemetry.io/docs/concepts/signals/traces/)
2. [Sampling Strategies](https://opentelemetry.io/docs/concepts/sampling/)
3. [Cardinality Best Practices](https://grafana.com/blog/2022/02/15/what-are-cardinality-spikes-and-why-do-they-matter/)

---

## Validation Checklist

### Schema Validation

- [x] All standard attributes follow OTel conventions
- [x] Custom attributes use `chiseai.` prefix
- [x] Attribute names use snake_case
- [x] No high-cardinality attributes defined
- [x] Maximum 50 attributes per span

### Sampling Validation

- [x] Head-based sampling rates defined per environment
- [x] Tail-based sampling rules cover critical scenarios
- [x] Service-specific slow thresholds defined
- [x] Sampling decision matrix documented

### Security Validation

- [x] No sensitive data in attribute definitions
- [x] Database statement sanitization required
- [x] User ID hashing specified
- [x] Baggage constraints documented

### Performance Validation

- [x] Storage impact calculated
- [x] Latency impact estimated
- [x] Memory impact estimated
- [x] Cardinality limits defined

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| High storage costs | Medium | High | Start with 10% sampling, monitor |
| Performance degradation | Low | Medium | Benchmark before rollout |
| Cardinality explosion | Medium | High | Enforce limits, review dashboards |
| Sensitive data exposure | Low | Critical | Sanitization rules, code review |
| Integration complexity | Medium | Medium | Phased rollout, testing |

---

## Next Steps

1. **Task 0.3** ✅ Complete - OTel SDK validation
2. **Task 0.4** - Deploy Tempo container
3. **Task 0.5** - Configure Grafana datasource
4. **Task 1.1** - Instrument API service
5. **Task 1.2** - Instrument strategy engine

---

## Evidence Files

| File | Description | Lines |
|------|-------------|-------|
| `docs/observability/trace-schema-design.md` | Complete schema design | ~900 |
| `docs/planning/sprints/TEMPO-2026-001-task-0-2-evidence.md` | This evidence document | ~500 |

---

**Sign-off:**

- **Designed by:** senior-dev
- **Date:** 2026-03-13
- **Status:** Ready for implementation

**Next Review:** 2026-04-13
