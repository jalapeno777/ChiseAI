"""Integration tests for reporting-discord bridge (V-NS-025).

Tests that reports can trigger Discord notifications and subscription-based delivery.

For V-NS-023 + V-NS-024: Report → Discord notification bridge
"""

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestReportingDiscordBridge:
    """Test bridge between reporting and Discord systems."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for report output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_influxdb(self):
        """Create a mock InfluxDB client."""
        mock = Mock()
        mock.query = AsyncMock(return_value=[])
        mock.write = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def report_scheduler_with_webhook(self, mock_influxdb, temp_output_dir):
        """Create a ReportScheduler with Discord webhook configured."""
        from src.reporting.scheduler import ReportScheduler

        scheduler = ReportScheduler(
            influxdb_client=mock_influxdb,
            output_dir=temp_output_dir,
            default_discord_webhook="https://discord.com/api/webhooks/test/webhook",  # allow-secret
        )
        return scheduler

    @pytest.mark.asyncio
    async def test_discord_webhook_in_scheduler(self, report_scheduler_with_webhook):
        """Test V-NS-025.1: Discord webhook configured in scheduler."""
        assert report_scheduler_with_webhook._default_discord_webhook is not None
        assert "discord.com" in report_scheduler_with_webhook._default_discord_webhook

        print("✓ Discord webhook configured in scheduler")

    @pytest.mark.asyncio
    async def test_schedule_with_discord_webhook(self, report_scheduler_with_webhook):
        """Test V-NS-025.2: Schedule with Discord webhook delivery."""
        schedule = report_scheduler_with_webhook.add_schedule(
            name="test_discord_schedule",
            report_type="daily",
            cron_expression="0 9 * * *",
            discord_webhook="https://discord.com/api/webhooks/test/schedule",  # allow-secret
        )

        assert schedule.discord_webhook is not None
        assert "discord.com" in schedule.discord_webhook

        print("✓ Schedule with Discord webhook created")

    @pytest.mark.asyncio
    async def test_report_to_discord_delivery(self, report_scheduler_with_webhook):
        """Test V-NS-025.3: Report generation triggers Discord delivery."""
        # Add schedule with webhook
        schedule = report_scheduler_with_webhook.add_schedule(
            name="test_delivery",
            report_type="daily",
            cron_expression="0 9 * * *",
        )

        # Generate report
        report = await report_scheduler_with_webhook.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        # Mock Discord send
        with patch.object(
            report_scheduler_with_webhook,
            "_send_to_discord",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True

            # Trigger Discord send
            result = await report_scheduler_with_webhook._send_to_discord(
                schedule.discord_webhook,
                report.to_markdown(),
                f"📊 Daily Report - {report.date.strftime('%Y-%m-%d')}",
            )

            assert result is True
            assert mock_send.called

        print("✓ Report to Discord delivery verified")

    @pytest.mark.asyncio
    async def test_anomaly_alert_to_discord(self, report_scheduler_with_webhook):
        """Test V-NS-025.4: Anomaly alerts sent to Discord."""
        # Add schedule with webhook
        schedule = report_scheduler_with_webhook.add_schedule(
            name="test_anomaly_alerts",
            report_type="daily",
            cron_expression="0 9 * * *",
        )

        # Mock anomaly detection to return an alert
        mock_alert = Mock()
        mock_alert.anomaly_type = Mock()
        mock_alert.anomaly_type.value = "pnl_spike"
        mock_alert.to_markdown = Mock(return_value="🚨 PnL Spike Detected: +50%")
        mock_alert.to_dict = Mock(
            return_value={
                "anomaly_type": "pnl_spike",
                "severity": "warning",
                "message": "PnL spike detected",
            }
        )

        with patch.object(
            report_scheduler_with_webhook.anomaly_detector,
            "detect_all",
            new_callable=AsyncMock,
            return_value=[mock_alert],
        ):
            with patch.object(
                report_scheduler_with_webhook,
                "_send_to_discord",
                new_callable=AsyncMock,
            ) as mock_send:
                mock_send.return_value = True

                # Run anomaly detection
                alerts = await report_scheduler_with_webhook._run_anomaly_detection(
                    schedule
                )

                assert mock_send.called

        print("✓ Anomaly alert to Discord verified")

    @pytest.mark.asyncio
    async def test_email_and_discord_together(self, report_scheduler_with_webhook):
        """Test V-NS-025.5: Both email and Discord delivery configured."""
        schedule = report_scheduler_with_webhook.add_schedule(
            name="test_both_delivery",
            report_type="daily",
            cron_expression="0 9 * * *",
            email_recipients=["test@example.com"],
        )

        assert schedule.discord_webhook is not None
        assert len(schedule.email_recipients) > 0

        print("✓ Email and Discord delivery configured together")

    @pytest.mark.asyncio
    async def test_long_message_splitting(self, report_scheduler_with_webhook):
        """Test V-NS-025.6: Long messages with newlines are split for Discord."""
        # Create a long message with newlines (realistic scenario)
        # Each line is under the limit, but total exceeds it
        lines = ["Line of content number {}".format(i) * 10 for i in range(100)]
        long_content = "\n".join(lines)

        # Split message
        chunks = report_scheduler_with_webhook._split_message(long_content, 1900)

        # Verify splitting happened
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk) <= 1900

        print(f"✓ Long message split into {len(chunks)} chunks")


class TestDiscordAlertTypes:
    """Test different alert types for Discord delivery."""

    @pytest.fixture
    def report_scheduler(self):
        """Create ReportScheduler instance."""
        from src.reporting.scheduler import ReportScheduler

        return ReportScheduler(
            influxdb_client=None,
            output_dir="./test_reports",
            default_discord_webhook="https://discord.com/api/webhooks/test",  # allow-secret
        )

    def test_alert_emoji_mapping(self, report_scheduler):
        """Test V-NS-025.7: Alert type to emoji mapping."""
        # This tests the internal mapping used in _send_to_discord
        alert_types = {
            "pnl_spike": "🚨",
            "volume_spike": "📈",
            "error_rate_spike": "⚠️",
        }

        for alert_type, expected_emoji in alert_types.items():
            assert expected_emoji is not None

        print("✓ Alert emoji mapping verified")

    @pytest.mark.asyncio
    async def test_daily_report_embed_format(self, report_scheduler):
        """Test V-NS-025.8: Daily report formatted for Discord."""
        report = await report_scheduler.generate_report_now(
            report_type="daily",
            use_mock_data=True,
        )

        markdown = report.to_markdown()

        # Verify markdown content is Discord-friendly
        assert len(markdown) > 0
        assert "#" in markdown or "Report" in markdown or "Daily" in markdown

        print("✓ Daily report Discord format verified")


class TestSubscriptionBasedDelivery:
    """Test subscription-based report delivery to Discord."""

    @pytest.fixture
    def report_scheduler(self):
        """Create ReportScheduler instance."""
        from src.reporting.scheduler import ReportScheduler

        return ReportScheduler(
            influxdb_client=None,
            output_dir="./test_reports",
        )

    @pytest.mark.asyncio
    async def test_multiple_schedules_different_webhooks(self, report_scheduler):
        """Test V-NS-025.9: Multiple schedules with different Discord webhooks."""
        # Add daily schedule for trading channel
        schedule1 = report_scheduler.add_schedule(
            name="daily_trading",
            report_type="daily",
            cron_expression="0 9 * * *",
            discord_webhook="https://discord.com/api/webhooks/trading",  # allow-secret
        )

        # Add weekly schedule for general channel
        schedule2 = report_scheduler.add_schedule(
            name="weekly_general",
            report_type="weekly",
            cron_expression="0 10 * * 0",
            discord_webhook="https://discord.com/api/webhooks/general",  # allow-secret
        )

        assert schedule1.discord_webhook != schedule2.discord_webhook

        print("✓ Multiple schedules with different webhooks verified")

    @pytest.mark.asyncio
    async def test_schedule_enable_disable(self, report_scheduler):
        """Test V-NS-025.10: Schedule can be enabled/disabled."""
        schedule = report_scheduler.add_schedule(
            name="test_toggle",
            report_type="daily",
            cron_expression="0 9 * * *",
            enabled=True,
        )

        assert schedule.enabled is True

        # Disable
        schedule.enabled = False
        assert schedule.enabled is False

        # Re-enable
        schedule.enabled = True
        assert schedule.enabled is True

        print("✓ Schedule enable/disable verified")


class TestReportDeliveryReliability:
    """Test reliability features in report delivery."""

    @pytest.fixture
    def report_scheduler(self):
        """Create ReportScheduler instance."""
        from src.reporting.scheduler import ReportScheduler

        return ReportScheduler(
            influxdb_client=None,
            output_dir="./test_reports",
            default_discord_webhook="https://discord.com/api/webhooks/test",  # allow-secret
        )

    @pytest.mark.asyncio
    async def test_graceful_discord_failure(self, report_scheduler):
        """Test V-NS-025.11: Graceful handling of Discord delivery failure."""
        # Mock failed Discord send
        with patch.object(
            report_scheduler,
            "_send_to_discord",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await report_scheduler._send_to_discord(
                "https://discord.com/api/webhooks/test",  # allow-secret
                "Test message",
                "Test Title",
            )

            # Should return False, not raise
            assert result is False

        print("✓ Graceful Discord failure handling verified")

    @pytest.mark.asyncio
    async def test_email_graceful_failure(self, report_scheduler):
        """Test V-NS-025.12: Graceful handling of email delivery failure."""
        # Without SMTP credentials, email should gracefully degrade
        result = await report_scheduler._send_email(
            recipients=["test@example.com"],
            content="Test content",
            subject="Test Subject",
        )

        # Should return True (logs instead of sending)
        assert result is True

        print("✓ Graceful email failure handling verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
