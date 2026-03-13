# ChiseAI Trace Schema Design

**Version:** 1.0  
**Date:** 2026-03-13  
**Story ID:** TEMPO-2026-001  
**Status:** Draft  
**Author:** senior-dev  
**Reviewers:** TBD

---

## 1. Executive Summary

### Purpose

This document defines the OpenTelemetry trace schema for the ChiseAI platform, establishing standardized span attributes, resource attributes, baggage specifications, and sampling strategies for distributed tracing across all services.

### Scope

This schema applies to the following services:

1. **API Gateway** (`chiseai-api-final`) - HTTP request handling
2. **Strategy Engine** (`chiseai-brain-scheduler`) - Strategy execution
3. **Data Ingestion** (`chiseai-ohlcv-ingestion`) - Market data ingestion
4. **Data Quality Monitor** (`chiseai-data-quality-monitor`) - Quality checks
5. **Datasource Health Monitor** (`chiseai-datasource-health-monitor`) - Health checks
6. **Daily Summary** (`chiseai-daily-summary`) - Reporting
7. **Kimi Adapter** (`chiseai-kimi-adapter`) - LLM integration

### Compatibility

- **OpenTelemetry Specification:** v1.20+
- **OTLP Protocol:** v1.0+
- **Tempo:** v2.4+
- **Grafana:** v10.4+

### Key Design Principles

1. **Standards Compliance:** Follow OpenTelemetry semantic conventions
2. **Minimal Cardinality:** Avoid high-cardinality attributes
3. **Service-Specific Context:** Capture domain-specific attributes for trading
4. **Performance Aware:** Balance observability with overhead
5. **Security Conscious:** Never include secrets, PII, or sensitive data

---

## 2. Span Attributes

### 2.1 Standard OpenTelemetry Attributes

#### HTTP Attributes (Required for HTTP spans)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `http.method` | string | HTTP request method | `GET`, `POST` |
| `http.url` | string | Full HTTP request URL | `https://api.chiseai.com/v1/trades` |
| `http.target` | string | Request target (path + query) | `/v1/trades?symbol=BTCUSDT` |
| `http.host` | string | Host header value | `api.chiseai.com` |
| `http.scheme` | string | URI scheme | `https` |
| `http.status_code` | int | HTTP response status code | `200`, `404`, `500` |
| `http.response_content_length` | int | Response body size in bytes | `1024` |
| `http.request_content_length` | int | Request body size in bytes | `256` |
| `http.user_agent` | string | User agent string | `ChiseAI-Client/1.0` |
| `http.route` | string | Route template | `/v1/trades/{trade_id}` |

#### Database Attributes (Required for DB spans)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `db.system` | string | Database system identifier | `postgresql`, `redis` |
| `db.connection_string` | string | Connection string (sanitized) | `postgresql://localhost:5434` |
| `db.user` | string | Database user | `chiseai_app` |
| `db.statement` | string | Database statement (sanitized) | `SELECT * FROM trades WHERE id = $1` |
| `db.operation` | string | Operation name | `SELECT`, `INSERT`, `UPDATE` |
| `db.sql.table` | string | Table name | `trades` |
| `db.postgresql.pid` | int | PostgreSQL process ID | `12345` |

#### Messaging Attributes (Required for async operations)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `messaging.system` | string | Messaging system | `redis`, `rabbitmq` |
| `messaging.destination` | string | Destination name | `trade_queue` |
| `messaging.destination_kind` | string | Destination type | `queue`, `topic` |
| `messaging.operation` | string | Operation type | `publish`, `receive`, `process` |
| `messaging.message_id` | string | Message identifier | `msg-12345` |
| `messaging.conversation_id` | string | Conversation identifier | `conv-67890` |

#### Exception Attributes (Required for error spans)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `exception.type` | string | Exception type | `ValueError`, `TimeoutError` |
| `exception.message` | string | Exception message | `Connection timeout after 30s` |
| `exception.stacktrace` | string | Stack trace (truncated) | `Traceback (most recent call last): ...` |
| `exception.escaped` | boolean | Whether exception escaped span | `true`, `false` |

### 2.2 Custom ChiseAI Attributes

