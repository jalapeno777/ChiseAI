# TEMPO-2026-001 Task 0.2 Evidence

**Task:** 0.2 - Design trace schema and sampling strategy  
**Story ID:** TEMPO-2026-001  
**Phase:** 0 (Preflight)  
**Date:** 2026-03-13  
**Status:** ✅ Complete

---

## 1. Task Overview

This document provides evidence for Task 0.2, which designed the OpenTelemetry trace schema and sampling strategy for the ChiseAI platform's distributed tracing implementation with Grafana Tempo.

## 2. Design Decisions

### 2.1 Span Attribute Design

**Decision:** Define 55+ span attributes across standard OTel and custom ChiseAI namespaces.

**Rationale:**
- Standard OTel attributes ensure compatibility with existing tools
- Custom `chiseai.*` attributes capture domain-specific context
- Comprehensive coverage enables powerful TraceQL queries
- Follows semantic conventions for interoperability

**Attributes by Category:**
- HTTP (9 attributes): Standard web request tracking
- Database (7 attributes): SQL and NoSQL operation tracking
- Messaging (6 attributes): Queue and event tracking
- ChiseAI Custom (33 attributes): Trading, strategy, user context, cache, error tracking, performance metrics

**Key Design Choices:**
1. **HTTP Attributes**: Standard OTel attributes for compatibility with existing dashboards
2. **Database Attributes**: Capture sanitized queries to avoid PII leakage
3. **Messaging Attributes**: Support Redis and future Kafka integration
4. **Custom Attributes**: Domain-specific context for trading and strategy operations

### 2.2 Resource Attribute Design

**Decision:** Require 3 core resource attributes + 12 optional attributes.

**Rationale:**
- `service.name`, `service.version`, `deployment.environment` are essential for filtering
- Container and process attributes aid debugging in production
- ChiseAI-specific attributes enable service grouping and tier-based routing

**Implementation:**
- Resource attributes set once at service startup
- Propagated to all spans from that service instance
- Used for service dependency mapping in Grafana

### 2.3 Baggage Specification

**Decision:** Support 10 baggage keys with 8192 byte limit.

**Rationale:**
- User ID and request ID propagation enables cross-service correlation
- Strategy and execution IDs maintain context through async operations
- Size limit prevents abuse and performance degradation
- Supports feature flags for A/B testing traceability

**Baggage Keys:**
- Standard: user.id, user.tier, request.id, request.priority, trace.origin, trace.correlation_id
- ChiseAI-specific: chiseai.strategy.id, chiseai.execution.id, chiseai.trace.priority, chiseai.feature.flags

**Constraints:**
- Maximum 10 baggage keys per trace
- Maximum 256 characters per key name
- String values only (no nested objects)
- No sensitive data (PII, credentials)

### 2.4 Sampling Strategy

**Decision:** Combine head-based (default rates) with tail-based (selective rules).

**Head-Based Rates:**
| Environment | Rate | Rationale |
|-------------|------|-----------|
| dev | 100% | Full visibility during development |
| staging | 50% | Balance visibility and cost |
| prod | 10% | Cost-effective with tail-based backup |
| prod-debug | 100% | Temporary debugging mode |

**Tail-Based Rules:**
1. Always sample errors (critical for debugging)
2. Always sample slow requests (performance analysis)
3. Always sample enterprise users (SLA compliance)
4. Reduced sampling for high-volume operations (strategy, trades)

**Rule Priority (100 = highest):**
| Priority | Rule | Condition | Action |
|----------|------|-----------|--------|
| 100 | Error Rule | Any span with error status | Always keep |
| 90 | Slow API Rule | HTTP duration > 500ms | Always keep |
| 85 | Slow Strategy Rule | Strategy execution > 2000ms | Always keep |
| 80 | Slow Ingestion Rule | Data ingestion > 10000ms | Always keep |
| 70 | Enterprise User Rule | user.tier = "enterprise" | Always keep |
| 50 | Strategy Execution Rule | chiseai.service.type = "strategy" | 50% sample |
| 40 | Trade Operation Rule | chiseai.trade.id exists | 25% sample |
| 0 | Default Rule | All other traces | Head-based rate |

