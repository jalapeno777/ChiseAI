"""Tests for telemetry export layer.

ST-CONTROL-001: Telemetry Pipeline
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from autonomous_control_plane.config.pipeline_settings import (
    DeadLetterQueueConfig,
    ExportDestinationConfig,
    ExportDestinationType,
)
from autonomous_control_plane.pipeline.export import (
    DeadLetterQueue,
    ExportResult,
    ExportStatus,
    FailedExport,
    LocalStorageFallback,
    TelemetryExportLayer,
)
from autonomous_control_plane.pipeline.processing import ProcessedMetric
from autonomous_control_plane.config.pipeline_settings import AggregationWindow


class TestDeadLetterQueue:
    """Test dead letter queue."""

    def test_add_failed_export(self):
        """Test adding failed export to queue."""
        config = DeadLetterQueueConfig(max_size=100)
        dlq = DeadLetterQueue(config)

        failed = FailedExport(
            destination="influxdb",
            metrics=[],
            failure_reason="Connection error",
            failure_timestamp=time.time(),
        )

        result = dlq.add(failed)

        assert result is True
        assert len(dlq._queue) == 1

    def test_queue_max_size(self):
        """Test queue respects max size."""
        config = DeadLetterQueueConfig(max_size=3)
        dlq = DeadLetterQueue(config)

        for i in range(5):
            failed = FailedExport(
                destination="influxdb",
                metrics=[],
                failure_reason=f"Error {i}",
                failure_timestamp=time.time(),
            )
            dlq.add(failed)

        # Should only have 3 items (max_size)
        assert len(dlq._queue) == 3
        assert dlq._dropped_count == 2

    def test_get_for_retry(self):
        """Test getting exports for retry."""
        config = DeadLetterQueueConfig(max_size=100, retention_hours=24)
        dlq = DeadLetterQueue(config)

        failed = FailedExport(
            destination="influxdb",
            metrics=[],
            failure_reason="Connection error",
            failure_timestamp=time.time(),
        )
        dlq.add(failed)

        eligible = dlq.get_for_retry(max_count=10)

        assert len(eligible) == 1

    def test_get_for_retry_expired(self):
        """Test that expired exports are not returned."""
        config = DeadLetterQueueConfig(max_size=100, retention_hours=1)
        dlq = DeadLetterQueue(config)

        failed = FailedExport(
            destination="influxdb",
            metrics=[],
            failure_reason="Connection error",
            failure_timestamp=time.time() - 7200,  # 2 hours ago
        )
        dlq.add(failed)

        eligible = dlq.get_for_retry(max_count=10)

        assert len(eligible) == 0

    def test_remove(self):
        """Test removing export from queue."""
        config = DeadLetterQueueConfig(max_size=100)
        dlq = DeadLetterQueue(config)

        failed = FailedExport(
            destination="influxdb",
            metrics=[],
            failure_reason="Connection error",
            failure_timestamp=time.time(),
        )
        dlq.add(failed)

        result = dlq.remove(failed.event_id)

        assert result is True
        assert len(dlq._queue) == 0

    def test_get_stats(self):
        """Test getting queue statistics."""
        config = DeadLetterQueueConfig(max_size=100, alert_threshold=10)
        dlq = DeadLetterQueue(config)

        for i in range(5):
            failed = FailedExport(
                destination="influxdb",
                metrics=[],
                failure_reason=f"Error {i}",
                failure_timestamp=time.time(),
            )
            dlq.add(failed)

        stats = dlq.get_stats()

        assert stats["size"] == 5
        assert stats["max_size"] == 100
        assert stats["is_above_threshold"] is False


class TestLocalStorageFallback:
    """Test local storage fallback."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving metrics."""
        fallback = LocalStorageFallback(base_path="/tmp/test_fallback")

        metrics = [
            ProcessedMetric(
                name="test",
                timestamp=time.time(),
                window=AggregationWindow.ONE_MINUTE,
                fields={"value": 42.0},
            )
        ]

        result = fallback.store("influxdb", metrics)

        assert result is True

        # Retrieve stored metrics
        stored = fallback.retrieve("influxdb")
        assert len(stored) >= 1

        # Cleanup
        fallback.clear("influxdb")

    def test_clear(self):
        """Test clearing stored metrics."""
        fallback = LocalStorageFallback(base_path="/tmp/test_fallback2")

        metrics = [
            ProcessedMetric(
                name="test",
                timestamp=time.time(),
                window=AggregationWindow.ONE_MINUTE,
                fields={"value": 42.0},
            )
        ]

        fallback.store("influxdb", metrics)
        fallback.clear("influxdb")

        stored = fallback.retrieve("influxdb")
        assert len(stored) == 0