#### Service Context Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.service.type` | string | Service classification | `api`, `strategy`, `ingestion`, `monitor` | Low (4 values) |
| `chiseai.service.name` | string | Service instance name | `chiseai-api-final` | Low (7 values) |
| `chiseai.service.version` | string | Service version | `1.2.3` | Low |
| `chiseai.service.region` | string | Deployment region | `us-east-1`, `eu-west-1` | Low |

#### Trading Domain Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.strategy.id` | string | Strategy identifier | `grid_btc_001` | Medium |
| `chiseai.strategy.type` | string | Strategy type | `grid`, `momentum`, `arbitrage` | Low (5 values) |
| `chiseai.trade.id` | string | Trade identifier | `trade-uuid-123` | High (use with care) |
| `chiseai.trade.symbol` | string | Trading pair | `BTCUSDT`, `ETHUSDT` | Medium |
| `chiseai.trade.side` | string | Trade side | `buy`, `sell` | Low (2 values) |
| `chiseai.trade.status` | string | Trade status | `pending`, `filled`, `cancelled` | Low (4 values) |
| `chiseai.execution.id` | string | Execution batch ID | `exec-uuid-456` | High (use with care) |
| `chiseai.order.id` | string | Exchange order ID | `order-uuid-789` | High (use with care) |
| `chiseai.exchange.name` | string | Exchange name | `binance`, `okx`, `bybit` | Low (5 values) |

#### User Context Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.user.id` | string | User identifier (hashed) | `user-hash-abc123` | High (use with care) |
| `chiseai.user.tier` | string | User tier | `free`, `pro`, `enterprise` | Low (3 values) |
| `chiseai.user.organization` | string | Organization ID (hashed) | `org-hash-def456` | Medium |

#### Data Ingestion Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.data.source` | string | Data source name | `binance_ohlcv`, `coinbase_ticker` | Medium |
| `chiseai.data.type` | string | Data type | `ohlcv`, `ticker`, `orderbook` | Low (5 values) |
| `chiseai.data.symbol` | string | Instrument symbol | `BTCUSDT` | Medium |
| `chiseai.data.interval` | string | Data interval | `1m`, `5m`, `1h`, `1d` | Low (8 values) |
| `chiseai.data.batch_size` | int | Records in batch | `1000` | Low |
| `chiseai.data.quality_score` | double | Quality score 0-1 | `0.95` | Low |

#### Performance Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.performance.duration_ms` | double | Operation duration | `125.5` | Low |
| `chiseai.performance.queue_wait_ms` | double | Time in queue | `10.2` | Low |
| `chiseai.performance.db_query_ms` | double | Database query time | `45.3` | Low |
| `chiseai.performance.cache_hit` | boolean | Cache hit indicator | `true`, `false` | Low (2 values) |
| `chiseai.performance.cache_tier` | string | Cache tier used | `l1`, `l2`, `miss` | Low (3 values) |

#### Error Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.error.type` | string | Error category | `validation`, `timeout`, `exchange_api`, `database` | Low (10 values) |
| `chiseai.error.severity` | string | Error severity | `warning`, `error`, `critical` | Low (3 values) |
| `chiseai.error.recoverable` | boolean | Whether error is recoverable | `true`, `false` | Low (2 values) |
| `chiseai.error.retry_count` | int | Number of retries attempted | `3` | Low |

#### Business Logic Attributes

| Attribute | Type | Description | Example | Cardinality |
|-----------|------|-------------|---------|-------------|
| `chiseai.business.decision` | string | Business decision made | `enter_long`, `exit_position`, `hold` | Low (5 values) |
| `chiseai.business.confidence` | double | Confidence score 0-1 | `0.87` | Low |
| `chiseai.business.risk_score` | double | Risk score 0-1 | `0.23` | Low |
| `chiseai.business.expected_pnl` | double | Expected PnL | `150.50` | Low |

---

## 3. Resource Attributes

Resource attributes describe the entity producing telemetry. These are attached to all spans from a service.

### 3.1 Required Resource Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `service.name` | string | Logical service name | `chiseai-api` |
| `service.version` | string | Service version | `1.2.3` |
| `service.instance.id` | string | Unique instance identifier | `chiseai-api-pod-abc123` |
| `deployment.environment` | string | Deployment environment | `dev`, `staging`, `prod` |

