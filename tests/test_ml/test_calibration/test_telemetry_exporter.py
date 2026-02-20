"""Unit tests for Calibration Telemetry Exporter.

Tests for CalibrationTelemetryExporter, CalibrationTelemetryConfig,
and CalibrationHealthMetrics.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

from ml.calibration.controller import ThresholdController, ThresholdMode
from ml.calibration.data_collector import CalibrationDataCollector
from ml.calibration.optimizer import ThresholdOptimizer
from ml.calibration.storage import InMemoryCalibrationStorage
from ml.calibration.telemetry_exporter import (
    CalibrationHealthMetrics,
    CalibrationTelemetryConfig,
    CalibrationTelemetryExporter,
)


@pytest.fixture
def mock_influxdb_client():
    """Create a mock InfluxDB client."""
    client = MagicMock()
    write_api = MagicMock()
    client.write_api.return_value = write_api
    return client


@pytest.fixture
def mock_influxdb_point():
    """Mock InfluxDB Point class."""
    with patch("influxdb_client.Point") as MockPoint:
        point_instance = MagicMock()
        point_instance.tag.return_value = point_instance
        point_instance.field.return_value = point_instance
        point_instance.time.return_value = point_instance
        MockPoint.return_value = point_instance
        yield MockPoint


class TestCalibrationTelemetryConfig:
    """Tests for CalibrationTelemetryConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CalibrationTelemetryConfig()

        assert config.bucket == "chiseai"
        assert config.org == "chiseai"
        assert config.measurement_prefix == "calibration"
        assert config.retention_days == 90
        assert config.batch_size == 100
        assert config.flush_interval == 60.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CalibrationTelemetryConfig(
            bucket="test-bucket",
            org="test-org",
            measurement_prefix="test",
            retention_days=30,
            batch_size=50,
            flush_interval=30.0,
        )

        assert config.bucket == "test-bucket"
        assert config.org == "test-org"
        assert config.measurement_prefix == "test"
        assert config.retention_days == 30
        assert config.batch_size == 50
        assert config.flush_interval == 30.0


class TestCalibrationHealthMetrics:
    """Tests for CalibrationHealthMetrics."""

    def test_creation(self):
        """Test creating health metrics."""
        timestamp = datetime.now(UTC)
        metrics = CalibrationHealthMetrics(
            timestamp=timestamp,
            signal_type="LONG",
            ece=0.12,
            threshold=0.65,
            health_status="well_calibrated",
            adjustment_count_1h=1,
            adjustment_count_24h=5,
            stability_score=25.0,
        )

        assert metrics.signal_type == "LONG"
        assert metrics.ece == 0.12
        assert metrics.threshold == 0.65
        assert metrics.health_status == "well_calibrated"
        assert metrics.adjustment_count_1h == 1
        assert metrics.adjustment_count_24h == 5
        assert metrics.stability_score == 25.0

    def test_to_dict(self):
        """Test converting to dictionary."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        metrics = CalibrationHealthMetrics(
            timestamp=timestamp,
            signal_type="SHORT",
            ece=0.123456,
            threshold=0.6543,
            health_status="poorly_calibrated",
            adjustment_count_1h=2,
            adjustment_count_24h=10,
            stability_score=75.5,
        )

        d = metrics.to_dict()

        assert d["signal_type"] == "SHORT"
        assert d["ece"] == 0.123456
        assert d["threshold"] == 0.6543
        assert d["health_status"] == "poorly_calibrated"
        assert d["adjustment_count_1h"] == 2
        assert d["adjustment_count_24h"] == 10
        assert d["stability_score"] == 75.5


class TestCalibrationTelemetryExporter:
    """Tests for CalibrationTelemetryExporter."""

    @pytest.fixture
    def exporter(self, mock_influxdb_client):
        """Create exporter with mock client."""
        return CalibrationTelemetryExporter(influxdb_client=mock_influxdb_client)

    @pytest.fixture
    def controller_with_data(self):
        """Create a controller with mock data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        # Add some calibration records
        for i in range(50):
            collector.collect(
                signal_id=f"sig-LONG-{i:04d}",
                predicted_prob=0.5 + (i / 100),
                actual_outcome=1 if i % 2 == 0 else 0,
                signal_type="LONG",
            )

        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        # Set some ECE values
        controller._last_ece["LONG"] = 0.12
        controller._last_ece["SHORT"] = 0.18
        controller._last_ece["SCALP"] = 0.08

        return controller

    def test_initialization(self, mock_influxdb_client):
        """Test exporter initialization."""
        exporter = CalibrationTelemetryExporter(influxdb_client=mock_influxdb_client)

        assert exporter._client is mock_influxdb_client
        assert exporter.config.bucket == "chiseai"
        assert exporter.config.org == "chiseai"
        assert exporter._export_count == 0
        assert exporter._failed_exports == 0

    def test_initialization_no_client(self):
        """Test exporter initialization without client."""
        exporter = CalibrationTelemetryExporter(influxdb_client=None)

        assert exporter._client is None
        assert exporter._write_api is None

    @pytest.mark.asyncio
    async def test_get_write_api(self, exporter, mock_influxdb_client):
        """Test getting write API."""
        write_api = await exporter._get_write_api()

        assert write_api is not None
        mock_influxdb_client.write_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_write_api_no_client(self):
        """Test getting write API without client."""
        exporter = CalibrationTelemetryExporter(influxdb_client=None)
        write_api = await exporter._get_write_api()

        assert write_api is None

    @pytest.mark.asyncio
    async def test_export_thresholds(
        self, exporter, controller_with_data, mock_influxdb_point
    ):
        """Test exporting thresholds."""
        result = await exporter.export_thresholds(controller_with_data)

        assert result is True
        # Should create 3 points (one per signal type)
        assert mock_influxdb_point.call_count == 3

    @pytest.mark.asyncio
    async def test_export_thresholds_no_client(self, controller_with_data):
        """Test exporting thresholds without client."""
        exporter = CalibrationTelemetryExporter(influxdb_client=None)
        result = await exporter.export_thresholds(controller_with_data)

        # Returns True - export succeeded (points queued but not yet written)
        assert result is True

    @pytest.mark.asyncio
    async def test_export_with_exception(self, controller_with_data):
        """Test handling of general exception."""
        mock_client = MagicMock()
        mock_client.write_api.side_effect = Exception("Write failed")

        exporter = CalibrationTelemetryExporter(influxdb_client=mock_client)

        with patch("influxdb_client.Point") as MockPoint:
            point_instance = MagicMock()
            point_instance.tag.return_value = point_instance
            point_instance.field.return_value = point_instance
            point_instance.time.return_value = point_instance
            MockPoint.return_value = point_instance

            result = await exporter.export_thresholds(controller_with_data)

            # Should return True because points are queued, not written yet
            assert result is True

    @pytest.mark.asyncio
    async def test_flush_with_exception(self):
        """Test flush with write exception."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_write_api.write.side_effect = Exception("Write failed")
        mock_client.write_api.return_value = mock_write_api

        exporter = CalibrationTelemetryExporter(influxdb_client=mock_client)
        exporter._batch = [MagicMock()]

        result = await exporter.flush()

        # Returns False because flush failed
        assert result is False
        assert exporter._failed_exports == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