**Rationale:**
- Head-based is simple and predictable for budget estimation
- Tail-based ensures important traces are never lost
- Combined approach optimizes storage cost vs. observability
- Priority system ensures critical traces are always captured

## 3. Storage Impact Analysis

### 3.1 Calculation Methodology

**Formula:**
```
Daily Storage = spans_per_sec × bytes_per_span × 86400 seconds
Total Storage = Daily Storage × retention_days
```

**Assumptions:**
- Base rate: 1000 spans/second at 100% sampling
- Average span size: 500 bytes
- Retention: 7 days
- Compression factor: 1.5x (Tempo uses efficient encoding)

### 3.2 Results by Environment

| Environment | Sampling | Spans/Sec | Daily Volume | 7-Day Total | With Compression |
|-------------|----------|-----------|--------------|-------------|------------------|
| dev | 100% | 1000 | 41.5 GB | 290.5 GB | ~194 GB |
| staging | 50% | 500 | 20.8 GB | 145.3 GB | ~97 GB |
| prod | 10% | 100 | 4.2 GB | 29.1 GB | ~19.4 GB |

### 3.3 Recommended Storage Allocation

| Environment | Calculated Need | Recommended | Headroom |
|-------------|-----------------|-------------|----------|
| Production | 29.1 GB | 50 GB | 72% |
| Staging | 145.3 GB | 200 GB | 38% |
| Development | 290.5 GB | 350 GB | 20% |

**Storage Growth Projections:**
- Assuming 2x growth in traffic per year
- Production: 50 GB → 100 GB within 12 months
- Staging: 200 GB → 400 GB within 12 months
- Development: 350 GB → 700 GB within 12 months

## 4. OpenTelemetry Compatibility

### 4.1 Version Requirements

- **OpenTelemetry API:** >= 1.20.0
- **OpenTelemetry SDK:** >= 1.20.0
- **OTLP Exporter:** >= 1.20.0
- **Python:** >= 3.11 (validated in Task 0.3)
- **Tempo:** >= 2.0.0

### 4.2 Semantic Conventions

Schema follows OpenTelemetry semantic conventions v1.20+:

**HTTP Attributes:**
- `http.method`, `http.status_code` - Standard request tracking
- `http.route` - Route template for grouping
- `http.response_content_length` - Response size

**Database Attributes:**
- `db.system`, `db.operation` - Database identification
- `db.statement` - Sanitized query
- `db.sql.table` - Table name

**Messaging Attributes:**
- `messaging.system`, `messaging.destination` - Broker identification
- `messaging.operation` - Send/receive/process
- `messaging.message_id` - Message correlation

**Resource Attributes:**
- `service.name`, `service.version` - Service identification
- `deployment.environment` - Environment filtering
- `host.name`, `container.name` - Infrastructure context

### 4.3 Tempo Compatibility

- OTLP/gRPC endpoint: `chiseai-tempo:4317`
- OTLP/HTTP endpoint: `chiseai-tempo:4318`
- TraceQL query support for all defined attributes
- Tempo 2.x+ recommended for full feature support
- Compatible with Grafana 10.0+

**Tempo Configuration Requirements:**
- Enable OTLP receivers on ports 4317 (gRPC) and 4318 (HTTP)
- Configure storage backend (local filesystem or S3)
- Set retention period to 7 days
- Enable compression for storage efficiency

## 5. Risk Assessment

### 5.1 Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Attribute cardinality explosion | Medium | High | Cardinality guidelines, monitoring alerts |
| Storage exhaustion | Low | High | Retention policies, sampling adjustment |
| Performance overhead | Medium | Medium | Async exporters, batching, sampling |
| Schema drift | Medium | Medium | Versioning, documentation, changelog |
| Sensitive data leakage | Low | Critical | Sanitization rules, PII detection |
| Network congestion | Low | Medium | Batching, compression, sampling |

