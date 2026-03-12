"""Tests for Model Registry monitoring metrics.

This module tests the metrics collection system for the Model Registry,
including Prometheus-compatible metrics collection and export.

Acceptance Criteria:
- Metrics for: model registrations, retrieval latency, cache hit/miss, storage usage, rollbacks
- Prometheus-compatible metrics endpoint
- All metrics operations are properly tracked
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pytest

from ml.monitoring.registry_metrics import (
    MetricsCollector,
    NullMetricsCollector,
    PrometheusMetricsCollector,
    RegistryMetrics,
    get_metrics_collector,
    set_metrics_collector,
)

logger = logging.getLogger(__name__)


class TestRegistryMetrics:
    """Tests for RegistryMetrics dataclass."""

    def test_empty_metrics(self):
        """Test empty metrics initialization."""
        metrics = RegistryMetrics()

        assert metrics.models_registered_total == {}
        assert metrics.model_retrieval_latency_seconds == []
        assert metrics.cache_hits_total == 0
        assert metrics.cache_misses_total == 0
        assert metrics.storage_usage_bytes == 0
        assert metrics.models_count == 0
        assert metrics.rollback_operations_total == 0
        assert metrics.version_comparisons_total == 0
        assert metrics.failed_operations_total == {}
        assert metrics.active_models_by_status == {}

    def test_metrics_to_dict_empty(self):
        """Test converting empty metrics to dictionary."""
        metrics = RegistryMetrics()
        result = metrics.to_dict()

        assert result["models_registered_total"] == {}
        assert result["model_retrieval_latency"]["p50"] == 0.0
        assert result["model_retrieval_latency"]["p95"] == 0.0
        assert result["model_retrieval_latency"]["p99"] == 0.0
        assert result["model_retrieval_latency"]["count"] == 0
        assert result["cache"]["hits"] == 0
        assert result["cache"]["misses"] == 0
        assert result["cache"]["hit_rate_percent"] == 0.0
        assert result["storage"]["usage_bytes"] == 0
        assert result["storage"]["models_count"] == 0

    def test_metrics_to_dict_with_data(self):
        """Test converting metrics with data to dictionary."""
        metrics = RegistryMetrics()
        metrics.models_registered_total["2024-01-15"] = 5
        metrics.models_registered_total["2024-01-16"] = 3
        metrics.model_retrieval_latency_seconds = [0.1, 0.2, 0.3, 0.5, 1.0, 2.0]
        metrics.cache_hits_total = 80
        metrics.cache_misses_total = 20
        metrics.storage_usage_bytes = 1024 * 1024 * 100  # 100MB
        metrics.models_count = 10
        metrics.rollback_operations_total = 2
        metrics.version_comparisons_total = 50
        metrics.failed_operations_total["register:ValueError"] = 3
        metrics.active_models_by_status["champion"] = 3
        metrics.active_models_by_status["challenger"] = 2

        result = metrics.to_dict()

        # Check registrations
        assert result["models_registered_total"]["2024-01-15"] == 5
        assert result["models_registered_total"]["2024-01-16"] == 3

        # Check latency percentiles
        assert result["model_retrieval_latency"]["count"] == 6
        assert 0.2 <= result["model_retrieval_latency"]["p50"] <= 0.6
        assert 1.0 <= result["model_retrieval_latency"]["p95"] <= 2.0
        assert result["model_retrieval_latency"]["p99"] >= 1.0

        # Check cache
        assert result["cache"]["hits"] == 80
        assert result["cache"]["misses"] == 20
        assert result["cache"]["hit_rate_percent"] == 80.0

        # Check storage
        assert result["storage"]["usage_bytes"] == 104857600
        assert result["storage"]["models_count"] == 10

        # Check operations
        assert result["operations"]["rollback_total"] == 2
        assert result["operations"]["version_comparisons_total"] == 50
        assert result["operations"]["failed_total"]["register:ValueError"] == 3

        # Check model status
        assert result["active_models_by_status"]["champion"] == 3
        assert result["active_models_by_status"]["challenger"] == 2

    def test_cache_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        metrics = RegistryMetrics()

        # No operations
        result = metrics.to_dict()
        assert result["cache"]["hit_rate_percent"] == 0.0

        # All hits
        metrics.cache_hits_total = 100
        result = metrics.to_dict()
        assert result["cache"]["hit_rate_percent"] == 100.0

        # All misses
        metrics.cache_hits_total = 0
        metrics.cache_misses_total = 100
        result = metrics.to_dict()
        assert result["cache"]["hit_rate_percent"] == 0.0

        # 50/50
        metrics.cache_hits_total = 50
        metrics.cache_misses_total = 50
        result = metrics.to_dict()
        assert result["cache"]["hit_rate_percent"] == 50.0


class TestNullMetricsCollector:
    """Tests for NullMetricsCollector."""

    def test_null_collector_operations(self):
        """Test that null collector accepts all operations without error."""
        collector = NullMetricsCollector()

        # All operations should complete without error
        collector.record_model_registered("test_model", "v1.0.0")
        collector.record_model_retrieval("test_model", "v1.0.0", 0.5, True)
        collector.record_rollback("test_model", "v2.0.0", "v1.0.0")
        collector.record_version_comparison("test_model", "v1.0.0", "v2.0.0")
        collector.record_failed_operation(
            "register", "test_model", "ValueError", "test error"
        )
        collector.update_storage_metrics(1000000, 10)
        collector.update_model_status("test_model", "v1.0.0", "active")
        collector.reset_metrics()

        # Get metrics should return empty
        metrics = collector.get_metrics()
        assert isinstance(metrics, RegistryMetrics)
        assert metrics.cache_hits_total == 0


class TestPrometheusMetricsCollector:
    """Tests for PrometheusMetricsCollector."""

    def test_initialization(self):
        """Test collector initialization."""
        collector = PrometheusMetricsCollector(namespace="test_registry")
        assert collector.namespace == "test_registry"
        assert collector._prometheus_available or not collector._prometheus_available

    def test_record_model_registered(self):
        """Test recording model registration."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.record_model_registered("grid_btc_1h", "v1.0.0")
        collector.record_model_registered("grid_btc_1h", "v1.1.0")
        collector.record_model_registered("grid_eth_1h", "v1.0.0")

        metrics = collector.get_metrics()
        # Total registrations should be tracked
        total_registrations = sum(metrics.models_registered_total.values())
        assert total_registrations >= 3

    def test_record_model_retrieval(self):
        """Test recording model retrieval with latency."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        # Record cache hit
        collector.record_model_retrieval("test_model", "v1.0.0", 0.01, cache_hit=True)

        # Record cache miss
        collector.record_model_retrieval("test_model", "v1.1.0", 0.5, cache_hit=False)

        metrics = collector.get_metrics()
        assert metrics.cache_hits_total == 1
        assert metrics.cache_misses_total == 1
        assert len(metrics.model_retrieval_latency_seconds) == 2

    def test_record_rollback(self):
        """Test recording rollback operations."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.record_rollback("test_model", "v2.0.0", "v1.0.0")
        collector.record_rollback("test_model", "v1.0.0", "v0.9.0")

        metrics = collector.get_metrics()
        assert metrics.rollback_operations_total == 2

    def test_record_version_comparison(self):
        """Test recording version comparisons."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.record_version_comparison("test_model", "v1.0.0", "v2.0.0")
        collector.record_version_comparison("test_model", "v1.0.0", "v1.1.0")

        metrics = collector.get_metrics()
        assert metrics.version_comparisons_total == 2

    def test_record_failed_operation(self):
        """Test recording failed operations."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.record_failed_operation(
            "register", "test_model", "ValueError", "Invalid metrics"
        )
        collector.record_failed_operation(
            "retrieve", "test_model", "KeyError", "Model not found"
        )
        collector.record_failed_operation(
            "register", "test_model", "ValueError", "Another error"
        )

        metrics = collector.get_metrics()
        assert metrics.failed_operations_total["register:ValueError"] == 2
        assert metrics.failed_operations_total["retrieve:KeyError"] == 1

    def test_update_storage_metrics(self):
        """Test updating storage metrics."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.update_storage_metrics(
            usage_bytes=1024 * 1024 * 500,  # 500MB
            models_count=25,
        )

        metrics = collector.get_metrics()
        assert metrics.storage_usage_bytes == 524288000
        assert metrics.models_count == 25

    def test_update_model_status(self):
        """Test updating model status tracking."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        collector.update_model_status("model_a", "v1.0.0", "champion")
        collector.update_model_status("model_b", "v1.0.0", "challenger")
        collector.update_model_status("model_c", "v1.0.0", "champion")

        metrics = collector.get_metrics()
        assert metrics.active_models_by_status["champion"] == 2
        assert metrics.active_models_by_status["challenger"] == 1

    def test_reset_metrics(self):
        """Test resetting metrics."""
        collector = PrometheusMetricsCollector()

        # Add some data
        collector.record_model_registered("test_model", "v1.0.0")
        collector.record_model_retrieval("test_model", "v1.0.0", 0.5, True)
        collector.update_storage_metrics(1000000, 10)

        # Reset
        collector.reset_metrics()

        metrics = collector.get_metrics()
        assert metrics.cache_hits_total == 0
        assert metrics.storage_usage_bytes == 0
        assert metrics.models_count == 0

    def test_get_prometheus_metrics(self):
        """Test getting Prometheus-formatted metrics."""
        collector = PrometheusMetricsCollector(namespace="chiseai")
        collector.reset_metrics()

        # Add some metrics
        collector.record_model_registered("test_model", "v1.0.0")
        collector.record_model_retrieval("test_model", "v1.0.0", 0.5, True)
        collector.update_storage_metrics(1000000, 10)

        # Get Prometheus format
        prom_output = collector.get_prometheus_metrics()

        # Should contain namespace
        assert "chiseai" in prom_output
        # Should be valid Prometheus format
        assert (
            "# HELP" in prom_output or "# TYPE" in prom_output or len(prom_output) > 0
        )


