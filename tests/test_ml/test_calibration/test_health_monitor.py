"""Unit tests for Calibration Health Monitor.

Tests for CalibrationHealthMonitor including ECE monitoring,
alerts, and stability scoring.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, "src")

from ml.calibration.controller import ThresholdController, ThresholdMode
from ml.calibration.data_collector import CalibrationDataCollector
from ml.calibration.dynamic import DynamicThresholdAdjuster, ThresholdAdjustment
from ml.calibration.health_monitor import (
    ECE_ALERT_THRESHOLD,
    ECE_CRITICAL_THRESHOLD,
    AdjustmentFrequencyMetrics,
    CalibrationAlert,
    CalibrationHealthMonitor,
    CalibrationStatus,
)
from ml.calibration.optimizer import ThresholdOptimizer
from ml.calibration.storage import InMemoryCalibrationStorage
from ml.calibration.telemetry_exporter import CalibrationHealthMetrics


class TestCalibrationAlert:
    """Tests for CalibrationAlert dataclass."""

    def test_creation(self):
        """Test creating an alert."""
        alert = CalibrationAlert(
            timestamp=datetime.now(UTC),
            signal_type="LONG",
            alert_type="ece_high",
            severity="warning",
            message="ECE is high: 0.18",
            ece_value=0.18,
            threshold=0.65,
        )

        assert alert.signal_type == "LONG"
        assert alert.alert_type == "ece_high"
        assert alert.severity == "warning"
        assert alert.ece_value == 0.18

    def test_to_dict(self):
        """Test converting to dictionary."""
        alert = CalibrationAlert(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            signal_type="SHORT",
            alert_type="adjustment_spike",
            severity="critical",
            message="Too many adjustments",
            ece_value=0.20,
            threshold=0.70,
        )

        d = alert.to_dict()

        assert d["signal_type"] == "SHORT"
        assert d["alert_type"] == "adjustment_spike"
        assert d["severity"] == "critical"
        assert d["ece_value"] == 0.20


class TestAdjustmentFrequencyMetrics:
    """Tests for AdjustmentFrequencyMetrics dataclass."""

    def test_creation(self):
        """Test creating metrics."""
        metrics = AdjustmentFrequencyMetrics(
            signal_type="LONG",
            adjustments_1h=2,
            adjustments_6h=5,
            adjustments_24h=12,
            avg_adjustment_size=0.045,
            max_adjustment_size=0.08,
        )

        assert metrics.signal_type == "LONG"
        assert metrics.adjustments_1h == 2
        assert metrics.adjustments_24h == 12

    def test_to_dict(self):
        """Test converting to dictionary."""
        metrics = AdjustmentFrequencyMetrics(
            signal_type="SCALP",
            adjustments_1h=1,
            adjustments_6h=3,
            adjustments_24h=8,
            avg_adjustment_size=0.0321,
            max_adjustment_size=0.0654,
        )

        d = metrics.to_dict()

        assert d["signal_type"] == "SCALP"
        assert d["adjustments_1h"] == 1
        assert d["avg_adjustment_size"] == 0.0321


class TestCalibrationHealthMonitor:
    """Tests for CalibrationHealthMonitor class."""

    @pytest.fixture
    def controller_with_data(self):
        """Create controller with ECE data."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)

        # Add calibration records
        for i in range(100):
            collector.collect(
                signal_id=f"sig-LONG-{i:04d}",
                predicted_prob=0.4 + (i / 200),
                actual_outcome=1 if i % 2 == 0 else 0,
                signal_type="LONG",
            )

        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        # Set ECE values
        controller._last_ece["LONG"] = 0.12
        controller._last_ece["SHORT"] = 0.18
        controller._last_ece["SCALP"] = 0.08

        return controller

    @pytest.fixture
    def adjuster_with_history(self, controller_with_data):
        """Create adjuster with adjustment history."""
        adjuster = DynamicThresholdAdjuster(controller_with_data)

        now = datetime.now(UTC)
        # Add adjustment history
        for i in range(5):
            adjuster._adjustment_history.append(
                ThresholdAdjustment(
                    timestamp=now - timedelta(hours=i),
                    signal_type="LONG",
                    old_threshold=0.60 + (i * 0.01),
                    new_threshold=0.61 + (i * 0.01),
                    change_amount=0.01,
                    ece_before=0.15,
                    ece_after=None,
                    reason="Test adjustment",
                )
            )

        return adjuster

    @pytest.fixture
    def monitor(self, controller_with_data, adjuster_with_history):
        """Create health monitor."""
        return CalibrationHealthMonitor(
            controller=controller_with_data,
            adjuster=adjuster_with_history,
            enable_alerts=True,
        )

    def test_initialization(self, controller_with_data):
        """Test monitor initialization."""
        monitor = CalibrationHealthMonitor(controller_with_data)

        assert monitor.controller is controller_with_data
        assert monitor.adjuster is None
        assert monitor.ece_alert_threshold == ECE_ALERT_THRESHOLD
        assert monitor.ece_critical_threshold == ECE_CRITICAL_THRESHOLD
        assert monitor.enable_alerts is True

    def test_check_health_well_calibrated(self, monitor):
        """Test health check for well calibrated signal."""
        # Set SCALP to have ECE of 0.04 (well calibrated, below half threshold)
        monitor.controller._last_ece["SCALP"] = 0.04
        metrics = monitor.check_health("SCALP")

        assert isinstance(metrics, CalibrationHealthMetrics)
        assert metrics.signal_type == "SCALP"
        assert metrics.ece == 0.04
        assert metrics.health_status == CalibrationStatus.WELL_CALIBRATED

    def test_check_health_poorly_calibrated(self, monitor):
        """Test health check for poorly calibrated signal."""
        # SHORT has ECE of 0.18 (above alert threshold)
        metrics = monitor.check_health("SHORT")

        assert metrics.signal_type == "SHORT"
        assert metrics.ece == 0.18
        assert metrics.health_status == CalibrationStatus.POORLY_CALIBRATED

    def test_check_health_all(self, monitor):
        """Test health check for all signal types."""
        all_metrics = monitor.check_health_all()

        assert "LONG" in all_metrics
        assert "SHORT" in all_metrics
        assert "SCALP" in all_metrics

        for st, metrics in all_metrics.items():
            assert isinstance(metrics, CalibrationHealthMetrics)
            assert metrics.signal_type == st

    def test_determine_health_status_well(self, monitor):
        """Test health status determination for good calibration."""
        status = monitor._determine_health_status(0.05)
        assert status == CalibrationStatus.WELL_CALIBRATED

    def test_determine_health_status_acceptable(self, monitor):
        """Test health status determination for acceptable calibration."""
        status = monitor._determine_health_status(0.10)
        assert status == CalibrationStatus.ACCEPTABLE

    def test_determine_health_status_poor(self, monitor):
        """Test health status determination for poor calibration."""
        status = monitor._determine_health_status(0.18)
        assert status == CalibrationStatus.POORLY_CALIBRATED

    def test_determine_health_status_critical(self, monitor):
        """Test health status determination for critical calibration."""
        status = monitor._determine_health_status(0.28)
        assert status == CalibrationStatus.CRITICAL

    def test_determine_health_status_none(self, monitor):
        """Test health status determination with no data."""
        status = monitor._determine_health_status(None)
        assert status == CalibrationStatus.POORLY_CALIBRATED

    def test_calculate_adjustment_counts(self, monitor):
        """Test adjustment count calculation."""
        counts = monitor._calculate_adjustment_counts("LONG")

        assert "1h" in counts
        assert "6h" in counts
        assert "24h" in counts

    def test_calculate_stability_score_with_data(self, monitor):
        """Test stability score calculation with ECE history."""
        # Add some ECE history
        now = datetime.now(UTC)
        monitor._ece_history["LONG"] = [
            (now - timedelta(hours=i), 0.10 + (i * 0.01)) for i in range(10)
        ]

        score = monitor._calculate_stability_score("LONG", 0.15)

        assert 0 <= score <= 100
        assert score > 0  # Should have some score with variance

    def test_calculate_stability_score_no_data(self, monitor):
        """Test stability score calculation without data."""
        score = monitor._calculate_stability_score("LONG", None)

        assert score == 100.0  # Worst score when no data

    def test_calculate_stability_score_no_history(self, monitor):
        """Test stability score with current ECE but no history."""
        score = monitor._calculate_stability_score("LONG", 0.20)

        # Should have ECE component (40 * 0.20 * 160 / something)
        assert score > 0


