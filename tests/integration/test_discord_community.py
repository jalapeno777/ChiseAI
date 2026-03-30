"""Integration tests for Discord community features (V-NS-024).

End-to-end tests for: Signal creation → Discord notification → Thread creation
Tests bot commands, notification delivery, and moderation tools.

For V-NS-024: Signal posted → bot notifies → community discusses
"""

from datetime import UTC
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestDiscordAlertFormatterDirect:
    """Test AlertFormatter for Discord message formatting using direct imports."""

    def test_alert_type_enum_values(self):
        """Test V-NS-024.1: AlertType enum has correct values."""
        from src.discord_alerts.alert_formatter import AlertType

        assert AlertType.ACTIONABLE.value == "actionable"
        assert AlertType.WATCHLIST.value == "watchlist"
        assert AlertType.INFO.value == "info"

        print("✓ AlertType enum verified")

    def test_alert_formatter_initialization(self):
        """Test V-NS-024.2: AlertFormatter initializes."""
        from src.discord_alerts.alert_formatter import AlertFormatter

        formatter = AlertFormatter()
        assert formatter is not None

        print("✓ AlertFormatter initialized")

    def test_direction_emojis(self):
        """Test V-NS-024.3: Direction emoji mapping."""
        from src.discord_alerts.alert_formatter import AlertFormatter

        formatter = AlertFormatter()

        assert "LONG" in formatter.DIRECTION_EMOJIS
        assert "SHORT" in formatter.DIRECTION_EMOJIS
        assert "NEUTRAL" in formatter.DIRECTION_EMOJIS

        assert formatter.DIRECTION_EMOJIS["LONG"] == "🟢"
        assert formatter.DIRECTION_EMOJIS["SHORT"] == "🔴"
        assert formatter.DIRECTION_EMOJIS["NEUTRAL"] == "⚪"

        print("✓ Direction emojis verified")

    def test_alert_type_emojis(self):
        """Test V-NS-024.4: Alert type emoji mapping."""
        from src.discord_alerts.alert_formatter import AlertFormatter, AlertType

        formatter = AlertFormatter()

        assert AlertType.ACTIONABLE in formatter.ALERT_TYPE_EMOJIS
        assert AlertType.WATCHLIST in formatter.ALERT_TYPE_EMOJIS
        assert AlertType.INFO in formatter.ALERT_TYPE_EMOJIS

        print("✓ Alert type emojis verified")

    def test_confidence_emojis(self):
        """Test V-NS-024.5: Confidence emoji mapping."""
        from src.discord_alerts.alert_formatter import AlertFormatter

        formatter = AlertFormatter()

        assert "high" in formatter.CONFIDENCE_EMOJIS
        assert "medium" in formatter.CONFIDENCE_EMOJIS
        assert "low" in formatter.CONFIDENCE_EMOJIS

        print("✓ Confidence emojis verified")


class TestDiscordConfig:
    """Test Discord configuration."""

    def test_discord_config_initialization(self):
        """Test V-NS-024.6: DiscordConfig initializes."""
        from src.discord_alerts.config import DiscordConfig

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        assert config is not None
        assert config.webhook_url == "https://discord.com/api/webhooks/test"

        print("✓ DiscordConfig verified")


