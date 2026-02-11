"""Tests for alert sender."""

import pytest

from portfolio_risk.alerts.sender import RiskAlertSender, RiskAlertSendResult
from portfolio_risk.alerts.types import (
    AlertSeverity,
    AlertType,
    RiskAlert,
)


class TestRiskAlertSendResult:
    """Test RiskAlertSendResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = RiskAlertSendResult(
            success=True,
            alert_type="exposure",
        )

        assert result.success is True
        assert result.alert_type == "exposure"
        assert result.suppressed is False
        assert result.error is None

    def test_full_creation(self):
        """Test result with all fields."""
        result = RiskAlertSendResult(
            success=False,
            alert_type="margin",
            suppressed=True,
            error="Rate limited",
            latency_ms=150.5,
            retries=2,
        )

        assert result.success is False
        assert result.alert_type == "margin"
        assert result.suppressed is True
        assert result.error == "Rate limited"
        assert result.latency_ms == 150.5
        assert result.retries == 2


class TestRiskAlertSender:
    """Test RiskAlertSender class."""

    def test_initialization_no_webhook(self):
        """Test initialization without webhook."""
        sender = RiskAlertSender()

        assert sender.webhook_url is None
        assert sender.max_retries == 3

    def test_initialization_with_webhook(self):
        """Test initialization with webhook."""
        sender = RiskAlertSender(webhook_url="https://discord.com/webhook")

        assert sender.webhook_url == "https://discord.com/webhook"

    def test_initialization_custom_retries(self):
        """Test initialization with custom retries."""
        sender = RiskAlertSender(max_retries=5)

        assert sender.max_retries == 5

    def test_get_suppressor(self):
        """Test getting suppressor."""
        sender = RiskAlertSender()
        suppressor = sender._get_suppressor()

        assert suppressor is not None
        assert suppressor.min_interval_seconds == 300

    def test_get_formatter(self):
        """Test getting formatter."""
        sender = RiskAlertSender()
        formatter = sender._get_formatter()

        assert formatter is not None

    def test_get_suppressor_stats(self):
        """Test getting suppressor stats."""
        sender = RiskAlertSender()
        stats = sender.get_suppressor_stats()

        assert "min_interval_seconds" in stats
        assert "tracked_alert_types" in stats
        assert stats["tracked_alert_types"] == 0

    @pytest.mark.asyncio
    async def test_health_check_no_webhook(self):
        """Test health check without webhook."""
        sender = RiskAlertSender()
        health = await sender.health_check()

        assert health["healthy"] is False
        assert health["webhook_configured"] is False
        assert "No webhook URL configured" in health["error"]

    @pytest.mark.asyncio
    async def test_health_check_with_webhook(self):
        """Test health check with webhook (no actual connection)."""
        sender = RiskAlertSender(webhook_url="https://example.com/webhook")
        health = await sender.health_check()

        # Will fail because webhook is invalid, but shows it's configured
        assert health["webhook_configured"] is True

    @pytest.mark.asyncio
    async def test_send_alert_no_webhook(self):
        """Test sending alert without webhook configured."""
        sender = RiskAlertSender()

        alert = RiskAlert(
            alert_type=AlertType.EXPOSURE,
            severity=AlertSeverity.WARNING,
            message="Test",
            threshold=80.0,
            current_value=85.0,
            portfolio_id="test",
        )

        result = await sender.send_alert(alert)

        assert result.success is False
        assert "No webhook URL configured" in result.error

    @pytest.mark.asyncio
    async def test_send_kill_switch_alert(self):
        """Test sending kill-switch alert."""
        sender = RiskAlertSender()

        alert = RiskAlert(
            alert_type=AlertType.KILL_SWITCH,
            severity=AlertSeverity.EMERGENCY,
            message="KILL SWITCH",
            threshold=95.0,
            current_value=97.0,
            portfolio_id="test",
        )

        # Will fail due to no webhook, but tests the method path
        result = await sender.send_kill_switch_alert(alert)

        # Kill-switch alerts bypass suppression
        assert result.suppressed is False

    @pytest.mark.asyncio
    async def test_send_alerts_multiple(self):
        """Test sending multiple alerts."""
        sender = RiskAlertSender()

        alerts = [
            RiskAlert(
                alert_type=AlertType.EXPOSURE,
                severity=AlertSeverity.WARNING,
                message="Test 1",
                threshold=80.0,
                current_value=85.0,
                portfolio_id="test",
            ),
            RiskAlert(
                alert_type=AlertType.MARGIN_UTILIZATION,
                severity=AlertSeverity.CRITICAL,
                message="Test 2",
                threshold=80.0,
                current_value=90.0,
                portfolio_id="test",
            ),
        ]

        results = await sender.send_alerts(alerts)

        assert len(results) == 2
        # Both will fail due to no webhook
        assert all(not r.success for r in results)