### 3.2 Recommended Resource Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `service.namespace` | string | Service namespace | `chiseai` |
| `host.name` | string | Hostname | `k8s-node-01` |
| `host.type` | string | Host type | `cloud`, `on-premise` |
| `container.id` | string | Container ID | `abc123def456` |
| `container.name` | string | Container name | `chiseai-api-final` |
| `container.image.name` | string | Container image | `chiseai-api` |
| `container.image.tag` | string | Image tag | `latest` |
| `process.pid` | int | Process ID | `12345` |
| `process.executable.name` | string | Executable name | `python` |
| `process.executable.path` | string | Executable path | `/usr/bin/python3` |
| `process.command` | string | Command line | `python -m chiseai.api` |
| `process.runtime.name` | string | Runtime name | `CPython` |
| `process.runtime.version` | string | Runtime version | `3.13.7` |
| `process.runtime.description` | string | Runtime description | `CPython 3.13.7` |

### 3.3 Cloud Resource Attributes (if applicable)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `cloud.provider` | string | Cloud provider | `aws`, `gcp`, `azure` |
| `cloud.region` | string | Cloud region | `us-east-1` |
| `cloud.availability_zone` | string | Availability zone | `us-east-1a` |
| `cloud.account.id` | string | Account ID | `123456789` |
| `cloud.platform` | string | Platform | `aws_ec2`, `aws_eks`, `gcp_gke` |

### 3.4 Kubernetes Resource Attributes (if applicable)

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `k8s.cluster.name` | string | Cluster name | `chiseai-prod` |
| `k8s.namespace.name` | string | Namespace | `production` |
| `k8s.pod.name` | string | Pod name | `chiseai-api-abc123` |
| `k8s.pod.uid` | string | Pod UID | `abc123-def456` |
| `k8s.deployment.name` | string | Deployment name | `chiseai-api` |
| `k8s.node.name` | string | Node name | `k8s-node-01` |

---

## 4. Baggage Specification

Baggage provides a mechanism to propagate key-value pairs across service boundaries. Use baggage sparingly as it adds overhead to every request.

### 4.1 Standard Baggage Keys

| Key | Description | Example | Propagation |
|-----|-------------|---------|-------------|
| `user.id` | User identifier (hashed) | `user-hash-abc123` | All requests |
| `user.tier` | User tier | `enterprise` | All requests |
| `request.id` | Request correlation ID | `req-uuid-123` | All requests |
| `request.priority` | Request priority | `high`, `normal`, `low` | All requests |

### 4.2 ChiseAI-Specific Baggage Keys

| Key | Description | Example | Propagation |
|-----|-------------|---------|-------------|
| `chiseai.strategy.id` | Strategy identifier | `grid_btc_001` | Strategy-related requests |
| `chiseai.execution.id` | Execution batch ID | `exec-uuid-456` | Execution-related requests |
| `chiseai.trace.priority` | Sampling priority override | `1` (always sample) | Error/slow requests |
| `chiseai.data.source` | Data source context | `binance_ohlcv` | Ingestion pipeline |
| `chiseai.trade.context` | Trade context flag | `true` | Trading operations |

### 4.3 Baggage Constraints

1. **Size Limit:** Maximum 8192 bytes per baggage entry
2. **Key Format:** Lowercase with dots as separators
3. **Value Format:** String only, no nested structures
4. **Propagation:** Only propagate baggage that downstream services need
5. **Security:** Never include secrets, tokens, or PII in baggage

### 4.4 Baggage Usage Guidelines

```python
# Example: Setting baggage in Python
from opentelemetry import baggage
from opentelemetry.context import attach, detach

# Set baggage for user context
token = attach(baggage.set_baggage("user.id", hashed_user_id))
try:
    # Make downstream calls - baggage propagates automatically
    result = await process_trade(request)
finally:
    detach(token)
```

---

## 5. Sampling Strategy

### 5.1 Head-Based Sampling

Head-based sampling makes the sampling decision at the start of a trace. This is efficient but cannot consider the full trace context.

#### Environment-Based Sampling Rates

| Environment | Sampling Rate | Rationale |
|-------------|---------------|-----------|
| `dev` | 100% | Full visibility for development and debugging |
| `staging` | 50% | Balance between visibility and cost |
| `prod` | 10% | Cost-effective while maintaining statistical significance |
| `prod-critical` | 25% | Higher rate for critical production paths |

