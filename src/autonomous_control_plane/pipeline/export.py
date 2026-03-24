"""Telemetry export layer for the autonomous control plane.

Provides InfluxDB batch export with retry, dead letter queue for failed exports,
export health monitoring, and automatic failover to local storage.

ST-CONTROL-001: Telemetry Pipeline
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from autonomous_control_plane.config.pipeline_settings import (
    DeadLetterQueueConfig,
    ExportDestinationConfig,
    ExportDestinationType,
    PipelineSettings,
    pipeline_settings,
)
from autonomous_control_plane.config.settings import settings
from autonomous_control_plane.pipeline.processing import ProcessedMetric

logger = logging.getLogger(__name__)


class ExportStatus(Enum):
    """Status of an export operation."""

    SUCCESS = "success"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    QUEUED = "queued"
    DROPPED = "dropped"


@dataclass
class ExportResult:
    """Result of an export operation."""

    status: ExportStatus
    destination: str
    metrics_count: int
    message: str = ""
    retry_after_seconds: float | None = None


@dataclass
class FailedExport:
    """A failed export for dead letter queue."""

    destination: str
    metrics: list[ProcessedMetric]
    failure_reason: str
    failure_timestamp: float
    retry_count: int = 0
    event_id: str = field(default_factory=lambda: str(time.time_ns()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "destination": self.destination,
            "metrics": [m.to_dict() for m in self.metrics],
            "failure_reason": self.failure_reason,
            "failure_timestamp": self.failure_timestamp,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailedExport:
        """Create from dictionary."""
        metrics = [ProcessedMetric(**m) for m in data.get("metrics", [])]
        return cls(
            destination=data["destination"],
            metrics=metrics,
            failure_reason=data["failure_reason"],
            failure_timestamp=data["failure_timestamp"],
            retry_count=data.get("retry_count", 0),
            event_id=data.get("event_id", str(time.time_ns())),
        )


class DeadLetterQueue:
    """Dead letter queue for failed exports."""

    def __init__(self, config: DeadLetterQueueConfig):
        """Initialize DLQ.

        Args:
            config: DLQ configuration
        """
        self.config = config
        self._queue: list[FailedExport] = []
        self._lock = threading.Lock()
        self._dropped_count = 0

    def add(self, failed_export: FailedExport) -> bool:
        """Add a failed export to the queue.

        Args:
            failed_export: Failed export to add

        Returns:
            True if added, False if queue full
        """
        with self._lock:
            if len(self._queue) >= self.config.max_size:
                self._dropped_count += 1
                # Remove oldest
                self._queue.pop(0)

            self._queue.append(failed_export)

            # Check alert threshold
            if len(self._queue) >= self.config.alert_threshold:
                logger.warning(
                    f"DLQ alert: {len(self._queue)} failed exports queued "
                    f"(threshold: {self.config.alert_threshold})"
                )

            return True

    def get_for_retry(self, max_count: int = 100) -> list[FailedExport]:
        """Get exports eligible for retry.

        Args:
            max_count: Maximum number to return

        Returns:
            List of failed exports
        """
        with self._lock:
            now = time.time()
            eligible = []

            for export in self._queue:
                # Check retention
                if now - export.failure_timestamp > self.config.retention_hours * 3600:
                    continue

                eligible.append(export)
                if len(eligible) >= max_count:
                    break

            return eligible

    def remove(self, event_id: str) -> bool:
        """Remove an export from the queue.

        Args:
            event_id: Event ID to remove

        Returns:
            True if removed
        """
        with self._lock:
            for i, export in enumerate(self._queue):
                if export.event_id == event_id:
                    self._queue.pop(i)
                    return True
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            now = time.time()
            expired = sum(
                1
                for e in self._queue
                if now - e.failure_timestamp > self.config.retention_hours * 3600
            )

            return {
                "size": len(self._queue),
                "max_size": self.config.max_size,
                "dropped_count": self._dropped_count,
                "expired_count": expired,
                "alert_threshold": self.config.alert_threshold,
                "is_above_threshold": len(self._queue) >= self.config.alert_threshold,
            }

    def clear(self) -> list[FailedExport]:
        """Clear all exports from queue."""
        with self._lock:
            exports = self._queue.copy()
            self._queue.clear()
            return exports


class LocalStorageFallback:
    """Local file storage fallback for failed exports."""

    def __init__(self, base_path: str = "/tmp/telemetry_fallback"):
        """Initialize fallback storage.

        Args:
            base_path: Base directory for fallback files
        """
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _get_file_path(self, destination: str) -> str:
        """Get file path for destination."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.base_path, f"{destination}_{timestamp}.jsonl")

    def store(self, destination: str, metrics: list[ProcessedMetric]) -> bool:
        """Store metrics to local file.

        Args:
            destination: Destination name
            metrics: Metrics to store

        Returns:
            True if stored successfully
        """
        try:
            file_path = self._get_file_path(destination)
            with open(file_path, "a") as f:
                for metric in metrics:
                    f.write(json.dumps(metric.to_dict()) + "\n")
            return True
        except Exception as e:
            logger.error(f"Failed to store fallback data: {e}")
            return False

    def retrieve(self, destination: str) -> list[dict[str, Any]]:
        """Retrieve stored metrics for destination.

        Args:
            destination: Destination name

        Returns:
            List of stored metric dictionaries
        """
        metrics = []
        try:
            for filename in os.listdir(self.base_path):
                if filename.startswith(destination):
                    file_path = os.path.join(self.base_path, filename)
                    with open(file_path) as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                metrics.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to retrieve fallback data: {e}")

        return metrics

    def clear(self, destination: str | None = None) -> None:
        """Clear stored metrics.

        Args:
            destination: Clear only this destination (None for all)
        """
        try:
            for filename in os.listdir(self.base_path):
                if destination is None or filename.startswith(destination):
                    os.remove(os.path.join(self.base_path, filename))
        except Exception as e:
            logger.error(f"Failed to clear fallback data: {e}")


