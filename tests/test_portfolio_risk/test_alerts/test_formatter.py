"""Tests for alert formatter."""

from datetime import UTC, datetime

import pytest

from portfolio_risk.alerts.formatter import RiskAlertFormatter
from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertType,
    RiskAlert,
)


class TestRiskAlertFormatter:
    """Test RiskAlertFormatter class."""

    def test_initialization(self):
        """Test formatter initialization."""
        formatter = RiskAlertFormatter()
        assert formatter is not None

    def test_format_alert_exposure(self):
        """Test formatting exposure alert."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Exposure threshold exceeded",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)

        assert "content" in formatted
        assert "embeds" in formatted
        assert len(formatted["embeds"]) == 1

        # Check content
        assert "test_portfolio" in formatted["content"]
        assert "📊" in formatted["content"]

        # Check embed
        embed = formatted["embeds"][0]
        assert "Exposure" in embed["title"]
        assert "Exposure threshold exceeded" in embed["description"]
        assert embed["color"] == 0xF39C12  # Warning color

    def test_format_alert_margin(self):
        """Test formatting margin utilization alert."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.MARGIN_UTILIZATION,
            severity=AlertSeverity.CRITICAL,
            message="Margin utilization critical",
            threshold=80.0,
            current_value=90.0,
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)

        embed = formatted["embeds"][0]
        assert "Margin Utilization" in embed["title"]
        assert embed["color"] == 0xE74C3C  # Critical color

    def test_format_alert_kill_switch(self):
        """Test formatting kill-switch alert."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.KILL_SWITCH,
            severity=AlertSeverity.EMERGENCY,
            message="KILL SWITCH ACTIVATED",
            threshold=95.0,
            current_value=97.0,
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)

        # Check content has kill switch messaging
        assert "KILL SWITCH" in formatted["content"]

        embed = formatted["embeds"][0]
        assert embed["color"] == 0x8E44AD  # Emergency color

    def test_format_alert_info_severity(self):
        """Test formatting info severity alert."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.CONCENTRATION,
            severity=AlertSeverity.INFO,
            message="Concentration info",
            threshold=50.0,
            current_value=52.0,
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)

        embed = formatted["embeds"][0]
        assert embed["color"] == 0x3498DB  # Info color

    def test_embed_fields(self):
        """Test that embed has correct fields."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test message",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)
        embed = formatted["embeds"][0]

        # Check fields
        field_names = [f["name"] for f in embed["fields"]]
        assert "Threshold" in field_names
        assert "Current Value" in field_names
        assert "Severity" in field_names

        # Check field values
        threshold_field = next(f for f in embed["fields"] if f["name"] == "Threshold")
        assert "80.00%" in threshold_field["value"]

    def test_breach_amount_field(self):
        """Test breach amount field when over threshold."""
        formatter = RiskAlertFormatter()

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test message",
            threshold=80.0,
            current_value=90.0,  # 12.5% over threshold
            portfolio_id="test_portfolio",
        )

        formatted = formatter.format_alert(alert)
        embed = formatted["embeds"][0]

        field_names = [f["name"] for f in embed["fields"]]
        assert "Breach Amount" in field_names

        breach_field = next(f for f in embed["fields"] if f["name"] == "Breach Amount")
        assert "+12.5%" in breach_field["value"]

    def test_format_simple_message(self):
        """Test simple message formatting."""
        formatter = RiskAlertFormatter()

        message = formatter.format_simple_message(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test message",
            threshold=80.0,
            current_value=85.0,
        )

        assert "Exposure" in message
        assert "Test message" in message
        assert "80.00%" in message
        assert "85.00%" in message

    def test_format_alert_type_names(self):
        """Test alert type name formatting."""
        formatter = RiskAlertFormatter()

        assert formatter._format_alert_type(AlertType.EXPOSURE) == "Exposure"
        assert (
            formatter._format_alert_type(AlertType.MARGIN_UTILIZATION)
            == "Margin Utilization"
        )
        assert formatter._format_alert_type(AlertType.CONCENTRATION) == "Concentration"
        assert formatter._format_alert_type(AlertType.KILL_SWITCH) == "Kill Switch"
        assert (
            formatter._format_alert_type(AlertType.POSITION_COUNT) == "Position Count"
        )
