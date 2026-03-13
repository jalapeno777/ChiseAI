# ChiseAI Trace Schema Design

**Story ID:** TEMPO-2026-001  
**Phase:** 0 (Preflight)  
**Task:** 0.2 - Design trace schema and sampling strategy  
**Date:** 2026-03-13  
**Author:** senior-dev  

---

## Executive Summary

This document defines the trace schema, resource attributes, baggage, and sampling strategy for ChiseAI's distributed tracing implementation using OpenTelemetry and Grafana Tempo. The design is based on Task 0.1 findings which identified a **completely greenfield tracing deployment** with no existing infrastructure.

### Key Design Decisions

| Decision | Value | Rationale |
|----------|-------|-----------|
| **Sampling Strategy** | Head-based 10% (prod), 100% (dev) | Balance visibility vs. storage cost |
| **Span Size Target** | ~500 bytes average | Storage efficiency from Task 0.1 |
| **Retention** | 7 days default, 14 days optional | Aligns with ~25-50 GB storage budget |
| **Schema Version** | OTel 1.20+ | Latest stable conventions |
| **Propagation** | W3C Trace Context | Industry standard, broad support |

---

## 1. Span Attributes Reference

### 1.1 Standard OpenTelemetry Attributes

All spans MUST include these standard OTel semantic convention attributes:

#### HTTP Attributes (for API services)

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `http.method` | string | Yes | HTTP request method | `GET`, `POST` |
| `http.url` | string | Yes | Full request URL | `https://api.chise.ai/v1/trades` |
| `http.target` | string | Yes | Request target (path + query) | `/v1/trades?status=open` |
| `http.host` | string | Yes | Host header value | `api.chise.ai` |
| `http.scheme` | string | Yes | Protocol scheme | `https` |
| `http.status_code` | int | Yes | HTTP response status code | `200`, `500` |
| `http.response_content_length` | int | No | Response body size in bytes | `1024` |
| `http.request_content_length` | int | No | Request body size in bytes | `256` |
| `http.route` | string | No | Route template | `/v1/trades/{trade_id}` |
| `http.client_ip` | string | No | Client IP address | `192.168.1.1` |

#### Database Attributes (for SQL operations)

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `db.system` | string | Yes | Database type | `postgresql` |
| `db.connection_string` | string | No | Connection string (sanitized) | `postgresql://host:5432/db` |
| `db.user` | string | No | Database user | `chiseai_app` |
| `db.statement` | string | No | SQL statement (sanitized) | `SELECT * FROM trades WHERE...` |
| `db.operation` | string | No | Operation type | `SELECT`, `INSERT` |
| `db.sql.table` | string | No | Table name | `trades` |
| `db.response.returned_rows` | int | No | Rows returned | `42` |

#### Cache Attributes (for Redis operations)

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `db.system` | string | Yes | Database type | `redis` |
| `db.redis.database_index` | int | No | Redis database number | `0` |
| `db.operation` | string | Yes | Redis command | `GET`, `SET`, `HGET` |
| `db.statement` | string | No | Full command (sanitized) | `GET user:123:profile` |

#### Messaging Attributes (for async jobs)

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `messaging.system` | string | Yes | Message broker | `redis` (for RQ) |
| `messaging.destination` | string | Yes | Queue/topic name | `strategy_execution` |
| `messaging.destination_kind` | string | Yes | `queue` or `topic` | `queue` |
| `messaging.operation` | string | Yes | `send`, `receive`, `process` | `process` |
| `messaging.message_id` | string | No | Message identifier | `msg_abc123` |
| `messaging.conversation_id` | string | No | Conversation identifier | `conv_xyz789` |

### 1.2 Custom ChiseAI Attributes

These attributes are specific to ChiseAI business logic:

#### Strategy Execution

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `chiseai.strategy.id` | string | Yes | Strategy identifier | `grid_btc_usdt_v1` |
| `chiseai.strategy.type` | string | Yes | Strategy type | `grid`, `momentum`, `arbitrage` |
| `chiseai.strategy.version` | string | Yes | Strategy version | `1.2.3` |
| `chiseai.strategy.params` | string | No | Key params (JSON, limited) | `{"grid_count": 10}` |
| `chiseai.execution.id` | string | Yes | Execution run ID | `exec_20240313_001` |
| `chiseai.execution.trigger` | string | No | What triggered execution | `schedule`, `manual`, `signal` |