class TestCalibrationHealthMonitorAlerts:
    """Tests for alert functionality."""

    @pytest.fixture
    def monitor_with_alerts(self):
        """Create monitor with alert conditions."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        adjuster = DynamicThresholdAdjuster(controller)
        now = datetime.now(UTC)

        # Add many recent adjustments to trigger spike alert
        for i in range(5):
            adjuster._adjustment_history.append(
                ThresholdAdjustment(
                    timestamp=now - timedelta(minutes=i * 10),
                    signal_type="LONG",
                    old_threshold=0.60,
                    new_threshold=0.65,
                    change_amount=0.05,
                    ece_before=0.18,
                    ece_after=None,
                    reason="Test",
                )
            )

        controller._last_ece["LONG"] = 0.20  # Above alert threshold
        controller._last_ece["SHORT"] = 0.30  # Above critical threshold

        monitor = CalibrationHealthMonitor(
            controller=controller,
            adjuster=adjuster,
            enable_alerts=True,
        )

        return monitor

    def test_check_alerts_high_ece(self, monitor_with_alerts):
        """Test alert generation for high ECE."""
        # This should trigger a warning alert
        monitor_with_alerts.check_health("LONG")

        alerts = monitor_with_alerts.get_active_alerts()
        assert len(alerts) > 0

        ece_alerts = [a for a in alerts if a.alert_type == "ece_high"]
        assert len(ece_alerts) > 0

    def test_check_alerts_critical_ece(self, monitor_with_alerts):
        """Test alert generation for critical ECE."""
        monitor_with_alerts.check_health("SHORT")

        alerts = monitor_with_alerts.get_active_alerts()

        critical_alerts = [a for a in alerts if a.alert_type == "ece_critical"]
        assert len(critical_alerts) > 0
        assert critical_alerts[0].severity == "critical"

    def test_check_alerts_adjustment_spike(self, monitor_with_alerts):
        """Test alert generation for adjustment spike."""
        monitor_with_alerts.check_health("LONG")

        alerts = monitor_with_alerts.get_active_alerts()

        spike_alerts = [a for a in alerts if a.alert_type == "adjustment_spike"]
        assert len(spike_alerts) > 0

    def test_get_active_alerts_filtered(self, monitor_with_alerts):
        """Test filtering active alerts."""
        monitor_with_alerts.check_health("LONG")
        monitor_with_alerts.check_health("SHORT")

        # Filter by signal type
        long_alerts = monitor_with_alerts.get_active_alerts(signal_type="LONG")
        for alert in long_alerts:
            assert alert.signal_type == "LONG"

        # Filter by severity
        critical_alerts = monitor_with_alerts.get_active_alerts(severity="critical")
        for alert in critical_alerts:
            assert alert.severity == "critical"

    def test_clear_all_alerts(self, monitor_with_alerts):
        """Test clearing all alerts."""
        monitor_with_alerts.check_health("LONG")

        count = monitor_with_alerts.clear_alerts()

        assert count > 0
        assert len(monitor_with_alerts.get_active_alerts()) == 0

    def test_clear_alerts_by_signal(self, monitor_with_alerts):
        """Test clearing alerts for specific signal."""
        monitor_with_alerts.check_health("LONG")
        monitor_with_alerts.check_health("SHORT")

        count = monitor_with_alerts.clear_alerts(signal_type="LONG")

        assert count > 0
        # Should still have SHORT alerts
        short_alerts = monitor_with_alerts.get_active_alerts(signal_type="SHORT")
        assert len(short_alerts) > 0

    def test_duplicate_alert_prevention(self, monitor_with_alerts):
        """Test that duplicate alerts are not created."""
        # Check health twice in quick succession
        monitor_with_alerts.check_health("LONG")
        monitor_with_alerts.check_health("LONG")

        # Should not have duplicate alerts
        alerts = monitor_with_alerts.get_active_alerts()
        ece_alerts = [a for a in alerts if a.alert_type == "ece_high"]

        # Should only have one ece_high alert per signal
        long_ece_alerts = [a for a in ece_alerts if a.signal_type == "LONG"]
        assert len(long_ece_alerts) <= 1


class TestAdjustmentFrequencyMetricsCalculation:
    """Tests for adjustment frequency metrics calculation."""

    @pytest.fixture
    def monitor_with_adjuster(self):
        """Create monitor with adjuster having history."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        adjuster = DynamicThresholdAdjuster(controller)
        now = datetime.now(UTC)

        # Add adjustment history with varying sizes
        adjustments = [
            (now - timedelta(minutes=10), 0.05),
            (now - timedelta(minutes=20), 0.03),
            (now - timedelta(minutes=30), 0.08),
            (now - timedelta(hours=2), 0.04),
            (now - timedelta(hours=5), 0.02),
        ]

        for ts, size in adjustments:
            adjuster._adjustment_history.append(
                ThresholdAdjustment(
                    timestamp=ts,
                    signal_type="LONG",
                    old_threshold=0.60,
                    new_threshold=0.60 + size,
                    change_amount=size,
                    ece_before=0.15,
                    ece_after=None,
                    reason="Test",
                )
            )

        monitor = CalibrationHealthMonitor(
            controller=controller,
            adjuster=adjuster,
        )

        return monitor

    def test_get_adjustment_frequency_metrics(self, monitor_with_adjuster):
        """Test adjustment frequency metrics calculation."""
        metrics = monitor_with_adjuster.get_adjustment_frequency_metrics("LONG")

        assert isinstance(metrics, AdjustmentFrequencyMetrics)
        assert metrics.signal_type == "LONG"
        assert metrics.adjustments_1h == 3  # Last 3 are within 1 hour
        assert metrics.adjustments_24h == 5  # All within 24 hours
        assert metrics.avg_adjustment_size > 0
        assert metrics.max_adjustment_size == 0.08

    def test_get_adjustment_frequency_no_adjuster(self):
        """Test metrics when no adjuster is configured."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)

        monitor = CalibrationHealthMonitor(controller=controller, adjuster=None)

        metrics = monitor.get_adjustment_frequency_metrics("LONG")

        assert metrics.signal_type == "LONG"
        assert metrics.adjustments_1h == 0
        assert metrics.adjustments_24h == 0


class TestHealthSummary:
    """Tests for health summary functionality."""

    def test_get_health_summary(self):
        """Test getting overall health summary."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)

        # Set varying ECE values
        controller._last_ece["LONG"] = 0.12  # Acceptable
        controller._last_ece["SHORT"] = 0.08  # Well calibrated
        controller._last_ece["SCALP"] = 0.20  # Poorly calibrated

        monitor = CalibrationHealthMonitor(controller=controller)

        summary = monitor.get_health_summary()

        assert "overall_status" in summary
        assert "active_alerts" in summary
        assert "signal_health" in summary

        # Overall should be worst status
        assert summary["overall_status"] == CalibrationStatus.POORLY_CALIBRATED

        # Each signal should have health info
        for st in ["LONG", "SHORT", "SCALP"]:
            assert st in summary["signal_health"]
            health = summary["signal_health"][st]
            assert "status" in health
            assert "ece" in health
            assert "threshold" in health
            assert "stability_score" in health


