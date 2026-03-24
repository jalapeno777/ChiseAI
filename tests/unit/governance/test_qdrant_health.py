"""Unit tests for Qdrant Health Monitor.

Tests the QdrantHealthMonitor class including:
- Connectivity checking
- Write latency measurement
- Success rate calculation
- Error type tracking
- Health status determination
- Alert threshold triggering
- Redis fallback queue
- Automatic retry

Usage:
    pytest tests/unit/governance/test_qdrant_health.py -v
    pytest tests/unit/governance/test_qdrant_health.py -v --cov=src.governance.memory.qdrant_health
"""

from __future__ import annotations

import json
from collections import deque
from unittest.mock import MagicMock, patch

import pytest
from src.governance.memory.qdrant_health import (
    DEFAULT_QDRANT_HOST,
    DEFAULT_QDRANT_PORT,
    DEFAULT_VECTOR_SIZE,
    FALLBACK_QUEUE_KEY,
    FALLBACK_QUEUE_MAX_SIZE,
    ErrorType,
    FallbackQueueEntry,
    HealthMetrics,
    HealthStatus,
    QdrantHealthMonitor,
)


class TestHealthMetrics:
    """Tests for HealthMetrics dataclass."""

    def test_init(self):
        """Test HealthMetrics initialization."""
        metrics = HealthMetrics()

        assert metrics.connectivity_checks_total == 0
        assert metrics.connectivity_checks_success == 0
        assert metrics.connectivity_checks_failed == 0
        assert metrics.last_connectivity_check_at is None
        assert isinstance(metrics.write_latencies_ms, deque)
        assert metrics.avg_write_latency_ms == 0.0
        assert metrics.p95_write_latency_ms == 0.0
        assert metrics.max_write_latency_ms == 0.0
        assert metrics.write_attempts_total == 0
        assert metrics.write_attempts_success == 0
        assert metrics.write_attempts_failed == 0
        assert metrics.success_rate == 1.0
        assert metrics.error_counts == {}
        assert metrics.consecutive_failures == 0
        assert metrics.alert_triggered is False
        assert metrics.recorded_at is not None

    def test_record_write_latency(self):
        """Test recording write latencies."""
        metrics = HealthMetrics()

        # Record some latencies
        metrics.record_write_latency(100.0)
        metrics.record_write_latency(200.0)
        metrics.record_write_latency(300.0)

        assert len(metrics.write_latencies_ms) == 3
        assert metrics.avg_write_latency_ms == 200.0
        assert metrics.max_write_latency_ms == 300.0

    def test_record_write_latency_p95(self):
        """Test p95 latency calculation."""
        metrics = HealthMetrics()

        # Record 100 latencies
        for i in range(100):
            metrics.record_write_latency(float(i))

        # p95 should be around 94 (95th percentile of 0-99)
        assert 93 <= metrics.p95_write_latency_ms <= 95

    def test_record_write_result_success(self):
        """Test recording successful write."""
        metrics = HealthMetrics()

        metrics.record_write_result(success=True)

        assert metrics.write_attempts_total == 1
        assert metrics.write_attempts_success == 1
        assert metrics.write_attempts_failed == 0
        assert metrics.success_rate == 1.0
        assert metrics.consecutive_failures == 0

    def test_record_write_result_failure(self):
        """Test recording failed write."""
        metrics = HealthMetrics()

        metrics.record_write_result(
            success=False,
            error_type=ErrorType.CONNECTION_ERROR,
            error_message="Connection refused",
        )

        assert metrics.write_attempts_total == 1
        assert metrics.write_attempts_success == 0
        assert metrics.write_attempts_failed == 1
        assert metrics.success_rate == 0.0
        assert metrics.consecutive_failures == 1
        assert metrics.error_counts["connection_error"] == 1
        assert metrics.last_error_type == "connection_error"
        assert metrics.last_error_message == "Connection refused"

    def test_record_multiple_failures(self):
        """Test recording multiple consecutive failures."""
        metrics = HealthMetrics()

        for i in range(3):
            metrics.record_write_result(
                success=False,
                error_type=ErrorType.WRITE_ERROR,
                error_message=f"Error {i}",
            )

        assert metrics.consecutive_failures == 3
        assert metrics.error_counts["write_error"] == 3
        assert metrics.write_attempts_failed == 3

    def test_record_mixed_results(self):
        """Test recording mixed success and failure."""
        metrics = HealthMetrics()

        # 2 failures
        metrics.record_write_result(success=False, error_type=ErrorType.TIMEOUT_ERROR)
        metrics.record_write_result(success=False, error_type=ErrorType.TIMEOUT_ERROR)

        # 1 success (resets consecutive failures)
        metrics.record_write_result(success=True)

        # 1 more failure
        metrics.record_write_result(success=False, error_type=ErrorType.READ_ERROR)

        assert metrics.write_attempts_total == 4
        assert metrics.write_attempts_success == 1
        assert metrics.write_attempts_failed == 3
        assert metrics.consecutive_failures == 1
        assert metrics.success_rate == 0.25

    def test_record_connectivity_result(self):
        """Test recording connectivity results."""
        metrics = HealthMetrics()

        metrics.record_connectivity_result(success=True)
        assert metrics.connectivity_checks_total == 1
        assert metrics.connectivity_checks_success == 1
        assert metrics.connectivity_checks_failed == 0
        assert metrics.last_connectivity_check_at is not None

        metrics.record_connectivity_result(success=False)
        assert metrics.connectivity_checks_total == 2
        assert metrics.connectivity_checks_success == 1
        assert metrics.connectivity_checks_failed == 1

    def test_trigger_alert(self):
        """Test alert triggering."""
        metrics = HealthMetrics()

        metrics.trigger_alert("Test alert message")

        assert metrics.alert_triggered is True
        assert metrics.alert_triggered_at is not None
        assert metrics.alert_message == "Test alert message"

    def test_clear_alert(self):
        """Test clearing alert."""
        metrics = HealthMetrics()

        metrics.trigger_alert("Test alert")
        assert metrics.alert_triggered is True

        metrics.clear_alert()
        assert metrics.alert_triggered is False

    def test_to_dict(self):
        """Test metrics serialization."""
        metrics = HealthMetrics()
        metrics.record_write_latency(100.0)
        metrics.record_write_result(success=True)
        metrics.record_connectivity_result(success=True)

        data = metrics.to_dict()

        assert "connectivity" in data
        assert "latency" in data
        assert "success_rate" in data
        assert "errors" in data
        assert "alert" in data
        assert "recorded_at" in data

        assert data["connectivity"]["checks_total"] == 1
        assert data["latency"]["samples"] == 1
        assert data["success_rate"]["rate"] == 1.0


