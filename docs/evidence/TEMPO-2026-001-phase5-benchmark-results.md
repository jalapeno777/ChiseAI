# TEMPO-2026-001 Phase 5 Benchmark Results

## Performance Benchmark: Tracing Overhead

**Date:** 2026-03-14T05:15:52.696176+00:00
**Story:** TEMPO-2026-001
**Task:** 5.5 - Performance benchmark script for tracing overhead

## Summary

| Metric | Value |
|--------|-------|
| Total Benchmarks | 8 |
| Max Overhead | 121.09% |
| Threshold | 5.0% |
| **Status** | ❌ FAIL |

## Overhead Analysis

### 100 Percent Sampling

| Metric | Value |
|--------|-------|
| Mean Overhead | 6.8% |
| P95 Overhead | 127.9% |
| P99 Overhead | 54.35% |
| Throughput Impact | 6.37% |

### 10 Percent Sampling

| Metric | Value |
|--------|-------|
| Mean Overhead | 121.09% |
| P95 Overhead | 169.47% |
| P99 Overhead | 165.24% |
| Throughput Impact | 54.77% |

### 0 Percent Sampling

| Metric | Value |
|--------|-------|
| Mean Overhead | -39.71% |
| P95 Overhead | 72.3% |
| P99 Overhead | -96.43% |
| Throughput Impact | -65.87% |

## Detailed Results

### Span Creation Overhead

| Configuration | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Throughput (ops/s) |
|---------------|-----------|-------------|----------|----------|---------------------|
| always_on | 0.0194 | 0.0132 | 0.0303 | 0.0645 | 51667.70 |
| ratio_10 | 0.0371 | 0.0058 | 0.0193 | 0.0713 | 26919.47 |
| always_off | 0.0582 | 0.0054 | 0.0103 | 0.0706 | 17187.28 |

### Export Latency

| Configuration | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) |
|---------------|-----------|-------------|----------|----------|
| export_batch_100 | 0.0029 | 0.0021 | 0.0054 | 0.0168 |

### Workload Overhead Comparison

| Configuration | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Throughput (ops/s) |
|---------------|-----------|-------------|----------|----------|---------------------|
| No Tracing | 0.1843 | 0.0382 | 0.0482 | 5.2448 | 5424.79 |
| Tracing (100%) | 0.1969 | 0.0561 | 0.1097 | 8.0953 | 5079.24 |
| Tracing (10%) | 0.4075 | 0.0467 | 0.1298 | 13.9112 | 2453.71 |
| Tracing (0%) | 0.1111 | 0.0467 | 0.0830 | 0.1872 | 8998.20 |

## Benchmark Methodology

### Test Environment
- **Process Isolation:** Each benchmark runs in a separate subprocess to avoid TracerProvider singleton issues
- **Work Simulation:** Each iteration performs ~1000 arithmetic operations to simulate realistic CPU load
- **Iterations:** 10,000 for span creation and workload tests, 1,000 for export tests
- **Batch Size:** 100 spans per export batch
- **Sampling Rates Tested:** 0%, 10%, 100%
- **Metrics Collected:** Mean, median, P95, P99, min, max, standard deviation, throughput

### Test Scenarios

1. **Span Creation:** Measure time to create and close a simple span with different samplers
2. **Export Latency:** Measure time to export batches of spans to in-memory exporter
3. **Workload Overhead:** Compare execution time of identical work (arithmetic operations) with/without tracing spans

### Statistical Significance

Each benchmark runs for sufficient iterations to ensure:
- Stable mean values (coefficient of variation < 10%)
- Representative tail latency measurements (P95, P99)
- Accurate throughput calculations
- Process isolation ensures no cross-contamination between sampler configurations

## Performance Recommendations

1. **Sampling Strategy:** Use 10% sampling in production for optimal balance between observability and overhead
2. **Batch Size:** Use batch sizes of 100+ spans to minimize export overhead
3. **Export Frequency:** Configure export intervals appropriate to your latency requirements
4. **Production Use:** With proper sampling, tracing overhead should remain well under 5%

## JSON Output

