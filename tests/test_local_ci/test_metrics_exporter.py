"""Test metrics exporter functionality.

Tests the local_ci_metrics_exporter module.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from local_ci_metrics_exporter import (
    CacheMetrics,
    CIMetrics,
    MetricsCollector,
    ParallelMetrics,
    SpeedOptimizationMetrics,
)


class TestCacheMetrics:
    """Test cases for CacheMetrics dataclass."""

    def test_cache_metrics_defaults(self):
        """Test CacheMetrics with default values."""
        metrics = CacheMetrics()
        assert metrics.hits == 0
        assert metrics.misses == 0
        assert metrics.invalidations == 0
        assert metrics.stored == 0
        assert metrics.hit_rate == 0.0

    def test_cache_metrics_with_values(self):
        """Test CacheMetrics with specific values."""
        metrics = CacheMetrics(hits=75, misses=25, hit_rate=75.0)
        assert metrics.hits == 75
        assert metrics.misses == 25
        assert metrics.hit_rate == 75.0


class TestParallelMetrics:
    """Test cases for ParallelMetrics dataclass."""

    def test_parallel_metrics_defaults(self):
        """Test ParallelMetrics with default values."""
        metrics = ParallelMetrics()
        assert metrics.worker_count == 0
        assert metrics.test_distribution == {}
        assert metrics.speedup == 0.0
        assert metrics.worker_utilization == 0.0

    def test_parallel_metrics_with_values(self):
        """Test ParallelMetrics with specific values."""
        metrics = ParallelMetrics(
            worker_count=4,
            test_distribution={"worker_0": 25, "worker_1": 25},
            speedup=2.5,
            worker_utilization=0.85,
        )
        assert metrics.worker_count == 4
        assert metrics.test_distribution == {"worker_0": 25, "worker_1": 25}
        assert metrics.speedup == 2.5
        assert metrics.worker_utilization == 0.85


class TestSpeedOptimizationMetrics:
    """Test cases for SpeedOptimizationMetrics dataclass."""

    def test_speed_optimization_metrics_defaults(self):
        """Test SpeedOptimizationMetrics with default values."""
        metrics = SpeedOptimizationMetrics()
        assert metrics.total_duration == 0.0
        assert metrics.selected_test_count == 0
        assert metrics.tests_run == 0
        assert metrics.parallel is False

    def test_speed_optimization_metrics_with_values(self):
        """Test SpeedOptimizationMetrics with specific values."""
        metrics = SpeedOptimizationMetrics(
            total_duration=45.5,
            selected_test_count=100,
            tests_run=100,
            tests_passed=98,
            tests_failed=2,
            parallel=True,
            cache_hit_rate=75.0,
        )
        assert metrics.total_duration == 45.5
        assert metrics.selected_test_count == 100
        assert metrics.tests_run == 100
        assert metrics.tests_passed == 98
        assert metrics.tests_failed == 2
        assert metrics.parallel is True
        assert metrics.cache_hit_rate == 75.0


class TestCIMetrics:
    """Test cases for CIMetrics dataclass."""

    def test_ci_metrics_defaults(self):
        """Test CIMetrics with default values."""
        metrics = CIMetrics()
        assert metrics.timestamp == ""
        assert metrics.test_count == 0
        assert metrics.duration == 0.0
        assert metrics.cache_hit_rate == 0.0
        assert metrics.parallel_speedup == 0.0
        assert metrics.worker_utilization == 0.0

    def test_ci_metrics_to_dict(self):
        """Test CIMetrics.to_dict() method."""
        metrics = CIMetrics()
        metrics.timestamp = datetime.now(UTC).isoformat()
        metrics.test_count = 100
        metrics.duration = 45.5
        metrics.cache_hit_rate = 75.0
        metrics.parallel_speedup = 2.3
        metrics.worker_utilization = 0.85
        metrics.cache.hits = 75
        metrics.cache.misses = 25
        metrics.cache.hit_rate = 75.0
        metrics.parallel.worker_count = 4
        metrics.speedup.total_duration = 45.5
        metrics.speedup.selected_test_count = 100

        result = metrics.to_dict()

        assert result["timestamp"] == metrics.timestamp
        assert result["test_count"] == 100
        assert result["duration"] == 45.5
        assert result["cache_hit_rate"] == 75.0
        assert result["cache"]["hits"] == 75
        assert result["parallel"]["worker_count"] == 4


class TestMetricsCollector:
    """Test cases for MetricsCollector class."""

    def test_collector_initialization(self):
        """Test MetricsCollector initializes correctly."""
        collector = MetricsCollector()
        assert collector.influx_host == "http://localhost:8086"
        assert collector.influx_db == "chiseai_ci"
        assert collector.measurement == "local_ci_metrics"

    def test_collector_custom_config(self):
        """Test MetricsCollector with custom configuration."""
        collector = MetricsCollector(
            influx_host="http://custom:8086",
            influx_db="custom_db",
            measurement="custom_metrics",
        )
        assert collector.influx_host == "http://custom:8086"
        assert collector.influx_db == "custom_db"
        assert collector.measurement == "custom_metrics"

    def test_collect_cache_metrics_empty(self):
        """Test collecting cache metrics with no cache."""
        collector = MetricsCollector()
        metrics = collector.collect_cache_metrics(cache=None)
        assert isinstance(metrics, CacheMetrics)
        # When no cache provided, should still return valid metrics structure
        assert metrics.hit_rate == 0.0

    def test_collect_parallel_metrics(self):
        """Test collecting parallel execution metrics."""
        collector = MetricsCollector()
        metrics = collector.collect_parallel_metrics(
            worker_count=4,
            test_distribution={
                "worker_0": 25,
                "worker_1": 25,
                "worker_2": 25,
                "worker_3": 25,
            },
            speedup=2.5,
        )
        assert isinstance(metrics, ParallelMetrics)
        assert metrics.worker_count == 4
        assert metrics.speedup == 2.5

    def test_collect_parallel_metrics_calculates_utilization(self):
        """Test that worker utilization is calculated."""
        collector = MetricsCollector()
        # Equal distribution should give high utilization
        metrics = collector.collect_parallel_metrics(
            worker_count=4,
            test_distribution={"w0": 25, "w1": 25, "w2": 25, "w3": 25},
            speedup=2.0,
        )
        assert metrics.worker_utilization > 0.7  # Should be highly utilized

    def test_collect_speed_optimization_metrics(self):
        """Test collecting speed optimization metrics."""
        collector = MetricsCollector()
        metrics = collector.collect_speed_optimization_metrics(
            total_duration=45.5,
            selected_test_count=100,
        )
        assert isinstance(metrics, SpeedOptimizationMetrics)
        assert metrics.total_duration == 45.5
        assert metrics.selected_test_count == 100

    def test_collect_all_metrics(self):
        """Test collecting all metrics at once."""
        collector = MetricsCollector()
        metrics = collector.collect_all_metrics(
            worker_count=4,
            speedup=2.5,
        )
        assert isinstance(metrics, CIMetrics)
        assert metrics.parallel.worker_count == 4
        assert metrics.parallel_speedup == 2.5

    def test_to_influx_line_protocol(self):
        """Test InfluxDB line protocol generation."""
        collector = MetricsCollector()

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
        test_metrics.parallel.worker_count = 4
        test_metrics.speedup.total_duration = 45.5
        test_metrics.speedup.selected_test_count = 100
        test_metrics.speedup.tests_run = 100
        test_metrics.speedup.parallel = True

        line = collector.to_influx_line_protocol(test_metrics)

        # Verify line protocol format
        assert "local_ci_metrics" in line
        assert "test_count=100" in line
        assert "duration=45.5" in line
        assert "cache_hit_rate=75.0" in line
        # Should end with nanosecond timestamp
        parts = line.split()
        assert len(parts) == 3
        # Last part should be a large number (nanoseconds)
        assert int(parts[-1]) > 1e18

    def test_to_json(self):
        """Test JSON export."""
        collector = MetricsCollector()

        test_metrics = CIMetrics()
        test_metrics.timestamp = datetime.now(UTC).isoformat()
        test_metrics.test_count = 100

        json_str = collector.to_json(test_metrics)
        data = json.loads(json_str)

        assert data["test_count"] == 100
        assert data["timestamp"] == test_metrics.timestamp

    def test_export_to_file_json(self, tmp_path):
        """Test exporting metrics to JSON file."""
        collector = MetricsCollector()

        test_metrics = CIMetrics()
        test_metrics.test_count = 100

        json_file = tmp_path / "metrics.json"
        result = collector.export_to_file(json_file, test_metrics, format="json")

        assert result is True
        assert json_file.exists()

        data = json.loads(json_file.read_text())
        assert data["test_count"] == 100

    def test_export_to_file_line(self, tmp_path):
        """Test exporting metrics to InfluxDB line protocol file."""
        collector = MetricsCollector()

        test_metrics = CIMetrics()
        test_metrics.test_count = 100
        test_metrics.speedup.parallel = True

        influx_file = tmp_path / "metrics.influx"
        result = collector.export_to_file(influx_file, test_metrics, format="line")

        assert result is True
        assert influx_file.exists()

        content = influx_file.read_text()
        assert "local_ci_metrics" in content
        assert "test_count=100" in content


class TestBucketize:
    """Test bucketization for tag values."""

    def test_bucketize_zero(self):
        """Test bucketization of zero."""
        collector = MetricsCollector()
        assert collector._bucketize(0.0, 10) == "0"

    def test_bucketize_full(self):
        """Test bucketization of 100."""
        collector = MetricsCollector()
        result = collector._bucketize(100.0, 10)
        assert result.startswith("gt")

    def test_bucketize_mid(self):
        """Test bucketization of middle values."""
        collector = MetricsCollector()
        # 50% with 10 buckets should be bucket 5
        result = collector._bucketize(50.0, 10)
        assert result == "5"


class TestEmitMetrics:
    """Test the emit_metrics convenience function."""

    def test_emit_metrics_returns_ci_metrics(self):
        """Test that emit_metrics returns CIMetrics."""
        from local_ci_metrics_exporter import emit_metrics

        metrics = emit_metrics(worker_count=4, speedup=2.5)
        assert isinstance(metrics, CIMetrics)
        assert metrics.parallel.worker_count == 4
        assert metrics.parallel_speedup == 2.5

    def test_emit_metrics_with_export(self, tmp_path):
        """Test emit_metrics with file export."""
        from local_ci_metrics_exporter import emit_metrics

        metrics = emit_metrics(
            worker_count=4,
            export_influx=True,
            export_json=True,
            output_dir=str(tmp_path),
        )
        assert isinstance(metrics, CIMetrics)

        # Verify files were created
        influx_file = tmp_path / "metrics.influx"
        json_file = tmp_path / "metrics.json"
        assert influx_file.exists()
        assert json_file.exists()