#### Trading Operations

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `chiseai.trade.id` | string | Yes | Trade identifier | `trade_abc123` |
| `chiseai.trade.side` | string | Yes | Buy or sell | `buy`, `sell` |
| `chiseai.trade.symbol` | string | Yes | Trading pair | `BTC-USDT` |
| `chiseai.trade.exchange` | string | Yes | Exchange name | `binance`, `okx` |
| `chiseai.trade.quantity` | float | No | Trade quantity | `0.5` |
| `chiseai.trade.price` | float | No | Execution price | `65000.00` |
| `chiseai.trade.status` | string | Yes | Trade status | `filled`, `partial`, `failed` |
| `chiseai.order.id` | string | Yes | Order identifier | `order_xyz789` |
| `chiseai.order.type` | string | No | Order type | `limit`, `market` |

#### User Context

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `chiseai.user.id` | string | Conditional | User identifier (if authenticated) | `user_12345` |
| `chiseai.user.tier` | string | No | User subscription tier | `free`, `pro`, `enterprise` |
| `chiseai.session.id` | string | No | Session identifier | `sess_abc123` |
| `chiseai.request.id` | string | Yes | Unique request ID | `req_20240313_uuid` |

#### Data Pipeline

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `chiseai.data.source` | string | Yes | Data source name | `binance_ohlcv` |
| `chiseai.data.symbol` | string | Yes | Data symbol | `BTC-USDT` |
| `chiseai.data.timeframe` | string | Yes | Data timeframe | `1h`, `1d` |
| `chiseai.data.records` | int | No | Records processed | `1000` |
| `chiseai.data.freshness_ms` | int | No | Data age in milliseconds | `60000` |
| `chiseai.ingestion.batch_id` | string | Yes | Ingestion batch ID | `batch_20240313_001` |

### 1.3 Error Attributes

All error spans MUST include:

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `error.type` | string | Yes | Error type/class | `ValueError`, `HTTPException` |
| `error.message` | string | Yes | Human-readable error | `Invalid trade quantity` |
| `error.stacktrace` | string | No | Stack trace (truncated) | `File "...", line 42...` |
| `error.code` | string | No | Application error code | `E_TRADE_001` |
| `error.retryable` | bool | No | Can be retried | `false` |

### 1.4 Performance Attributes

| Attribute | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `execution.duration_ms` | float | Calculated | Span duration (auto) | `150.5` |
| `queue.wait_time_ms` | float | No | Time spent in queue | `25.0` |
| `processing.time_ms` | float | No | Actual processing time | `125.5` |
| `serialization.time_ms` | float | No | Serialization overhead | `5.0` |
| `network.latency_ms` | float | No | Network round-trip | `50.0` |

---

## 2. Resource Attributes Reference

Resource attributes describe the entity producing telemetry. These are set once per process and attached to all spans.

### 2.1 Required Resource Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `service.name` | string | Logical service name | `chiseai-api`, `chiseai-strategy` |
| `service.version` | string | Service version | `1.2.3` or git SHA `abc123d` |
| `service.instance.id` | string | Unique instance ID | `instance_abc123` |
| `deployment.environment` | string | Deployment environment | `dev`, `staging`, `prod` |

### 2.2 Host/Container Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `host.name` | string | Hostname | `chiseai-api-01` |
| `host.arch` | string | CPU architecture | `amd64`, `arm64` |
| `container.id` | string | Docker container ID | `a1b2c3d4...` |
| `container.name` | string | Docker container name | `chiseai-api-final` |
| `container.image.name` | string | Container image | `chiseai-api:latest` |
| `container.image.tag` | string | Image tag | `v1.2.3` |

### 2.3 Process Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `process.pid` | int | Process ID | `42` |
| `process.executable.name` | string | Executable name | `python` |
| `process.executable.path` | string | Executable path | `/usr/bin/python3.11` |
| `process.command` | string | Full command | `python -m uvicorn main:app` |
| `process.runtime.name` | string | Runtime name | `cpython` |
| `process.runtime.version` | string | Runtime version | `3.11.4` |

