# ChiseAI Trace Schema Design

**Story ID:** TEMPO-2026-001  
**Phase:** 0 (Preflight)  
**Date:** 2026-03-13  
**Status:** Complete

## 1. Executive Summary

This document defines the OpenTelemetry trace schema for the ChiseAI platform, including span attributes, resource attributes, baggage specification, and sampling strategy for distributed tracing with Grafana Tempo.

## 2. Design Principles

- Follow OpenTelemetry semantic conventions v1.20+
- Use chiseai. prefix for custom attributes
- Support 7 core services: API, strategy engine, data ingestion, database, Redis, workers
- Storage-efficient design targeting ~500 bytes per span

## 3. Span Attributes

### 3.1 Standard OpenTelemetry HTTP Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| http.method | string | HTTP request method | GET, POST |
| http.url | string | Full request URL | https://api.chise.ai/v1/trades |
| http.target | string | Request target path | /v1/trades |
| http.host | string | Request host | api.chise.ai |
| http.scheme | string | Protocol scheme | https |
| http.status_code | int | Response status code | 200, 404 |
| http.response_content_length | int | Response body size | 1024 |
| http.request_content_length | int | Request body size | 256 |
| http.route | string | Route template | /v1/trades/{id} |

### 3.2 Standard OpenTelemetry Database Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| db.system | string | Database system | postgresql, redis |
| db.connection_string | string | Connection string (sanitized) | postgresql://user@host/db |
| db.user | string | Database user | chiseai_app |
| db.statement | string | Database statement (sanitized) | SELECT * FROM trades |
| db.operation | string | Operation name | SELECT, INSERT |
| db.sql.table | string | Table name | trades |
| db.response.returned_rows | int | Rows returned | 100 |

### 3.3 Standard OpenTelemetry Messaging Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| messaging.system | string | Message broker | redis, kafka |
| messaging.destination | string | Queue/topic name | trade-queue |
| messaging.operation | string | Operation | send, receive, process |
| messaging.message_id | string | Message ID | msg-abc123 |
| messaging.conversation_id | string | Conversation ID | conv-xyz789 |
| messaging.batch_size | int | Batch size | 100 |

### 3.4 Custom ChiseAI Attributes

#### Service Identification
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.service.type | string | Service category | api, strategy, ingestion |
| chiseai.service.group | string | Service group | trading, data, infrastructure |
| chiseai.service.instance | string | Instance identifier | api-01, strategy-worker-03 |

#### Strategy Execution
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.strategy.id | string | Strategy identifier | momentum-v2 |
| chiseai.strategy.version | string | Strategy version | 2.1.0 |
| chiseai.execution.id | string | Execution run ID | exec-20260313-001 |
| chiseai.execution.mode | string | Execution mode | backtest, paper, live |
| chiseai.signal.id | string | Signal identifier | sig-abc123 |
| chiseai.signal.strength | float | Signal strength | 0.85 |
| chiseai.signal.timestamp | string | Signal generation time | 2026-03-13T12:00:00Z |

#### Trading Operations
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.trade.id | string | Trade identifier | trade-xyz789 |
| chiseai.trade.symbol | string | Trading symbol | BTCUSDT |
| chiseai.trade.side | string | Trade side | buy, sell |
| chiseai.trade.quantity | float | Trade quantity | 0.5 |
| chiseai.trade.price | float | Trade price | 65000.00 |
| chiseai.trade.status | string | Trade status | pending, filled, cancelled |
| chiseai.order.type | string | Order type | market, limit, stop |
| chiseai.order.exchange | string | Exchange name | bybit, binance |

#### User Context
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.user.id | string | User identifier | user-12345 |
| chiseai.user.tier | string | User tier | free, pro, enterprise |
| chiseai.user.plan | string | Subscription plan | basic, premium |
| chiseai.user.session_id | string | Session identifier | sess-abc123 |