#### Service-Specific Overrides

| Service | Default Rate | Override Rate | Condition |
|---------|--------------|---------------|-----------|
| `chiseai-api-final` | 10% | 50% | Enterprise user requests |
| `chiseai-brain-scheduler` | 10% | 100% | Strategy execution spans |
| `chiseai-ohlcv-ingestion` | 10% | 25% | Data quality issues |
| `chiseai-data-quality-monitor` | 100% | - | Always sample (low volume) |

### 5.2 Tail-Based Sampling Rules

Tail-based sampling makes the decision after the trace completes, allowing for intelligent sampling based on trace characteristics.

#### Rule 1: Always Sample Errors

```yaml
name: error_sampling
condition: status_code >= 500 OR exception.type exists
rate: 100%
priority: 1
```

**Applies to:**
- HTTP 5xx responses
- Unhandled exceptions
- Database connection failures
- External API timeouts

#### Rule 2: Always Sample Slow Requests

```yaml
name: slow_request_sampling
condition: duration_ms > 500
rate: 100%
priority: 2
```

**Thresholds by service:**

| Service | Slow Threshold | Rationale |
|---------|----------------|-----------|
| `chiseai-api-final` | 500ms | API response SLA |
| `chiseai-brain-scheduler` | 2000ms | Strategy execution |
| `chiseai-ohlcv-ingestion` | 10000ms | Batch processing |
| `chiseai-kimi-adapter` | 5000ms | LLM API latency |

#### Rule 3: Always Sample Enterprise Users

```yaml
name: enterprise_sampling
condition: user.tier == "enterprise"
rate: 100%
priority: 3
```

#### Rule 4: Probabilistic Strategy Execution Sampling

```yaml
name: strategy_execution_sampling
condition: chiseai.strategy.id exists
rate: 50%
priority: 4
```

#### Rule 5: Probabilistic Trade Sampling

```yaml
name: trade_sampling
condition: chiseai.trade.id exists
rate: 25%
priority: 5
```

### 5.3 Sampling Configuration

#### Tempo Tail-Based Sampling Configuration

```yaml
# tempo.yaml
distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"
        http:
          endpoint: "0.0.0.0:4318"

ingester:
  trace_idle_period: 10s
  max_block_duration: 5m

compactor:
  compaction:
    compaction_window: 1h
    max_compaction_objects: 1000000

generator:
  registry:
    external_labels:
      source: tempo
      cluster: chiseai
  storage:
    path: /tmp/tempo/generator/wal
    remote_write:
      - url: http://prometheus:9090/api/v1/write
        send_exemplars: true

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/traces
    wal:
      path: /tmp/tempo/wal
    pool:
      max_workers: 100
      queue_depth: 10000

overrides:
  defaults:
    ingestion:
      rate_limit_bytes: 15000000
      burst_size_bytes: 20000000
    global:
      max_bytes_per_trace: 5000000
```

#### OpenTelemetry Collector Sampling Configuration

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 100000
    expected_new_traces_per_sec: 1000
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow_requests
        type: latency
        latency: {threshold_ms: 500}
      - name: probabilistic
        type: probabilistic
        probabilistic: {sampling_percentage: 10}
      - name: composite
        type: composite
        composite:
          max_total_spans_per_second: 1000
          policy_order: [errors, slow_requests, probabilistic]

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [tail_sampling]
      exporters: [otlp/tempo]