### 5.2 Mitigation Strategies

1. **Cardinality Monitoring:**
   - Alert on attributes with >1000 unique values
   - Weekly cardinality audits
   - Automatic detection of unbounded attributes

2. **Storage Management:**
   - 80% capacity warning, 90% critical alert
   - Automatic sampling rate adjustment
   - Configurable retention policies by environment

3. **Performance Optimization:**
   - Async span exporters (BatchSpanProcessor)
   - Configurable batch sizes and queue limits
   - Benchmark tests before production deployment

4. **Schema Governance:**
   - Document all attribute changes
   - Maintain backward compatibility
   - Versioned schema definitions
   - Approval process for new attributes

5. **Security Controls:**
   - Sanitize all database statements
   - Hash cache keys
   - No PII in baggage or attributes
   - Regular security audits

## 6. Implementation Checklist

### 6.1 Phase 1: Infrastructure
- [ ] Deploy Tempo container on chiseai network
- [ ] Configure OTLP receivers (ports 4317, 4318)
- [ ] Set up storage backend (local/S3)
- [ ] Verify health endpoints (`/_stcore/health`)
- [ ] Configure retention policies (7 days)
- [ ] Set up storage monitoring and alerts

### 6.2 Phase 2: Grafana Wiring
- [ ] Provision Tempo datasource
- [ ] Create service dependency dashboard
- [ ] Configure trace-derived alerts
- [ ] Test trace search functionality
- [ ] Create custom TraceQL queries
- [ ] Set up alerting for slow traces and errors

### 6.3 Phase 3: App Instrumentation
- [ ] Add OpenTelemetry dependencies to requirements.txt
- [ ] Create tracing initialization module
- [ ] Configure OTLP exporter with endpoint
- [ ] Implement auto-instrumentation for HTTP
- [ ] Implement auto-instrumentation for database
- [ ] Configure sampling based on environment

### 6.4 Phase 4: Service Coverage
- [ ] Instrument API endpoints with HTTP spans
- [ ] Instrument strategy engine with custom spans
- [ ] Instrument data ingestion pipeline
- [ ] Add database span wrappers (PostgreSQL)
- [ ] Add Redis span wrappers
- [ ] Add messaging span wrappers (Redis queues)

### 6.5 Phase 5: Hardening
- [ ] Configure production sampling rates
- [ ] Set retention policies by environment
- [ ] Create operational runbooks
- [ ] Performance benchmark overhead
- [ ] Load test with production traffic patterns
- [ ] Document troubleshooting procedures

## 7. References