#### Data Pipeline
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.data.source | string | Data source | bybit, binance, coinbase |
| chiseai.data.type | string | Data type | ohlcv, orderbook, trades |
| chiseai.data.symbol | string | Data symbol | BTCUSDT |
| chiseai.data.interval | string | Data interval | 1m, 5m, 1h, 1d |
| chiseai.ingestion.batch_id | string | Batch identifier | batch-20260313-001 |
| chiseai.ingestion.records_count | int | Records in batch | 1000 |
| chiseai.ingestion.latency_ms | int | Ingestion latency | 150 |
| chiseai.ingestion.source_timestamp | string | Source timestamp | 2026-03-13T12:00:00Z |

#### Error Tracking
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.error.type | string | Error type | validation, execution, network |
| chiseai.error.code | string | Error code | E1001, E2002 |
| chiseai.error.severity | string | Error severity | warning, error, critical |
| chiseai.error.retryable | boolean | Is retryable | true, false |
| chiseai.error.service | string | Service that failed | strategy-engine |
| chiseai.error.details | string | Error details JSON | {"field": "invalid"} |

#### Performance Metrics
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.performance.duration_ms | float | Operation duration | 45.5 |
| chiseai.performance.queue_wait_ms | float | Queue wait time | 12.3 |
| chiseai.performance.processing_ms | float | Processing time | 33.2 |
| chiseai.performance.cpu_percent | float | CPU usage | 15.5 |
| chiseai.performance.memory_mb | float | Memory usage | 128.5 |
| chiseai.performance.io_read_bytes | int | IO read bytes | 1024 |
| chiseai.performance.io_write_bytes | int | IO write bytes | 512 |

#### Cache Attributes
| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.cache.operation | string | Cache operation | get, set, delete |
| chiseai.cache.key | string | Cache key (hashed) | a1b2c3d4 |
| chiseai.cache.hit | boolean | Cache hit | true, false |
| chiseai.cache.ttl_seconds | int | TTL in seconds | 3600 |

## 4. Resource Attributes

### 4.1 Required Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| service.name | string | Service name | chiseai-api |
| service.version | string | Service version | 1.2.3 or git SHA |
| deployment.environment | string | Environment | dev, staging, prod |

### 4.2 Host/Container Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| host.name | string | Hostname | server-01 |
| host.arch | string | Architecture | x86_64, arm64 |
| container.id | string | Container ID | abc123def456 |
| container.name | string | Container name | chiseai-api |
| container.image.name | string | Image name | chiseai-api:latest |
| container.image.tag | string | Image tag | v1.2.3 |

### 4.3 Process Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| process.pid | int | Process ID | 12345 |
| process.runtime.name | string | Runtime | cpython |
| process.runtime.version | string | Runtime version | 3.13.7 |
| process.runtime.description | string | Runtime description | CPython 3.13.7 |
| process.command | string | Command line | python -m chiseai.api |
| process.command_args | string | Command arguments | --port 8001 |

### 4.4 ChiseAI-Specific Resource Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| chiseai.service.group | string | Service group | trading, data |
| chiseai.service.tier | string | Service tier | critical, standard |
| chiseai.deployment.region | string | Deployment region | us-east-1 |
| chiseai.deployment.cluster | string | Cluster name | production-01 |
| chiseai.deployment.node | string | Node identifier | node-01 |

## 5. Baggage Specification

### 5.1 Standard Baggage Keys

| Key | Description | Example | Propagation |
|-----|-------------|---------|-------------|
| user.id | User identifier | user-12345 | All services |
| user.tier | User tier | enterprise | All services |
| request.id | Request identifier | req-abc123 | All services |
| request.priority | Request priority | high, normal, low | All services |
| trace.origin | Origin service | api-gateway | All services |
| trace.correlation_id | Correlation ID | corr-xyz789 | All services |

### 5.2 ChiseAI-Specific Baggage Keys

| Key | Description | Example | Propagation |
|-----|-------------|---------|-------------|
| chiseai.strategy.id | Strategy ID | momentum-v2 | Strategy services |
| chiseai.execution.id | Execution ID | exec-001 | Execution services |
| chiseai.trace.priority | Trace priority | 1-10 | All services |
| chiseai.feature.flags | Feature flags | flag1,flag2 | All services |
| chiseai.experiment.id | Experiment ID | exp-abc123 | All services |
| chiseai.session.context | Session context JSON | {"role": "admin"} | All services |