```

---

## 6. Attribute Naming Conventions

### 6.1 General Conventions

1. **Use snake_case:** All attribute names use lowercase with underscores
   - ✅ `http.status_code`
   - ❌ `http.statusCode`
   - ❌ `HttpStatusCode`

2. **Prefix custom attributes:** All ChiseAI-specific attributes use `chiseai.` prefix
   - ✅ `chiseai.strategy.id`
   - ❌ `strategy_id`
   - ❌ `chiseai_strategy_id`

3. **Follow OTel semantic conventions:** Use standard OTel attributes where available
   - ✅ `http.method`
   - ❌ `request_method`

4. **Use dot notation for namespacing:** Group related attributes with dots
   - ✅ `chiseai.performance.duration_ms`
   - ❌ `chiseai_performance_duration_ms`

### 6.2 Value Conventions

1. **Enums use lowercase:** Enumeration values are lowercase
   - ✅ `buy`, `sell`
   - ❌ `BUY`, `SELL`

2. **Booleans are actual booleans:** Not strings
   - ✅ `true`
   - ❌ `"true"`

3. **Numeric values are actual numbers:** Not strings
   - ✅ `200`
   - ❌ `"200"`

4. **Timestamps use ISO 8601:** When stored as strings
   - ✅ `2026-03-13T10:30:00Z`

### 6.3 Cardinality Guidelines

1. **Maximum 50 attributes per span:** Including resource attributes
2. **Avoid high-cardinality values:**
   - ❌ Timestamps as attribute values
   - ❌ UUIDs as attribute values (unless necessary)
   - ❌ User-generated content
   - ❌ Stack traces (use exception.stacktrace instead)

3. **Use enums where possible:**
   - ✅ `chiseai.trade.side: buy`
   - ❌ `chiseai.trade.side: "buy order for BTC at price 50000"`

4. **Hash high-cardinality identifiers:**
   - User IDs: Hash to reduce cardinality while maintaining correlation
   - Trade IDs: Consider sampling or bucketing

---

## 7. Service-Specific Span Examples

### 7.1 API HTTP Request Span

```json
{
  "trace_id": "abc123def456",
  "span_id": "span001",
  "parent_span_id": null,
  "name": "POST /v1/trades",
  "kind": "SERVER",
  "start_time": "2026-03-13T10:30:00.000Z",
  "end_time": "2026-03-13T10:30:00.150Z",
  "status": {"code": "OK"},
  "attributes": {
    "http.method": "POST",
    "http.url": "https://api.chiseai.com/v1/trades",
    "http.target": "/v1/trades",
    "http.host": "api.chiseai.com",
    "http.scheme": "https",
    "http.status_code": 201,
    "http.route": "/v1/trades",
    "http.request_content_length": 256,
    "http.response_content_length": 512,
    "chiseai.service.type": "api",
    "chiseai.service.name": "chiseai-api-final",
    "chiseai.user.id": "user-hash-abc123",
    "chiseai.user.tier": "enterprise",
    "chiseai.trade.symbol": "BTCUSDT",
    "chiseai.trade.side": "buy",
    "chiseai.performance.duration_ms": 150.0
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-api",
      "service.version": "1.2.3",
      "service.instance.id": "chiseai-api-pod-abc123",
      "deployment.environment": "prod",
      "host.name": "k8s-node-01",
      "container.name": "chiseai-api-final",
      "process.runtime.name": "CPython",
      "process.runtime.version": "3.13.7"
    }
  }
}
```

### 7.2 Strategy Execution Span

```json
{
  "trace_id": "abc123def456",
  "span_id": "span002",
  "parent_span_id": "span001",
  "name": "execute_strategy",
  "kind": "INTERNAL",
  "start_time": "2026-03-13T10:30:00.050Z",
  "end_time": "2026-03-13T10:30:00.120Z",
  "status": {"code": "OK"},
  "attributes": {
    "chiseai.service.type": "strategy",
    "chiseai.service.name": "chiseai-brain-scheduler",
    "chiseai.strategy.id": "grid_btc_001",
    "chiseai.strategy.type": "grid",
    "chiseai.execution.id": "exec-uuid-456",
    "chiseai.trade.symbol": "BTCUSDT",
    "chiseai.business.decision": "enter_long",
    "chiseai.business.confidence": 0.87,
    "chiseai.business.risk_score": 0.23,
    "chiseai.business.expected_pnl": 150.50,
    "chiseai.performance.duration_ms": 70.0,
    "chiseai.performance.cache_hit": true,
    "chiseai.performance.cache_tier": "l1"
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-brain-scheduler",
      "service.version": "2.1.0",
      "service.instance.id": "chiseai-brain-scheduler-pod-def456",
      "deployment.environment": "prod"
    }
  }
}
```

### 7.3 Database Query Span

```json
{
  "trace_id": "abc123def456",
  "span_id": "span003",
  "parent_span_id": "span002",
  "name": "SELECT trades",
  "kind": "CLIENT",
  "start_time": "2026-03-13T10:30:00.060Z",
  "end_time": "2026-03-13T10:30:00.080Z",
  "status": {"code": "OK"},
  "attributes": {
    "db.system": "postgresql",
    "db.connection_string": "postgresql://chiseai-postgres:5434",
    "db.user": "chiseai_app",
    "db.statement": "SELECT * FROM trades WHERE strategy_id = $1 AND status = $2",
    "db.operation": "SELECT",
    "db.sql.table": "trades",
    "chiseai.service.type": "database",
    "chiseai.performance.db_query_ms": 20.0
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-api",
      "service.version": "1.2.3"
    }
  }
}
```

### 7.4 Redis Operation Span

```json
{
  "trace_id": "abc123def456",
  "span_id": "span004",
  "parent_span_id": "span002",
  "name": "GET cache",
  "kind": "CLIENT",
  "start_time": "2026-03-13T10:30:00.055Z",
  "end_time": "2026-03-13T10:30:00.056Z",
  "status": {"code": "OK"},
  "attributes": {
    "db.system": "redis",
    "db.connection_string": "redis://chiseai-redis:6380",
    "db.operation": "GET",
    "db.statement": "GET strategy:grid_btc_001:config",
    "chiseai.service.type": "cache",
    "chiseai.performance.cache_hit": true,
    "chiseai.performance.cache_tier": "l1",
    "chiseai.performance.duration_ms": 1.0
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-brain-scheduler",
      "service.version": "2.1.0"
    }
  }
}
```

### 7.5 Data Ingestion Batch Span

```json
{
  "trace_id": "def789ghi012",
  "span_id": "span005",
  "parent_span_id": null,
  "name": "ingest_ohlcv_batch",
  "kind": "CONSUMER",
  "start_time": "2026-03-13T10:30:00.000Z",
  "end_time": "2026-03-13T10:30:05.000Z",
  "status": {"code": "OK"},
  "attributes": {
    "chiseai.service.type": "ingestion",
    "chiseai.service.name": "chiseai-ohlcv-ingestion",
    "chiseai.data.source": "binance_ohlcv",
    "chiseai.data.type": "ohlcv",
    "chiseai.data.symbol": "BTCUSDT",
    "chiseai.data.interval": "1m",
    "chiseai.data.batch_size": 1000,
    "chiseai.data.quality_score": 0.98,
    "chiseai.performance.duration_ms": 5000.0,
    "chiseai.performance.queue_wait_ms": 100.0,
    "messaging.system": "redis",
    "messaging.destination": "ohlcv_queue",
    "messaging.destination_kind": "queue",
    "messaging.operation": "process"
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-ohlcv-ingestion",
      "service.version": "1.5.0",
      "service.instance.id": "chiseai-ohlcv-ingestion-pod-ghi789",
      "deployment.environment": "prod"
    }
  }
}
```

### 7.6 Error Span Example

```json
{
  "trace_id": "ghi345jkl678",
  "span_id": "span006",
  "parent_span_id": "span001",
  "name": "exchange_api_call",
  "kind": "CLIENT",
  "start_time": "2026-03-13T10:30:00.200Z",
  "end_time": "2026-03-13T10:30:30.200Z",
  "status": {
    "code": "ERROR",
    "message": "Connection timeout after 30s"
  },
  "attributes": {
    "http.method": "POST",
    "http.url": "https://api.binance.com/api/v3/order",
    "http.status_code": 504,
    "chiseai.service.type": "api",
    "chiseai.exchange.name": "binance",
    "chiseai.error.type": "timeout",
    "chiseai.error.severity": "error",
    "chiseai.error.recoverable": true,
    "chiseai.error.retry_count": 3,
    "chiseai.performance.duration_ms": 30000.0,
    "exception.type": "TimeoutError",
    "exception.message": "Connection timeout after 30s",
    "exception.stacktrace": "Traceback (most recent call last): ...",
    "exception.escaped": true
  },
  "resource": {
    "attributes": {
      "service.name": "chiseai-api",
      "service.version": "1.2.3"
    }
  }
}
```

---

## 8. Trace Context Propagation

### 8.1 W3C Trace Context

ChiseAI uses W3C Trace Context for trace propagation:

- **Traceparent Header:** `traceparent: 00-{trace_id}-{parent_span_id}-{flags}`
- **Tracestate Header:** `tracestate: chiseai=vendor_specific_data`

### 8.2 Propagation Format

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             |  |                                |                |
             |  |                                |                Trace flags (sampled=01)
             |  |                                Parent span ID
             |  Trace ID (32 hex chars)
             Version (00)
```