class TestFallbackQueueEntry:
    """Tests for FallbackQueueEntry dataclass."""

    def test_init(self):
        """Test FallbackQueueEntry initialization."""
        entry = FallbackQueueEntry(
            point_id="test-123",
            vector=[0.1, 0.2, 0.3],
            payload={"key": "value"},
            collection="test_collection",
        )

        assert entry.point_id == "test-123"
        assert entry.vector == [0.1, 0.2, 0.3]
        assert entry.payload == {"key": "value"}
        assert entry.collection == "test_collection"
        assert entry.timestamp is not None
        assert entry.retry_count == 0
        assert entry.last_error is None

    def test_to_json(self):
        """Test JSON serialization."""
        entry = FallbackQueueEntry(
            point_id="test-123",
            vector=[0.1, 0.2],
            payload={"key": "value"},
            collection="test_collection",
            retry_count=2,
            last_error="Test error",
        )

        json_str = entry.to_json()
        data = json.loads(json_str)

        assert data["point_id"] == "test-123"
        assert data["vector"] == [0.1, 0.2]
        assert data["payload"] == {"key": "value"}
        assert data["collection"] == "test_collection"
        assert data["retry_count"] == 2
        assert data["last_error"] == "Test error"

    def test_from_json(self):
        """Test JSON deserialization."""
        data = {
            "point_id": "test-123",
            "vector": [0.1, 0.2],
            "payload": {"key": "value"},
            "collection": "test_collection",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "retry_count": 1,
            "last_error": "Previous error",
        }

        entry = FallbackQueueEntry.from_json(json.dumps(data))

        assert entry.point_id == "test-123"
        assert entry.vector == [0.1, 0.2]
        assert entry.payload == {"key": "value"}
        assert entry.collection == "test_collection"
        assert entry.timestamp == "2024-01-01T00:00:00+00:00"
        assert entry.retry_count == 1
        assert entry.last_error == "Previous error"


