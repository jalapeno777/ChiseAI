"""
Base Metrics Exporter for Governance Features.

Provides abstract base class and data structures for collecting
and exporting governance metrics to InfluxDB.

Story: ST-GOV-004
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class MetricType(Enum):
    """Types of metrics supported."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    """Metric name (e.g., 'governance.sentinel.tasks_blocked')"""

    value: float
    """Metric value"""

    metric_type: MetricType = MetricType.GAUGE
    """Type of metric"""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    """When this metric was collected"""

    tags: dict[str, str] = field(default_factory=dict)
    """Tags for filtering/grouping (e.g., {'feature': 'sentinel'})"""

    fields: dict[str, Any] = field(default_factory=dict)
    """Additional fields for complex metrics"""


@dataclass
class ExportResult:
    """Result of a metrics export operation."""

    success: bool
    """Whether export was successful"""

    points_exported: int = 0
    """Number of metric points exported"""

    errors: list[str] = field(default_factory=list)
    """Any errors encountered"""

    export_time_seconds: float = 0.0
    """Time taken to export"""


class BaseMetricsExporter(ABC):
    """
    Abstract base class for governance metrics exporters.

    Each governance feature (sentinel, memory, constitution) should
    implement its own exporter that collects relevant metrics.

    Usage:
        class SentinelMetricsExporter(BaseMetricsExporter):
            def collect(self) -> list[MetricPoint]:
                return [
                    MetricPoint("tasks_validated", count, tags={"status": "approved"}),
                ]
    """

    def __init__(
        self,
        feature_name: str,
        influx_client: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize the metrics exporter.

        Args:
            feature_name: Name of the governance feature (e.g., 'sentinel')
            influx_client: Optional InfluxDB client for writing metrics
            redis_client: Optional Redis client for reading feature state
        """
        self.feature_name = feature_name
        self._influx_client = influx_client
        self._redis_client = redis_client
        self._last_collection: datetime | None = None
        self._collection_count: int = 0

    @abstractmethod
    def collect(self) -> list[MetricPoint]:
        """
        Collect metrics from the feature.

        Must be implemented by each feature-specific exporter.

        Returns:
            List of MetricPoint objects representing current state
        """
        pass

    def export(self, bucket: str = "governance") -> ExportResult:
        """
        Export collected metrics to InfluxDB.

        Args:
            bucket: InfluxDB bucket to write to

        Returns:
            ExportResult with success status and details
        """
        import time

        start_time = time.time()
        result = ExportResult(success=True)

        try:
            points = self.collect()
            result.points_exported = len(points)

            if self._influx_client is not None and points:
                self._write_to_influx(points, bucket)

            self._last_collection = datetime.now(UTC)
            self._collection_count += 1

        except Exception as e:
            result.success = False
            result.errors.append(str(e))

        finally:
            result.export_time_seconds = time.time() - start_time

        return result

    def _write_to_influx(self, points: list[MetricPoint], bucket: str) -> None:
        """Write metric points to InfluxDB."""
        if self._influx_client is None:
            return

        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS

        write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)

        influx_points = []
        for mp in points:
            p = (
                Point(mp.name)
                .tag("feature", self.feature_name)
                .tag("metric_type", mp.metric_type.value)
                .field("value", mp.value)
                .time(mp.timestamp)
            )

            for key, value in mp.tags.items():
                p.tag(key, value)

            for key, value in mp.fields.items():
                p.field(key, value)

            influx_points.append(p)

        write_api.write(bucket=bucket, record=influx_points)

    def get_last_collection_time(self) -> datetime | None:
        """Get timestamp of last successful collection."""
        return self._last_collection

    def get_collection_count(self) -> int:
        """Get total number of collections performed."""
        return self._collection_count

    def is_healthy(self) -> bool:
        """
        Check if the exporter is healthy.

        Returns:
            True if exporter has collected successfully recently
        """
        if self._last_collection is None:
            return False

        age = (datetime.now(UTC) - self._last_collection).total_seconds()
        return age < 300  # Consider healthy if collected within 5 minutes