### 5.3 Baggage Constraints

- Maximum 10 baggage keys per trace
- Maximum 256 characters per key name
- Maximum 8192 bytes total baggage size
- String values only
- No sensitive data (PII, credentials)
- Keys are case-sensitive
- Values should be URL-encoded if they contain special characters
- Nested JSON should be minimized to reduce overhead

## 6. Sampling Strategy

### 6.1 Head-Based Sampling

Head-based sampling makes the sampling decision at the start of the request.

| Environment | Default Rate | Override Variable |
|-------------|--------------|-------------------|
| dev | 100% | TEMPO_SAMPLE_RATE=1.0 |
| staging | 50% | TEMPO_SAMPLE_RATE=0.5 |
| prod | 10% | TEMPO_SAMPLE_RATE=0.1 |
| prod-debug | 100% | TEMPO_SAMPLE_RATE=1.0 (temporary) |

**Configuration:**
```python
# Environment-based sampling
sample_rate = float(os.getenv("TEMPO_SAMPLE_RATE", "0.1"))
sampler = TraceIdRatioBased(sample_rate)
```

### 6.2 Tail-Based Sampling Rules

Tail-based sampling makes the decision after the trace completes, allowing selective retention.

**Rule Priority (highest to lowest):**

1. **Error Rule** (Priority: 100)
   - Condition: Any span with error status or exception event
   - Action: Always keep
   - Rationale: Errors are rare and critical for debugging

2. **Slow API Request Rule** (Priority: 90)
   - Condition: HTTP request duration > 500ms
   - Action: Always keep
   - Rationale: Performance issues need investigation

3. **Slow Strategy Execution Rule** (Priority: 85)
   - Condition: Strategy execution duration > 2000ms
   - Action: Always keep
   - Rationale: Strategy performance impacts trading

4. **Slow Ingestion Rule** (Priority: 80)
   - Condition: Data ingestion duration > 10000ms
   - Action: Always keep
   - Rationale: Data pipeline issues affect all services

5. **Enterprise User Rule** (Priority: 70)
   - Condition: user.tier = "enterprise"
   - Action: Always keep
   - Rationale: Enterprise customers get full observability

6. **Strategy Execution Rule** (Priority: 50)
   - Condition: chiseai.service.type = "strategy"
   - Action: 50% sample
   - Rationale: Strategy traces are voluminous

7. **Trade Operation Rule** (Priority: 40)
   - Condition: chiseai.trade.id exists
   - Action: 25% sample
   - Rationale: Trade traces are numerous

8. **Default Rule** (Priority: 0)
   - Condition: All other traces
   - Action: Apply head-based rate
   - Rationale: Standard sampling for normal traffic

### 6.3 Storage Impact Calculation

**Assumptions:**
- 1000 spans/second at 100% sampling
- Average span size: 500 bytes
- Retention: 7 days

**Storage by Environment:**
| Environment | Sampling Rate | Daily Volume | 7-Day Total |
|-------------|---------------|--------------|-------------|
| dev | 100% | 41.5 GB | 290.5 GB |
| staging | 50% | 20.8 GB | 145.3 GB |
| prod | 10% | 4.2 GB | 29.1 GB |

**Recommended Storage Allocation:**
- Production: 50 GB (includes headroom)
- Staging: 200 GB
- Development: 350 GB

## 7. Attribute Naming Conventions

### 7.1 General Rules

1. **Use snake_case**: All lowercase with underscores
   - ✅ `http.status_code`
   - ❌ `http.statusCode`, `HTTP_STATUS_CODE`

2. **Use dots for namespacing**: Group related attributes
   - ✅ `chiseai.strategy.id`
   - ❌ `chiseai_strategy_id`

3. **Prefix custom attributes**: Use `chiseai.` prefix
   - ✅ `chiseai.trade.symbol`
   - ❌ `trade_symbol`, `tradeSymbol`

4. **Follow OTel conventions**: Use standard names where they exist
   - ✅ `http.method`
   - ❌ `http_method`, `http_verb`

5. **Be consistent**: Use the same name for the same concept
   - ✅ `chiseai.user.id` everywhere
   - ❌ `user.id` in one place, `user_id` in another