### 8.3 Baggage Propagation

Baggage is propagated via the `baggage` header:

```
baggage: user.id=abc123,user.tier=enterprise,chiseai.strategy.id=grid_btc_001
```

---

## 9. Instrumentation Guidelines

### 9.1 Python Instrumentation

```python
from opentelemetry import trace, baggage
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

# Initialize tracer provider
provider = TracerProvider(
    resource=Resource.create({
        "service.name": "chiseai-api",
        "service.version": "1.2.3",
        "deployment.environment": "prod"
    })
)
trace.set_tracer_provider(provider)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint="http://tempo:4317",
    insecure=True
)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Get tracer
tracer = trace.get_tracer("chiseai.api")

# Auto-instrument libraries
FastAPIInstrumentor.instrument_app(app)
RedisInstrumentor().instrument()
Psycopg2Instrumentor().instrument()

# Manual span creation
with tracer.start_as_current_span("process_trade") as span:
    span.set_attribute("chiseai.trade.symbol", "BTCUSDT")
    span.set_attribute("chiseai.trade.side", "buy")
    span.set_attribute("chiseai.user.tier", "enterprise")
    
    # Add events
    span.add_event("validation_complete", {"valid": True})
    
    # Process trade
    result = await execute_trade(request)
    
    span.set_attribute("chiseai.trade.status", result.status)
```