class TestInfluxDBExport:
    """Tests for InfluxDB export functionality."""

    @pytest.mark.asyncio
    async def test_export_health_metrics(self):
        """Test exporting health metrics to InfluxDB."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)
        controller._last_ece["LONG"] = 0.12

        monitor = CalibrationHealthMonitor(controller=controller)

        # Create mock exporter
        mock_exporter = AsyncMock()

        result = await monitor.export_health_metrics(mock_exporter)

        assert result is True
        # Should have called export_health_status 3 times (once per signal type)
        assert mock_exporter.export_health_status.call_count == 3

    @pytest.mark.asyncio
    async def test_export_health_metrics_specific_signal(self):
        """Test exporting health metrics for specific signal."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)
        controller._last_ece["LONG"] = 0.12

        monitor = CalibrationHealthMonitor(controller=controller)

        mock_exporter = AsyncMock()

        result = await monitor.export_health_metrics(mock_exporter, signal_type="LONG")

        assert result is True
        assert mock_exporter.export_health_status.call_count == 1

    @pytest.mark.asyncio
    async def test_export_health_metrics_failure(self):
        """Test handling export failure."""
        storage = InMemoryCalibrationStorage()
        collector = CalibrationDataCollector(storage=storage)
        optimizer = ThresholdOptimizer(collector)
        controller = ThresholdController(optimizer)

        monitor = CalibrationHealthMonitor(controller=controller)

        # Create exporter that raises exception
        mock_exporter = AsyncMock()
        mock_exporter.export_health_status.side_effect = Exception("Export failed")

        result = await monitor.export_health_metrics(mock_exporter)

        assert result is False


class TestHealthMonitorConstants:
    """Tests for health monitor constants."""

    def test_ece_alert_threshold(self):
        """Test ECE alert threshold constant."""
        assert ECE_ALERT_THRESHOLD == 0.15

    def test_ece_critical_threshold(self):
        """Test ECE critical threshold constant."""
        assert ECE_CRITICAL_THRESHOLD == 0.25

    def test_calibration_status_values(self):
        """Test calibration status values."""
        assert CalibrationStatus.WELL_CALIBRATED == "well_calibrated"
        assert CalibrationStatus.ACCEPTABLE == "acceptable"
        assert CalibrationStatus.POORLY_CALIBRATED == "poorly_calibrated"
        assert CalibrationStatus.CRITICAL == "critical"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