### 7.2 Value Constraints

1. **String values**: Use descriptive, consistent values
   - ✅ `status: "filled"`
   - ❌ `status: "1"`, `status: "FILLED"`

2. **Numeric values**: Use appropriate units in attribute names
   - ✅ `duration_ms: 1500`
   - ❌ `duration: 1.5` (ambiguous unit)

3. **Boolean values**: Use positive naming
   - ✅ `is_retryable: true`
   - ❌ `is_not_retryable: false`

4. **Timestamp values**: Use ISO 8601 format in UTC
   - ✅ `timestamp: "2026-03-13T12:00:00Z"`
   - ❌ `timestamp: "2026-03-13 12:00:00"`

5. **Enum values**: Use lowercase with hyphens or underscores
   - ✅ `status: "in-progress"`, `status: "completed"`
   - ❌ `status: "In Progress"`, `status: "COMPLETED"`

## 8. Cardinality Guidelines

### 8.1 High-Cardinality Warning

Avoid attributes with unbounded cardinality:

| Attribute | Cardinality | Risk Level |
|-----------|-------------|------------|
| chiseai.user.id | High (thousands) | ⚠️ Medium |
| chiseai.trade.id | Very High (millions) | 🔴 High |
| chiseai.execution.id | Very High (millions) | 🔴 High |
| chiseai.signal.id | Very High (millions) | 🔴 High |
| chiseai.ingestion.batch_id | High (thousands) | ⚠️ Medium |
| chiseai.strategy.id | Low (tens) | 🟢 Low |
| chiseai.trade.symbol | Low (hundreds) | 🟢 Low |
| chiseai.trade.status | Low (single digits) | 🟢 Low |

### 8.2 Mitigation Strategies

1. **Use enums for status fields**
   - ✅ `status: "pending"`, `status: "filled"`
   - ❌ `status: "pending_20260313_001"`

2. **Hash high-cardinality IDs for grouping**
   - Use `trade.id_hash` (first 8 chars) instead of full ID
   - Example: `chiseai.trade.id_short: "abc123de"`

3. **Limit attribute count**
   - Maximum 50 attributes per span
   - Prioritize most valuable attributes
   - Consider using events for detailed data

4. **Use sampling for high-volume operations**
   - Apply lower sampling rates to high-cardinality spans
   - Use tail-based sampling to capture errors regardless

5. **Regular cardinality audits**
   - Monitor attribute cardinality weekly
   - Alert on sudden cardinality increases
   - Document approved high-cardinality attributes

## 9. Service Span Examples

### 9.1 API HTTP Request Span

```json
{
  "trace_id": "abc123...",
  "span_id": "def456...",
  "parent_span_id": null,
  "name": "GET /v1/trades",
  "kind": "SERVER",
  "start_time": "2026-03-13T12:00:00Z",
  "end_time": "2026-03-13T12:00:00.150Z",
  "attributes": {
    "http.method": "GET",
    "http.url": "https://api.chise.ai/v1/trades?symbol=BTCUSDT",
    "http.route": "/v1/trades",
    "http.status_code": 200,
    "http.response_content_length": 2048,
    "chiseai.service.type": "api",
    "chiseai.user.id": "user-12345",
    "chiseai.user.tier": "enterprise",
    "chiseai.performance.duration_ms": 150.0
  },
  "resource": {
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": "prod"
  }
}
```

### 9.2 Strategy Execution Span

```json
{
  "trace_id": "abc123...",
  "span_id": "ghi789...",
  "parent_span_id": null,
  "name": "strategy.execute",
  "kind": "INTERNAL",
  "start_time": "2026-03-13T12:00:00Z",
  "end_time": "2026-03-13T12:00:02.500Z",
  "attributes": {
    "chiseai.strategy.id": "momentum-v2",
    "chiseai.strategy.version": "2.1.0",
    "chiseai.execution.id": "exec-20260313-001",
    "chiseai.execution.mode": "live",
    "chiseai.signal.id": "sig-abc123",
    "chiseai.signal.strength": 0.85,
    "chiseai.performance.duration_ms": 2500.0,
    "chiseai.performance.queue_wait_ms": 100.0
  },
  "resource": {
    "service.name": "chiseai-strategy",
    "service.version": "2.0.0",
    "deployment.environment": "prod"
  }
}
```

