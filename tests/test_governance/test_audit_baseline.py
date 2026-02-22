"""
Tests for Audit Snapshot and Retrieval Baseline.

ST-GOV-MINI-001: Audit Snapshot + Retrieval Baseline

Test coverage:
- Snapshot capture
- Baseline metrics collection
- Redis storage integration
"""

import pytest
from datetime import datetime, timezone
import json

from src.governance.audit.baseline import (
    AuditSnapshot,
    RetrievalBaseline,
    evaluate_metric,
    METRIC_THRESHOLDS,
)


class TestAuditSnapshot:
    """Test cases for AuditSnapshot class."""

    def test_snapshot_creation_default_values(self) -> None:
        """Test creating a snapshot with default values."""
        snapshot = AuditSnapshot()

        assert snapshot.component == "system"
        assert snapshot.metrics == {}
        assert snapshot.metadata == {}
        assert snapshot.snapshot_id is not None
        assert snapshot.timestamp is not None

    def test_snapshot_creation_custom_values(self) -> None:
        """Test creating a snapshot with custom values."""
        custom_time = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
        snapshot = AuditSnapshot(
            timestamp=custom_time,
            component="memory",
            metrics={"heap_size": 1024},
            metadata={"source": "test"},
        )

        assert snapshot.component == "memory"
        assert snapshot.metrics == {"heap_size": 1024}
        assert snapshot.metadata == {"source": "test"}
        assert snapshot.timestamp == custom_time

    def test_snapshot_capture(self) -> None:
        """Test capturing a snapshot with additional metrics."""
        snapshot = AuditSnapshot()
        result = snapshot.capture(
            component="retrieval",
            latency_ms=42.5,
            hit_count=100,
        )

        # Should return self for chaining
        assert result is snapshot
        assert snapshot.component == "retrieval"
        assert snapshot.metrics["latency_ms"] == 42.5
        assert snapshot.metrics["hit_count"] == 100
        assert "retrieval-" in snapshot.snapshot_id

    def test_snapshot_to_dict(self) -> None:
        """Test converting snapshot to dictionary."""
        snapshot = AuditSnapshot(
            component="test",
            metrics={"value": 123},
            metadata={"key": "val"},
        )
        data = snapshot.to_dict()

        assert "snapshot_id" in data
        assert "timestamp" in data
        assert data["component"] == "test"
        assert data["metrics"] == {"value": 123}
        assert data["metadata"] == {"key": "val"}

    def test_snapshot_to_json(self) -> None:
        """Test converting snapshot to JSON."""
        snapshot = AuditSnapshot(component="test", metrics={"count": 1})
        json_str = snapshot.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["component"] == "test"
        assert parsed["metrics"]["count"] == 1

    def test_snapshot_from_dict(self) -> None:
        """Test creating snapshot from dictionary."""
        data = {
            "snapshot_id": "test-123",
            "timestamp": "2026-02-22T12:00:00+00:00",
            "component": "memory",
            "metrics": {"size": 100},
            "metadata": {},
        }
        snapshot = AuditSnapshot.from_dict(data)

        assert snapshot.snapshot_id == "test-123"
        assert snapshot.component == "memory"
        assert snapshot.metrics == {"size": 100}


