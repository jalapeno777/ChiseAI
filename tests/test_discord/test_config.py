"""Tests for Discord configuration.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import os
from unittest import mock

from discord_alerts.config import DiscordConfig


class TestDiscordConfig:
    """Test cases for DiscordConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = DiscordConfig()

        assert config.bot_token is None
        assert config.webhook_url is None
        assert config.default_channel == "trading-signals"
        assert config.watchlist_channel == "watchlist"
        assert config.rate_limit_per_minute == 10
        assert config.enable_duplicate_suppression is True
        assert config.alert_cooldown_seconds == 60
        assert config.actionable_threshold == 0.75
        assert config.watchlist_threshold == 0.40
        assert config.max_retries == 3
        assert config.retry_base_delay == 1.0
        assert config.retry_max_delay == 30.0

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = DiscordConfig(
            bot_token="test_token",
            webhook_url="https://discord.com/api/webhooks/test",
            default_channel="alerts",
            watchlist_channel="low-priority",
            rate_limit_per_minute=20,
            enable_duplicate_suppression=False,
            alert_cooldown_seconds=120,
            actionable_threshold=0.80,
            watchlist_threshold=0.50,
            max_retries=5,
            retry_base_delay=2.0,
            retry_max_delay=60.0,
        )

        assert config.bot_token == "test_token"
        assert config.webhook_url == "https://discord.com/api/webhooks/test"
        assert config.default_channel == "alerts"
        assert config.watchlist_channel == "low-priority"
        assert config.rate_limit_per_minute == 20
        assert config.enable_duplicate_suppression is False
        assert config.alert_cooldown_seconds == 120
        assert config.actionable_threshold == 0.80
        assert config.watchlist_threshold == 0.50
        assert config.max_retries == 5
        assert config.retry_base_delay == 2.0
        assert config.retry_max_delay == 60.0

    def test_from_dict(self) -> None:
        """Test creating config from dictionary."""
        config_dict = {
            "bot_token": "dict_token",
            "webhook_url": "https://webhook.url/test",
            "default_channel": "dict-channel",
            "rate_limit_per_minute": 15,
        }

        config = DiscordConfig.from_dict(config_dict)

        assert config.bot_token == "dict_token"
        assert config.webhook_url == "https://webhook.url/test"
        assert config.default_channel == "dict-channel"
        assert config.rate_limit_per_minute == 15
        # Check defaults preserved (watchlist_channel defaults to None if not in dict)
        assert config.enable_duplicate_suppression is True

    def test_from_dict_empty(self) -> None:
        """Test creating config from empty dictionary."""
        config = DiscordConfig.from_dict({})

        # Should use all defaults
        assert config.bot_token is None
        assert config.default_channel == "trading-signals"
        assert config.rate_limit_per_minute == 10

    def test_from_env(self) -> None:
        """Test creating config from environment variables."""
        env_vars = {
            "DISCORD_BOT_TOKEN": "env_token",
            "DISCORD_WEBHOOK_URL": "https://env.webhook.url",
            "DISCORD_DEFAULT_CHANNEL": "env-channel",
            "DISCORD_WATCHLIST_CHANNEL": "env-watchlist",
            "DISCORD_RATE_LIMIT_PER_MINUTE": "25",
            "DISCORD_ENABLE_DUPLICATE_SUPPRESSION": "false",
            "DISCORD_ALERT_COOLDOWN_SECONDS": "90",
            "DISCORD_ACTIONABLE_THRESHOLD": "0.85",
            "DISCORD_WATCHLIST_THRESHOLD": "0.45",
            "DISCORD_MAX_RETRIES": "4",
            "DISCORD_RETRY_BASE_DELAY": "1.5",
            "DISCORD_RETRY_MAX_DELAY": "45.0",
        }

        with mock.patch.dict(os.environ, env_vars, clear=True):
            config = DiscordConfig.from_env()

        assert config.bot_token == "env_token"
        assert config.webhook_url == "https://env.webhook.url"
        assert config.default_channel == "env-channel"
        assert config.watchlist_channel == "env-watchlist"
        assert config.rate_limit_per_minute == 25
        assert config.enable_duplicate_suppression is False
        assert config.alert_cooldown_seconds == 90
        assert config.actionable_threshold == 0.85
        assert config.watchlist_threshold == 0.45
        assert config.max_retries == 4
        assert config.retry_base_delay == 1.5
        assert config.retry_max_delay == 45.0

    def test_from_env_defaults(self) -> None:
        """Test creating config from env with missing vars uses defaults."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = DiscordConfig.from_env()

        assert config.bot_token is None
        assert config.webhook_url is None
        assert config.default_channel == "trading-signals"
        assert config.rate_limit_per_minute == 10

    def test_to_dict(self) -> None:
        """Test converting config to dictionary."""
        config = DiscordConfig(
            bot_token="test",
            default_channel="test-channel",
        )

        config_dict = config.to_dict()

        assert config_dict["bot_token"] == "test"
        assert config_dict["default_channel"] == "test-channel"
        assert config_dict["rate_limit_per_minute"] == 10
        assert config_dict["enable_duplicate_suppression"] is True

    def test_threshold_validation(self) -> None:
        """Test that thresholds are properly bounded."""
        config = DiscordConfig(
            actionable_threshold=0.75,
            watchlist_threshold=0.40,
        )

        # Actionable should be higher than watchlist
        assert config.actionable_threshold > config.watchlist_threshold
        # Both should be in valid range
        assert 0.0 <= config.actionable_threshold <= 1.0
        assert 0.0 <= config.watchlist_threshold <= 1.0