### 9.3 Database Query Span

```json
{
  "trace_id": "abc123...",
  "span_id": "jkl012...",
  "parent_span_id": "def456...",
  "name": "SELECT trades",
  "kind": "CLIENT",
  "start_time": "2026-03-13T12:00:00.050Z",
  "end_time": "2026-03-13T12:00:00.100Z",
  "attributes": {
    "db.system": "postgresql",
    "db.operation": "SELECT",
    "db.sql.table": "trades",
    "db.statement": "SELECT * FROM trades WHERE user_id = $1",
    "db.response.returned_rows": 50,
    "chiseai.performance.duration_ms": 50.0
  },
  "resource": {
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": "prod"
  }
}
```

### 9.4 Redis Operation Span

```json
{
  "trace_id": "abc123...",
  "span_id": "mno345...",
  "parent_span_id": "def456...",
  "name": "GET",
  "kind": "CLIENT",
  "start_time": "2026-03-13T12:00:00.010Z",
  "end_time": "2026-03-13T12:00:00.015Z",
  "attributes": {
    "db.system": "redis",
    "db.operation": "GET",
    "db.statement": "GET user:12345:profile",
    "chiseai.cache.operation": "get",
    "chiseai.cache.key": "a1b2c3d4",
    "chiseai.cache.hit": true,
    "chiseai.performance.duration_ms": 5.0
  },
  "resource": {
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": "prod"
  }
}
```

### 9.5 Data Ingestion Span

```json
{
  "trace_id": "abc123...",
  "span_id": "pqr678...",
  "parent_span_id": null,
  "name": "ingestion.batch",
  "kind": "CONSUMER",
  "start_time": "2026-03-13T12:00:00Z",
  "end_time": "2026-03-13T12:00:05Z",
  "attributes": {
    "chiseai.data.source": "bybit",
    "chiseai.data.type": "ohlcv",
    "chiseai.data.symbol": "BTCUSDT",
    "chiseai.data.interval": "1m",
    "chiseai.ingestion.batch_id": "batch-20260313-001",
    "chiseai.ingestion.records_count": 1000,
    "chiseai.ingestion.latency_ms": 5000,
    "chiseai.performance.duration_ms": 5000.0
  },
  "resource": {
    "service.name": "chiseai-ingestion",
    "service.version": "1.0.0",
    "deployment.environment": "prod"
  }
}
```

### 9.6 Error Span

```json
{
  "trace_id": "abc123...",
  "span_id": "stu901...",
  "parent_span_id": "def456...",
  "name": "trade.execute",
  "kind": "INTERNAL",
  "start_time": "2026-03-13T12:00:00Z",
  "end_time": "2026-03-13T12:00:00.200Z",
  "status": {
    "code": "ERROR",
    "message": "Insufficient balance"
  },
  "attributes": {
    "chiseai.trade.id": "trade-xyz789",
    "chiseai.trade.symbol": "BTCUSDT",
    "chiseai.trade.side": "buy",
    "chiseai.error.type": "execution",
    "chiseai.error.code": "E1001",
    "chiseai.error.severity": "error",
    "chiseai.error.retryable": false,
    "chiseai.performance.duration_ms": 200.0
  },
  "events": [
    {
      "name": "exception",
      "timestamp": "2026-03-13T12:00:00.200Z",
      "attributes": {
        "exception.type": "InsufficientBalanceError",
        "exception.message": "Account balance too low for trade",
        "exception.stacktrace": "..."
      }
    }
  ],
  "resource": {
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": "prod"
  }
}
```

### 9.7 Messaging Span

```json
{
  "trace_id": "abc123...",
  "span_id": "vwx234...",
  "parent_span_id": null,
  "name": "trade-queue send",
  "kind": "PRODUCER",
  "start_time": "2026-03-13T12:00:00Z",
  "end_time": "2026-03-13T12:00:00.010Z",
  "attributes": {
    "messaging.system": "redis",
    "messaging.destination": "trade-queue",
    "messaging.operation": "send",
    "messaging.message_id": "msg-abc123",
    "chiseai.trade.id": "trade-xyz789",
    "chiseai.performance.duration_ms": 10.0
  },
  "resource": {
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": "prod"
  }
}
```

