"""
Tests for Governance Metrics Exporters.

Story: ST-GOV-004
"""

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
    MetricType,
    ExportResult,
)
from src.governance.metrics.registry import MetricsRegistry, get_registry
from src.governance.constitution.metrics_exporter import ConstitutionMetricsExporter
from src.governance.sentinel.metrics_exporter import SentinelMetricsExporter
from src.governance.memory.metrics_exporter import MemoryMetricsExporter


class TestMetricPoint:
    """Test MetricPoint dataclass."""

    def test_metric_point_creation(self):
        """Test basic MetricPoint creation."""
        point = MetricPoint(
            name="test.metric",
            value=42.0,
        )
        assert point.name == "test.metric"
        assert point.value == 42.0
        assert point.metric_type == MetricType.GAUGE
        assert isinstance(point.timestamp, datetime)
        assert point.tags == {}
        assert point.fields == {}

    def test_metric_point_with_tags(self):
        """Test MetricPoint with tags and fields."""
        point = MetricPoint(
            name="test.metric",
            value=100.0,
            metric_type=MetricType.COUNTER,
            tags={"feature": "test", "status": "active"},
            fields={"unit": "ms"},
        )
        assert point.tags == {"feature": "test", "status": "active"}
        assert point.fields == {"unit": "ms"}
        assert point.metric_type == MetricType.COUNTER


class DummyExporter(BaseMetricsExporter):
    """Dummy exporter for testing."""

    def collect(self) -> list[MetricPoint]:
        return [
            MetricPoint(name="dummy.count", value=10.0, metric_type=MetricType.COUNTER),
            MetricPoint(name="dummy.gauge", value=5.0, metric_type=MetricType.GAUGE),
        ]


class TestBaseMetricsExporter:
    """Test BaseMetricsExporter abstract class."""

    def test_exporter_initialization(self):
        """Test exporter initialization."""
        exporter = DummyExporter(feature_name="dummy")
        assert exporter.feature_name == "dummy"
        assert exporter._influx_client is None
        assert exporter._redis_client is None

    def test_exporter_collect(self):
        """Test collect method returns metrics."""
        exporter = DummyExporter(feature_name="dummy")
        points = exporter.collect()
        assert len(points) == 2
        assert points[0].name == "dummy.count"
        assert points[1].name == "dummy.gauge"

    def test_export_without_influx(self):
        """Test export without InfluxDB client."""
        exporter = DummyExporter(feature_name="dummy")
        result = exporter.export()
        assert result.success
        assert result.points_exported == 2

    def test_exporter_health(self):
        """Test exporter health check."""
        exporter = DummyExporter(feature_name="dummy")
        assert not exporter.is_healthy()  # Never collected

        exporter.export()
        assert exporter.is_healthy()  # Just collected


class TestMetricsRegistry:
    """Test MetricsRegistry singleton."""

    def test_registry_singleton(self):
        """Test that registry is a singleton."""
        r1 = MetricsRegistry()
        r2 = MetricsRegistry()
        assert r1 is r2

    def test_get_registry(self):
        """Test get_registry function."""
        registry = get_registry()
        assert isinstance(registry, MetricsRegistry)

    def test_register_exporter(self):
        """Test registering an exporter."""
        registry = get_registry()
        registry.clear()  # Start fresh

        exporter = DummyExporter(feature_name="test")
        registry.register(exporter)

        assert "test" in registry.get_feature_names()
        assert registry.get_exporter("test") is exporter

    def test_unregister_exporter(self):
        """Test unregistering an exporter."""
        registry = get_registry()
        registry.clear()

        exporter = DummyExporter(feature_name="test2")
        registry.register(exporter)
        assert registry.unregister("test2")
        assert registry.get_exporter("test2") is None

    def test_collect_all(self):
        """Test collecting from all exporters."""
        registry = get_registry()
        registry.clear()

        exporter1 = DummyExporter(feature_name="e1")
        exporter2 = DummyExporter(feature_name="e2")
        registry.register(exporter1)
        registry.register(exporter2)

        all_points = registry.collect_all()
        assert len(all_points) == 4  # 2 points each


