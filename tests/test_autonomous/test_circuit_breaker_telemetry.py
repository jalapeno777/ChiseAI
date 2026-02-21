"""Telemetry-specific tests for Circuit Breaker Registry.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from autonomous_control_plane.telemetry.metrics import (
    CircuitBreakerTelemetryExporter,
    MetricPoint,
    TelemetryCollector,
)


class TestMetricPoint(unittest.TestCase):
    """Test cases for MetricPoint dataclass."""

    def test_metric_point_creation(self):
        """Test creating a MetricPoint."""
        point = MetricPoint(
            measurement="test_metric",
            tags={"service": "test"},
            fields={"value": 42},
        )

        self.assertEqual(point.measurement, "test_metric")
        self.assertEqual(point.tags, {"service": "test"})
        self.assertEqual(point.fields, {"value": 42})
        self.assertIsInstance(point.timestamp, float)

    def test_metric_point_to_influxdb(self):
        """Test converting MetricPoint to InfluxDB format."""
        point = MetricPoint(
            measurement="circuit_breaker_state",
            tags={"service_name": "redis", "state": "closed"},
            fields={"failure_count": 5, "success_count": 100},
            timestamp=1234567890.0,
        )

        influx_point = point.to_influxdb_point()

        self.assertEqual(influx_point["measurement"], "circuit_breaker_state")
        self.assertEqual(influx_point["tags"]["service_name"], "redis")
        self.assertEqual(influx_point["fields"]["failure_count"], 5)
        self.assertEqual(influx_point["time"], 1234567890000000000)


class TestTelemetryCollector(unittest.TestCase):
    """Test cases for TelemetryCollector."""

    def tearDown(self):
        """Clean up singleton."""
        TelemetryCollector._instance = None

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_singleton_pattern(self, mock_settings):
        """Test that TelemetryCollector is a singleton."""
        mock_settings.telemetry.enabled = False

        collector1 = TelemetryCollector()
        collector2 = TelemetryCollector()

        self.assertIs(collector1, collector2)

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_record_metric(self, mock_settings):
        """Test recording a metric."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100

        collector = TelemetryCollector()
        collector._buffer = []  # Reset buffer

        collector.record(
            measurement="test_metric",
            tags={"service": "test"},
            fields={"value": 42},
        )

        self.assertEqual(collector.get_buffer_size(), 1)

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_record_multiple_metrics(self, mock_settings):
        """Test recording multiple metrics."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100

        collector = TelemetryCollector()
        collector._buffer = []

        for i in range(5):
            collector.record(
                measurement="test_metric",
                tags={"service": f"test{i}"},
                fields={"value": i},
            )

        self.assertEqual(collector.get_buffer_size(), 5)

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_flush_clears_buffer(self, mock_settings):
        """Test that flush clears the buffer when InfluxDB is available."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100
        mock_settings.influxdb.bucket = "test_bucket"
        mock_settings.influxdb.org = "test_org"

        collector = TelemetryCollector()
        collector._buffer = []

        # Mock InfluxDB
        mock_write_api = MagicMock()
        mock_influxdb = MagicMock()
        mock_influxdb.write_api.return_value = mock_write_api
        collector._influxdb = mock_influxdb

        collector.record(
            measurement="test_metric",
            tags={"service": "test"},
            fields={"value": 42},
        )

        self.assertEqual(collector.get_buffer_size(), 1)
        collector.flush()
        self.assertEqual(collector.get_buffer_size(), 0)

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_record_circuit_breaker_state(self, mock_settings):
        """Test recording circuit breaker state."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100
        mock_settings.cb_telemetry_measurement = "circuit_breaker_state"

        collector = TelemetryCollector()
        collector._buffer = []

        collector.record_circuit_breaker_state(
            service_name="redis_service",
            state="closed",
            failure_count=5,
            success_count=100,
            rejection_count=2,
        )

        self.assertEqual(collector.get_buffer_size(), 1)
        point = collector._buffer[0]
        self.assertEqual(point.measurement, "circuit_breaker_state")
        self.assertEqual(point.tags["service_name"], "redis_service")
        self.assertEqual(point.tags["state"], "closed")
        self.assertEqual(point.fields["failure_count"], 5)
        self.assertEqual(point.fields["success_count"], 100)

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_start_stop(self, mock_settings):
        """Test starting and stopping the collector."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.flush_interval_seconds = 1

        collector = TelemetryCollector()

        # Start
        collector.start()
        self.assertIsNotNone(collector._flush_thread)
        self.assertTrue(collector._flush_thread.is_alive())

        # Stop
        collector.stop()
        self.assertFalse(collector._flush_thread.is_alive())

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_start_already_running(self, mock_settings):
        """Test starting when already running."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.flush_interval_seconds = 1

        collector = TelemetryCollector()

        collector.start()
        thread1 = collector._flush_thread

        # Try to start again
        collector.start()
        thread2 = collector._flush_thread

        # Should be the same thread
        self.assertIs(thread1, thread2)

        collector.stop()

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_flush_with_influxdb(self, mock_settings):
        """Test flushing metrics to InfluxDB."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100
        mock_settings.influxdb.bucket = "test_bucket"
        mock_settings.influxdb.org = "test_org"

        collector = TelemetryCollector()
        collector._buffer = []

        # Mock InfluxDB
        mock_write_api = MagicMock()
        mock_influxdb = MagicMock()
        mock_influxdb.write_api.return_value = mock_write_api
        collector._influxdb = mock_influxdb

        collector.record(
            measurement="test_metric",
            tags={"service": "test"},
            fields={"value": 42},
        )

        collector.flush()

        # Verify write was called
        mock_write_api.write.assert_called_once()

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_flush_with_influxdb_error(self, mock_settings):
        """Test handling InfluxDB flush errors."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 100
        mock_settings.influxdb.bucket = "test_bucket"
        mock_settings.influxdb.org = "test_org"

        collector = TelemetryCollector()
        collector._buffer = []

        # Mock InfluxDB that raises error
        mock_influxdb = MagicMock()
        mock_influxdb.write_api.side_effect = Exception("InfluxDB error")
        collector._influxdb = mock_influxdb

        collector.record(
            measurement="test_metric",
            tags={"service": "test"},
            fields={"value": 42},
        )

        # Should not raise exception
        collector.flush()

    @patch("autonomous_control_plane.telemetry.metrics.settings")
    def test_buffer_auto_flush_on_full(self, mock_settings):
        """Test auto-flush when buffer is full."""
        mock_settings.telemetry.enabled = False
        mock_settings.telemetry.batch_size = 3
        mock_settings.influxdb.bucket = "test_bucket"
        mock_settings.influxdb.org = "test_org"

        collector = TelemetryCollector()
        collector._buffer = []

        # Mock InfluxDB
        mock_write_api = MagicMock()
        mock_influxdb = MagicMock()
        mock_influxdb.write_api.return_value = mock_write_api
        collector._influxdb = mock_influxdb

        # Add 3 metrics (batch_size)
        for i in range(3):
            collector.record(
                measurement="test_metric",
                tags={"service": f"test{i}"},
                fields={"value": i},
            )

        # Should have auto-flushed
        mock_write_api.write.assert_called_once()
        self.assertEqual(collector.get_buffer_size(), 0)


class TestCircuitBreakerTelemetryExporter(unittest.TestCase):
    """Test cases for CircuitBreakerTelemetryExporter."""

    def tearDown(self):
        """Clean up singleton."""
        TelemetryCollector._instance = None

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_start_stop(self, mock_collector_class):
        """Test starting and stopping the exporter."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        mock_registry = MagicMock()
        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        exporter.start()
        self.assertTrue(exporter._running)
        self.assertIsNotNone(exporter._thread)

        time.sleep(0.15)  # Wait for one cycle

        exporter.stop()
        self.assertFalse(exporter._running)

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_export_metrics(self, mock_collector_class):
        """Test exporting metrics."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        # Mock registry with circuit breakers
        mock_state = MagicMock()
        mock_state.state.value = "closed"
        mock_state.metrics.failure_count = 5
        mock_state.metrics.success_count = 100
        mock_state.metrics.rejection_count = 2
        mock_state.metrics.state_transition_count = 1
        mock_state.metrics.consecutive_successes = 10
        mock_state.metrics.consecutive_failures = 0
        mock_state.half_open_calls = 0

        mock_registry = MagicMock()
        mock_registry.get_all_states.return_value = {"test_service": mock_state}

        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        exporter._export_metrics()

        # Verify metrics were recorded
        mock_collector.record_circuit_breaker_state.assert_called_once()
        call_args = mock_collector.record_circuit_breaker_state.call_args
        self.assertEqual(call_args.kwargs["service_name"], "test_service")
        self.assertEqual(call_args.kwargs["state"], "closed")

        # Verify flush was called
        mock_collector.flush.assert_called_once()

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_handles_empty_registry(self, mock_collector_class):
        """Test exporting with empty registry."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        mock_registry = MagicMock()
        mock_registry.get_all_states.return_value = {}

        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        exporter._export_metrics()

        # Should not record any metrics
        mock_collector.record_circuit_breaker_state.assert_not_called()
        # But should still flush
        mock_collector.flush.assert_called_once()

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_handles_export_error(self, mock_collector_class):
        """Test handling export errors gracefully."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        mock_registry = MagicMock()
        mock_registry.get_all_states.side_effect = Exception("Registry error")

        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        # Should not raise exception
        exporter._export_metrics()

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_start_when_already_running(self, mock_collector_class):
        """Test starting when already running."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        mock_registry = MagicMock()
        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        exporter.start()
        thread1 = exporter._thread

        exporter.start()  # Try to start again
        thread2 = exporter._thread

        # Should be the same thread
        self.assertIs(thread1, thread2)

        exporter.stop()

    @patch("autonomous_control_plane.telemetry.metrics.TelemetryCollector")
    def test_exporter_stop_when_not_running(self, mock_collector_class):
        """Test stopping when not running."""
        mock_collector = MagicMock()
        mock_collector_class.return_value = mock_collector

        mock_registry = MagicMock()
        exporter = CircuitBreakerTelemetryExporter(
            registry=mock_registry,
            flush_interval_seconds=0.1,
        )

        # Should not raise exception
        exporter.stop()


if __name__ == "__main__":
    unittest.main()