### 2.4 ChiseAI-Specific Resource Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `chiseai.service.type` | string | Service category | `api`, `worker`, `ingestion` |
| `chiseai.service.group` | string | Service group | `core`, `data`, `analytics` |
| `chiseai.cluster` | string | Cluster name | `main`, `analytics` |
| `chiseai.region` | string | Deployment region | `us-east-1`, `eu-west-1` |

---

## 3. Baggage Specification

Baggage provides cross-service context propagation. Use sparingly as it adds overhead to every request.

### 3.1 Standard Baggage Keys

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `user.id` | string | Authenticated user ID | `user_12345` |
| `user.tier` | string | User subscription tier | `pro` |
| `request.id` | string | Request correlation ID | `req_abc123` |
| `session.id` | string | Session identifier | `sess_xyz789` |

### 3.2 ChiseAI Baggage Keys

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `chiseai.strategy.id` | string | Strategy being executed | `grid_btc_v1` |
| `chiseai.execution.id` | string | Execution run ID | `exec_001` |
| `chiseai.trace.priority` | string | Priority for tail sampling | `high`, `low` |
| `chiseai.feature.flags` | string | Active feature flags | `new_engine,beta_ui` |

### 3.3 Baggage Constraints

- **Maximum keys per request:** 10
- **Maximum key length:** 256 characters
- **Maximum value length:** 8192 characters
- **Total baggage size:** Maximum 8192 bytes
- **Propagation:** Only propagate baggage when necessary

### 3.4 Baggage Usage Guidelines

**DO use baggage for:**
- User identification across service boundaries
- Request correlation through async workflows
- Feature flag propagation
- A/B test group assignment

**DON'T use baggage for:**
- Large data payloads
- Sensitive information (PII)
- Data that changes frequently within a request
- Information already available in span attributes

---

## 4. Sampling Strategy

### 4.1 Head-Based Sampling

Head-based sampling makes the sampling decision at the start of the trace.

#### Default Sampling Rates

| Environment | Rate | Use Case |
|-------------|------|----------|
| `dev` | 100% | Full visibility during development |
| `staging` | 50% | Pre-production testing |
| `prod` | 10% | Production with cost control |
| `prod-debug` | 100% | Emergency debugging (temporary) |

#### Configuration

```yaml
# Environment variable
TEMPO_SAMPLE_RATE=0.1  # 10% sampling

# Or in config
sampling:
  strategy: head_based
  rate: 0.1
  parent_based: true  # Respect parent sampling decision
```

### 4.2 Tail-Based Sampling

Tail-based sampling makes the decision after the trace completes, allowing selective retention.

#### Tail Sampling Rules (Priority Order)

| Priority | Rule | Condition | Action |
|----------|------|-----------|--------|
| 1 | **Error Rule** | Any span has `error.type` | **KEEP** |
| 2 | **Slow Request Rule** | Root span duration > 500ms | **KEEP** |
| 3 | **High Value Rule** | `chiseai.user.tier=enterprise` | **KEEP** |
| 4 | **Strategy Execution Rule** | `chiseai.execution.id` present | 50% sample |
| 5 | **Default Rule** | All other traces | Apply head-based rate |

#### Error Span Sampling

All error spans are always sampled (100% retention):

```python
# Pseudo-code for error rule
def should_sample(trace):
    for span in trace.spans:
        if span.attributes.get("error.type"):
            return True  # Always keep errors
    return apply_head_based_sampling(trace)
```

#### Slow Span Thresholds

| Service Type | Threshold | Rationale |
|--------------|-----------|-----------|
| API (FastAPI) | > 500ms | User-facing latency SLA |
| Strategy Execution | > 2000ms | Batch processing tolerance |
| Data Ingestion | > 5000ms | Large batch operations |
| Database Query | > 100ms | Query performance baseline |
| Redis Operation | > 10ms | Cache should be fast |

### 4.3 Sampling Configuration Example

