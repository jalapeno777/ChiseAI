"""Tests for risk alert types."""

from datetime import UTC, datetime

import pytest

from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertState,
    AlertThresholds,
    AlertType,
    RiskAlert,
)


class TestAlertSeverity:
    """Test AlertSeverity enum."""

    def test_enum_values(self):
        """Test alert severity enum values."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.EMERGENCY.value == "emergency"

    def test_enum_str(self):
        """Test string representation."""
        assert str(AlertSeverity.INFO) == "info"
        assert str(AlertSeverity.WARNING) == "warning"


class TestAlertType:
    """Test AlertType enum."""

    def test_enum_values(self):
        """Test alert type enum values."""
        assert AlertType.EXPOSURE.value == "exposure"
        assert AlertType.MARGIN_UTILIZATION.value == "margin_utilization"
        assert AlertType.CONCENTRATION.value == "concentration"
        assert AlertType.KILL_SWITCH.value == "kill_switch"
        assert AlertType.POSITION_COUNT.value == "position_count"

    def test_enum_str(self):
        """Test string representation."""
        assert str(AlertType.EXPOSURE) == "exposure"
        assert str(AlertType.KILL_SWITCH) == "kill_switch"


class TestRiskAlert:
    """Test RiskAlert dataclass."""

    def test_basic_creation(self):
        """Test basic alert creation."""
        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test alert",
            threshold=80.0,
            current_value=85.0,
        )

        assert alert.alert_type == AlertType.EXPOSURE
        assert alert.severity == AlertSeverity.WARNING
        assert alert.message == "Test alert"
        assert alert.threshold == 80.0
        assert alert.current_value == 85.0
        assert alert.portfolio_id == "default"
        assert alert.timestamp is not None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        alert = RiskAlert(
            alert_type=AlertType.MARGIN_UTILIZATION,
            severity=AlertSeverity.CRITICAL,
            message="Margin high",
            threshold=80.0,
            current_value=90.0,
            portfolio_id="test_portfolio",
            timestamp=ts,
            metadata={"extra": "data"},
        )

        d = alert.to_dict()

        assert d["alert_type"] == "margin_utilization"
        assert d["severity"] == "critical"
        assert d["message"] == "Margin high"
        assert d["threshold"] == 80.0
        assert d["current_value"] == 90.0
        assert d["portfolio_id"] == "test_portfolio"
        assert d["timestamp"] == ts.isoformat()
        assert d["metadata"] == {"extra": "data"}

    def test_alert_key(self):
        """Test alert key generation."""
        alert = RiskAlert(
            alert_type=AlertType.CONCENTRATION,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=50.0,
            current_value=60.0,
            portfolio_id="my_portfolio",
        )

        assert alert.alert_key == "my_portfolio:concentration"


class TestAlertThresholds:
    """Test AlertThresholds dataclass."""

    def test_default_values(self):
        """Test default threshold values."""
        thresholds = AlertThresholds()

        assert thresholds.exposure_threshold_pct == 80.0
        assert thresholds.margin_utilization_threshold_pct == 80.0
        assert thresholds.concentration_threshold_pct == 50.0
        assert thresholds.min_alert_interval_seconds == 300

    def test_custom_values(self):
        """Test custom threshold values."""
        thresholds = AlertThresholds(
            exposure_threshold_pct=70.0,
            margin_utilization_threshold_pct=75.0,
            concentration_threshold_pct=40.0,
            min_alert_interval_seconds=600,
        )

        assert thresholds.exposure_threshold_pct == 70.0
        assert thresholds.margin_utilization_threshold_pct == 75.0
        assert thresholds.concentration_threshold_pct == 40.0
        assert thresholds.min_alert_interval_seconds == 600

    def test_to_dict(self):
        """Test conversion to dictionary."""
        thresholds = AlertThresholds()
        d = thresholds.to_dict()

        assert d["exposure_threshold_pct"] == 80.0
        assert d["margin_utilization_threshold_pct"] == 80.0
        assert d["concentration_threshold_pct"] == 50.0
        assert d["min_alert_interval_seconds"] == 300


class TestAlertState:
    """Test AlertState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = AlertState()

        assert state.last_alert_time is None
        assert state.alert_count == 0
        assert state.suppressed_count == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = AlertState(
            last_alert_time=ts,
            alert_count=5,
            suppressed_count=3,
        )

        d = state.to_dict()

        assert d["last_alert_time"] == ts.isoformat()
        assert d["alert_count"] == 5
        assert d["suppressed_count"] == 3

    def test_to_dict_no_timestamp(self):
        """Test to_dict with no timestamp."""
        state = AlertState()
        d = state.to_dict()

        assert d["last_alert_time"] is None
