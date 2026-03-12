# ST-GOV-MINI-001: Week 1 Audit Snapshot + Retrieval Baseline

## Overview

This document describes the Week 1 audit snapshot and retrieval baseline implementation for the ChiseAI governance system.

## Components

### 1. Week 1 Audit Snapshot (`scripts/governance/week1_audit_snapshot.py`)

Captures a comprehensive snapshot of the system's state at Week 1, including:

#### Data Captured

| Component | Description | Source |
|-----------|-------------|--------|
| Active Stories | Currently tracked stories from Redis iterlog | Redis |
| Memory Stats | Redis keys, Qdrant vectors, storage usage | Redis + Qdrant |
| Governance Metrics | Retrieval latency, hit rate, dedup ratio | Redis + Calculated |
| Agent Activity | Ownership locks, parallel workers | Redis |

#### Usage

```bash
# Capture snapshot with defaults
python scripts/governance/week1_audit_snapshot.py

# Capture with custom output directory
python scripts/governance/week1_audit_snapshot.py --output-dir /path/to/output

# Capture as YAML
python scripts/governance/week1_audit_snapshot.py --format yaml

# Enable verbose logging
python scripts/governance/week1_audit_snapshot.py --verbose
```

#### Output

Creates: `docs/governance/audit/week1_snapshot_YYYYMMDD.json`

Example output:
```json
{
  "metadata": {
    "capture_time": "2026-03-11T12:00:00Z",
    "agent_version": "1.0.0",
    "data_sources": ["redis", "qdrant"],
    "snapshot_type": "week1_audit",
    "story_id": "ST-GOV-MINI-001"
  },
  "active_stories": [
    {
      "story_id": "ST-001",
      "story_title": "Example Story",
      "started_at": "2026-03-01T10:00:00Z",
      "agent": "dev",
      "branch": "feature/ST-001-example",
      "status": "active"
    }
  ],
  "memory_stats": {
    "redis_keys_total": 1500,
    "redis_keys_by_db": {"db0": 1200, "db1": 300},
    "redis_memory_used_mb": 45.5,
    "qdrant_collections": ["ChiseAI"],
    "qdrant_total_vectors": 5000
  },
  "governance_metrics": {
    "retrieval_latency_ms": 25.0,
    "memory_hit_rate": 75.0,
    "deduplication_ratio": 0.7,
    "active_ownership_locks": 3,
    "parallel_workers": 2
  },
  "agent_activity": {
    "timestamp": "2026-03-11T12:00:00Z",
    "active_agents": [...],
    "total_stories_tracked": 10,
    "ownership_claims": {...}
  }
}
```

### 2. Retrieval Quality Baseline (`scripts/governance/retrieval_baseline.py`)

Establishes a retrieval quality baseline by measuring vector search performance.

#### Metrics Captured

| Metric | Description | Target |
|--------|-------------|--------|
| Latency (p50/p95/p99) | Query response times | p95 < 100ms |
| Relevance Score | Average similarity scores | > 0.7 |
| P@5 / P@10 | Precision at k=5 and k=10 | > 0.85 |
| R@5 / R@10 | Recall at k=5 and k=10 | > 0.80 |
| MRR | Mean Reciprocal Rank | > 0.75 |
| Coverage Ratio | Queries returning results | > 90% |

#### Test Queries

Default test queries cover common patterns:

1. `trading strategy patterns`
2. `risk management decisions`
3. `incident prevention rules`
4. `agent workflow optimizations`
5. `memory retrieval patterns`
6. `governance audit procedures`
7. `vector similarity search`
8. `parallel execution safety`
9. `skill validation criteria`
10. `metacognition reflection loops`

#### Usage

```bash
# Run baseline with default queries
python scripts/governance/retrieval_baseline.py

# Run with custom queries
python scripts/governance/retrieval_baseline.py \
  --queries "custom query 1" "custom query 2"

# Specify collection
python scripts/governance/retrieval_baseline.py --collection MyCollection

# Custom output directory
python scripts/governance/retrieval_baseline.py --output-dir /path/to/output

# Enable verbose logging
python scripts/governance/retrieval_baseline.py --verbose
```

