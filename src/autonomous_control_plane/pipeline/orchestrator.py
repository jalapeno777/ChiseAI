"""Pipeline orchestrator for the autonomous control plane telemetry system.

Provides pipeline lifecycle management, stage coordination, error handling,
and performance monitoring.

ST-CONTROL-001: Telemetry Pipeline
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from autonomous_control_plane.config.pipeline_settings import (
    PipelineSettings,
    pipeline_settings,
)
from autonomous_control_plane.pipeline.export import (
    ExportStatus,
    get_export_layer,
)
from autonomous_control_plane.pipeline.ingestion import (
    IngestionResult,
    IngestionStatus,
    TelemetryEvent,
    get_ingestion_layer,
)
from autonomous_control_plane.pipeline.processing import (
    ProcessedMetric,
    get_processing_layer,
)

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """State of the telemetry pipeline."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


class PipelineStage(Enum):
    """Pipeline processing stages."""

    INGESTION = "ingestion"
    PROCESSING = "processing"
    EXPORT = "export"


@dataclass
class PipelineMetrics:
    """Metrics for pipeline performance monitoring."""

    events_ingested: int = 0
    events_processed: int = 0
    events_dropped: int = 0
    metrics_exported: int = 0
    export_failures: int = 0
    processing_time_ms: float = 0.0
    last_flush_time: float = 0.0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "events_ingested": self.events_ingested,
            "events_processed": self.events_processed,
            "events_dropped": self.events_dropped,
            "metrics_exported": self.metrics_exported,
            "export_failures": self.export_failures,
            "processing_time_ms": self.processing_time_ms,
            "last_flush_time": self.last_flush_time,
            "error_count": len(self.errors),
        }


@dataclass
class StageHealth:
    """Health status of a pipeline stage."""

    stage: PipelineStage
    healthy: bool
    message: str
    last_check: float
    metrics: dict[str, Any] = field(default_factory=dict)


class PipelineStageCoordinator:
    """Coordinates data flow between pipeline stages."""

    def __init__(self):
        """Initialize stage coordinator."""
        self._ingestion_queue: list[TelemetryEvent] = []
        self._processing_queue: list[TelemetryEvent] = []
        self._export_queue: list[ProcessedMetric] = []
        self._lock = threading.Lock()

    def submit_to_ingestion(self, event: TelemetryEvent) -> None:
        """Submit event to ingestion queue."""
        with self._lock:
            self._ingestion_queue.append(event)

    def submit_to_processing(self, events: list[TelemetryEvent]) -> None:
        """Submit events to processing queue."""
        with self._lock:
            self._processing_queue.extend(events)

    def submit_to_export(self, metrics: list[ProcessedMetric]) -> None:
        """Submit metrics to export queue."""
        with self._lock:
            self._export_queue.extend(metrics)

    def get_ingestion_batch(self, max_size: int) -> list[TelemetryEvent]:
        """Get batch from ingestion queue."""
        with self._lock:
            batch = self._ingestion_queue[:max_size]
            self._ingestion_queue = self._ingestion_queue[max_size:]
            return batch

    def get_processing_batch(self, max_size: int) -> list[TelemetryEvent]:
        """Get batch from processing queue."""
        with self._lock:
            batch = self._processing_queue[:max_size]
            self._processing_queue = self._processing_queue[max_size:]
            return batch

    def get_export_batch(self, max_size: int) -> list[ProcessedMetric]:
        """Get batch from export queue."""
        with self._lock:
            batch = self._export_queue[:max_size]
            self._export_queue = self._export_queue[max_size:]
            return batch

    def get_queue_sizes(self) -> dict[str, int]:
        """Get current queue sizes."""
        with self._lock:
            return {
                "ingestion": len(self._ingestion_queue),
                "processing": len(self._processing_queue),
                "export": len(self._export_queue),
            }