class TestQdrantHealthMonitorInit:
    """Tests for QdrantHealthMonitor initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        monitor = QdrantHealthMonitor()

        assert monitor.host == DEFAULT_QDRANT_HOST
        assert monitor.port == DEFAULT_QDRANT_PORT
        assert monitor.collection == "ChiseAI"
        assert monitor.vector_size == DEFAULT_VECTOR_SIZE
        assert monitor._redis_client is None
        assert monitor._qdrant_client is None
        assert monitor._monitoring_thread is None

    def test_custom_init(self):
        """Test initialization with custom values."""
        monitor = QdrantHealthMonitor(
            host="custom.host",
            port=9999,
            collection="CustomCollection",
            vector_size=768,
            check_interval_seconds=60,
            alert_threshold_consecutive_failures=5,
        )

        assert monitor.host == "custom.host"
        assert monitor.port == 9999
        assert monitor.collection == "CustomCollection"
        assert monitor.vector_size == 768
        assert monitor.check_interval_seconds == 60
        assert monitor.alert_threshold_consecutive_failures == 5


class TestQdrantHealthMonitorConnectivity:
    """Tests for QdrantHealthMonitor connectivity checking."""

    def test_check_connectivity_success(self):
        """Test successful connectivity check."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        monitor._qdrant_client = mock_client

        result = monitor.check_connectivity()

        assert result is True
        mock_client.get_collections.assert_called_once()

        metrics = monitor._metrics
        assert metrics.connectivity_checks_success == 1
        assert metrics.connectivity_checks_failed == 0

    def test_check_connectivity_failure(self):
        """Test failed connectivity check."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        mock_client.get_collections.side_effect = Exception("Connection refused")
        monitor._qdrant_client = mock_client

        result = monitor.check_connectivity()

        assert result is False

        metrics = monitor._metrics
        assert metrics.connectivity_checks_failed == 1
        assert metrics.consecutive_failures == 1

    def test_check_connectivity_client_reuse(self):
        """Test that client is reused."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        monitor._qdrant_client = mock_client

        # First check uses existing client
        monitor.check_connectivity()
        assert mock_client.get_collections.call_count == 1

        # Second check reuses client
        monitor.check_connectivity()
        assert mock_client.get_collections.call_count == 2


class TestQdrantHealthMonitorLatency:
    """Tests for QdrantHealthMonitor latency measurement."""

    def test_get_write_latency_success(self):
        """Test successful latency measurement."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        monitor._qdrant_client = mock_client

        latency = monitor.get_write_latency()

        assert latency > 0
        assert monitor._metrics.write_attempts_success == 1

    def test_get_write_latency_failure(self):
        """Test failed latency measurement."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        mock_client.upsert.side_effect = Exception("Write failed")
        monitor._qdrant_client = mock_client

        latency = monitor.get_write_latency()

        assert latency > 0  # Still returns elapsed time
        assert monitor._metrics.write_attempts_failed == 1
        assert monitor._metrics.consecutive_failures == 1

    def test_get_write_latency_records_metrics(self):
        """Test that latency is recorded in metrics."""
        monitor = QdrantHealthMonitor()
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        monitor._qdrant_client = mock_client

        latency = monitor.get_write_latency()

        assert len(monitor._metrics.write_latencies_ms) == 1
        assert monitor._metrics.avg_write_latency_ms == latency


class TestQdrantHealthMonitorSuccessRate:
    """Tests for QdrantHealthMonitor success rate calculation."""

    def test_get_success_rate_default(self):
        """Test default success rate."""
        monitor = QdrantHealthMonitor()
        rate = monitor.get_success_rate()

        assert rate == 1.0

    def test_get_success_rate_after_operations(self):
        """Test success rate after operations."""
        monitor = QdrantHealthMonitor()

        # Simulate some operations
        monitor._metrics.record_write_result(success=True)
        monitor._metrics.record_write_result(success=True)
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.WRITE_ERROR
        )

        rate = monitor.get_success_rate()
        assert rate == 2 / 3


class TestQdrantHealthMonitorErrorTypes:
    """Tests for QdrantHealthMonitor error type tracking."""

    def test_get_error_types_empty(self):
        """Test error types with no errors."""
        monitor = QdrantHealthMonitor()
        errors = monitor.get_error_types()

        assert errors == {}

    def test_get_error_types_with_errors(self):
        """Test error types with recorded errors."""
        monitor = QdrantHealthMonitor()

        # Simulate various errors
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.CONNECTION_ERROR
        )
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.CONNECTION_ERROR
        )
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.TIMEOUT_ERROR
        )

        errors = monitor.get_error_types()
        assert errors["connection_error"] == 2
        assert errors["timeout_error"] == 1


