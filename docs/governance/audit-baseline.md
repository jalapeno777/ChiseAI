# Audit Baseline Metrics

> ST-GOV-MINI-001: Audit Snapshot + Retrieval Baseline

## Overview

This document defines the audit baseline metrics captured for system governance
and monitoring in the ChiseAI platform.

## Core Metrics

### 1. Retrieval Latency (`retrieval_latency_ms`)

**Definition:** Time in milliseconds to retrieve data from memory/cache layer.

| Rating | Threshold | Description |
|--------|-----------|-------------|
| Excellent | ≤ 10ms | Optimal performance |
| Good | ≤ 50ms | Acceptable for most use cases |
| Acceptable | ≤ 100ms | May impact user experience |
| Needs Improvement | > 100ms | Requires optimization |

**Measurement Points:**
- Memory cache hit lookup
- Redis key retrieval
- Qdrant vector search

### 2. Memory Hit Rate (`memory_hit_rate`)

**Definition:** Percentage of requests served directly from memory cache
without requiring fallback to slower storage.

| Rating | Threshold | Description |
|--------|-----------|-------------|
| Excellent | ≥ 95% | Near-optimal cache efficiency |
| Good | ≥ 80% | Good cache utilization |
| Acceptable | ≥ 60% | Moderate cache efficiency |
| Needs Improvement | < 60% | Cache optimization needed |

**Calculation:**
```
memory_hit_rate = (cache_hits / total_requests) * 100
```

### 3. Deduplication Ratio (`deduplication_ratio`)

**Definition:** Ratio of unique items to total items processed,
indicating effectiveness of deduplication logic.

| Rating | Threshold | Description |
|--------|-----------|-------------|
| Excellent | ≥ 0.9 | High uniqueness |
| Good | ≥ 0.7 | Good deduplication |
| Acceptable | ≥ 0.5 | Moderate effectiveness |
| Needs Improvement | < 0.5 | Poor deduplication |

**Calculation:**
```
deduplication_ratio = unique_items / total_items_processed
```

## Redis Storage Schema

### Snapshot Storage

```
Key: governance:audit:snapshot:<timestamp>
Type: Hash
TTL: 7 days (604800 seconds)

Fields:
- timestamp: ISO 8601 timestamp
- component: Component identifier
- metrics: JSON-encoded metrics dictionary
- metadata: JSON-encoded metadata dictionary
```

### Baseline Storage

```
Key: governance:audit:baseline:current
Type: Hash
TTL: None (persistent until updated)

Fields:
- baseline_id: Unique identifier
- created_at: ISO 8601 timestamp
- metrics: JSON-encoded current metrics
- samples: Number of samples collected
```

## Usage Examples

### Capturing a Snapshot

```python
from src.governance.audit import AuditSnapshot

# Create and capture a snapshot
snapshot = AuditSnapshot().capture(
    component="memory",
    heap_size=1024,
    gc_count=5,
)

# Export to dictionary
data = snapshot.to_dict()

# Export to JSON
json_data = snapshot.to_json()
```

### Collecting Baseline Metrics

```python
from src.governance.audit import RetrievalBaseline

# Create baseline
baseline = RetrievalBaseline(baseline_id="production-001")

# Update metrics
baseline.update_metrics(
    retrieval_latency_ms=25.5,
    memory_hit_rate=87.0,
    deduplication_ratio=0.78,
)

# Get current metrics
metrics = baseline.get_metrics()

# Export to Redis
redis_keys = baseline.export_to_redis()
```

### Evaluating Metrics

```python
from src.governance.audit.baseline import evaluate_metric

# Evaluate a metric value
rating = evaluate_metric("retrieval_latency_ms", 45.0)
# Returns: "good"
```

## Alert Thresholds

When metrics fall below acceptable thresholds, alerts should be triggered:

| Metric | Alert Threshold | Severity |
|--------|-----------------|----------|
| retrieval_latency_ms | > 100ms | Warning |
| retrieval_latency_ms | > 200ms | Critical |
| memory_hit_rate | < 60% | Warning |
| memory_hit_rate | < 40% | Critical |
| deduplication_ratio | < 0.5 | Warning |
| deduplication_ratio | < 0.3 | Critical |

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| AuditSnapshot | ✅ Implemented | Core class complete |
| RetrievalBaseline | ✅ Implemented | Core class complete |
| Redis Export | ⏳ Skeleton | Requires Redis client integration |
| Metric Evaluation | ✅ Implemented | Threshold evaluation complete |
| Tests | ✅ Implemented | Unit test skeleton complete |
| Documentation | ✅ Implemented | This document |

## Future Enhancements

1. **Time-series aggregation**: Aggregate metrics over time windows
2. **Anomaly detection**: Automatic detection of metric anomalies
3. **Alerting integration**: Connect to alerting system
4. **Dashboard integration**: Visualize metrics in Grafana
5. **Historical analysis**: Long-term trend analysis

---

*Last Updated: 2026-02-22*
*Story: ST-GOV-MINI-001*