class TestConstitutionMetricsExporter:
    """Test ConstitutionMetricsExporter."""

    def test_collect_without_redis(self):
        """Test collection without Redis client."""
        exporter = ConstitutionMetricsExporter()
        points = exporter.collect()

        # Should return metrics even without Redis
        assert len(points) > 0

        # Check for expected metric names
        names = [p.name for p in points]
        assert "governance.constitution.violations.total" in names
        assert "governance.constitution.queries.total" in names
        assert "governance.constitution.enabled" in names

    def test_record_violation(self):
        """Test recording a violation."""
        exporter = ConstitutionMetricsExporter()
        exporter.record_violation("test_type")

        points = exporter.collect()
        violations_point = next(
            (p for p in points if p.name == "governance.constitution.violations.total"),
            None,
        )
        assert violations_point is not None
        assert violations_point.value == 1.0

    def test_record_query(self):
        """Test recording a query."""
        exporter = ConstitutionMetricsExporter()
        exporter.record_query(latency_ms=50.0)

        points = exporter.collect()
        queries_point = next(
            (p for p in points if p.name == "governance.constitution.queries.total"),
            None,
        )
        assert queries_point is not None
        assert queries_point.value == 1.0


class TestSentinelMetricsExporter:
    """Test SentinelMetricsExporter."""

    def test_collect_without_redis(self):
        """Test collection without Redis client."""
        exporter = SentinelMetricsExporter()
        points = exporter.collect()

        assert len(points) > 0

        names = [p.name for p in points]
        assert "governance.sentinel.tasks.validated" in names
        assert "governance.sentinel.tasks.blocked" in names
        assert "governance.sentinel.enabled" in names

    def test_record_validation(self):
        """Test recording task validation."""
        exporter = SentinelMetricsExporter()
        exporter.record_validation(story_points=8, blocked=True)
        exporter.record_validation(story_points=3, approved=True)

        points = exporter.collect()

        validated = next(
            p for p in points if p.name == "governance.sentinel.tasks.validated"
        )
        blocked = next(
            p for p in points if p.name == "governance.sentinel.tasks.blocked"
        )

        assert validated.value == 2.0
        assert blocked.value == 1.0


class TestMemoryMetricsExporter:
    """Test MemoryMetricsExporter."""

    def test_collect_without_redis(self):
        """Test collection without Redis client."""
        exporter = MemoryMetricsExporter()
        points = exporter.collect()

        assert len(points) > 0

        names = [p.name for p in points]
        assert "governance.memory.dedup.scanned" in names
        assert "governance.memory.retrieval.hit_rate" in names
        assert "governance.memory.enabled" in names

    def test_record_dedup_run(self):
        """Test recording dedup run."""
        exporter = MemoryMetricsExporter()
        exporter.record_dedup_run(
            scanned=100, duplicates=10, removed=8, bytes_saved=1024
        )

        points = exporter.collect()

        scanned = next(p for p in points if p.name == "governance.memory.dedup.scanned")
        assert scanned.value == 100.0

    def test_record_retrieval(self):
        """Test recording retrieval."""
        exporter = MemoryMetricsExporter()
        exporter.record_retrieval(hit=True)
        exporter.record_retrieval(hit=True)
        exporter.record_retrieval(hit=False)

        points = exporter.collect()

        hits = next(p for p in points if p.name == "governance.memory.retrieval.hits")
        misses = next(
            p for p in points if p.name == "governance.memory.retrieval.misses"
        )

        assert hits.value == 2.0
        assert misses.value == 1.0

    def test_hit_rate_calculation(self):
        """Test hit rate is calculated correctly."""
        exporter = MemoryMetricsExporter()

        # 80% hit rate
        for _ in range(8):
            exporter.record_retrieval(hit=True)
        for _ in range(2):
            exporter.record_retrieval(hit=False)

        points = exporter.collect()
        hit_rate = next(
            p for p in points if p.name == "governance.memory.retrieval.hit_rate"
        )

        assert hit_rate.value == 80.0