### 9.2 Span Naming Conventions

| Operation Type | Span Name Pattern | Example |
|----------------|-------------------|---------|
| HTTP Server | `{method} {route}` | `GET /v1/trades` |
| HTTP Client | `HTTP {method}` | `HTTP POST` |
| Database | `{operation} {table}` | `SELECT trades` |
| Redis | `{command} {key_pattern}` | `GET cache` |
| Function | `{function_name}` | `execute_strategy` |
| Message | `{operation} {destination}` | `publish trade_queue` |

### 9.3 Event Naming

| Event Type | Event Name | Attributes |
|------------|------------|------------|
| Validation | `validation_complete` | `valid`, `errors` |
| Cache | `cache_hit` / `cache_miss` | `tier`, `key_pattern` |
| Retry | `retry_attempt` | `attempt_number`, `max_retries` |
| Decision | `decision_made` | `decision`, `confidence` |
| Exception | `exception` | `type`, `message` |

---

## 10. Storage and Retention

### 10.1 Trace Storage Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Block size | 5MB | Balance between query performance and storage |
| Retention | 7 days | Sufficient for debugging, cost-effective |
| Compression | ZSTD | Good compression ratio, fast decompression |
| Indexing | Trace ID, Service Name, Span Name | Fast lookups for common queries |

### 10.2 Storage Estimates

Based on 10% sampling in production:

| Metric | Estimate |
|--------|----------|
| Spans per second | ~100 |
| Average span size | 2KB |
| Daily storage | ~17GB |
| 7-day retention | ~120GB |
| Monthly storage | ~500GB |

### 10.3 Query Performance Targets

| Query Type | Target Latency |
|------------|----------------|
| Trace by ID | <100ms |
| Service overview | <1s |
| Error search | <2s |
| Duration histogram | <3s |

---

## 11. Security Considerations

### 11.1 Data to Exclude

Never include in traces:

- API keys or secrets
- Passwords or credentials
- Personal identifiable information (PII)
- Credit card numbers
- Private keys
- Session tokens
- Internal IP addresses (use host.name instead)

### 11.2 Sanitization Rules

| Attribute | Sanitization Rule |
|-----------|-------------------|
| `db.statement` | Remove literal values, keep placeholders |
| `http.url` | Remove query parameters with sensitive data |
| `chiseai.user.id` | Hash with salt |
| Exception messages | Truncate and sanitize |

### 11.3 Access Control

- Traces accessible only to authorized personnel
- Audit log of trace access
- Data residency compliance (GDPR, CCPA)

---

## 12. Validation and Testing

### 12.1 Schema Validation