### 7.1 OpenTelemetry Resources
- [Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
- [Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [OTLP Protocol](https://opentelemetry.io/docs/specs/otlp/)
- [Trace API](https://opentelemetry.io/docs/instrumentation/python/api/tracing/)
- [Sampling](https://opentelemetry.io/docs/concepts/sampling/)

### 7.2 Grafana Tempo Resources
- [Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [TraceQL Reference](https://grafana.com/docs/tempo/latest/traceql/)
- [Architecture Guide](https://grafana.com/docs/tempo/latest/operations/architecture/)
- [Deployment Guide](https://grafana.com/docs/tempo/latest/setup/)

### 7.3 Related Documents
- Task 0.1: `docs/observability/audit-current-state.md`
- Task 0.2: `docs/observability/trace-schema-design.md`
- Task 0.3: `docs/planning/sprints/TEMPO-2026-001-task-0-3-evidence.md`
- Sprint Plan: `docs/planning/sprints/TEMPO-2026-001-sprint-plan.md`
- Git Protocol: `docs/planning/sprints/TEMPO-2026-001-git-merge-protocol.md`
- Execution Tracker: `docs/planning/sprints/TEMPO-2026-001-execution-tracker.md`

## 8. Verification

### 8.1 Acceptance Criteria

| Criteria | Status | Evidence |
|----------|--------|----------|
| Span attributes defined | ✅ | 55+ attributes documented in trace-schema-design.md |
| Resource attributes defined | ✅ | 15+ attributes documented |
| Baggage specification | ✅ | 10 keys with constraints documented |
| Sampling strategy | ✅ | Head + tail-based rules with priorities |
| 10% prod, 100% dev sampling | ✅ | Documented in section 2.4 |
| OTel compatibility | ✅ | v1.20+ verified |
| Storage-efficient design | ✅ | Cardinality guidelines in section 8 |
| Service examples | ✅ | 7 service types with JSON examples |
| TraceQL examples | ✅ | 5 query patterns documented |

### 8.2 Files Created

| File | Lines | Status |
|------|-------|--------|
| `docs/observability/trace-schema-design.md` | 1,104 | ✅ Created |
| `docs/planning/sprints/TEMPO-2026-001-task-0-2-evidence.md` | 522 | ✅ Created |

### 8.3 Traceability Matrix

| Requirement | Design Section | Implementation Phase |
|-------------|----------------|----------------------|
| HTTP span attributes | 3.1 | Phase 3 |
| Database span attributes | 3.2 | Phase 4 |
| Messaging span attributes | 3.3 | Phase 4 |
| ChiseAI custom attributes | 3.4 | Phase 4 |
| Resource attributes | 4 | Phase 3 |
| Baggage propagation | 5 | Phase 3 |
| Head-based sampling | 6.1 | Phase 3 |
| Tail-based sampling | 6.2 | Phase 5 |
| Storage calculations | 6.3 | Phase 1 |
| Cardinality guidelines | 8 | Phase 4 |

## 9. Sign-off

**Designed by:** senior-dev  
**Reviewed by:** Jarvis (orchestrator)  
**Date:** 2026-03-13  
**Status:** Ready for Phase 1 implementation

---

## Appendix A: Attribute Quick Reference

### Required Span Attributes
- `http.method`, `http.status_code` (HTTP spans)
- `db.system`, `db.operation` (DB spans)
- `chiseai.service.type` (all spans)
- `chiseai.performance.duration_ms` (all spans)

### Required Resource Attributes
- `service.name`
- `service.version`
- `deployment.environment`

### Sampling Configuration
```bash
# Environment variables
export TEMPO_SAMPLE_RATE=0.1  # 10% in prod
export TEMPO_ENVIRONMENT=prod  # dev, staging, prod
```

## Appendix B: Common TraceQL Queries

### Find All Errors
```traceql
{ status = error }
```

### Find API Requests by User
```traceql
{ .chiseai.service.type = "api" && .chiseai.user.id = "user-12345" }
```

### Find Strategy Executions
```traceql
{ .chiseai.strategy.id != "" }
```

### Find Slow Database Queries
```traceql
{ .db.system = "postgresql" && duration > 100ms }
```

### Find Cache Misses
```traceql
{ .chiseai.cache.operation = "get" && .chiseai.cache.hit = false }
```

## Appendix C: Environment Configuration

### Development
```bash
export TEMPO_SAMPLE_RATE=1.0
export TEMPO_ENDPOINT=http://chiseai-tempo:4317
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=dev"
```

### Staging
```bash
export TEMPO_SAMPLE_RATE=0.5
export TEMPO_ENDPOINT=http://chiseai-tempo:4317
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=staging"
```

### Production
```bash
export TEMPO_SAMPLE_RATE=0.1
export TEMPO_ENDPOINT=http://chiseai-tempo:4317
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=prod"
```

## Appendix D: Performance Targets

| Metric | Target | Maximum |
|--------|--------|---------|
| Span export latency | < 100ms | 500ms |
| Memory overhead | < 50 MB | 100 MB |
| CPU overhead | < 5% | 10% |
| Network overhead | < 1 Mbps | 5 Mbps |
| Trace completeness | > 99% | - |
