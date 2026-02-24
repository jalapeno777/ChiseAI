"""
Tests for MetricsRegistry.

Story: ST-GOV-004
"""

import pytest
from src.governance.metrics.base_exporter import (
    BaseMetricsExporter,
    MetricPoint,
)
from src.governance.metrics.registry import get_registry


class TestExporter(BaseMetricsExporter):
    """Test exporter for registry tests."""

    def collect(self) -> list[MetricPoint]:
        return [MetricPoint(name="test.metric", value=1.0)]


class TestMetricsRegistryAdvanced:
    """Advanced tests for MetricsRegistry."""

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """Clear registry before each test."""
        registry = get_registry()
        registry.clear()
        yield registry
        registry.clear()

    def test_singleton_consistency(self):
        """Test that get_registry returns consistent singleton."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_export_all_returns_results(self):
        """Test export_all returns results for each exporter."""
        registry = get_registry()

        exporter1 = TestExporter(feature_name="e1")
        exporter2 = TestExporter(feature_name="e2")

        registry.register(exporter1)
        registry.register(exporter2)

        results = registry.export_all()

        assert "e1" in results
        assert "e2" in results
        assert results["e1"].success
        assert results["e2"].success

    def test_stats_tracking(self):
        """Test that registry tracks statistics correctly."""
        registry = get_registry()

        exporter = TestExporter(feature_name="test")
        registry.register(exporter)

        # Initial stats
        stats = registry.get_stats()
        assert stats.exporters_registered == 1
        assert stats.total_collections == 0

        # After collection
        registry.collect_all()
        stats = registry.get_stats()
        assert stats.total_collections == 1

    def test_health_check(self):
        """Test registry health check."""
        registry = get_registry()

        # No exporters
        assert not registry.is_healthy()

        # With healthy exporter
        exporter = TestExporter(feature_name="test")
        registry.register(exporter)
        exporter.export()  # Makes it healthy

        assert registry.is_healthy()

    def test_multiple_exporters(self):
        """Test registering multiple exporters."""
        registry = get_registry()

        for i in range(5):
            registry.register(TestExporter(feature_name=f"exporter_{i}"))

        assert len(registry.get_feature_names()) == 5

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent exporter."""
        registry = get_registry()
        result = registry.unregister("nonexistent")
        assert not result

    def test_overwrite_exporter(self):
        """Test overwriting existing exporter."""
        registry = get_registry()

        exporter1 = TestExporter(feature_name="test")
        exporter2 = TestExporter(feature_name="test")

        registry.register(exporter1)
        registry.register(exporter2)

        # Should have exporter2, not exporter1
        assert registry.get_exporter("test") is exporter2
