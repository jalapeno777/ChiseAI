"""Discord configuration.

Configuration dataclass for Discord alert integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiscordConfig:
    """Configuration for Discord alert integration.

    Attributes:
        bot_token: Discord bot token for authentication
        webhook_url: Discord webhook URL (alternative to bot token)
        default_channel: Default channel for actionable alerts
        watchlist_channel: Channel for watchlist alerts (40-74% confidence)
        rate_limit_per_minute: Max alerts per channel per minute
        enable_duplicate_suppression: Whether to suppress duplicate alerts
        alert_cooldown_seconds: Cooldown between same signal alerts
        actionable_threshold: Minimum confidence for actionable alerts (0.75 = 75%)
        watchlist_threshold: Minimum confidence for watchlist alerts (0.40 = 40%)
        max_retries: Maximum retry attempts for failed deliveries
        retry_base_delay: Base delay for exponential backoff (seconds)
        retry_max_delay: Maximum delay for exponential backoff (seconds)
        batch_max_size: Maximum number of signals in a batch
        batch_max_wait_ms: Maximum wait time for batch in milliseconds
        batch_enabled: Whether batching is enabled
    """

    bot_token: str | None = None
    webhook_url: str | None = None
    default_channel: str = "trading-signals"
    watchlist_channel: str | None = "watchlist"
    rate_limit_per_minute: int = 10
    enable_duplicate_suppression: bool = True
    alert_cooldown_seconds: int = 60
    actionable_threshold: float = 0.75
    watchlist_threshold: float = 0.40
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    batch_max_size: int = 5
    batch_max_wait_ms: int = 100
    batch_enabled: bool = True

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> DiscordConfig:
        """Create config from dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            DiscordConfig instance
        """
        return cls(
            bot_token=config.get("bot_token"),
            webhook_url=config.get("webhook_url"),
            default_channel=config.get("default_channel", "trading-signals"),
            watchlist_channel=config.get("watchlist_channel"),
            rate_limit_per_minute=config.get("rate_limit_per_minute", 10),
            enable_duplicate_suppression=config.get(
                "enable_duplicate_suppression", True
            ),
            alert_cooldown_seconds=config.get("alert_cooldown_seconds", 60),
            actionable_threshold=config.get("actionable_threshold", 0.75),
            watchlist_threshold=config.get("watchlist_threshold", 0.40),
            max_retries=config.get("max_retries", 3),
            retry_base_delay=config.get("retry_base_delay", 1.0),
            retry_max_delay=config.get("retry_max_delay", 30.0),
            batch_max_size=config.get("batch_max_size", 5),
            batch_max_wait_ms=config.get("batch_max_wait_ms", 100),
            batch_enabled=config.get("batch_enabled", True),
        )

    @classmethod
    def from_env(cls) -> DiscordConfig:
        """Create config from environment variables.

        Environment variables:
            DISCORD_BOT_TOKEN: Bot token
            DISCORD_WEBHOOK_URL: Webhook URL
            DISCORD_DEFAULT_CHANNEL: Default channel name
            DISCORD_WATCHLIST_CHANNEL: Watchlist channel name
            DISCORD_RATE_LIMIT_PER_MINUTE: Rate limit per minute

        Returns:
            DiscordConfig instance
        """
        import os

        return cls(
            bot_token=os.getenv("DISCORD_BOT_TOKEN"),
            webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            default_channel=os.getenv("DISCORD_DEFAULT_CHANNEL", "trading-signals"),
            watchlist_channel=os.getenv("DISCORD_WATCHLIST_CHANNEL"),
            rate_limit_per_minute=int(os.getenv("DISCORD_RATE_LIMIT_PER_MINUTE", "10")),
            enable_duplicate_suppression=os.getenv(
                "DISCORD_ENABLE_DUPLICATE_SUPPRESSION", "true"
            ).lower()
            == "true",
            alert_cooldown_seconds=int(
                os.getenv("DISCORD_ALERT_COOLDOWN_SECONDS", "60")
            ),
            actionable_threshold=float(
                os.getenv("DISCORD_ACTIONABLE_THRESHOLD", "0.75")
            ),
            watchlist_threshold=float(os.getenv("DISCORD_WATCHLIST_THRESHOLD", "0.40")),
            max_retries=int(os.getenv("DISCORD_MAX_RETRIES", "3")),
            retry_base_delay=float(os.getenv("DISCORD_RETRY_BASE_DELAY", "1.0")),
            retry_max_delay=float(os.getenv("DISCORD_RETRY_MAX_DELAY", "30.0")),
            batch_max_size=int(os.getenv("DISCORD_BATCH_MAX_SIZE", "5")),
            batch_max_wait_ms=int(os.getenv("DISCORD_BATCH_MAX_WAIT_MS", "100")),
            batch_enabled=os.getenv("DISCORD_BATCH_ENABLED", "true").lower() == "true",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Configuration dictionary
        """
        return {
            "bot_token": self.bot_token,
            "webhook_url": self.webhook_url,
            "default_channel": self.default_channel,
            "watchlist_channel": self.watchlist_channel,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "enable_duplicate_suppression": self.enable_duplicate_suppression,
            "alert_cooldown_seconds": self.alert_cooldown_seconds,
            "actionable_threshold": self.actionable_threshold,
            "watchlist_threshold": self.watchlist_threshold,
            "max_retries": self.max_retries,
            "retry_base_delay": self.retry_base_delay,
            "retry_max_delay": self.retry_max_delay,
            "batch_max_size": self.batch_max_size,
            "batch_max_wait_ms": self.batch_max_wait_ms,
            "batch_enabled": self.batch_enabled,
        }