class TestRetrievalBaseline:
    """Test cases for RetrievalBaseline class."""

    def test_baseline_creation_default_values(self) -> None:
        """Test creating a baseline with default values."""
        baseline = RetrievalBaseline()

        assert baseline.baseline_id == "default"
        assert baseline.samples == 0
        assert "retrieval_latency_ms" in baseline.metrics
        assert "memory_hit_rate" in baseline.metrics
        assert "deduplication_ratio" in baseline.metrics

    def test_baseline_creation_custom_values(self) -> None:
        """Test creating a baseline with custom values."""
        baseline = RetrievalBaseline(
            baseline_id="custom-001",
            metrics={
                "retrieval_latency_ms": 25.5,
                "memory_hit_rate": 85.0,
                "deduplication_ratio": 0.75,
            },
            samples=100,
        )

        assert baseline.baseline_id == "custom-001"
        assert baseline.metrics["retrieval_latency_ms"] == 25.5
        assert baseline.samples == 100

    def test_get_metrics(self) -> None:
        """Test getting baseline metrics."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 30.0,
                "memory_hit_rate": 90.0,
                "deduplication_ratio": 0.8,
            }
        )
        metrics = baseline.get_metrics()

        assert metrics["retrieval_latency_ms"] == 30.0
        assert metrics["memory_hit_rate"] == 90.0
        assert metrics["deduplication_ratio"] == 0.8

    def test_update_metrics(self) -> None:
        """Test updating baseline metrics."""
        baseline = RetrievalBaseline()

        baseline.update_metrics(
            retrieval_latency_ms=50.0,
            memory_hit_rate=75.0,
            deduplication_ratio=0.6,
        )

        assert baseline.metrics["retrieval_latency_ms"] == 50.0
        assert baseline.metrics["memory_hit_rate"] == 75.0
        assert baseline.metrics["deduplication_ratio"] == 0.6
        assert baseline.samples == 1

    def test_update_metrics_partial(self) -> None:
        """Test partial metric updates."""
        baseline = RetrievalBaseline(
            metrics={
                "retrieval_latency_ms": 100.0,
                "memory_hit_rate": 50.0,
                "deduplication_ratio": 0.5,
            }
        )

        baseline.update_metrics(retrieval_latency_ms=50.0)

        assert baseline.metrics["retrieval_latency_ms"] == 50.0
        assert baseline.metrics["memory_hit_rate"] == 50.0  # Unchanged

    def test_update_metrics_bounds(self) -> None:
        """Test that metrics are bounded to valid ranges."""
        baseline = RetrievalBaseline()

        # memory_hit_rate should be clamped to 0-100
        baseline.update_metrics(memory_hit_rate=150.0)
        assert baseline.metrics["memory_hit_rate"] == 100.0

        baseline.update_metrics(memory_hit_rate=-10.0)
        assert baseline.metrics["memory_hit_rate"] == 0.0

        # deduplication_ratio should be clamped to 0-1
        baseline.update_metrics(deduplication_ratio=2.0)
        assert baseline.metrics["deduplication_ratio"] == 1.0

    def test_export_to_redis_keys(self) -> None:
        """Test Redis export returns correct key structure."""
        baseline = RetrievalBaseline()
        result = baseline.export_to_redis()

        assert "baseline_key" in result
        assert "snapshot_key" in result
        assert result["baseline_key"] == "governance:audit:baseline:current"
        assert "governance:audit:snapshot:" in result["snapshot_key"]

    def test_export_to_redis_data(self) -> None:
        """Test Redis export contains valid JSON data."""
        baseline = RetrievalBaseline(
            baseline_id="test-001",
            metrics={
                "retrieval_latency_ms": 25.0,
                "memory_hit_rate": 80.0,
                "deduplication_ratio": 0.7,
            },
        )
        result = baseline.export_to_redis()

        # baseline_data should be valid JSON
        baseline_data = json.loads(result["baseline_data"])
        assert baseline_data["baseline_id"] == "test-001"

        # snapshot_data should be valid JSON
        snapshot_data = json.loads(result["snapshot_data"])
        assert "timestamp" in snapshot_data
        assert "metrics" in snapshot_data

    def test_create_snapshot(self) -> None:
        """Test creating an AuditSnapshot from baseline."""
        baseline = RetrievalBaseline(
            baseline_id="test-snapshot",
            metrics={
                "retrieval_latency_ms": 15.0,
                "memory_hit_rate": 95.0,
                "deduplication_ratio": 0.9,
            },
            samples=50,
        )
        snapshot = baseline.create_snapshot()

        assert isinstance(snapshot, AuditSnapshot)
        assert snapshot.component == "retrieval_baseline"
        assert snapshot.metrics["retrieval_latency_ms"] == 15.0
        assert snapshot.metadata["baseline_id"] == "test-snapshot"
        assert snapshot.metadata["samples"] == 50

    def test_baseline_to_dict(self) -> None:
        """Test converting baseline to dictionary."""
        baseline = RetrievalBaseline(baseline_id="dict-test", samples=25)
        data = baseline.to_dict()

        assert data["baseline_id"] == "dict-test"
        assert data["samples"] == 25
        assert "created_at" in data
        assert "metrics" in data

    def test_baseline_from_dict(self) -> None:
        """Test creating baseline from dictionary."""
        data = {
            "baseline_id": "restore-test",
            "created_at": "2026-02-22T10:00:00+00:00",
            "metrics": {
                "retrieval_latency_ms": 20.0,
                "memory_hit_rate": 85.0,
                "deduplication_ratio": 0.75,
            },
            "samples": 100,
        }
        baseline = RetrievalBaseline.from_dict(data)

        assert baseline.baseline_id == "restore-test"
        assert baseline.samples == 100
        assert isinstance(baseline.created_at, datetime)


class TestEvaluateMetric:
    """Test cases for metric evaluation function."""

    def test_evaluate_latency_excellent(self) -> None:
        """Test latency evaluation for excellent performance."""
        assert evaluate_metric("retrieval_latency_ms", 5.0) == "excellent"
        assert evaluate_metric("retrieval_latency_ms", 10.0) == "excellent"

    def test_evaluate_latency_good(self) -> None:
        """Test latency evaluation for good performance."""
        assert evaluate_metric("retrieval_latency_ms", 25.0) == "good"
        assert evaluate_metric("retrieval_latency_ms", 50.0) == "good"

    def test_evaluate_latency_acceptable(self) -> None:
        """Test latency evaluation for acceptable performance."""
        assert evaluate_metric("retrieval_latency_ms", 75.0) == "acceptable"
        assert evaluate_metric("retrieval_latency_ms", 100.0) == "acceptable"

    def test_evaluate_latency_needs_improvement(self) -> None:
        """Test latency evaluation for poor performance."""
        assert evaluate_metric("retrieval_latency_ms", 150.0) == "needs_improvement"

    def test_evaluate_memory_hit_rate(self) -> None:
        """Test memory hit rate evaluation."""
        assert evaluate_metric("memory_hit_rate", 98.0) == "excellent"
        assert evaluate_metric("memory_hit_rate", 85.0) == "good"
        assert evaluate_metric("memory_hit_rate", 65.0) == "acceptable"
        assert evaluate_metric("memory_hit_rate", 40.0) == "needs_improvement"

    def test_evaluate_deduplication_ratio(self) -> None:
        """Test deduplication ratio evaluation."""
        assert evaluate_metric("deduplication_ratio", 0.95) == "excellent"
        assert evaluate_metric("deduplication_ratio", 0.75) == "good"
        assert evaluate_metric("deduplication_ratio", 0.55) == "acceptable"
        assert evaluate_metric("deduplication_ratio", 0.3) == "needs_improvement"

    def test_evaluate_unknown_metric(self) -> None:
        """Test evaluation for unknown metric."""
        assert evaluate_metric("unknown_metric", 100.0) == "unknown"


class TestMetricThresholds:
    """Test cases for metric thresholds constants."""

    def test_thresholds_exist(self) -> None:
        """Test that all expected thresholds are defined."""
        assert "retrieval_latency_ms" in METRIC_THRESHOLDS
        assert "memory_hit_rate" in METRIC_THRESHOLDS
        assert "deduplication_ratio" in METRIC_THRESHOLDS

    def test_threshold_levels_exist(self) -> None:
        """Test that all threshold levels are defined."""
        for metric_name, thresholds in METRIC_THRESHOLDS.items():
            assert "excellent" in thresholds
            assert "good" in thresholds
            assert "acceptable" in thresholds


class TestRedisIntegration:
    """Test cases for Redis storage integration (skeleton)."""

    @pytest.mark.skip(reason="Requires Redis connection - skeleton test")
    def test_store_snapshot_to_redis(self) -> None:
        """Test storing snapshot to Redis."""
        # TODO: Implement with actual Redis client
        pass

    @pytest.mark.skip(reason="Requires Redis connection - skeleton test")
    def test_retrieve_baseline_from_redis(self) -> None:
        """Test retrieving baseline from Redis."""
        # TODO: Implement with actual Redis client
        pass

    @pytest.mark.skip(reason="Requires Redis connection - skeleton test")
    def test_redis_key_expiration(self) -> None:
        """Test that Redis keys have proper TTL."""
        # TODO: Implement with actual Redis client
        pass


# Integration test markers
pytestmark = [
    pytest.mark.unit,
]