class InfluxDBExporter:
    """InfluxDB exporter with batching and retry."""

    def __init__(self, config: ExportDestinationConfig):
        """Initialize InfluxDB exporter.

        Args:
            config: Export configuration
        """
        self.config = config
        self._client = None
        self._write_api = None
        self._health_status = {"healthy": False, "last_check": 0, "message": ""}
        self._health_lock = threading.Lock()

    def _get_client(self):
        """Get or create InfluxDB client."""
        if self._client is None:
            try:
                from influxdb_client import InfluxDBClient
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._client = InfluxDBClient(
                    url=settings.influxdb.url,
                    token=settings.influxdb.token,
                    org=settings.influxdb.org,
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.error(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def check_health(self) -> tuple[bool, str]:
        """Check InfluxDB health.

        Returns:
            Tuple of (is_healthy, message)
        """
        with self._health_lock:
            now = time.time()
            # Cache health check for interval
            if (
                now - self._health_status["last_check"]
                < self.config.health_check_interval_seconds
            ):
                return (
                    self._health_status["healthy"],
                    self._health_status["message"],
                )

            try:
                client = self._get_client()
                if client is None:
                    self._health_status = {
                        "healthy": False,
                        "last_check": now,
                        "message": "Client not initialized",
                    }
                    return False, "Client not initialized"

                health = client.health()
                is_healthy = health.status == "pass"
                message = f"InfluxDB health: {health.status}"

                self._health_status = {
                    "healthy": is_healthy,
                    "last_check": now,
                    "message": message,
                }

                return is_healthy, message
            except Exception as e:
                message = f"Health check failed: {e}"
                self._health_status = {
                    "healthy": False,
                    "last_check": now,
                    "message": message,
                }
                return False, message

    def export(self, metrics: list[ProcessedMetric]) -> ExportResult:
        """Export metrics to InfluxDB.

        Args:
            metrics: Metrics to export

        Returns:
            Export result
        """
        if not metrics:
            return ExportResult(
                status=ExportStatus.SUCCESS,
                destination=self.config.name,
                metrics_count=0,
            )

        # Check health first
        is_healthy, health_msg = self.check_health()
        if not is_healthy:
            return ExportResult(
                status=ExportStatus.FAILED_RETRYABLE,
                destination=self.config.name,
                metrics_count=len(metrics),
                message=health_msg,
                retry_after_seconds=self.config.retry_backoff_seconds,
            )

        try:
            from influxdb_client import Point

            points = []
            for metric in metrics:
                point = Point(metric.name)
                point.time(int(metric.timestamp * 1e9))  # Nanoseconds

                # Add tags
                for key, value in metric.tags.items():
                    point.tag(key, value)

                # Add window tag
                point.tag("window_seconds", str(metric.window.value))

                # Add fields
                for key, value in metric.fields.items():
                    if isinstance(value, (int, float)):
                        point.field(key, value)
                    else:
                        point.field(key, str(value))

                points.append(point)

            if self._write_api:
                self._write_api.write(
                    bucket=settings.influxdb.bucket,
                    org=settings.influxdb.org,
                    record=points,
                )

            return ExportResult(
                status=ExportStatus.SUCCESS,
                destination=self.config.name,
                metrics_count=len(metrics),
                message=f"Exported {len(metrics)} points",
            )

        except Exception as e:
            logger.error(f"InfluxDB export failed: {e}")
            return ExportResult(
                status=ExportStatus.FAILED_RETRYABLE,
                destination=self.config.name,
                metrics_count=len(metrics),
                message=str(e),
                retry_after_seconds=self.config.retry_backoff_seconds,
            )

    def close(self) -> None:
        """Close InfluxDB client."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing InfluxDB client: {e}")
            finally:
                self._client = None
                self._write_api = None


class TelemetryExportLayer:
    """Telemetry export layer with retry and failover.

    Manages multiple export destinations with batching, retry logic,
    dead letter queue, and automatic failover to local storage.

    Example:
        >>> export = TelemetryExportLayer()
        >>> result = export.export_metrics(metrics)
        >>> print(result.status)
        ExportStatus.SUCCESS
    """

    def __init__(self, settings: PipelineSettings | None = None):
        """Initialize export layer.

        Args:
            settings: Pipeline settings (uses default if not provided)
        """
        self.settings = settings or pipeline_settings

        # Initialize exporters
        self._exporters: dict[str, Any] = {}
        for dest_config in self.settings.destinations:
            if dest_config.destination_type == ExportDestinationType.INFLUXDB:
                self._exporters[dest_config.name] = InfluxDBExporter(dest_config)

        # Dead letter queue
        self._dlq = DeadLetterQueue(self.settings.dead_letter_queue)

        # Local storage fallback
        self._fallback = LocalStorageFallback()

        # Metrics
        self._export_metrics = {
            "success": 0,
            "failed": 0,
            "retried": 0,
            "dlq": 0,
            "fallback": 0,
        }
        self._metrics_lock = threading.Lock()

    def export_metrics(
        self, metrics: list[ProcessedMetric], destination: str | None = None
    ) -> list[ExportResult]:
        """Export metrics to destinations.

        Args:
            metrics: Metrics to export
            destination: Specific destination (None for all)

        Returns:
            List of export results
        """
        if not metrics:
            return []

        results = []

        if destination:
            # Export to specific destination
            exporter = self._exporters.get(destination)
            if exporter:
                result = self._export_with_retry(exporter, metrics, destination)
                results.append(result)
            else:
                results.append(
                    ExportResult(
                        status=ExportStatus.FAILED_PERMANENT,
                        destination=destination,
                        metrics_count=len(metrics),
                        message=f"Destination '{destination}' not found",
                    )
                )
        else:
            # Export to all enabled destinations
            for name, exporter in self._exporters.items():
                config = next(
                    (d for d in self.settings.destinations if d.name == name), None
                )
                if config and config.enabled:
                    result = self._export_with_retry(exporter, metrics, name)
                    results.append(result)

        return results

    def _export_with_retry(
        self, exporter: Any, metrics: list[ProcessedMetric], destination: str
    ) -> ExportResult:
        """Export with retry logic.

        Args:
            exporter: Exporter instance
            metrics: Metrics to export
            destination: Destination name

        Returns:
            Export result
        """
        config = next(
            (d for d in self.settings.destinations if d.name == destination), None
        )
        max_retries = config.retry_attempts if config else 3

        for attempt in range(max_retries + 1):
            result = exporter.export(metrics)

            if result.status == ExportStatus.SUCCESS:
                with self._metrics_lock:
                    self._export_metrics["success"] += 1
                return result

            if result.status == ExportStatus.FAILED_PERMANENT:
                with self._metrics_lock:
                    self._export_metrics["failed"] += 1
                # Add to DLQ
                self._dlq.add(
                    FailedExport(
                        destination=destination,
                        metrics=metrics,
                        failure_reason=result.message,
                        failure_timestamp=time.time(),
                        retry_count=attempt,
                    )
                )
                return result

            # Retryable failure
            if attempt < max_retries:
                with self._metrics_lock:
                    self._export_metrics["retried"] += 1
                retry_delay = (config.retry_backoff_seconds if config else 1.0) * (
                    2**attempt
                )  # Exponential backoff
                logger.warning(
                    f"Export to {destination} failed (attempt {attempt + 1}), "
                    f"retrying in {retry_delay}s: {result.message}"
                )
                time.sleep(retry_delay)
            else:
                # Max retries exceeded
                with self._metrics_lock:
                    self._export_metrics["failed"] += 1

                # Try fallback to local storage
                if self._fallback.store(destination, metrics):
                    with self._metrics_lock:
                        self._export_metrics["fallback"] += 1
                    logger.info(f"Stored {len(metrics)} metrics to local fallback")

                # Add to DLQ
                self._dlq.add(
                    FailedExport(
                        destination=destination,
                        metrics=metrics,
                        failure_reason=f"Max retries exceeded: {result.message}",
                        failure_timestamp=time.time(),
                        retry_count=attempt,
                    )
                )

                return ExportResult(
                    status=ExportStatus.FAILED_PERMANENT,
                    destination=destination,
                    metrics_count=len(metrics),
                    message=f"Max retries exceeded: {result.message}",
                )

        # Should not reach here
        return ExportResult(
            status=ExportStatus.FAILED_PERMANENT,
            destination=destination,
            metrics_count=len(metrics),
            message="Unknown error",
        )

    def retry_dlq(self, max_count: int = 100) -> list[ExportResult]:
        """Retry failed exports from DLQ.

        Args:
            max_count: Maximum number to retry

        Returns:
            List of export results
        """
        results = []
        failed_exports = self._dlq.get_for_retry(max_count)

        for failed in failed_exports:
            exporter = self._exporters.get(failed.destination)
            if exporter:
                result = self._export_with_retry(
                    exporter, failed.metrics, failed.destination
                )
                results.append(result)

                if result.status == ExportStatus.SUCCESS:
                    self._dlq.remove(failed.event_id)

        return results

    def get_health_status(self) -> dict[str, dict[str, Any]]:
        """Get health status of all destinations."""
        status = {}
        for name, exporter in self._exporters.items():
            is_healthy, message = exporter.check_health()
            status[name] = {
                "healthy": is_healthy,
                "message": message,
            }
        return status

    def get_metrics(self) -> dict[str, Any]:
        """Get export metrics."""
        with self._metrics_lock:
            return self._export_metrics.copy()

    def get_dlq_stats(self) -> dict[str, Any]:
        """Get dead letter queue statistics."""
        return self._dlq.get_stats()

    def close(self) -> None:
        """Close all exporters."""
        for exporter in self._exporters.values():
            try:
                exporter.close()
            except Exception as e:
                logger.warning(f"Error closing exporter: {e}")


# Singleton instance
export_layer: TelemetryExportLayer | None = None


def get_export_layer() -> TelemetryExportLayer:
    """Get global export layer instance."""
    global export_layer
    if export_layer is None:
        export_layer = TelemetryExportLayer()
    return export_layer