## 10. Implementation Notes

### 10.1 OpenTelemetry SDK Configuration

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
import os

# Resource configuration
resource = Resource.create({
    "service.name": "chiseai-api",
    "service.version": "1.2.3",
    "deployment.environment": os.getenv("DEPLOYMENT_ENV", "dev")
})

# Tracer provider
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# OTLP exporter to Tempo
exporter = OTLPSpanExporter(
    endpoint="http://chiseai-tempo:4317"
)
processor = BatchSpanProcessor(
    exporter,
    max_queue_size=2048,
    max_export_batch_size=512,
    schedule_delay_millis=5000
)
provider.add_span_processor(processor)
```

### 10.2 Sampling Configuration

```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Head-based sampling
sample_rate = float(os.getenv("TEMPO_SAMPLE_RATE", "0.1"))
sampler = TraceIdRatioBased(sample_rate)
provider = TracerProvider(sampler=sampler, resource=resource)
```

### 10.3 Baggage Propagation

```python
from opentelemetry.baggage import set_baggage, get_baggage
from opentelemetry.propagate import extract, inject

# Set baggage
set_baggage("user.id", "user-12345")
set_baggage("chiseai.strategy.id", "momentum-v2")
set_baggage("chiseai.execution.id", "exec-001")

# Propagate in HTTP headers
carrier = {}
inject(carrier)
# carrier now contains: {"traceparent": "...", "baggage": "user.id=user-12345,..."}

# Extract baggage from incoming request
context = extract(carrier)
user_id = get_baggage("user.id", context)
```

### 10.4 Custom Span Creation

```python
from opentelemetry import trace

tracer = trace.get_tracer("chiseai.api")

# Create a span with attributes
with tracer.start_as_current_span(
    "trade.execute",
    attributes={
        "chiseai.trade.id": trade_id,
        "chiseai.trade.symbol": symbol,
        "chiseai.trade.side": side,
    }
) as span:
    # Add more attributes dynamically
    span.set_attribute("chiseai.trade.status", "pending")
    
    # Record events
    span.add_event("validation.started")
    
    # Execute trade logic
    result = execute_trade(trade_id)
    
    span.add_event("validation.completed", {
        "validation.duration_ms": 50.0
    })
    
    # Set status on error
    if result.error:
        span.set_status(Status(StatusCode.ERROR, result.error.message))
        span.set_attribute("chiseai.error.code", result.error.code)
```

## 11. TraceQL Query Examples

### 11.1 Find Slow API Requests

```traceql
{ .chiseai.service.type = "api" && .http.duration > 500ms }
```

### 11.2 Find Failed Trades

```traceql
{ .chiseai.trade.id != "" && status = error }
```

### 11.3 Find Strategy Executions by User

```traceql
{ .chiseai.strategy.id = "momentum-v2" && .chiseai.user.id = "user-12345" }
```

### 11.4 Find Slow Database Queries

```traceql
{ .db.system = "postgresql" && .db.statement =~ ".*SELECT.*trades.*" && duration > 100ms }
```

### 11.5 Find High-Latency Ingestion

```traceql
{ .chiseai.ingestion.latency_ms > 10000 }
```

## 12. References

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
- [OpenTelemetry Trace API](https://opentelemetry.io/docs/instrumentation/python/api/tracing/)
- [Grafana Tempo Documentation](https://grafana.com/docs/tempo/latest/)
- [Tempo TraceQL Query Language](https://grafana.com/docs/tempo/latest/traceql/)
- [OpenTelemetry Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [OTLP Protocol Specification](https://opentelemetry.io/docs/specs/otlp/)

## 13. Document History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-03-13 | 1.0 | senior-dev | Initial schema design |
| 2026-03-13 | 1.1 | senior-dev | Added messaging attributes and cache attributes sections |
| 2026-03-13 | 1.2 | senior-dev | Added TraceQL query examples and implementation code snippets |