class TestQdrantHealthMonitorHealthStatus:
    """Tests for QdrantHealthMonitor health status determination."""

    def test_is_healthy_default(self):
        """Test default health status."""
        monitor = QdrantHealthMonitor()
        assert monitor.is_healthy() is True
        assert monitor.get_health_status() == HealthStatus.HEALTHY

    def test_is_healthy_with_consecutive_failures(self):
        """Test unhealthy with consecutive failures."""
        monitor = QdrantHealthMonitor(alert_threshold_consecutive_failures=3)

        # 3 consecutive failures
        for _ in range(3):
            monitor._metrics.record_write_result(
                success=False, error_type=ErrorType.WRITE_ERROR
            )

        assert monitor.is_healthy() is False
        assert monitor.get_health_status() == HealthStatus.UNHEALTHY

    def test_is_healthy_with_high_latency(self):
        """Test degraded with high latency."""
        monitor = QdrantHealthMonitor(latency_threshold_ms=100)

        # Record high latency
        monitor._metrics.record_write_latency(200.0)

        assert monitor.get_health_status() == HealthStatus.DEGRADED

    def test_is_healthy_with_low_success_rate(self):
        """Test degraded with low success rate."""
        monitor = QdrantHealthMonitor(success_rate_threshold=0.95)

        # Need at least 10 samples for success rate check
        for i in range(10):
            monitor._metrics.record_write_result(
                success=(i < 8),  # 8/10 = 80% success
                error_type=ErrorType.WRITE_ERROR if i >= 8 else None,
            )

        assert monitor.get_health_status() == HealthStatus.DEGRADED

    def test_is_healthy_with_active_alert(self):
        """Test unhealthy with active alert."""
        monitor = QdrantHealthMonitor()
        monitor._metrics.trigger_alert("Test alert")

        assert monitor.is_healthy() is False

    def test_is_healthy_connectivity_failure(self):
        """Test unhealthy when connectivity fails."""
        monitor = QdrantHealthMonitor()
        monitor._metrics.record_connectivity_result(success=False)

        assert monitor.get_health_status() == HealthStatus.UNHEALTHY


class TestQdrantHealthMonitorMetrics:
    """Tests for QdrantHealthMonitor metrics."""

    def test_get_metrics_structure(self):
        """Test metrics dictionary structure."""
        monitor = QdrantHealthMonitor()
        metrics = monitor.get_metrics()

        assert "health_status" in metrics
        assert "connectivity" in metrics
        assert "latency" in metrics
        assert "success_rate" in metrics
        assert "errors" in metrics
        assert "alert" in metrics
        assert "config" in metrics
        assert "fallback_queue" in metrics

    def test_get_metrics_config(self):
        """Test metrics includes configuration."""
        monitor = QdrantHealthMonitor(
            host="test.host",
            port=1234,
            collection="TestCollection",
        )
        metrics = monitor.get_metrics()

        assert metrics["config"]["host"] == "test.host"
        assert metrics["config"]["port"] == 1234
        assert metrics["config"]["collection"] == "TestCollection"


class TestQdrantHealthMonitorAlertThresholds:
    """Tests for QdrantHealthMonitor alert threshold checking."""

    def test_check_alert_thresholds_consecutive_failures(self):
        """Test alert on consecutive failures."""
        monitor = QdrantHealthMonitor(alert_threshold_consecutive_failures=3)

        # 3 consecutive failures
        for _ in range(3):
            monitor._metrics.record_write_result(
                success=False, error_type=ErrorType.WRITE_ERROR
            )

        monitor._check_alert_thresholds()

        assert monitor._metrics.alert_triggered is True
        assert monitor._metrics.alert_message is not None
        assert "consecutive failures" in monitor._metrics.alert_message

    def test_check_alert_thresholds_success_rate(self):
        """Test alert on low success rate."""
        monitor = QdrantHealthMonitor(
            success_rate_threshold=0.95,
            alert_threshold_consecutive_failures=10,  # High threshold to avoid consecutive failures alert
        )

        # 10 samples with 50% success rate - interleaved to avoid consecutive failures
        for i in range(10):
            success = i % 2 == 0  # Alternate success/failure
            monitor._metrics.record_write_result(
                success=success,
                error_type=ErrorType.WRITE_ERROR if not success else None,
            )

        monitor._check_alert_thresholds()

        assert monitor._metrics.alert_triggered is True
        assert monitor._metrics.alert_message is not None
        assert "success rate" in monitor._metrics.alert_message

    def test_check_alert_thresholds_high_latency(self):
        """Test alert on high latency."""
        monitor = QdrantHealthMonitor(latency_threshold_ms=100)

        # Record high latency
        monitor._metrics.record_write_latency(200.0)

        monitor._check_alert_thresholds()

        assert monitor._metrics.alert_triggered is True
        assert monitor._metrics.alert_message is not None
        assert "latency" in monitor._metrics.alert_message

    def test_check_alert_thresholds_clear_alert(self):
        """Test alert clearing when conditions normalize."""
        monitor = QdrantHealthMonitor()

        # Trigger alert
        monitor._metrics.trigger_alert("Test alert")
        assert monitor._metrics.alert_triggered is True

        # Clear conditions (all successful operations)
        for _ in range(5):
            monitor._metrics.record_write_result(success=True)

        monitor._check_alert_thresholds()

        assert monitor._metrics.alert_triggered is False