```python
# Validate span attributes against schema
def validate_span(span: ReadableSpan) -> List[str]:
    errors = []
    
    # Check required attributes
    if "service.name" not in span.resource.attributes:
        errors.append("Missing required attribute: service.name")
    
    # Check attribute naming conventions
    for attr in span.attributes:
        if not re.match(r'^[a-z][a-z0-9_.]*$', attr):
            errors.append(f"Invalid attribute name: {attr}")
    
    # Check cardinality limits
    if len(span.attributes) > 50:
        errors.append(f"Too many attributes: {len(span.attributes)}")
    
    return errors
```

### 12.2 Testing Checklist

- [ ] Spans emitted for all service entry points
- [ ] Trace context propagates across service boundaries
- [ ] Baggage values propagate correctly
- [ ] Sampling rules apply as configured
- [ ] Error spans include exception details
- [ ] Database spans include query information
- [ ] Redis spans include operation details
- [ ] Custom attributes follow naming conventions
- [ ] No sensitive data in traces
- [ ] Trace IDs are unique
- [ ] Parent-child relationships are correct

---

## 13. Migration and Rollout

### 13.1 Phase 1: API Service (Week 1)

- Instrument `chiseai-api-final`
- Configure 100% sampling in dev
- Validate trace quality

### 13.2 Phase 2: Strategy Engine (Week 2)

- Instrument `chiseai-brain-scheduler`
- Enable trace context propagation
- Test end-to-end traces

### 13.3 Phase 3: Data Services (Week 3)

- Instrument `chiseai-ohlcv-ingestion`
- Instrument `chiseai-data-quality-monitor`
- Configure tail-based sampling

### 13.4 Phase 4: Full Rollout (Week 4)

- Instrument remaining services
- Enable production sampling (10%)
- Monitor and tune

---

## 14. References

### 14.1 OpenTelemetry Specifications

- [OpenTelemetry Specification v1.20](https://opentelemetry.io/docs/specs/otel/)
- [OTLP Protocol](https://opentelemetry.io/docs/specs/otlp/)
- [Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)

### 14.2 Tempo Documentation

- [Grafana Tempo](https://grafana.com/docs/tempo/)
- [Tempo Configuration](https://grafana.com/docs/tempo/latest/configuration/)
- [Tail-Based Sampling](https://grafana.com/docs/tempo/latest/configuration/tail-based-sampling/)

### 14.3 Related Documents

- `docs/observability/audit-current-state.md` - Current observability gaps
- `docs/planning/sprints/TEMPO-2026-001-task-0-1-evidence.md` - Task 0.1 evidence
- `docs/planning/sprints/TEMPO-2026-001-sprint-plan.md` - Sprint plan

---

## 15. Appendix

### 15.1 Attribute Quick Reference

| Category | Attribute | Type | Required |
|----------|-----------|------|----------|
| HTTP | `http.method` | string | Yes |
| HTTP | `http.url` | string | Yes |
| HTTP | `http.status_code` | int | Yes |
| DB | `db.system` | string | Yes |
| DB | `db.statement` | string | Yes |
| ChiseAI | `chiseai.service.type` | string | Yes |
| ChiseAI | `chiseai.strategy.id` | string | No |
| ChiseAI | `chiseai.trade.symbol` | string | No |
| ChiseAI | `chiseai.performance.duration_ms` | double | Yes |

### 15.2 Sampling Decision Matrix

| Condition | Dev | Staging | Prod |
|-----------|-----|---------|------|
| Default | 100% | 50% | 10% |
| Error | 100% | 100% | 100% |
| Slow (>500ms) | 100% | 100% | 100% |
| Enterprise | 100% | 100% | 100% |
| Strategy | 100% | 100% | 50% |

### 15.3 Glossary

| Term | Definition |
|------|------------|
| Span | A single operation within a trace |
| Trace | A collection of spans forming a request tree |
| Attribute | Key-value pair on a span |
| Resource | Entity producing telemetry |
| Baggage | Context propagated across services |
| Sampling | Selecting which traces to keep |
| OTLP | OpenTelemetry Protocol |
| Tempo | Grafana's distributed tracing backend |

---

**Document Version History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-13 | senior-dev | Initial schema design |

**Next Review Date:** 2026-04-13
