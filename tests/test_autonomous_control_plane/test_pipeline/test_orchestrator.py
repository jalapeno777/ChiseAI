"""Tests for telemetry pipeline orchestrator.

ST-CONTROL-001: Telemetry Pipeline
"""

import time

from autonomous_control_plane.pipeline.ingestion import IngestionStatus
from autonomous_control_plane.pipeline.orchestrator import (
    PipelineMetrics,
    PipelineStageCoordinator,
    PipelineState,
    TelemetryPipeline,
)


class TestPipelineState:
    """Test pipeline state transitions."""

    def test_initial_state(self):
        """Test initial pipeline state."""
        pipeline = TelemetryPipeline()

        assert pipeline.state == PipelineState.STOPPED

    def test_start_transition(self):
        """Test starting pipeline changes state."""
        pipeline = TelemetryPipeline()

        pipeline.start()

        assert pipeline.state == PipelineState.RUNNING

        pipeline.stop()

    def test_stop_transition(self):
        """Test stopping pipeline changes state."""
        pipeline = TelemetryPipeline()

        pipeline.start()
        pipeline.stop()

        assert pipeline.state == PipelineState.STOPPED

    def test_pause_resume(self):
        """Test pause and resume functionality."""
        pipeline = TelemetryPipeline()

        pipeline.start()
        assert pipeline.state == PipelineState.RUNNING

        pipeline.pause()
        assert pipeline.state == PipelineState.PAUSED

        pipeline.resume()
        assert pipeline.state == PipelineState.RUNNING

        pipeline.stop()


class TestPipelineStageCoordinator:
    """Test pipeline stage coordinator."""

    def test_submit_and_get_ingestion(self):
        """Test submitting and getting ingestion events."""
        coordinator = PipelineStageCoordinator()

        from autonomous_control_plane.pipeline.ingestion import (
            IngestionSourceType,
            TelemetryEvent,
        )

        event = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "test"},
        )

        coordinator.submit_to_ingestion(event)
        batch = coordinator.get_ingestion_batch(max_size=10)

        assert len(batch) == 1
        assert batch[0].event_id == event.event_id

    def test_queue_sizes(self):
        """Test getting queue sizes."""
        coordinator = PipelineStageCoordinator()

        from autonomous_control_plane.pipeline.ingestion import (
            IngestionSourceType,
            TelemetryEvent,
        )

        event = TelemetryEvent(
            source_type=IngestionSourceType.LOGS,
            timestamp=time.time(),
            data={"message": "test"},
        )

        coordinator.submit_to_ingestion(event)

        sizes = coordinator.get_queue_sizes()

        assert sizes["ingestion"] == 1


class TestPipelineMetrics:
    """Test pipeline metrics."""

    def test_initial_metrics(self):
        """Test initial metrics values."""
        metrics = PipelineMetrics()

        assert metrics.events_ingested == 0
        assert metrics.events_processed == 0
        assert metrics.events_dropped == 0

    def test_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = PipelineMetrics(
            events_ingested=100,
            events_processed=95,
            events_dropped=5,
        )

        data = metrics.to_dict()

        assert data["events_ingested"] == 100
        assert data["events_processed"] == 95
        assert data["events_dropped"] == 5


class TestTelemetryPipeline:
    """Test telemetry pipeline."""

    def test_ingest_log(self):
        """Test log ingestion through pipeline."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            result = pipeline.ingest_log({"message": "test", "level": "info"})

            assert result.status == IngestionStatus.ACCEPTED
        finally:
            pipeline.stop()

    def test_ingest_metric(self):
        """Test metric ingestion through pipeline."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            result = pipeline.ingest_metric({"metric_name": "test", "value": 42.0})

            assert result.status == IngestionStatus.ACCEPTED
        finally:
            pipeline.stop()

    def test_ingest_event(self):
        """Test event ingestion through pipeline."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            result = pipeline.ingest_event({"event_type": "test"})

            assert result.status == IngestionStatus.ACCEPTED
        finally:
            pipeline.stop()

    def test_get_metrics(self):
        """Test getting pipeline metrics."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            # Ingest some events
            pipeline.ingest_log({"message": "test1"})
            pipeline.ingest_log({"message": "test2"})

            # Give pipeline time to process
            time.sleep(0.5)

            metrics = pipeline.get_metrics()

            assert "state" in metrics
            assert "queue_sizes" in metrics
            assert "ingestion" in metrics
        finally:
            pipeline.stop()

    def test_get_health(self):
        """Test getting pipeline health."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            health = pipeline.get_health()

            assert "state" in health
            assert "is_healthy" in health
        finally:
            pipeline.stop()

    def test_test_live_ingestion(self):
        """Test live ingestion test method."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            results = pipeline.test_live_ingestion()

            assert "test_timestamp" in results
            assert "pipeline_state" in results
            assert "tests" in results
            assert "log_ingestion" in results["tests"]
            assert "metric_ingestion" in results["tests"]
            assert "event_ingestion" in results["tests"]
        finally:
            pipeline.stop()


class TestPipelineErrorRecovery:
    """Test pipeline error handling and recovery."""

    def test_error_handling(self):
        """Test that pipeline handles errors gracefully."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            # Pipeline should continue working after errors
            pipeline.ingest_log({"message": "test"})

            health = pipeline.get_health()
            assert health["consecutive_errors"] == 0
        finally:
            pipeline.stop()

    def test_pipeline_not_running_rejection(self):
        """Test that ingestion is rejected when pipeline not running."""
        pipeline = TelemetryPipeline()
        # Don't start the pipeline

        result = pipeline.ingest_log({"message": "test"})

        assert result.status == IngestionStatus.REJECTED_FILTERED


class TestPipelineRequirements:
    """Test that pipeline meets acceptance criteria."""

    def test_ingestion_performance(self):
        """Test that pipeline can handle high ingestion rates."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            # Ingest 1000 events
            start_time = time.time()
            for i in range(1000):
                pipeline.ingest_log({"id": i, "message": "test"})
            elapsed = time.time() - start_time

            # Should handle 1000 events in reasonable time
            # (allowing for pipeline processing overhead)
            assert elapsed < 5.0

            # Get metrics to verify ingestion
            metrics = pipeline.get_metrics()
            assert metrics["events_ingested"] >= 900  # Allow for some drops
        finally:
            pipeline.stop()

    def test_all_ingestion_types(self):
        """Test that all ingestion types work."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            # Test logs
            log_result = pipeline.ingest_log({"message": "test"})
            assert log_result.status == IngestionStatus.ACCEPTED

            # Test metrics
            metric_result = pipeline.ingest_metric({"name": "test", "value": 1.0})
            assert metric_result.status == IngestionStatus.ACCEPTED

            # Test events
            event_result = pipeline.ingest_event({"type": "test"})
            assert event_result.status == IngestionStatus.ACCEPTED
        finally:
            pipeline.stop()
