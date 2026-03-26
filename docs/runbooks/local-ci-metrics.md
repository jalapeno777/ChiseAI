# Local CI Metrics Dashboard

This document describes the Local CI metrics exported for Grafana monitoring.

## Overview

The Local CI Metrics system exports test performance, cache hit rates, and parallel execution efficiency metrics to Grafana via InfluxDB line protocol.

## Available Metrics

### Core Metrics

| Metric               | Type    | Description                            |
| -------------------- | ------- | -------------------------------------- |
| `test_count`         | integer | Total number of tests run              |
| `duration`           | float   | Total execution time in seconds        |
| `cache_hit_rate`     | float   | Percentage of cache hits (0-100)       |
| `parallel_speedup`   | float   | Speedup factor vs sequential execution |
| `worker_utilization` | float   | Worker utilization ratio (0-1)         |

### Cache Metrics

| Metric                | Type    | Description                     |
| --------------------- | ------- | ------------------------------- |
| `cache_hits`          | integer | Number of cache hits            |
| `cache_misses`        | integer | Number of cache misses          |
| `cache_invalidations` | integer | Number of cache invalidations   |
| `cache_stored`        | integer | Number of cached results stored |

### Parallel Execution Metrics

| Metric              | Type    | Description                     |
| ------------------- | ------- | ------------------------------- |
| `worker_count`      | integer | Number of parallel workers      |
| `test_distribution` | dict    | Mapping of worker to test count |

### Speed Optimization Metrics

| Metric                | Type    | Description               |
| --------------------- | ------- | ------------------------- |
| `total_duration`      | float   | Total duration in seconds |
| `selected_test_count` | integer | Number of selected tests  |
| `tests_passed`        | integer | Number of passing tests   |
| `tests_failed`        | integer | Number of failing tests   |
| `tests_skipped`       | integer | Number of skipped tests   |

## Data Export

### InfluxDB Line Protocol

Metrics are exported in InfluxDB line protocol format:

```
local_ci_metrics,parallel=true test_count=100,duration=45.5,cache_hit_rate=75.0,selected_test_count=100,tests_passed=98,tests_failed=2,tests_skipped=0,workers=4 1711489200000000000
```

### JSON Export

For local debugging, metrics are also exported as JSON:

```json
{
  "timestamp": "2026-03-26T20:00:00+00:00",
  "test_count": 100,
  "duration": 45.5,
  "cache_hit_rate": 75.0,
  "parallel_speedup": 2.3,
  "worker_utilization": 0.85,
  "cache": {
    "hits": 75,
    "misses": 25,
    "invalidations": 5,
    "stored": 100,
    "hit_rate": 75.0
  },
  "parallel": {
    "worker_count": 4,
    "test_distribution": {
      "worker_0": 25,
      "worker_1": 25,
      "worker_2": 25,
      "worker_3": 25
    },
    "speedup": 2.3,
    "worker_utilization": 0.85
  },
  "speedup": {
    "total_duration": 45.5,
    "selected_test_count": 100,
    "tests_run": 100,
    "tests_passed": 98,
    "tests_failed": 2,
    "tests_skipped": 0,
    "parallel": true,
    "cache_hit_rate": 75.0
  }
}
```

## Grafana Dashboard Queries

### Test Count Over Time

```promql
test_count{job="local-ci"}
```

### Cache Hit Rate

```promql
cache_hit_rate{job="local-ci"}
```

### Duration Trends

```promql
duration{job="local-ci"}
```

### Parallel Speedup

```promql
parallel_speedup{job="local-ci"}
```

### Worker Utilization

```promql
worker_utilization{job="local-ci"}
```

### Tests Passed vs Failed

```promql
sum(tests_passed{job="local-ci"}) by (branch)
sum(tests_failed{job="local-ci"}) by (branch)
```

## File Locations

- **Metrics Output**: `_bmad-output/ci/metrics.influx`
- **JSON Output**: `_bmad-output/ci/metrics.json`
- **Metrics Exporter**: `scripts/local_ci_metrics_exporter.py`

## Usage

### Command Line

```bash
# Export metrics in InfluxDB line protocol format
python scripts/local_ci_metrics_exporter.py --export-influx

# Export metrics in JSON format
python scripts/local_ci_metrics_exporter.py --export-json

# Run test export to verify functionality
python scripts/local_ci_metrics_exporter.py --test-export
```

### Integration with CI Scripts

The metrics exporter is automatically called by `local_ci_speed_optimizations.py` after each benchmark run:

```python
from local_ci_speed_optimizations import run_selective_suite, emit_ci_metrics

result = run_selective_suite(parallel=True, workers=4)
emit_ci_metrics(result, output_dir="_bmad-output/ci")
```

## Interpreting the Dashboard

### High Cache Hit Rate (>70%)

Indicates the incremental cache is working effectively. Tests are being skipped when source files haven't changed.

### Low Cache Hit Rate (<30%)

May indicate:

- Source files are changing frequently
- Cache TTL is too short (1 hour default)
- Cache is being cleared between runs

### Parallel Speedup < 1.5x

May indicate:

- Tests are not parallelizable
- Worker count too high for test suite size
- I/O bottlenecks

### Low Worker Utilization (<0.7)

May indicate:

- Uneven test distribution
- Some workers finishing before others
- Need to rebalance test selection

## Alerting Recommendations

### Cache Hit Rate Alert

```yaml
alert: LowCacheHitRate
expr: cache_hit_rate < 30
for: 10m
labels:
  severity: warning
annotations:
  summary: "Low cache hit rate detected"
  description: "Cache hit rate is {{ $value }}%"
```

### Test Failure Alert

```yaml
alert: CITestFailures
expr: tests_failed > 0
for: 5m
labels:
  severity: critical
annotations:
  summary: "CI test failures detected"
  description: "{{ $value }} tests failed"
```

### Duration Alert

```yaml
alert: HighCIDuration
expr: duration > 300
for: 15m
labels:
  severity: warning
annotations:
  summary: "CI duration exceeds threshold"
  description: "CI run took {{ $value }}s"
```

## Troubleshooting

### Metrics Not Appearing

1. Check that `_bmad-output/ci/` directory exists
2. Verify InfluxDB is running and accessible
3. Check file permissions on output directory

### Empty Metrics

1. Run `python scripts/local_ci_metrics_exporter.py --test-export` to verify functionality
2. Check that CI scripts are running successfully
3. Verify cache is being populated

### Inconsistent Metrics

1. Ensure metrics are being collected from the same run
2. Check for multiple CI runs overlapping
3. Verify timestamp consistency across metrics