```yaml
# tempo-sampling.yaml
sampling:
  head_based:
    default_rate: 0.1
    environment_rates:
      dev: 1.0
      staging: 0.5
      prod: 0.1
  
  tail_based:
    enabled: true
    policies:
      - name: "error_policy"
        type: "always_sample"
        condition: "has_error"
      
      - name: "slow_api_policy"
        type: "latency"
        threshold_ms: 500
        services: ["chiseai-api"]
      
      - name: "slow_strategy_policy"
        type: "latency"
        threshold_ms: 2000
        services: ["chiseai-strategy"]
      
      - name: "enterprise_policy"
        type: "string_attribute"
        key: "chiseai.user.tier"
        values: ["enterprise"]
        sample_rate: 1.0
```

### 4.4 Sampling Overrides

#### Per-Request Override

Clients can force sampling via header:

```http
X-ChiseAI-Force-Trace: true
```

This sets the sampling decision to `RECORD_AND_SAMPLE` for this trace.

#### Per-User Override

Enterprise users can have elevated sampling:

```python
if user.tier == "enterprise":
    trace_config.sample_rate = 1.0  # 100% sampling
```

---

## 5. Attribute Naming Conventions

### 5.1 General Rules

1. **Use snake_case** for all attribute names
2. **Use dot notation** for namespacing: `chiseai.trade.id`
3. **Be descriptive** but concise: prefer `trade.id` over `t_id`
4. **Use consistent terminology** across services
5. **Follow OTel conventions** for standard attributes

### 5.2 Namespace Guidelines

| Namespace | Purpose | Example |
|-----------|---------|---------|
| `http.*` | HTTP protocol attributes | `http.method` |
| `db.*` | Database attributes | `db.system` |
| `messaging.*` | Messaging system attributes | `messaging.destination` |
| `chiseai.*` | ChiseAI-specific attributes | `chiseai.trade.id` |
| `error.*` | Error-related attributes | `error.type` |
| `process.*` | Process attributes | `process.pid` |
| `service.*` | Service attributes | `service.name` |

### 5.3 Value Type Guidelines

| Type | Use For | Example |
|------|---------|---------|
| `string` | IDs, names, enums | `"trade_123"`, `"BTC-USDT"` |
| `int` | Counts, sizes, codes | `200`, `1024` |
| `float` | Durations, prices | `150.5`, `65000.00` |
| `bool` | Flags, states | `true`, `false` |
| `array` | Multiple values (rare) | `["tag1", "tag2"]` |

---

## 6. Cardinality Guidelines

### 6.1 Attribute Cardinality Limits

High-cardinality attributes can explode storage costs and degrade query performance.

| Cardinality Level | Safe For | Avoid For |
|-------------------|----------|-----------|
| **Low** (< 100) | Enums, status codes, service names | - |
| **Medium** (100-10k) | User IDs, strategy IDs, trade IDs | - |
| **High** (10k-1M) | Session IDs, request IDs | Span names, attributes |
| **Unbounded** (> 1M) | Timestamps, UUIDs | Any indexed attribute |

### 6.2 High-Cardinality Attribute Handling

**Instead of high-cardinality attributes, use:**

| Instead Of | Use | Example |
|------------|-----|---------|
| Full timestamp | Bucketed time | `time_bucket: "2024-03-13T10:00:00Z"` |
| Full UUID | Short hash prefix | `request_prefix: "abc123"` |
| Unique session ID | Session bucket | `session_bucket: "hour_10"` |
| Full error message | Error category | `error_category: "validation_error"` |

### 6.3 Cardinality by Attribute

| Attribute | Expected Cardinality | Mitigation |
|-----------|---------------------|------------|
| `chiseai.user.id` | Medium (thousands) | ✅ Acceptable |
| `chiseai.trade.id` | High (millions) | ⚠️ Consider bucketing |
| `chiseai.request.id` | Unbounded | ❌ Use only in logs, not spans |
| `chiseai.strategy.id` | Low (< 100) | ✅ Acceptable |
| `http.url` | High | ❌ Use `http.route` instead |
| `db.statement` | Unbounded | ⚠️ Sanitize, use `db.operation` |

---

## 7. Service-Specific Examples

### 7.1 chiseai-api (FastAPI HTTP Service)