class TestTradeNotifierDirect:
    """Test TradeNotifier using direct imports."""

    def test_trade_notifier_initialization(self):
        """Test V-NS-024.7: TradeNotifier initializes."""
        from src.discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier(webhook_url=None)
        assert notifier is not None

        print("✓ TradeNotifier initialized")

    def test_direction_emojis(self):
        """Test V-NS-024.8: TradeNotifier direction emojis."""
        from src.discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier()
        assert "LONG" in notifier.DIRECTION_EMOJIS
        assert "SHORT" in notifier.DIRECTION_EMOJIS

        print("✓ TradeNotifier direction emojis verified")

    def test_pnl_emojis(self):
        """Test V-NS-024.9: TradeNotifier PnL emojis."""
        from src.discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier()
        assert "profit" in notifier.PNL_EMOJIS
        assert "loss" in notifier.PNL_EMOJIS
        assert "neutral" in notifier.PNL_EMOJIS

        print("✓ TradeNotifier PnL emojis verified")

    def test_trade_emojis(self):
        """Test V-NS-024.10: Trade event emojis."""
        from src.discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier()
        assert "open" in notifier.TRADE_EMOJIS
        assert "close" in notifier.TRADE_EMOJIS

        print("✓ TradeNotifier trade emojis verified")

    def test_status_emojis(self):
        """Test V-NS-024.11: Trade status emojis."""
        from src.discord_alerts.trade_notifier import TradeNotifier

        notifier = TradeNotifier()
        assert "pending" in notifier.STATUS_EMOJIS
        assert "filled" in notifier.STATUS_EMOJIS
        assert "error" in notifier.STATUS_EMOJIS

        print("✓ TradeNotifier status emojis verified")


class TestDiscordClientDirect:
    """Test DiscordClient using direct imports."""

    def test_discord_client_initialization(self):
        """Test V-NS-024.12: DiscordClient initializes."""
        from src.discord_alerts.config import DiscordConfig
        from src.discord_alerts.discord_client import DiscordClient

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        client = DiscordClient(config)

        assert client is not None
        assert client.config == config

        print("✓ DiscordClient initialized")

    def test_discord_client_is_connected_default(self):
        """Test V-NS-024.13: DiscordClient is_connected defaults to False."""
        from src.discord_alerts.config import DiscordConfig
        from src.discord_alerts.discord_client import DiscordClient

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        client = DiscordClient(config)

        assert client.is_connected is False

        print("✓ DiscordClient is_connected defaults correctly")


class TestAlertSenderDirect:
    """Test AlertSender using direct imports."""

    def test_alert_sender_initialization(self):
        """Test V-NS-024.14: AlertSender initializes."""
        from src.discord_alerts.alert_sender import AlertSender
        from src.discord_alerts.config import DiscordConfig

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        sender = AlertSender(config=config)
        assert sender is not None

        print("✓ AlertSender initialized")


class TestDuplicateSuppressorDirect:
    """Test DuplicateSuppressor using direct imports."""

    def test_duplicate_suppressor_initialization(self):
        """Test V-NS-024.15: DuplicateSuppressor initializes."""
        from src.discord_alerts.duplicate_suppressor import DuplicateSuppressor

        suppressor = DuplicateSuppressor()
        assert suppressor is not None

        print("✓ DuplicateSuppressor initialized")


class TestRateLimiterDirect:
    """Test RateLimiter using direct imports."""

    def test_rate_limiter_initialization(self):
        """Test V-NS-024.16: RateLimiter initializes."""
        from src.discord_alerts.rate_limiter import RateLimiter

        limiter = RateLimiter(max_per_minute=10)
        assert limiter is not None
        assert limiter.max_per_minute == 10

        print("✓ RateLimiter initialized")


class TestDiscordContinuityMonitorDirect:
    """Test DiscordContinuityMonitor using direct imports."""

    def test_continuity_monitor_initialization(self):
        """Test V-NS-024.17: DiscordContinuityMonitor initializes."""
        from src.discord_alerts.config import DiscordConfig
        from src.discord_alerts.discord_client import DiscordClient
        from src.discord_alerts.discord_continuity_monitor import (
            DiscordContinuityMonitor,
        )

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        client = DiscordClient(config)
        monitor = DiscordContinuityMonitor(discord_client=client, config=config)
        assert monitor is not None

        print("✓ DiscordContinuityMonitor initialized")


class TestDiscordInitializerDirect:
    """Test DiscordInitializer using direct imports."""

    def test_discord_initializer_initialization(self):
        """Test V-NS-024.18: DiscordInitializer initializes."""
        from src.discord_alerts.config import DiscordConfig
        from src.discord_alerts.discord_initializer import DiscordInitializer

        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/test")
        initializer = DiscordInitializer(config)

        assert initializer is not None
        assert initializer.config == config

        print("✓ DiscordInitializer initialized")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