class TestFailedExport:
    """Test failed export dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        failed = FailedExport(
            destination="influxdb",
            metrics=[
                ProcessedMetric(
                    name="test",
                    timestamp=time.time(),
                    window=AggregationWindow.ONE_MINUTE,
                    fields={"value": 42.0},
                )
            ],
            failure_reason="Connection error",
            failure_timestamp=time.time(),
        )

        data = failed.to_dict()

        assert data["destination"] == "influxdb"
        assert data["failure_reason"] == "Connection error"
        assert "event_id" in data

    def test_from_dict(self):
        """Test creation from dictionary."""
        original = FailedExport(
            destination="influxdb",
            metrics=[],
            failure_reason="Connection error",
            failure_timestamp=time.time(),
        )

        data = original.to_dict()
        restored = FailedExport.from_dict(data)

        assert restored.destination == original.destination
        assert restored.failure_reason == original.failure_reason


class TestTelemetryExportLayer:
    """Test telemetry export layer."""

    def test_export_metrics_empty(self):
        """Test exporting empty metrics list."""
        layer = TelemetryExportLayer()

        results = layer.export_metrics([])

        assert len(results) == 0

    def test_get_metrics(self):
        """Test getting export metrics."""
        layer = TelemetryExportLayer()

        metrics = layer.get_metrics()

        assert "success" in metrics
        assert "failed" in metrics
        assert "retried" in metrics

    def test_get_dlq_stats(self):
        """Test getting DLQ statistics."""
        layer = TelemetryExportLayer()

        stats = layer.get_dlq_stats()

        assert "size" in stats
        assert "max_size" in stats


class TestExportResult:
    """Test export result."""

    def test_success_result(self):
        """Test successful export result."""
        result = ExportResult(
            status=ExportStatus.SUCCESS,
            destination="influxdb",
            metrics_count=10,
            message="Exported successfully",
        )

        assert result.status == ExportStatus.SUCCESS
        assert result.destination == "influxdb"
        assert result.metrics_count == 10

    def test_failed_result(self):
        """Test failed export result."""
        result = ExportResult(
            status=ExportStatus.FAILED_RETRYABLE,
            destination="influxdb",
            metrics_count=10,
            message="Connection timeout",
            retry_after_seconds=5.0,
        )

        assert result.status == ExportStatus.FAILED_RETRYABLE
        assert result.retry_after_seconds == 5.0


class TestExportRequirements:
    """Test that export requirements are met."""

    def test_dlq_configured(self):
        """Test that DLQ is configured."""
        layer = TelemetryExportLayer()

        assert layer._dlq is not None
        assert layer._dlq.config.enabled is True

    def test_fallback_configured(self):
        """Test that local fallback is configured."""
        layer = TelemetryExportLayer()

        assert layer._fallback is not None

    def test_retry_logic_exists(self):
        """Test that retry logic exists."""
        layer = TelemetryExportLayer()

        # Check that retry_dlq method exists
        assert hasattr(layer, "retry_dlq")
        assert callable(getattr(layer, "retry_dlq"))