```python
# Example span for API request
{
    "name": "POST /v1/trades",
    "kind": "SERVER",
    "attributes": {
        # Standard HTTP
        "http.method": "POST",
        "http.url": "https://api.chise.ai/v1/trades",
        "http.target": "/v1/trades",
        "http.host": "api.chise.ai",
        "http.scheme": "https",
        "http.status_code": 201,
        "http.route": "/v1/trades",
        
        # ChiseAI
        "chiseai.user.id": "user_12345",
        "chiseai.user.tier": "pro",
        "chiseai.request.id": "req_abc123",
        "chiseai.trade.id": "trade_xyz789",
        "chiseai.trade.symbol": "BTC-USDT",
        "chiseai.trade.side": "buy",
        "chiseai.trade.status": "filled"
    },
    "resource": {
        "service.name": "chiseai-api",
        "service.version": "1.2.3",
        "deployment.environment": "prod"
    }
}
```

### 7.2 chiseai-strategy (Strategy Execution)

```python
# Example span for strategy execution
{
    "name": "execute_strategy",
    "kind": "INTERNAL",
    "attributes": {
        # ChiseAI Strategy
        "chiseai.strategy.id": "grid_btc_usdt_v1",
        "chiseai.strategy.type": "grid",
        "chiseai.strategy.version": "2.1.0",
        "chiseai.execution.id": "exec_20240313_001",
        "chiseai.execution.trigger": "schedule",
        
        # Performance
        "execution.duration_ms": 1250.5,
        "processing.time_ms": 1200.0,
        "queue.wait_time_ms": 50.5
    },
    "resource": {
        "service.name": "chiseai-strategy",
        "service.version": "2.1.0",
        "deployment.environment": "prod"
    }
}
```

### 7.3 chiseai-ingestion (Data Pipeline)

```python
# Example span for data ingestion
{
    "name": "ingest_ohlcv_batch",
    "kind": "CONSUMER",
    "attributes": {
        # ChiseAI Data
        "chiseai.data.source": "binance_ohlcv",
        "chiseai.data.symbol": "BTC-USDT",
        "chiseai.data.timeframe": "1h",
        "chiseai.data.records": 1000,
        "chiseai.data.freshness_ms": 60000,
        "chiseai.ingestion.batch_id": "batch_20240313_001",
        
        # Messaging
        "messaging.system": "redis",
        "messaging.destination": "ohlcv_ingestion",
        "messaging.destination_kind": "queue",
        "messaging.operation": "process"
    },
    "resource": {
        "service.name": "chiseai-ingestion",
        "service.version": "1.0.0",
        "deployment.environment": "prod"
    }
}
```

### 7.4 Database Operations (PostgreSQL)

```python
# Example span for database query
{
    "name": "SELECT trades",
    "kind": "CLIENT",
    "attributes": {
        # Database
        "db.system": "postgresql",
        "db.user": "chiseai_app",
        "db.operation": "SELECT",
        "db.sql.table": "trades",
        "db.statement": "SELECT * FROM trades WHERE user_id = $1",
        "db.response.returned_rows": 42,
        
        # Performance
        "execution.duration_ms": 15.2
    },
    "resource": {
        "service.name": "chiseai-api",
        "service.version": "1.2.3"
    }
}
```

### 7.5 Redis Operations (Cache)

```python
# Example span for Redis operation
{
    "name": "GET user:123:profile",
    "kind": "CLIENT",
    "attributes": {
        # Cache
        "db.system": "redis",
        "db.redis.database_index": 0,
        "db.operation": "GET",
        "db.statement": "GET user:123:profile",
        
        # Performance
        "execution.duration_ms": 0.5,
        "cache.hit": True
    },
    "resource": {
        "service.name": "chiseai-api",
        "service.version": "1.2.3"
    }
}
```

---

## 8. Trace Structure Examples

### 8.1 Full Request Flow (Trade Creation)

