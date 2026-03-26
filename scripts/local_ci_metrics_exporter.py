#!/usr/bin/env python3
"""Local CI Metrics Exporter - Exports metrics to InfluxDB line protocol for Grafana.

This module provides:
- Metrics collection from cache, parallel runner, and speed optimizations
- InfluxDB line protocol output for Grafana integration
- JSON export for local debugging
- Metrics: test_count, duration, cache_hit_rate, parallel_speedup, worker_utilization

Usage:
    python scripts/local_ci_metrics_exporter.py --export-influx
    python scripts/local_ci_metrics_exporter.py --export-json
    python scripts/local_ci_metrics_exporter.py --test-export

Integration:
    This exporter is called by local_ci_speed_optimizations.py and local_ci_parallel_runner.py
    to emit metrics during CI runs.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure project root is in sys.path for imports
_script_dir = Path(__file__).parent.resolve()
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Try to import local modules
try:
    from local_ci_incremental_cache import IncrementalCache
except ImportError:
    IncrementalCache = None

try:
    from local_ci_speed_optimizations import BenchmarkResult
except ImportError:
    BenchmarkResult = None


# Default InfluxDB configuration
DEFAULT_INFLUX_HOST = "http://localhost:8086"
DEFAULT_INFLUX_DB = "chiseai_ci"
DEFAULT_INFLUX_MEASUREMENT = "local_ci_metrics"


@dataclass
class CacheMetrics:
    """Cache-related metrics."""

    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    stored: int = 0
    hit_rate: float = 0.0


@dataclass
class ParallelMetrics:
    """Parallel execution metrics."""

    worker_count: int = 0
    test_distribution: dict[str, int] = field(default_factory=dict)
    speedup: float = 0.0
    worker_utilization: float = 0.0


@dataclass
class SpeedOptimizationMetrics:
    """Speed optimization metrics."""

    total_duration: float = 0.0
    selected_test_count: int = 0
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    parallel: bool = False
    cache_hit_rate: float = 0.0


@dataclass
class CIMetrics:
    """Complete CI metrics snapshot."""

    timestamp: str = ""
    test_count: int = 0
    duration: float = 0.0
    cache_hit_rate: float = 0.0
    parallel_speedup: float = 0.0
    worker_utilization: float = 0.0
    cache: CacheMetrics = field(default_factory=CacheMetrics)
    parallel: ParallelMetrics = field(default_factory=ParallelMetrics)
    speedup: SpeedOptimizationMetrics = field(default_factory=SpeedOptimizationMetrics)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "timestamp": self.timestamp,
            "test_count": self.test_count,
            "duration": self.duration,
            "cache_hit_rate": self.cache_hit_rate,
            "parallel_speedup": self.parallel_speedup,
            "worker_utilization": self.worker_utilization,
            "cache": {
                "hits": self.cache.hits,
                "misses": self.cache.misses,
                "invalidations": self.cache.invalidations,
                "stored": self.cache.stored,
                "hit_rate": self.cache.hit_rate,
            },
            "parallel": {
                "worker_count": self.parallel.worker_count,
                "test_distribution": self.parallel.test_distribution,
                "speedup": self.parallel.speedup,
                "worker_utilization": self.parallel.worker_utilization,
            },
            "speedup": {
                "total_duration": self.speedup.total_duration,
                "selected_test_count": self.speedup.selected_test_count,
                "tests_run": self.speedup.tests_run,
                "tests_passed": self.speedup.tests_passed,
                "tests_failed": self.speedup.tests_failed,
                "tests_skipped": self.speedup.tests_skipped,
                "parallel": self.speedup.parallel,
                "cache_hit_rate": self.speedup.cache_hit_rate,
            },
        }


class MetricsCollector:
    """Collects and exports CI metrics."""

    def __init__(
        self,
        influx_host: str = DEFAULT_INFLUX_HOST,
        influx_db: str = DEFAULT_INFLUX_DB,
        measurement: str = DEFAULT_INFLUX_MEASUREMENT,
    ):
        """Initialize metrics collector.

        Args:
            influx_host: InfluxDB host URL
            influx_db: InfluxDB database name
            measurement: Measurement name for metrics
        """
        self.influx_host = influx_host
        self.influx_db = influx_db
        self.measurement = measurement
        self._current_metrics: CIMetrics | None = None

    def collect_cache_metrics(
        self, cache: IncrementalCache | None = None
    ) -> CacheMetrics:
        """Collect cache metrics from IncrementalCache.

        Args:
            cache: Optional IncrementalCache instance to collect from

        Returns:
            CacheMetrics object
        """
        metrics = CacheMetrics()

        if cache is None:
            # Try to get from default cache
            if IncrementalCache:
                with contextlib.suppress(Exception):
                    cache = IncrementalCache()

        if cache:
            try:
                stats = cache.get_stats()
                metrics.hits = stats.hits
                metrics.misses = stats.misses
                metrics.invalidations = stats.invalidations
                metrics.stored = stats.stored
                metrics.hit_rate = stats.hit_rate
            except Exception:
                pass

        return metrics

    def collect_parallel_metrics(
        self,
        worker_count: int = 0,
        test_distribution: dict[str, int] | None = None,
        speedup: float = 0.0,
    ) -> ParallelMetrics:
        """Collect parallel execution metrics.

        Args:
            worker_count: Number of parallel workers
            test_distribution: Dict mapping worker to test count
            speedup: Speedup factor vs sequential execution

        Returns:
            ParallelMetrics object
        """
        metrics = ParallelMetrics()
        metrics.worker_count = worker_count
        metrics.test_distribution = test_distribution or {}
        metrics.speedup = speedup

        # Calculate worker utilization
        if worker_count > 0 and test_distribution:
            total_tests = sum(test_distribution.values())
            if total_tests > 0:
                # Estimate utilization based on test distribution variance
                avg_tests = total_tests / worker_count
                if avg_tests > 0:
                    variance = (
                        sum(
                            (count - avg_tests) ** 2
                            for count in test_distribution.values()
                        )
                        / worker_count
                    )
                    # Higher variance = lower utilization
                    cv = (variance**0.5) / avg_tests if avg_tests > 0 else 0
                    metrics.worker_utilization = max(0.0, min(1.0, 1.0 - (cv * 0.5)))

        return metrics

    def collect_speed_optimization_metrics(
        self,
        benchmark_result: BenchmarkResult | None = None,
        total_duration: float = 0.0,
        selected_test_count: int = 0,
    ) -> SpeedOptimizationMetrics:
        """Collect speed optimization metrics.

        Args:
            benchmark_result: Optional BenchmarkResult from speed optimizations
            total_duration: Total duration in seconds
            selected_test_count: Number of selected tests

        Returns:
            SpeedOptimizationMetrics object
        """
        metrics = SpeedOptimizationMetrics()
        metrics.total_duration = total_duration
        metrics.selected_test_count = selected_test_count

        if benchmark_result:
            metrics.total_duration = benchmark_result.duration_seconds
            metrics.selected_test_count = len(benchmark_result.selected_tests)
            metrics.tests_run = benchmark_result.tests_run
            metrics.tests_passed = benchmark_result.tests_passed
            metrics.tests_failed = benchmark_result.tests_failed
            metrics.tests_skipped = benchmark_result.tests_skipped
            metrics.parallel = benchmark_result.parallel
            metrics.cache_hit_rate = benchmark_result.cache_hit_rate

        return metrics

    def collect_all_metrics(
        self,
        cache: IncrementalCache | None = None,
        benchmark_result: BenchmarkResult | None = None,
        worker_count: int = 0,
        test_distribution: dict[str, int] | None = None,
        speedup: float = 0.0,
    ) -> CIMetrics:
        """Collect all CI metrics.

        Args:
            cache: Optional IncrementalCache instance
            benchmark_result: Optional BenchmarkResult
            worker_count: Number of parallel workers
            test_distribution: Dict mapping worker to test count
            speedup: Speedup factor vs sequential

        Returns:
            CIMetrics object with all collected metrics
        """
        metrics = CIMetrics()
        metrics.timestamp = datetime.now(UTC).isoformat()

        # Collect cache metrics
        metrics.cache = self.collect_cache_metrics(cache)
        metrics.cache_hit_rate = metrics.cache.hit_rate

        # Collect parallel metrics
        metrics.parallel = self.collect_parallel_metrics(
            worker_count, test_distribution, speedup
        )
        metrics.parallel_speedup = metrics.parallel.speedup
        metrics.worker_utilization = metrics.parallel.worker_utilization

        # Collect speed optimization metrics
        metrics.speedup = self.collect_speed_optimization_metrics(benchmark_result)
        metrics.duration = metrics.speedup.total_duration
        metrics.test_count = metrics.speedup.tests_run

        self._current_metrics = metrics
        return metrics

    def to_influx_line_protocol(self, metrics: CIMetrics | None = None) -> str:
        """Convert metrics to InfluxDB line protocol format.

        Args:
            metrics: Optional metrics to convert (uses current if not provided)

        Returns:
            String in InfluxDB line protocol format
        """
        if metrics is None:
            metrics = self._current_metrics
        if metrics is None:
            metrics = CIMetrics()

        timestamp = int(time.time() * 1e9)  # nanoseconds

        # Build tag set
        tags = [
            f"parallel={str(metrics.speedup.parallel).lower()}",
            f"cache_hit_rate_bucket={self._bucketize(metrics.cache_hit_rate, 10)}",
        ]

        # Build field set
        fields = [
            f"test_count={metrics.test_count}",
            f"duration={metrics.duration}",
            f"cache_hit_rate={metrics.cache_hit_rate}",
            f"parallel_speedup={metrics.parallel_speedup}",
            f"worker_utilization={metrics.worker_utilization}",
            f"cache_hits={metrics.cache.hits}i",
            f"cache_misses={metrics.cache.misses}i",
            f"cache_invalidations={metrics.cache.invalidations}i",
            f"cache_stored={metrics.cache.stored}i",
            f"worker_count={metrics.parallel.worker_count}i",
            f"selected_test_count={metrics.speedup.selected_test_count}i",
            f"tests_run={metrics.speedup.tests_run}i",
            f"tests_passed={metrics.speedup.tests_passed}i",
            f"tests_failed={metrics.speedup.tests_failed}i",
            f"tests_skipped={metrics.speedup.tests_skipped}i",
        ]

        tag_str = ",".join(tags)
        field_str = ",".join(fields)

        return f"{self.measurement},{tag_str} {field_str} {timestamp}"

    def to_json(self, metrics: CIMetrics | None = None, indent: int = 2) -> str:
        """Convert metrics to JSON format.

        Args:
            metrics: Optional metrics to convert (uses current if not provided)
            indent: JSON indentation level

        Returns:
            JSON string
        """
        if metrics is None:
            metrics = self._current_metrics
        if metrics is None:
            metrics = CIMetrics()

        return json.dumps(metrics.to_dict(), indent=indent)

    def export_to_file(
        self,
        filepath: str | Path,
        metrics: CIMetrics | None = None,
        format: str = "json",
    ) -> bool:
        """Export metrics to a file.

        Args:
            filepath: Path to output file
            metrics: Optional metrics to export (uses current if not provided)
            format: Export format ('json' or 'line')

        Returns:
            True if successful
        """
        if metrics is None:
            metrics = self._current_metrics
        if metrics is None:
            metrics = CIMetrics()

        try:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)

            if format == "line":
                content = self.to_influx_line_protocol(metrics)
            else:
                content = self.to_json(metrics)

            with open(path, "w") as f:
                f.write(content)

            return True
        except Exception as e:
            print(f"Failed to export metrics: {e}", file=sys.stderr)
            return False

    def _bucketize(self, value: float, bucket_count: int = 10) -> str:
        """Bucket a value into categories for tags.

        Args:
            value: Value to bucket
            bucket_count: Number of buckets (0-100 divided into bucket_count buckets)

        Returns:
            Bucket label string
        """
        if value <= 0:
            return "0"
        if value >= 100:
            return f"gt{bucket_count - 1}"

        bucket_size = 100 / bucket_count
        bucket = int(value / bucket_size)
        return str(min(bucket, bucket_count - 1))


# Global metrics collector instance
_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    """Get or create the global metrics collector.

    Returns:
        MetricsCollector instance
    """
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def emit_metrics(
    cache: IncrementalCache | None = None,
    benchmark_result: BenchmarkResult | None = None,
    worker_count: int = 0,
    test_distribution: dict[str, int] | None = None,
    speedup: float = 0.0,
    export_influx: bool = False,
    export_json: bool = False,
    output_dir: str = "_bmad-output/ci",
) -> CIMetrics:
    """Convenience function to emit metrics from CI components.

    Args:
        cache: Optional IncrementalCache instance
        benchmark_result: Optional BenchmarkResult
        worker_count: Number of parallel workers
        test_distribution: Dict mapping worker to test count
        speedup: Speedup factor vs sequential
        export_influx: Whether to export in InfluxDB line protocol
        export_json: Whether to export in JSON format
        output_dir: Output directory for exports

    Returns:
        CIMetrics object with all collected metrics
    """
    collector = get_collector()

    metrics = collector.collect_all_metrics(
        cache=cache,
        benchmark_result=benchmark_result,
        worker_count=worker_count,
        test_distribution=test_distribution,
        speedup=speedup,
    )

    # Export to files if requested
    if export_influx:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        influx_file = output_path / "metrics.influx"
        collector.export_to_file(influx_file, metrics, format="line")

    if export_json:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_file = output_path / "metrics.json"
        collector.export_to_file(json_file, metrics, format="json")

    return metrics


def main() -> int:
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Local CI Metrics Exporter - Export metrics to InfluxDB/Grafana"
    )
    parser.add_argument(
        "--export-influx",
        action="store_true",
        help="Export metrics in InfluxDB line protocol format",
    )
    parser.add_argument(
        "--export-json",
        action="store_true",
        help="Export metrics in JSON format",
    )
    parser.add_argument(
        "--test-export",
        action="store_true",
        help="Run a test export to verify functionality",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/ci",
        help="Output directory for exports (default: _bmad-output/ci)",
    )
    parser.add_argument(
        "--influx-host",
        default=DEFAULT_INFLUX_HOST,
        help=f"InfluxDB host URL (default: {DEFAULT_INFLUX_HOST})",
    )
    parser.add_argument(
        "--influx-db",
        default=DEFAULT_INFLUX_DB,
        help=f"InfluxDB database name (default: {DEFAULT_INFLUX_DB})",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print metrics to stdout",
    )

    args = parser.parse_args()

    collector = MetricsCollector(
        influx_host=args.influx_host,
        influx_db=args.influx_db,
    )

    if args.test_export:
        print("Running metrics exporter test...")

        # Create test metrics
        test_metrics = CIMetrics()
        test_metrics.timestamp = datetime.now(UTC).isoformat()
        test_metrics.test_count = 100
        test_metrics.duration = 45.5
        test_metrics.cache_hit_rate = 75.0
        test_metrics.parallel_speedup = 2.3
        test_metrics.worker_utilization = 0.85
        test_metrics.cache.hits = 75
        test_metrics.cache.misses = 25
        test_metrics.cache.invalidations = 5
        test_metrics.cache.stored = 100
        test_metrics.parallel.worker_count = 4
        test_metrics.parallel.test_distribution = {
            "worker_0": 25,
            "worker_1": 25,
            "worker_2": 25,
            "worker_3": 25,
        }
        test_metrics.parallel.speedup = 2.3
        test_metrics.parallel.worker_utilization = 0.85
        test_metrics.speedup.total_duration = 45.5
        test_metrics.speedup.selected_test_count = 100
        test_metrics.speedup.tests_run = 100
        test_metrics.speedup.tests_passed = 98
        test_metrics.speedup.tests_failed = 2
        test_metrics.speedup.tests_skipped = 0
        test_metrics.speedup.parallel = True
        test_metrics.speedup.cache_hit_rate = 75.0

        # Test JSON export
        json_output = collector.to_json(test_metrics)
        print("\nJSON Export:")
        print(json_output)

        # Test InfluxDB line protocol export
        influx_output = collector.to_influx_line_protocol(test_metrics)
        print("\nInfluxDB Line Protocol:")
        print(influx_output)

        # Test file export
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        json_file = output_path / "test_metrics.json"
        collector.export_to_file(json_file, test_metrics, format="json")
        print(f"\nExported JSON to: {json_file}")

        influx_file = output_path / "test_metrics.influx"
        collector.export_to_file(influx_file, test_metrics, format="line")
        print(f"Exported InfluxDB line protocol to: {influx_file}")

        print("\n✓ Metrics exporter test completed successfully!")
        return 0

    # Default: print current metrics
    metrics = collector.collect_all_metrics()

    if args.print:
        print(collector.to_json(metrics))

    if args.export_json:
        collector.export_to_file(
            Path(args.output_dir) / "metrics.json", metrics, format="json"
        )
        print(f"Exported JSON to: {args.output_dir}/metrics.json")

    if args.export_influx:
        collector.export_to_file(
            Path(args.output_dir) / "metrics.influx", metrics, format="line"
        )
        print(f"Exported InfluxDB line protocol to: {args.output_dir}/metrics.influx")

    if not args.print and not args.export_json and not args.export_influx:
        print("No export options specified. Use --help for options.")
        print("\nCurrent metrics:")
        print(collector.to_json(metrics))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