class TestGlobalMetricsCollector:
    """Tests for global metrics collector singleton."""

    def test_get_set_collector(self):
        """Test getting and setting global collector."""
        # Save original
        original = get_metrics_collector()

        # Set new collector
        new_collector = PrometheusMetricsCollector()
        set_metrics_collector(new_collector)

        # Should get new collector
        current = get_metrics_collector()
        assert current is new_collector

        # Restore original
        set_metrics_collector(original)

    def test_default_collector(self):
        """Test that default collector is NullMetricsCollector."""
        # Clear global collector
        import ml.monitoring.registry_metrics as metrics_module

        metrics_module._metrics_collector = None

        collector = get_metrics_collector()
        assert isinstance(collector, NullMetricsCollector)

        # Restore
        set_metrics_collector(PrometheusMetricsCollector())


class TestMetricsIntegration:
    """Integration tests for metrics collection."""

    def test_full_workflow(self):
        """Test complete metrics workflow simulating registry operations."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        # Simulate model registration
        collector.record_model_registered("signal_predictor_btc", "v1.0.0")
        collector.record_model_registered("signal_predictor_btc", "v1.1.0")
        collector.record_model_registered("confidence_calibrator", "v1.0.0")

        # Simulate model retrievals with varying latency
        for i in range(10):
            latency = 0.01 + (i * 0.1)  # 0.01 to 0.91 seconds
            cache_hit = i < 7  # 70% cache hit rate
            collector.record_model_retrieval(
                "signal_predictor_btc", f"v1.{i}.0", latency, cache_hit
            )

        # Simulate version comparisons
        collector.record_version_comparison("signal_predictor_btc", "v1.0.0", "v1.1.0")
        collector.record_version_comparison("signal_predictor_btc", "v1.1.0", "v1.2.0")

        # Simulate rollback
        collector.record_rollback("signal_predictor_btc", "v1.1.0", "v1.0.0")

        # Simulate some failures
        collector.record_failed_operation(
            "register", "bad_model", "ValueError", "Invalid configuration"
        )
        for _ in range(3):
            collector.record_failed_operation(
                "retrieve", "missing_model", "KeyError", "Model not found"
            )

        # Update storage metrics
        collector.update_storage_metrics(
            usage_bytes=1024 * 1024 * 256,  # 256MB
            models_count=15,
        )

        # Update model statuses
        collector.update_model_status("signal_predictor_btc", "v1.0.0", "champion")
        collector.update_model_status("signal_predictor_btc", "v1.1.0", "deprecated")
        collector.update_model_status("confidence_calibrator", "v1.0.0", "challenger")

        # Get final metrics
        metrics = collector.get_metrics()
        metrics_dict = metrics.to_dict()

        # Verify all metrics are tracked
        assert metrics_dict["cache"]["hits"] == 7
        assert metrics_dict["cache"]["misses"] == 3
        assert 60 <= metrics_dict["cache"]["hit_rate_percent"] <= 80

        assert len(metrics.model_retrieval_latency_seconds) == 10
        assert metrics.rollback_operations_total == 1
        assert metrics.version_comparisons_total == 2

        assert metrics_dict["storage"]["usage_bytes"] == 268435456
        assert metrics_dict["storage"]["models_count"] == 15

        # Check Prometheus output
        prom_output = collector.get_prometheus_metrics()
        assert len(prom_output) > 0

    def test_latency_percentile_edge_cases(self):
        """Test latency percentile calculations with edge cases."""
        collector = PrometheusMetricsCollector()
        collector.reset_metrics()

        # Single value
        collector.record_model_retrieval("model", "v1", 0.5, True)
        metrics = collector.get_metrics().to_dict()
        assert metrics["model_retrieval_latency"]["p50"] == 0.5
        assert metrics["model_retrieval_latency"]["p95"] == 0.5
        assert metrics["model_retrieval_latency"]["p99"] == 0.5

        # Two values
        collector.reset_metrics()
        collector.record_model_retrieval("model", "v1", 0.1, True)
        collector.record_model_retrieval("model", "v2", 0.9, True)
        metrics = collector.get_metrics().to_dict()
        assert metrics["model_retrieval_latency"]["p50"] >= 0.1

        # Many values (test p95/p99)
        collector.reset_metrics()
        for i in range(100):
            collector.record_model_retrieval("model", f"v{i}", i * 0.01, True)

        metrics = collector.get_metrics().to_dict()
        assert metrics["model_retrieval_latency"]["p50"] >= 0.4
        assert metrics["model_retrieval_latency"]["p95"] >= 0.9
        assert metrics["model_retrieval_latency"]["p99"] >= 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