class TestQdrantHealthMonitorFallbackQueue:
    """Tests for QdrantHealthMonitor Redis fallback queue."""

    def test_add_to_fallback_queue_success(self):
        """Test successful add to fallback queue."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 0

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis

        result = monitor.add_to_fallback_queue(
            point_id="test-123",
            vector=[0.1, 0.2],
            payload={"key": "value"},
        )

        assert result is True
        mock_redis.lpush.assert_called_once()

    def test_add_to_fallback_queue_full(self):
        """Test add to fallback queue when full."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = FALLBACK_QUEUE_MAX_SIZE

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis

        result = monitor.add_to_fallback_queue(
            point_id="test-123",
            vector=[0.1],
            payload={},
        )

        assert result is False

    def test_add_to_fallback_queue_redis_unavailable(self):
        """Test add to fallback queue when Redis is unavailable."""
        monitor = QdrantHealthMonitor()
        # Simulate Redis connection failure by setting _redis to None
        # and patching _get_redis to return None
        monitor._redis = None

        with patch.object(monitor, "_get_redis", return_value=None):
            result = monitor.add_to_fallback_queue(
                point_id="test-123",
                vector=[0.1],
                payload={},
            )

        assert result is False

    def test_get_fallback_queue_entries(self):
        """Test getting fallback queue entries."""
        mock_redis = MagicMock()

        entry = FallbackQueueEntry(
            point_id="test-123",
            vector=[0.1],
            payload={"key": "value"},
            collection=None,
        )
        mock_redis.lrange.return_value = [entry.to_json()]

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis

        entries = monitor.get_fallback_queue_entries()

        assert len(entries) == 1
        assert entries[0].point_id == "test-123"

    def test_clear_fallback_queue(self):
        """Test clearing fallback queue."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 5

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis

        count = monitor.clear_fallback_queue()

        assert count == 5
        mock_redis.delete.assert_called_once_with(FALLBACK_QUEUE_KEY)

    def test_get_fallback_queue_info(self):
        """Test getting fallback queue info."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 100

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis

        info = monitor._get_fallback_queue_info()

        assert info["available"] is True
        assert info["queue_length"] == 100
        assert info["max_size"] == FALLBACK_QUEUE_MAX_SIZE
        assert info["utilization"] == 100 / FALLBACK_QUEUE_MAX_SIZE


