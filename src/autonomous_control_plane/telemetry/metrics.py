"""Telemetry metrics for the autonomous control plane.

Provides unified telemetry collection and export to InfluxDB.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.config.settings import settings

if TYPE_CHECKING:
    from influxdb_client.client.influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""

    measurement: str
    tags: dict[str, str]
    fields: dict[str, float | int | bool | str]
    timestamp: float = field(default_factory=time.time)

    def to_influxdb_point(self) -> dict[str, Any]:
        """Convert to InfluxDB point format."""
        return {
            "measurement": self.measurement,
            "tags": self.tags,
            "fields": self.fields,
            "time": int(self.timestamp * 1e9),  # Nanoseconds
        }


class TelemetryCollector:
    """Collects and exports telemetry metrics.

    Provides automatic batching and periodic flushing to InfluxDB.

    Example:
        >>> collector = TelemetryCollector()
        >>> collector.record("circuit_breaker", {"service": "redis"}, {"failures": 5})
        >>> collector.start()
        # Metrics are automatically flushed every 15 seconds
    """

    _instance: TelemetryCollector | None = None
    _lock = threading.Lock()

    def __new__(cls) -> TelemetryCollector:
        """Singleton pattern for global collector access."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, influxdb_client: InfluxDBClient | None = None):
        """Initialize the telemetry collector.

        Args:
            influxdb_client: Optional InfluxDB client (creates new if not provided)
        """
        if self._initialized:
            return

        self._initialized = True
        self._buffer: list[MetricPoint] = []
        self._buffer_lock = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._influxdb = influxdb_client

        # Initialize InfluxDB if not provided
        if self._influxdb is None and settings.telemetry.enabled:
            try:
                from influxdb_client.client.influxdb_client import InfluxDBClient

                self._influxdb = InfluxDBClient(
                    url=settings.influxdb.url,
                    token=settings.influxdb.token,
                    org=settings.influxdb.org,
                )
                logger.info("TelemetryCollector: InfluxDB connection established")
            except Exception as e:
                logger.warning(f"TelemetryCollector: InfluxDB unavailable ({e})")
                self._influxdb = None

    def start(self) -> None:
        """Start the background flush thread."""
        if self._flush_thread is not None and self._flush_thread.is_alive():
            logger.warning("TelemetryCollector: Already running")
            return

        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="TelemetryCollector-Flush",
            daemon=True,
        )
        self._flush_thread.start()
        logger.info(
            f"TelemetryCollector: Started (flush interval={settings.telemetry.flush_interval_seconds}s)"
        )

    def stop(self) -> None:
        """Stop the background flush thread."""
        self._stop_event.set()

        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

        # Final flush
        self.flush()
        logger.info("TelemetryCollector: Stopped")

    def _flush_loop(self) -> None:
        """Background loop for periodic flushing."""
        while not self._stop_event.is_set():
            self._stop_event.wait(settings.telemetry.flush_interval_seconds)
            if not self._stop_event.is_set():
                self.flush()

    def record(
        self,
        measurement: str,
        tags: dict[str, str],
        fields: dict[str, float | int | bool | str],
    ) -> None:
        """Record a metric point.

        Args:
            measurement: Metric measurement name
            tags: Tag key-value pairs
            fields: Field key-value pairs
        """
        point = MetricPoint(
            measurement=measurement,
            tags=tags,
            fields=fields,
        )

        with self._buffer_lock:
            self._buffer.append(point)

            # Flush immediately if buffer is full
            if len(self._buffer) >= settings.telemetry.batch_size:
                self._flush_unlocked()

    def flush(self) -> None:
        """Manually flush buffered metrics."""
        with self._buffer_lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        """Flush metrics without acquiring lock (caller must hold lock)."""
        if not self._buffer or self._influxdb is None:
            return

        try:
            from influxdb_client.client.write_api import SYNCHRONOUS

            write_api = self._influxdb.write_api(write_options=SYNCHRONOUS)

            points = [p.to_influxdb_point() for p in self._buffer]
            write_api.write(
                bucket=settings.influxdb.bucket,
                org=settings.influxdb.org,
                record=points,
            )

            logger.debug(f"TelemetryCollector: Flushed {len(points)} points")
            self._buffer.clear()

        except Exception as e:
            logger.warning(f"TelemetryCollector: Flush failed ({e})")

    def record_circuit_breaker_state(
        self,
        service_name: str,
        state: str,
        failure_count: int,
        success_count: int,
        rejection_count: int,
        **additional_fields: int | float | bool | str,
    ) -> None:
        """Record circuit breaker state metric.

        Args:
            service_name: Name of the service
            state: Circuit breaker state (closed/open/half_open)
            failure_count: Number of failures
            success_count: Number of successes
            rejection_count: Number of rejections
            **additional_fields: Additional fields to record
        """
        fields = {
            "failure_count": failure_count,
            "success_count": success_count,
            "rejection_count": rejection_count,
            **additional_fields,
        }

        self.record(
            measurement=settings.cb_telemetry_measurement,
            tags={
                "service_name": service_name,
                "state": state,
            },
            fields=fields,
        )

    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        with self._buffer_lock:
            return len(self._buffer)


class CircuitBreakerTelemetryExporter:
    """Dedicated telemetry exporter for circuit breaker registry.

    Emits circuit breaker state metrics to InfluxDB with configurable flush interval.
    """

    def __init__(
        self,
        registry: Any,
        flush_interval_seconds: float = 15.0,
    ):
        """Initialize the exporter.

        Args:
            registry: CircuitBreakerRegistry instance
            flush_interval_seconds: Interval between telemetry flushes
        """
        self._registry = registry
        self._flush_interval = flush_interval_seconds
        self._collector = TelemetryCollector()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the telemetry export loop."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._export_loop,
            name="CB-Telemetry-Exporter",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"CircuitBreakerTelemetryExporter: Started ({self._flush_interval}s interval)"
        )

    def stop(self) -> None:
        """Stop the telemetry export loop."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        # Final export
        self._export_metrics()
        logger.info("CircuitBreakerTelemetryExporter: Stopped")

    def _export_loop(self) -> None:
        """Background loop for exporting metrics."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval)
            if not self._stop_event.is_set():
                self._export_metrics()

    def _export_metrics(self) -> None:
        """Export current circuit breaker metrics."""
        try:
            states = self._registry.get_all_states()

            for name, state in states.items():
                self._collector.record_circuit_breaker_state(
                    service_name=name,
                    state=state.state.value,
                    failure_count=state.metrics.failure_count,
                    success_count=state.metrics.success_count,
                    rejection_count=state.metrics.rejection_count,
                    state_transition_count=state.metrics.state_transition_count,
                    consecutive_successes=state.metrics.consecutive_successes,
                    consecutive_failures=state.metrics.consecutive_failures,
                    half_open_calls=state.half_open_calls,
                )

            # Flush immediately
            self._collector.flush()

        except Exception as e:
            logger.warning(f"CircuitBreakerTelemetryExporter: Export failed ({e})")
