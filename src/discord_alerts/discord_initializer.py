"""Discord client initialization with retry logic.

Provides resilient Discord client initialization with automatic retry,
fallback to webhook-only mode, and periodic health monitoring.

For PM-BATCH-2: Discord Initialization (CF-3)
For PM-BATCH-2: Discord Rate Limiting (QW-2)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient

logger = logging.getLogger(__name__)


class DiscordInitializer:
    """Resilient Discord client initialization with retry logic.

    Features:
        - Automatic retry with exponential backoff
        - Fallback to webhook-only mode
        - Rate limit tracking and handling
        - Periodic health monitoring with failure tracking
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    RETRY_BACKOFF = 2  # exponential
    HEALTH_CHECK_INTERVAL = 30  # seconds

    def __init__(self, config: DiscordConfig):
        """Initialize DiscordInitializer.

        Args:
            config: Discord configuration
        """
        self.config = config
        self.client: DiscordClient | None = None
        self._health_check_task: asyncio.Task | None = None
        self._mode: str = "none"  # bot, webhook, none
        self._last_error: str | None = None
        self._rate_limit_backoff_until: datetime | None = None
        self._max_consecutive_failures = 5

    def is_rate_limited(self) -> bool:
        """Check if currently backing off due to rate limits.

        Returns:
            True if rate limited, False otherwise
        """
        if self._rate_limit_backoff_until is None:
            return False
        if datetime.now(UTC) >= self._rate_limit_backoff_until:
            self._rate_limit_backoff_until = None
            return False
        return True

    async def _handle_rate_limit(self, retry_after: float) -> None:
        """Handle rate limit with exponential backoff.

        Args:
            retry_after: Seconds to back off
        """
        self._rate_limit_backoff_until = datetime.now(UTC) + timedelta(
            seconds=retry_after
        )
        logger.warning(f"Discord rate limited, backing off for {retry_after}s")

    async def initialize(self) -> bool:
        """Initialize with retry logic and fallback.

        Attempts to connect with bot token first, then falls back to
        webhook-only mode if bot connection fails.

        Returns:
            True if initialization successful, False otherwise
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.client = DiscordClient(self.config)

                # Try full connection first
                if await self.client.connect():
                    self._mode = "bot" if self.config.bot_token else "webhook"
                    logger.info(
                        f"Discord connected on attempt {attempt} (mode: {self._mode})"
                    )
                    self._start_health_monitor()
                    return True

                # Try webhook-only fallback if bot failed
                if self.config.bot_token and self.config.webhook_url:
                    logger.warning("Bot connection failed, trying webhook-only mode")
                    webhook_config = DiscordConfig(
                        webhook_url=self.config.webhook_url,
                        default_channel=self.config.default_channel,
                        guild_id=self.config.guild_id,
                    )
                    self.client = DiscordClient(webhook_config)
                    if await self.client.connect():
                        self._mode = "webhook"
                        logger.info(
                            f"Discord connected via webhook on attempt {attempt}"
                        )
                        self._start_health_monitor()
                        return True

            except Exception as e:
                self._last_error = str(e)
                logger.error(f"Discord init attempt {attempt} failed: {e}")
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAY * (self.RETRY_BACKOFF ** (attempt - 1))
                    logger.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)

        logger.error("Discord initialization failed after all retries")
        self._mode = "none"
        return False

    def _start_health_monitor(self):
        """Start background health check."""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self):
        """Periodic health checks with reconnection and failure tracking."""
        consecutive_health_failures = 0

        while True:
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

            # Skip if rate limited
            if self.is_rate_limited():
                continue

            if self.client and not self.client.is_connected:
                consecutive_health_failures += 1
                logger.warning(
                    f"Discord disconnected (failure {consecutive_health_failures}/"
                    f"{self._max_consecutive_failures})"
                )

                if consecutive_health_failures >= self._max_consecutive_failures:
                    logger.error(
                        f"Discord failed {consecutive_health_failures} consecutive "
                        "health checks, disabling reconnection attempts"
                    )
                    # Stop trying to reconnect - let DiscordClient handle it
                    break

                await self.initialize()
            else:
                # Reset on success
                if consecutive_health_failures > 0:
                    consecutive_health_failures = 0

    async def shutdown(self):
        """Cleanup and disconnect."""
        if self._health_check_task:
            self._health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_check_task
        if self.client:
            await self.client.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if Discord is connected and not disabled.

        Returns:
            True if connected and not disabled, False otherwise
        """
        if self.client is None:
            return False
        if not self.client.is_connected:
            return False
        # Check if client is disabled due to failures
        return not (hasattr(self.client, "is_disabled") and self.client.is_disabled)

    @property
    def mode(self) -> str:
        """Get current connection mode.

        Returns:
            Connection mode: 'bot', 'webhook', or 'none'
        """
        return self._mode

    @property
    def last_error(self) -> str | None:
        """Get last error message.

        Returns:
            Last error message or None
        """
        return self._last_error

    def get_health(self) -> dict[str, Any]:
        """Get health status for API endpoint.

        Returns:
            Dictionary with health status information including rate limit info
        """
        base_health = {
            "connected": self.is_connected,
            "mode": self._mode,
            "guild_restricted": self.config.guild_id is not None,
            "last_error": self._last_error,
            "is_rate_limited": self.is_rate_limited(),
        }

        # Add client health if available
        if self.client:
            try:
                client_health = asyncio.get_event_loop().run_until_complete(
                    self.client.health_check()
                )
                base_health.update(client_health)
            except Exception:
                pass

        return base_health