class TestQdrantHealthMonitorReplay:
    """Tests for QdrantHealthMonitor fallback queue replay."""

    def test_replay_fallback_queue_success(self):
        """Test successful replay of fallback queue."""
        mock_redis = MagicMock()
        # First call returns 1 for queue_length check, then 0 after processing
        mock_redis.llen.side_effect = [1, 0]

        entry = FallbackQueueEntry(
            point_id="test-123",
            vector=[0.1] * 384,
            payload={"key": "value"},
            collection=None,
        )
        # First rpop returns entry, subsequent calls return None
        mock_redis.rpop.side_effect = [entry.to_json(), None]

        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis
        monitor._qdrant_client = mock_client
        # Make monitor healthy for replay
        monitor._metrics.record_write_result(success=True)

        count = monitor._replay_fallback_queue()

        assert count == 1
        mock_client.upsert.assert_called_once()

    def test_replay_fallback_queue_unhealthy(self):
        """Test replay skipped when unhealthy."""
        mock_redis = MagicMock()

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis
        # Make monitor unhealthy
        for _ in range(3):
            monitor._metrics.record_write_result(
                success=False, error_type=ErrorType.WRITE_ERROR
            )

        count = monitor._replay_fallback_queue()

        assert count == 0

    def test_replay_fallback_queue_max_retries(self):
        """Test entries with max retries are dropped."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 1

        # Entry with max retries exceeded
        entry = FallbackQueueEntry(
            point_id="test-123",
            vector=[0.1] * 384,
            payload={"key": "value"},
            collection=None,
            retry_count=3,  # Max retries
        )
        mock_redis.rpop.return_value = entry.to_json()

        mock_client = MagicMock()
        mock_client.upsert.side_effect = Exception("Write failed")

        monitor = QdrantHealthMonitor()
        monitor._redis = mock_redis
        monitor._qdrant_client = mock_client
        # Make monitor healthy for replay
        monitor._metrics.record_write_result(success=True)

        count = monitor._replay_fallback_queue()

        assert count == 0  # Entry dropped, not re-queued


class TestQdrantHealthMonitorBackgroundMonitoring:
    """Tests for QdrantHealthMonitor background monitoring."""

    def test_start_stop_monitoring(self):
        """Test starting and stopping background monitoring."""
        monitor = QdrantHealthMonitor(check_interval_seconds=1)

        # Mock the client and redis to avoid network calls
        monitor._qdrant_client = MagicMock()
        monitor._redis = MagicMock()

        assert monitor._monitoring_thread is None

        monitor.start_monitoring()
        assert monitor._monitoring_thread is not None
        assert monitor._monitoring_thread.is_alive()

        monitor.stop_monitoring()
        assert not monitor._monitoring_thread.is_alive()

    def test_start_monitoring_already_running(self):
        """Test starting monitoring when already running."""
        monitor = QdrantHealthMonitor()
        monitor._monitoring_thread = MagicMock()
        monitor._monitoring_thread.is_alive.return_value = True

        monitor.start_monitoring()  # Should not raise or create new thread

    def test_stop_monitoring_not_running(self):
        """Test stopping monitoring when not running."""
        monitor = QdrantHealthMonitor()
        monitor.stop_monitoring()  # Should not raise

    def test_context_manager(self):
        """Test context manager."""
        monitor = QdrantHealthMonitor(check_interval_seconds=1)
        monitor._qdrant_client = MagicMock()
        monitor._redis = MagicMock()

        with monitor:
            assert monitor._monitoring_thread is not None
            assert monitor._monitoring_thread.is_alive()

        # After exit, should be stopped
        assert not monitor._monitoring_thread.is_alive()


class TestQdrantHealthMonitorIntegration:
    """Integration-style tests for QdrantHealthMonitor."""

    def test_full_health_check_workflow(self):
        """Test complete health check workflow."""
        monitor = QdrantHealthMonitor()

        # Simulate some operations
        monitor._metrics.record_write_result(success=True)
        monitor._metrics.record_write_result(success=True)
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.TIMEOUT_ERROR
        )
        monitor._metrics.record_write_latency(50.0)
        monitor._metrics.record_write_latency(100.0)

        # Check health status
        status = monitor.get_health_status()
        assert status == HealthStatus.HEALTHY  # Still healthy with one failure

        # Check metrics
        metrics = monitor.get_metrics()
        assert metrics["success_rate"]["attempts_total"] == 3
        assert metrics["latency"]["samples"] == 2

    def test_degraded_to_unhealthy_transition(self):
        """Test transition from degraded to unhealthy."""
        monitor = QdrantHealthMonitor(
            alert_threshold_consecutive_failures=3,
            latency_threshold_ms=100,
        )

        # Start healthy
        assert monitor.get_health_status() == HealthStatus.HEALTHY

        # Degrade with high latency
        monitor._metrics.record_write_latency(200.0)
        assert monitor.get_health_status() == HealthStatus.DEGRADED

        # Become unhealthy with consecutive failures
        for _ in range(3):
            monitor._metrics.record_write_result(
                success=False, error_type=ErrorType.WRITE_ERROR
            )

        assert monitor.get_health_status() == HealthStatus.UNHEALTHY

    def test_error_aggregation(self):
        """Test error type aggregation across operations."""
        monitor = QdrantHealthMonitor()

        error_types = [
            ErrorType.CONNECTION_ERROR,
            ErrorType.CONNECTION_ERROR,
            ErrorType.TIMEOUT_ERROR,
            ErrorType.WRITE_ERROR,
            ErrorType.TIMEOUT_ERROR,
            ErrorType.TIMEOUT_ERROR,
        ]

        for error_type in error_types:
            monitor._metrics.record_write_result(success=False, error_type=error_type)

        errors = monitor.get_error_types()
        assert errors["connection_error"] == 2
        assert errors["timeout_error"] == 3
        assert errors["write_error"] == 1

    def test_metrics_serialization(self):
        """Test that metrics can be fully serialized."""
        monitor = QdrantHealthMonitor()

        # Add some data
        monitor._metrics.record_write_result(success=True)
        monitor._metrics.record_write_result(
            success=False, error_type=ErrorType.WRITE_ERROR
        )
        monitor._metrics.record_write_latency(100.0)
        monitor._metrics.record_connectivity_result(success=True)

        metrics = monitor.get_metrics()

        # Should be JSON serializable
        json_str = json.dumps(metrics, default=str)
        assert json_str is not None
        assert len(json_str) > 0

        # Should be deserializable
        restored = json.loads(json_str)
        assert restored["health_status"] == metrics["health_status"]


class TestQdrantHealthMonitorEdgeCases:
    """Edge case tests for QdrantHealthMonitor."""

    def test_empty_latency_list_stats(self):
        """Test latency stats with empty list."""
        metrics = HealthMetrics()

        # No latencies recorded
        assert metrics.avg_write_latency_ms == 0.0
        assert metrics.p95_write_latency_ms == 0.0
        assert metrics.max_write_latency_ms == 0.0

    def test_single_latency_stat(self):
        """Test latency stats with single value."""
        metrics = HealthMetrics()
        metrics.record_write_latency(100.0)

        assert metrics.avg_write_latency_ms == 100.0
        assert metrics.p95_write_latency_ms == 100.0
        assert metrics.max_write_latency_ms == 100.0

    def test_latency_deque_maxlen(self):
        """Test that latency deque respects maxlen."""
        metrics = HealthMetrics()

        # Add more than maxlen entries
        for i in range(1500):
            metrics.record_write_latency(float(i))

        assert len(metrics.write_latencies_ms) == 1000  # maxlen

    def test_zero_division_in_success_rate(self):
        """Test success rate with no operations."""
        monitor = QdrantHealthMonitor()

        # No operations recorded
        rate = monitor.get_success_rate()
        assert rate == 1.0  # Default to 1.0

    def test_consecutive_failures_reset_on_success(self):
        """Test that consecutive failures reset on success."""
        monitor = QdrantHealthMonitor()

        # Record failures
        for _ in range(2):
            monitor._metrics.record_write_result(
                success=False, error_type=ErrorType.WRITE_ERROR
            )
        assert monitor._metrics.consecutive_failures == 2

        # Record success
        monitor._metrics.record_write_result(success=True)
        assert monitor._metrics.consecutive_failures == 0

    def test_health_status_unknown_with_no_data(self):
        """Test health status when no data available."""
        monitor = QdrantHealthMonitor()

        # No connectivity data
        status = monitor._determine_health_status()
        assert status == HealthStatus.HEALTHY  # Default assumption

    def test_import_error_handling(self):
        """Test handling of import errors."""
        monitor = QdrantHealthMonitor()

        # Mock the import to fail
        with patch.dict("sys.modules", {"qdrant_client": None}):
            with pytest.raises(ImportError):
                monitor._get_qdrant_client()

    def test_alert_message_truncation(self):
        """Test that alert messages are handled correctly."""
        monitor = QdrantHealthMonitor()

        # Trigger alert with long message
        long_message = "A" * 1000
        monitor._metrics.trigger_alert(long_message)

        assert monitor._metrics.alert_triggered is True
        assert monitor._metrics.alert_message is not None
        assert len(monitor._metrics.alert_message) == 1000

    def test_collection_name_override(self):
        """Test fallback queue with collection override."""
        entry = FallbackQueueEntry(
            point_id="test",
            vector=[0.1],
            payload={},
            collection="custom_collection",
        )

        assert entry.collection == "custom_collection"

        # Test serialization preserves collection
        json_str = entry.to_json()
        restored = FallbackQueueEntry.from_json(json_str)
        assert restored.collection == "custom_collection"