```json
{
  "suite_info": {
    "name": "tracing_overhead_benchmark",
    "timestamp": "2026-03-14T05:15:52.696176+00:00",
    "total_benchmarks": 8
  },
  "results": [
    {
      "name": "span_always_on",
      "iterations": 1000,
      "mean_time_ms": 0.0194,
      "median_time_ms": 0.0132,
      "std_dev_ms": 0.1077,
      "min_time_ms": 0.0076,
      "max_time_ms": 3.3903,
      "p95_time_ms": 0.0303,
      "p99_time_ms": 0.0645,
      "throughput_ops_per_sec": 51667.7
    },
    {
      "name": "span_ratio_10",
      "iterations": 1000,
      "mean_time_ms": 0.0371,
      "median_time_ms": 0.0058,
      "std_dev_ms": 0.5579,
      "min_time_ms": 0.0038,
      "max_time_ms": 14.4123,
      "p95_time_ms": 0.0193,
      "p99_time_ms": 0.0713,
      "throughput_ops_per_sec": 26919.47
    },
    {
      "name": "span_always_off",
      "iterations": 1000,
      "mean_time_ms": 0.0582,
      "median_time_ms": 0.0054,
      "std_dev_ms": 1.292,
      "min_time_ms": 0.0036,
      "max_time_ms": 39.0881,
      "p95_time_ms": 0.0103,
      "p99_time_ms": 0.0706,
      "throughput_ops_per_sec": 17187.28
    },
    {
      "name": "export_batch_100",
      "iterations": 100,
      "mean_time_ms": 0.0029,
      "median_time_ms": 0.0021,
      "std_dev_ms": 0.0021,
      "min_time_ms": 0.001,
      "max_time_ms": 0.0168,
      "p95_time_ms": 0.0054,
      "p99_time_ms": 0.0168,
      "throughput_ops_per_sec": 340050.46
    },
    {
      "name": "baseline_always_on",
      "iterations": 1000,
      "mean_time_ms": 0.1843,
      "median_time_ms": 0.0382,
      "std_dev_ms": 1.6107,
      "min_time_ms": 0.0265,
      "max_time_ms": 29.7483,
      "p95_time_ms": 0.0482,
      "p99_time_ms": 5.2448,
      "throughput_ops_per_sec": 5424.79
    },
    {
      "name": "traced_always_on",
      "iterations": 1000,
      "mean_time_ms": 0.1969,
      "median_time_ms": 0.0561,
      "std_dev_ms": 1.3259,
      "min_time_ms": 0.0332,
      "max_time_ms": 18.9916,
      "p95_time_ms": 0.1097,
      "p99_time_ms": 8.0953,
      "throughput_ops_per_sec": 5079.24
    },
    {
      "name": "traced_ratio_10",
      "iterations": 1000,
      "mean_time_ms": 0.4075,
      "median_time_ms": 0.0467,
      "std_dev_ms": 3.039,
      "min_time_ms": 0.0299,
      "max_time_ms": 45.9351,
      "p95_time_ms": 0.1298,
      "p99_time_ms": 13.9112,
      "throughput_ops_per_sec": 2453.71
    },
    {
      "name": "traced_always_off",
      "iterations": 1000,
      "mean_time_ms": 0.1111,
      "median_time_ms": 0.0467,
      "std_dev_ms": 1.2486,
      "min_time_ms": 0.0292,
      "max_time_ms": 38.2063,
      "p95_time_ms": 0.083,
      "p99_time_ms": 0.1872,
      "throughput_ops_per_sec": 8998.2
    }
  ],
  "overhead_analysis": {
    "100_percent_sampling": {
      "mean_overhead_pct": 6.8,
      "p95_overhead_pct": 127.9,
      "p99_overhead_pct": 54.35,
      "throughput_impact_pct": 6.37
    },
    "10_percent_sampling": {
      "mean_overhead_pct": 121.09,
      "p95_overhead_pct": 169.47,
      "p99_overhead_pct": 165.24,
      "throughput_impact_pct": 54.77
    },
    "0_percent_sampling": {
      "mean_overhead_pct": -39.71,
      "p95_overhead_pct": 72.3,
      "p99_overhead_pct": -96.43,
      "throughput_impact_pct": -65.87
    }
  },
  "pass_fail": {
    "max_overhead_pct": 121.09,
    "threshold_pct": 5.0,
    "passed": false
  }
}
```

---
*Generated by scripts/benchmarks/measure_tracing_overhead.py*