```
Trace: req_abc123 (chiseai-api)
├── Span: POST /v1/trades (SERVER) [150ms]
│   ├── Span: auth_middleware (INTERNAL) [5ms]
│   ├── Span: validate_request (INTERNAL) [10ms]
│   ├── Span: SELECT user (CLIENT - postgres) [15ms]
│   │   └── Attributes: db.operation=SELECT, db.sql.table=users
│   ├── Span: GET rate_limit (CLIENT - redis) [0.5ms]
│   │   └── Attributes: db.operation=GET, cache.hit=true
│   ├── Span: create_trade (INTERNAL) [100ms]
│   │   ├── Span: INSERT trade (CLIENT - postgres) [20ms]
│   │   ├── Span: publish_to_exchange (CLIENT - external) [60ms]
│   │   │   └── Attributes: http.url=https://api.binance.com/...
│   │   └── Span: UPDATE trade_status (CLIENT - postgres) [15ms]
│   └── Span: cache_invalidate (CLIENT - redis) [0.5ms]
│       └── Attributes: db.operation=DEL
```

### 8.2 Strategy Execution Flow

```
Trace: exec_20240313_001 (chiseai-strategy)
├── Span: execute_strategy (INTERNAL) [2000ms]
│   ├── Span: load_strategy_config (INTERNAL) [50ms]
│   │   └── Attributes: chiseai.strategy.id=grid_btc_v1
│   ├── Span: fetch_market_data (CLIENT - postgres) [100ms]
│   │   └── Attributes: db.operation=SELECT, chiseai.data.records=100
│   ├── Span: calculate_signals (INTERNAL) [500ms]
│   │   └── Attributes: chiseai.strategy.type=grid
│   ├── Span: evaluate_positions (INTERNAL) [800ms]
│   │   └── Attributes: chiseai.trade.count=5
│   ├── Span: execute_orders (INTERNAL) [400ms]
│   │   ├── Span: POST order (CLIENT - external) [100ms]
│   │   │   └── Attributes: http.url=https://api.exchange.com/order
│   │   └── Span: INSERT order (CLIENT - postgres) [20ms]
│   └── Span: update_metrics (INTERNAL) [50ms]
```

---

## 9. Implementation Checklist

### 9.1 Phase 1: Infrastructure

- [ ] Deploy Tempo container with sampling config
- [ ] Configure OTLP receivers (gRPC: 4317, HTTP: 4318)
- [ ] Set up storage backend (local or S3)
- [ ] Configure retention policies

### 9.2 Phase 2: Application Instrumentation

- [ ] Add OpenTelemetry SDK dependencies
- [ ] Create `src/telemetry/tracing.py` module
- [ ] Configure resource attributes per service
- [ ] Set up span exporters

### 9.3 Phase 3: Service Instrumentation

- [ ] Instrument chiseai-api (FastAPI auto-instrumentation)
- [ ] Instrument chiseai-strategy (manual spans)
- [ ] Instrument chiseai-ingestion (messaging spans)
- [ ] Instrument database operations
- [ ] Instrument Redis operations

### 9.4 Phase 4: Sampling & Validation

- [ ] Configure head-based sampling rates
- [ ] Implement tail-based sampling rules
- [ ] Validate span attribute coverage
- [ ] Test sampling behavior
- [ ] Benchmark overhead

---

## 10. References

### 10.1 OpenTelemetry Conventions

- [OTel Semantic Conventions - HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [OTel Semantic Conventions - Database](https://opentelemetry.io/docs/specs/semconv/database/)
- [OTel Semantic Conventions - Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/)
- [OTel Trace Context - W3C](https://www.w3.org/TR/trace-context/)

### 10.2 Tempo Documentation

- [Grafana Tempo Configuration](https://grafana.com/docs/tempo/latest/configuration/)
- [Tempo Sampling Strategies](https://grafana.com/docs/tempo/latest/configuration/grafana-agent/#tail-based-sampling)
- [TraceQL Query Language](https://grafana.com/docs/tempo/latest/traceql/)

### 10.3 Related Documents

- `docs/observability/audit-current-state.md` - Task 0.1 findings
- `docs/planning/sprints/TEMPO-2026-001-task-0-2-evidence.md` - This task's evidence
- `docs/planning/sprints/TEMPO-2026-001-sprint-plan.md` - Sprint roadmap

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-13 | senior-dev | Initial schema design |

---

**Next Steps:**
1. Review schema with team
2. Approve sampling rates
3. Begin Phase 1: Tempo deployment
4. Implement instrumentation in Phase 3

(End of document)