class TelemetryPipeline:
    """Complete telemetry pipeline orchestrator.

        Manages the entire telemetry pipeline from ingestion through processing
    to export, with lifecycle management and error recovery.

        Example:
            >>> pipeline = TelemetryPipeline()
            >>> pipeline.start()
            >>> pipeline.ingest_log({"message": "test"})
            >>> pipeline.stop()
    """

    def __init__(self, settings: PipelineSettings | None = None):
        """Initialize telemetry pipeline.

        Args:
            settings: Pipeline settings (uses default if not provided)
        """
        self.settings = settings or pipeline_settings

        # Pipeline stages
        self._ingestion = get_ingestion_layer()
        self._processing = get_processing_layer()
        self._export = get_export_layer()

        # Stage coordinator
        self._coordinator = PipelineStageCoordinator()

        # State
        self._state = PipelineState.STOPPED
        self._state_lock = threading.Lock()

        # Processing threads
        self._processing_thread: threading.Thread | None = None
        self._export_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Metrics
        self._metrics = PipelineMetrics()
        self._metrics_lock = threading.Lock()

        # Error recovery
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5
        self._error_cooldown_seconds = 5.0

    @property
    def state(self) -> PipelineState:
        """Get current pipeline state."""
        with self._state_lock:
            return self._state

    def _set_state(self, state: PipelineState) -> None:
        """Set pipeline state."""
        with self._state_lock:
            old_state = self._state
            self._state = state
            logger.info(f"Pipeline state: {old_state.value} -> {state.value}")

    def start(self) -> bool:
        """Start the telemetry pipeline.

        Returns:
            True if started successfully
        """
        if self.state != PipelineState.STOPPED:
            logger.warning(f"Cannot start pipeline in state: {self.state.value}")
            return False

        self._set_state(PipelineState.STARTING)

        try:
            # Reset state
            self._stop_event.clear()
            self._consecutive_errors = 0

            # Start processing thread
            self._processing_thread = threading.Thread(
                target=self._processing_loop,
                name="TelemetryPipeline-Processing",
                daemon=True,
            )
            self._processing_thread.start()

            # Start export thread
            self._export_thread = threading.Thread(
                target=self._export_loop,
                name="TelemetryPipeline-Export",
                daemon=True,
            )
            self._export_thread.start()

            self._set_state(PipelineState.RUNNING)
            logger.info("Telemetry pipeline started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start pipeline: {e}")
            self._set_state(PipelineState.ERROR)
            return False

    def stop(self, timeout: float = 30.0) -> bool:
        """Stop the telemetry pipeline.

        Args:
            timeout: Timeout for graceful shutdown

        Returns:
            True if stopped successfully
        """
        if self.state not in (PipelineState.RUNNING, PipelineState.ERROR):
            logger.warning(f"Cannot stop pipeline in state: {self.state.value}")
            return False

        self._set_state(PipelineState.STOPPING)
        self._stop_event.set()

        # Wait for threads to finish
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=timeout / 2)

        if self._export_thread and self._export_thread.is_alive():
            self._export_thread.join(timeout=timeout / 2)

        # Final flush
        self._flush_all()

        # Close export layer
        self._export.close()

        self._set_state(PipelineState.STOPPED)
        logger.info("Telemetry pipeline stopped")
        return True

    def pause(self) -> bool:
        """Pause the pipeline (stop processing but keep ingestion)."""
        if self.state != PipelineState.RUNNING:
            return False

        self._set_state(PipelineState.PAUSED)
        return True

    def resume(self) -> bool:
        """Resume the pipeline from paused state."""
        if self.state != PipelineState.PAUSED:
            return False

        self._set_state(PipelineState.RUNNING)
        return True

    def _processing_loop(self) -> None:
        """Background processing loop."""
        logger.info("Processing loop started")

        while not self._stop_event.is_set():
            try:
                if self.state == PipelineState.PAUSED:
                    time.sleep(0.1)
                    continue

                start_time = time.time()

                # Get events from ingestion sources
                for source_name, source in self._ingestion._sources.items():
                    events = source.get_events(max_count=1000, timeout=0.1)
                    if events:
                        self._coordinator.submit_to_processing(events)

                # Process events
                events = self._coordinator.get_processing_batch(max_size=1000)
                if events:
                    processed = self._processing.process_batch(events)
                    self._coordinator.submit_to_export(self._processing.flush())

                    with self._metrics_lock:
                        self._metrics.events_processed += len(processed)

                # Reset error counter on success
                self._consecutive_errors = 0

                # Update processing time
                elapsed_ms = (time.time() - start_time) * 1000
                with self._metrics_lock:
                    self._metrics.processing_time_ms = elapsed_ms

                # Small sleep to prevent tight loop
                time.sleep(0.001)

            except Exception as e:
                self._handle_error("processing_loop", e)

        logger.info("Processing loop stopped")

    def _export_loop(self) -> None:
        """Background export loop."""
        logger.info("Export loop started")

        while not self._stop_event.is_set():
            try:
                if self.state == PipelineState.PAUSED:
                    time.sleep(0.1)
                    continue

                # Get metrics from queue
                metrics = self._coordinator.get_export_batch(max_size=1000)
                if metrics:
                    results = self._export.export_metrics(metrics)

                    for result in results:
                        with self._metrics_lock:
                            if result.status == ExportStatus.SUCCESS:
                                self._metrics.metrics_exported += result.metrics_count
                            else:
                                self._metrics.export_failures += 1

                # Retry DLQ periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    self._export.retry_dlq(max_count=50)

                # Small sleep to prevent tight loop
                time.sleep(0.001)

            except Exception as e:
                self._handle_error("export_loop", e)

        logger.info("Export loop stopped")

    def _handle_error(self, context: str, error: Exception) -> None:
        """Handle pipeline error with recovery logic.

        Args:
            context: Error context
            error: Exception that occurred
        """
        self._consecutive_errors += 1

        error_info = {
            "context": context,
            "error": str(error),
            "timestamp": time.time(),
            "consecutive_errors": self._consecutive_errors,
        }

        with self._metrics_lock:
            self._metrics.errors.append(error_info)
            # Keep only last 100 errors
            if len(self._metrics.errors) > 100:
                self._metrics.errors = self._metrics.errors[-100:]

        logger.error(f"Pipeline error in {context}: {error}")

        # Check if we should enter error state
        if self._consecutive_errors >= self._max_consecutive_errors:
            logger.error(
                f"Too many consecutive errors ({self._consecutive_errors}), "
                "entering error state"
            )
            self._set_state(PipelineState.ERROR)
            time.sleep(self._error_cooldown_seconds)

    def _flush_all(self) -> None:
        """Flush all pending data."""
        logger.info("Flushing all pending data")

        # Flush ingestion buffers
        for source in self._ingestion._sources.values():
            events = source.clear()
            if events:
                self._coordinator.submit_to_processing(events)

        # Process remaining events
        events = self._coordinator.get_processing_batch(max_size=10000)
        if events:
            processed = self._processing.process_batch(events)
            metrics = self._processing.flush()
            self._coordinator.submit_to_export(metrics)

        # Export remaining metrics
        metrics = self._coordinator.get_export_batch(max_size=10000)
        if metrics:
            self._export.export_metrics(metrics)

        with self._metrics_lock:
            self._metrics.last_flush_time = time.time()

    def ingest_log(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a log event.

        Args:
            data: Log data
            metadata: Log metadata

        Returns:
            Ingestion result
        """
        if self.state not in (PipelineState.RUNNING, PipelineState.PAUSED):
            return IngestionResult(
                status=IngestionStatus.REJECTED_FILTERED,
                message=f"Pipeline not running (state: {self.state.value})",
            )

        result = self._ingestion.ingest_log(data, metadata)

        if result.status == IngestionStatus.ACCEPTED:
            with self._metrics_lock:
                self._metrics.events_ingested += 1
        else:
            with self._metrics_lock:
                self._metrics.events_dropped += 1

        return result

    def ingest_metric(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a metric event."""
        if self.state not in (PipelineState.RUNNING, PipelineState.PAUSED):
            return IngestionResult(
                status=IngestionStatus.REJECTED_FILTERED,
                message=f"Pipeline not running (state: {self.state.value})",
            )

        result = self._ingestion.ingest_metric(data, metadata)

        if result.status == IngestionStatus.ACCEPTED:
            with self._metrics_lock:
                self._metrics.events_ingested += 1
        else:
            with self._metrics_lock:
                self._metrics.events_dropped += 1

        return result

    def ingest_event(
        self, data: dict[str, Any], metadata: dict[str, str] | None = None
    ) -> IngestionResult:
        """Ingest a generic event."""
        if self.state not in (PipelineState.RUNNING, PipelineState.PAUSED):
            return IngestionResult(
                status=IngestionStatus.REJECTED_FILTERED,
                message=f"Pipeline not running (state: {self.state.value})",
            )

        result = self._ingestion.ingest_event(data, metadata)

        if result.status == IngestionStatus.ACCEPTED:
            with self._metrics_lock:
                self._metrics.events_ingested += 1
        else:
            with self._metrics_lock:
                self._metrics.events_dropped += 1

        return result

    def get_metrics(self) -> dict[str, Any]:
        """Get pipeline metrics."""
        with self._metrics_lock:
            metrics = self._metrics.to_dict()

        metrics.update(
            {
                "state": self.state.value,
                "queue_sizes": self._coordinator.get_queue_sizes(),
                "ingestion": self._ingestion.get_all_metrics(),
                "processing": self._processing.get_metrics(),
                "export": self._export.get_metrics(),
                "dlq": self._export.get_dlq_stats(),
            }
        )

        return metrics

    def get_health(self) -> dict[str, Any]:
        """Get pipeline health status."""
        return {
            "state": self.state.value,
            "is_healthy": self.state == PipelineState.RUNNING,
            "consecutive_errors": self._consecutive_errors,
            "stage_health": self._export.get_health_status(),
            "backpressure": self._ingestion.get_backpressure_status(),
        }

    def test_live_ingestion(self) -> dict[str, Any]:
        """Test live ingestion and return results.

        Returns:
            Test results dictionary
        """
        results = {
            "test_timestamp": time.time(),
            "pipeline_state": self.state.value,
            "tests": {},
        }

        # Test log ingestion
        log_result = self.ingest_log(
            {
                "message": "Test log message",
                "level": "info",
                "test": True,
            }
        )
        results["tests"]["log_ingestion"] = {
            "status": log_result.status.value,
            "event_id": log_result.event_id,
        }

        # Test metric ingestion
        metric_result = self.ingest_metric(
            {
                "metric_name": "test_metric",
                "value": 42.0,
                "test": True,
            }
        )
        results["tests"]["metric_ingestion"] = {
            "status": metric_result.status.value,
            "event_id": metric_result.event_id,
        }

        # Test event ingestion
        event_result = self.ingest_event(
            {
                "event_type": "test_event",
                "test": True,
            }
        )
        results["tests"]["event_ingestion"] = {
            "status": event_result.status.value,
            "event_id": event_result.event_id,
        }

        # Get current metrics
        results["metrics"] = self.get_metrics()

        return results


# Singleton instance
_pipeline: TelemetryPipeline | None = None


def get_pipeline() -> TelemetryPipeline:
    """Get global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = TelemetryPipeline()
    return _pipeline