#### Output

Creates: `docs/governance/audit/retrieval_baseline_YYYYMMDD.json`

Example output:
```json
{
  "metadata": {
    "capture_time": "2026-03-11T12:00:00Z",
    "baseline_type": "retrieval_quality",
    "story_id": "ST-GOV-MINI-001",
    "test_queries_count": 10,
    "collection": "ChiseAI"
  },
  "latency": {
    "p50_ms": 25.0,
    "p95_ms": 50.0,
    "p99_ms": 100.0,
    "mean_ms": 30.0,
    "min_ms": 10.0,
    "max_ms": 150.0,
    "samples": 10
  },
  "relevance": {
    "mean_score": 0.75,
    "min_score": 0.5,
    "max_score": 0.95,
    "std_dev": 0.12
  },
  "top_k_accuracy": {
    "k5_precision": 0.85,
    "k5_recall": 0.80,
    "k10_precision": 0.82,
    "k10_recall": 0.85,
    "mrr": 0.78
  },
  "coverage": {
    "total_queries": 10,
    "queries_with_results": 9,
    "coverage_ratio": 0.9,
    "empty_results_count": 1
  },
  "query_results": [...]
}
```

## Running Tests

### Week 1 Audit Snapshot Tests

```bash
pytest tests/unit/governance/test_week1_audit_snapshot.py -v
```

### Retrieval Baseline Tests

```bash
pytest tests/unit/governance/test_retrieval_baseline.py -v
```

### Run All Governance Tests

```bash
pytest tests/unit/governance/ -v
```

## Interpretation Guide

### Week 1 Snapshot

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Redis Keys | < 10K | 10K-50K | > 50K |
| Memory Usage | < 100MB | 100-500MB | > 500MB |
| Active Stories | < 20 | 20-50 | > 50 |
| Parallel Workers | < 5 | 5-10 | > 10 |

### Retrieval Baseline

| Metric | Excellent | Good | Acceptable | Needs Work |
|--------|-----------|------|------------|------------|
| Latency p95 | < 10ms | < 50ms | < 100ms | > 100ms |
| Relevance | > 0.85 | > 0.75 | > 0.60 | < 0.60 |
| P@5 | > 0.90 | > 0.85 | > 0.70 | < 0.70 |
| R@10 | > 0.90 | > 0.80 | > 0.60 | < 0.60 |
| MRR | > 0.85 | > 0.75 | > 0.60 | < 0.60 |
| Coverage | > 95% | > 90% | > 80% | < 80% |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `host.docker.internal` | Redis server hostname |
| `REDIS_PORT` | `6380` | Redis server port |
| `REDIS_DB` | `1` | Redis database number |
| `QDRANT_HOST` | `host.docker.internal` | Qdrant server hostname |
| `QDRANT_PORT` | `6334` | Qdrant server port |

## Integration with Existing Components

### Uses Existing Modules

- `src/governance.audit.baseline` - AuditSnapshot and RetrievalBaseline classes
- `src/governance.retrieval.evaluator` - RetrievalEvaluator for metrics
- `src/governance.memory.deduplication` - MemoryDeduplicationEngine for stats

### Redis Key Patterns

- `bmad:chiseai:iterlog:story:*` - Story iteration logs
- `bmad:chiseai:ownership` - Scope ownership claims
- `governance:audit:baseline:current` - Current baseline metrics
- `governance:audit:snapshot:*` - Historical snapshots

## Future Enhancements

1. **Scheduled Snapshots**: Automate weekly snapshot capture
2. **Trend Analysis**: Compare snapshots over time
3. **Alert Integration**: Trigger alerts on metric degradation
4. **Dashboard Export**: Feed metrics to Grafana
5. **Historical Comparison**: Compare against previous baselines

## References

- [Audit Baseline Documentation](audit-baseline.md)
- `src/governance/audit/baseline.py`
- `src/governance/retrieval/evaluator.py`
- `src/governance/memory/deduplication.py`

---

*Last Updated: 2026-03-11*  
*Story: ST-GOV-MINI-001*
