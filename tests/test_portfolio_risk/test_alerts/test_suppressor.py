"""Tests for alert suppressor."""

from datetime import UTC, datetime, timedelta

import pytest

from portfolio_risk.alerts.suppressor import AlertSuppressor
from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertState,
    AlertType,
    RiskAlert,
)


class TestAlertSuppressor:
    """Test AlertSuppressor class."""

    def test_initialization(self):
        """Test suppressor initialization."""
        suppressor = AlertSuppressor(min_interval_seconds=300)
        assert suppressor.min_interval_seconds == 300

    def test_should_send_first_alert(self):
        """Test that first alert is allowed."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        assert suppressor.should_send(alert) is True

    def test_should_send_duplicate_within_window(self):
        """Test that duplicate within window is suppressed."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # First alert allowed
        assert suppressor.should_send(alert) is True

        # Second alert suppressed
        assert suppressor.should_send(alert) is False

    def test_should_send_after_window(self):
        """Test that alert after window is allowed."""
        suppressor = AlertSuppressor(min_interval_seconds=1)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # First alert allowed
        assert suppressor.should_send(alert) is True

        # Wait for window to pass
        import time

        time.sleep(1.1)

        # Second alert allowed after window
        assert suppressor.should_send(alert) is True

    def test_different_alert_types_not_suppressed(self):
        """Test that different alert types are not suppressed."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert1 = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        alert2 = RiskAlert(
            alert_type=AlertType.MARGIN_UTILIZATION,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # Both alerts allowed (different types)
        assert suppressor.should_send(alert1) is True
        assert suppressor.should_send(alert2) is True

    def test_different_portfolios_not_suppressed(self):
        """Test that different portfolios are not suppressed."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert1 = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="portfolio1",
        )

        alert2 = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="portfolio2",
        )

        # Both alerts allowed (different portfolios)
        assert suppressor.should_send(alert1) is True
        assert suppressor.should_send(alert2) is True

    def test_force_send(self):
        """Test force send bypasses suppression."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # First alert allowed
        assert suppressor.should_send(alert) is True

        # Force send bypasses suppression
        suppressor.force_send(alert)

        # Check state was updated
        state = suppressor.get_state("test:exposure")
        assert state is not None
        assert state.alert_count == 2

    def test_get_state(self):
        """Test getting alert state."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # No state before sending
        assert suppressor.get_state("test:exposure") is None

        # Send alert
        suppressor.should_send(alert)

        # State exists after sending
        state = suppressor.get_state("test:exposure")
        assert state is not None
        assert state.alert_count == 1

    def test_get_time_until_next_allowed(self):
        """Test getting time until next allowed alert."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # No time for unknown key
        assert suppressor.get_time_until_next_allowed("unknown") == 0.0

        # Send alert
        suppressor.should_send(alert)

        # Should have time remaining
        remaining = suppressor.get_time_until_next_allowed("test:exposure")
        assert remaining > 0
        assert remaining <= 300

    def test_reset_single_key(self):
        """Test resetting single alert key."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # Send and suppress
        suppressor.should_send(alert)
        suppressor.should_send(alert)  # Suppressed

        # Reset
        suppressor.reset("test:exposure")

        # Should be allowed again
        assert suppressor.should_send(alert) is True

    def test_reset_all(self):
        """Test resetting all alert states."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert1 = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        alert2 = RiskAlert(
            alert_type=AlertType.MARGIN_UTILIZATION,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # Send both
        suppressor.should_send(alert1)
        suppressor.should_send(alert2)

        # Reset all
        suppressor.reset()

        # Both should be allowed again
        assert suppressor.should_send(alert1) is True
        assert suppressor.should_send(alert2) is True

    def test_get_stats(self):
        """Test getting suppressor statistics."""
        suppressor = AlertSuppressor(min_interval_seconds=300)

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        # Send and suppress
        suppressor.should_send(alert)
        suppressor.should_send(alert)  # Suppressed

        stats = suppressor.get_stats()

        assert stats["min_interval_seconds"] == 300
        assert stats["tracked_alert_types"] == 1
        assert stats["total_alerts_sent"] == 1
        assert stats["total_alerts_suppressed"] == 1
        assert "test:exposure" in stats["alert_states"]
