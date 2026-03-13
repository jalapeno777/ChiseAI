"""Integration tests for telemetry pipeline end-to-end flow.

ST-CONTROL-001: Telemetry Pipeline
"""

import time

import pytest

from autonomous_control_plane.pipeline import (
    TelemetryPipeline,
    get_pipeline,
)
from autonomous_control_plane.pipeline.ingestion import IngestionStatus


class TestTelemetryPipelineIntegration:
    """End-to-end integration tests for telemetry pipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create and start pipeline for testing."""
        pipeline = TelemetryPipeline()
        pipeline.start()
        yield pipeline
        pipeline.stop()

    def test_end_to_end_log_flow(self, pipeline):
        """Test complete flow from log ingestion to export."""
        # Ingest log events
        for i in range(100):
            result = pipeline.ingest_log(
                {
                    "message": f"Test log {i}",
                    "level": "info",
                    "service": "test-service",
                }
            )
            assert result.status == IngestionStatus.ACCEPTED

        # Wait for processing
        time.sleep(1.0)

        # Check metrics
        metrics = pipeline.get_metrics()
        assert metrics["state"] == "running"
        assert metrics["events_ingested"] >= 100

    def test_end_to_end_metric_flow(self, pipeline):
        """Test complete flow from metric ingestion to export."""
        # Ingest metric events
        for i in range(100):
            result = pipeline.ingest_metric(
                {
                    "metric_name": "test_metric",
                    "value": float(i),
                    "tags": {"host": "server1"},
                }
            )
            assert result.status == IngestionStatus.ACCEPTED

        # Wait for processing
        time.sleep(1.0)

        # Check metrics
        metrics = pipeline.get_metrics()
        assert metrics["events_ingested"] >= 100

    def test_mixed_ingestion(self, pipeline):
        """Test mixed log, metric, and event ingestion."""
        # Ingest mixed events
        for i in range(50):
            pipeline.ingest_log({"message": f"Log {i}"})
            pipeline.ingest_metric({"metric_name": "counter", "value": float(i)})
            pipeline.ingest_event({"event_type": "user_action", "user_id": f"user_{i}"})

        # Wait for processing
        time.sleep(1.0)

        # Check metrics
        metrics = pipeline.get_metrics()
        assert metrics["events_ingested"] >= 150

    def test_backpressure_handling(self, pipeline):
        """Test pipeline handles backpressure correctly."""
        # Rapid ingestion to trigger backpressure
        results = []
        for i in range(10000):
            result = pipeline.ingest_log({"id": i, "data": "x" * 100})
            results.append(result)

        # Check that some events were accepted
        accepted = sum(1 for r in results if r.status == IngestionStatus.ACCEPTED)
        assert accepted > 0

        # Get backpressure status
        health = pipeline.get_health()
        assert "backpressure" in health

    def test_pipeline_health(self, pipeline):
        """Test pipeline health monitoring."""
        # Ingest some events
        pipeline.ingest_log({"message": "health check"})

        # Get health status
        health = pipeline.get_health()

        assert health["state"] == "running"
        assert health["is_healthy"] is True
        assert "stage_health" in health

    def test_pipeline_recovery(self, pipeline):
        """Test pipeline recovers from errors."""
        # Ingest events
        for i in range(50):
            pipeline.ingest_log({"id": i, "message": "test"})

        # Wait a bit
        time.sleep(0.5)

        # Check pipeline is still healthy
        health = pipeline.get_health()
        assert health["is_healthy"] is True
        assert health["consecutive_errors"] == 0

    def test_metrics_accumulation(self, pipeline):
        """Test that metrics accumulate correctly."""
        initial_metrics = pipeline.get_metrics()

        # Ingest events
        for i in range(100):
            pipeline.ingest_log({"id": i})

        # Wait for processing
        time.sleep(0.5)

        final_metrics = pipeline.get_metrics()

        # Metrics should have increased
        assert final_metrics["events_ingested"] > initial_metrics["events_ingested"]


class TestPipelineSingleton:
    """Test pipeline singleton functionality."""

    def test_singleton_instance(self):
        """Test that get_pipeline returns same instance."""
        pipeline1 = get_pipeline()
        pipeline2 = get_pipeline()

        assert pipeline1 is pipeline2

    def test_singleton_state(self):
        """Test that singleton maintains state."""
        pipeline = get_pipeline()

        # Start singleton
        pipeline.start()

        try:
            assert pipeline.state.value == "running"

            # Get singleton again and verify state
            pipeline2 = get_pipeline()
            assert pipeline2.state.value == "running"
        finally:
            pipeline.stop()


class TestLiveDataVerification:
    """Tests for live data verification."""

    def test_live_ingestion_test(self):
        """Test live ingestion test method."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            results = pipeline.test_live_ingestion()

            assert "test_timestamp" in results
            assert "pipeline_state" in results
            assert results["pipeline_state"] == "running"

            # Check all test types passed
            tests = results["tests"]
            assert tests["log_ingestion"]["status"] == "accepted"
            assert tests["metric_ingestion"]["status"] == "accepted"
            assert tests["event_ingestion"]["status"] == "accepted"
        finally:
            pipeline.stop()

    def test_live_data_metrics(self):
        """Test that live data produces metrics."""
        pipeline = TelemetryPipeline()
        pipeline.start()

        try:
            # Run live test
            pipeline.test_live_ingestion()

            # Get metrics
            metrics = pipeline.get_metrics()

            assert "ingestion" in metrics
            assert "processing" in metrics
            assert "export" in metrics
        finally:
            pipeline.stop()
