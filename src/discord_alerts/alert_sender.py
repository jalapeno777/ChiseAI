"""Alert sender with retry logic.

Async alert sender that coordinates Discord client, formatter,
deduplication, and rate limiting with exponential backoff retry.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.alert_formatter import AlertFormatter
    from discord_alerts.config import DiscordConfig
    from discord_alerts.discord_client import DiscordClient
    from discord_alerts.duplicate_suppressor import DuplicateSuppressor
    from discord_alerts.rate_limiter import RateLimiter
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Result of alert send attempt.

    Attributes:
        success: Whether send was successful
        message_id: Discord message ID (if available)
        channel: Channel the alert was sent to
        error: Error message if failed
        latency_ms: Time taken to send (ms)
        retries: Number of retry attempts
        suppressed: Whether alert was suppressed (duplicate/rate limited)
    """

    success: bool
    message_id: str | None = None
    channel: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    retries: int = 0
    suppressed: bool = False


class AlertSender:
    """Sends Discord alerts with retry logic and coordination.

    Coordinates:
    - Discord client for actual sending
    - Alert formatter for message formatting
    - Duplicate suppressor for deduplication
    - Rate limiter for throttling

    Implements exponential backoff retry for failed deliveries.
    """

    def __init__(
        self,
        config: DiscordConfig,
        client: DiscordClient | None = None,
        formatter: AlertFormatter | None = None,
        suppressor: DuplicateSuppressor | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        """Initialize alert sender.

        Args:
            config: Discord configuration
            client: Discord client (created if None)
            formatter: Alert formatter (created if None)
            suppressor: Duplicate suppressor (created if None)
            rate_limiter: Rate limiter (created if None)
        """
        self.config = config

        # Initialize or store dependencies
        self._client = client
        self._formatter = formatter
        self._suppressor = suppressor
        self._rate_limiter = rate_limiter

        logger.info(
            f"AlertSender initialized: max_retries={config.max_retries}, "
            f"rate_limit={config.rate_limit_per_minute}/min"
        )

    def _get_client(self) -> DiscordClient:
        """Get or create Discord client."""
        if self._client is None:
            from discord_alerts.discord_client import DiscordClient

            self._client = DiscordClient(self.config)
        return self._client

    def _get_formatter(self) -> AlertFormatter:
        """Get or create alert formatter."""
        if self._formatter is None:
            from discord_alerts.alert_formatter import AlertFormatter

            self._formatter = AlertFormatter()
        return self._formatter

    def _get_suppressor(self) -> DuplicateSuppressor:
        """Get or create duplicate suppressor."""
        if self._suppressor is None:
            from discord_alerts.duplicate_suppressor import DuplicateSuppressor

            self._suppressor = DuplicateSuppressor(
                window_seconds=900,  # 15 minutes
                enable_suppression=self.config.enable_duplicate_suppression,
            )
        return self._suppressor

    def _get_rate_limiter(self) -> RateLimiter:
        """Get or create rate limiter."""
        if self._rate_limiter is None:
            from discord_alerts.rate_limiter import RateLimiter

            self._rate_limiter = RateLimiter(
                max_per_minute=self.config.rate_limit_per_minute,
                block_when_limited=False,
            )
        return self._rate_limiter

    async def send_signal(
        self,
        signal: Signal,
        force: bool = False,
    ) -> SendResult:
        """Send a signal alert to Discord.

        Args:
            signal: Trading signal to send
            force: Force send even if suppressed

        Returns:
            SendResult with status
        """
        start_time = time.perf_counter()

        # Determine alert type and channel
        alert_type, channel = self._determine_alert_type_and_channel(signal)

        # Check duplicate suppression
        if not force and self.config.enable_duplicate_suppression:
            suppressor = self._get_suppressor()
            is_duplicate = suppressor.is_duplicate(
                signal.token, signal.direction_str, signal.signal_id
            )

            if is_duplicate:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(f"Alert suppressed (duplicate): {signal.token}")
                return SendResult(
                    success=False,
                    channel=channel,
                    error="Duplicate alert suppressed",
                    latency_ms=latency_ms,
                    suppressed=True,
                )

        # Check rate limit
        rate_limiter = self._get_rate_limiter()
        rate_result = rate_limiter.acquire(channel)

        if not rate_result["success"]:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                f"Rate limited for channel {channel}: "
                f"retry_after={rate_result['retry_after']:.1f}s"
            )
            return SendResult(
                success=False,
                channel=channel,
                error=f"Rate limited. Retry after {rate_result['retry_after']:.1f}s",
                latency_ms=latency_ms,
                suppressed=True,
            )

        # Format the alert
        formatter = self._get_formatter()
        formatted = formatter.format_signal(signal, alert_type)

        # Send with retry logic
        result = await self._send_with_retry(
            content=formatted["content"],
            channel=channel,
            embeds=formatted["embeds"],
        )

        # Record latency
        result.latency_ms = (time.perf_counter() - start_time) * 1000
        result.channel = channel

        # Record successful alert for deduplication
        if result.success and self.config.enable_duplicate_suppression:
            suppressor = self._get_suppressor()
            suppressor.record_alert(
                signal.token, signal.direction_str, signal.signal_id, signal.confidence
            )

        # Log result
        if result.success:
            logger.info(
                f"Alert sent: {signal.token} [{signal.direction_str}] "
                f"to {channel} ({result.latency_ms:.1f}ms)"
            )
        else:
            logger.error(
                f"Alert failed: {signal.token} [{signal.direction_str}] - "
                f"{result.error}"
            )

        return result

    def _determine_alert_type_and_channel(self, signal: Signal) -> tuple[Any, str]:
        """Determine alert type and target channel for signal.

        Args:
            signal: Trading signal

        Returns:
            Tuple of (alert_type, channel)
        """
        from discord_alerts.alert_formatter import AlertType

        confidence = signal.confidence

        if confidence >= self.config.actionable_threshold:
            # Actionable alert (75%+)
            return AlertType.ACTIONABLE, self.config.default_channel
        elif confidence >= self.config.watchlist_threshold:
            # Watchlist alert (40-74%)
            watchlist_channel = self.config.watchlist_channel
            if watchlist_channel:
                return AlertType.WATCHLIST, watchlist_channel
            else:
                # Fall back to default channel
                return AlertType.WATCHLIST, self.config.default_channel
        else:
            # Below watchlist threshold - still use default but marked as info
            return AlertType.INFO, self.config.default_channel

    async def _send_with_retry(
        self,
        content: str,
        channel: str,
        embeds: list[dict[str, Any]] | None = None,
    ) -> SendResult:
        """Send message with exponential backoff retry.

        Args:
            content: Message content
            channel: Target channel
            embeds: Optional embeds

        Returns:
            SendResult with status
        """
        client = self._get_client()

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                result = await client.send_message(
                    content=content,
                    channel=channel,
                    embeds=embeds,
                )

                if result["success"]:
                    return SendResult(
                        success=True,
                        message_id=result.get("message_id"),
                        channel=channel,
                        retries=attempt,
                    )

                # Check for rate limit response
                if "retry_after" in result:
                    retry_after = result["retry_after"]
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    last_error = result.get("error", "Rate limited")
                    continue

                # Other error
                last_error = result.get("error", "Unknown error")

                # Don't retry on certain errors
                if result.get("status") in (400, 401, 403, 404):
                    break

            except Exception as e:
                last_error = str(e)
                logger.error(f"Send attempt {attempt + 1} failed: {e}")

            # Calculate exponential backoff delay
            if attempt < self.config.max_retries - 1:
                delay = min(
                    self.config.retry_base_delay * (2**attempt),
                    self.config.retry_max_delay,
                )
                logger.debug(f"Retrying in {delay:.1f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)

        # All retries exhausted
        return SendResult(
            success=False,
            channel=channel,
            error=last_error or "Max retries exceeded",
            retries=self.config.max_retries,
        )

    async def send_batch(
        self,
        signals: list[Signal],
        force: bool = False,
    ) -> list[SendResult]:
        """Send multiple signal alerts.

        Args:
            signals: List of trading signals
            force: Force send even if suppressed

        Returns:
            List of SendResults
        """
        results = []
        for signal in signals:
            result = await self.send_signal(signal, force)
            results.append(result)
        return results

    async def health_check(self) -> dict[str, Any]:
        """Check alert sender health.

        Returns:
            Dictionary with health status
        """
        client = self._get_client()
        client_health = await client.health_check()

        rate_limiter = self._get_rate_limiter()
        rate_stats = rate_limiter.get_stats()

        suppressor = self._get_suppressor()
        suppressor_stats = suppressor.get_stats()

        return {
            "healthy": client_health.get("healthy", False),
            "client": client_health,
            "rate_limiter": rate_stats,
            "suppressor": suppressor_stats,
            "config": {
                "max_retries": self.config.max_retries,
                "rate_limit_per_minute": self.config.rate_limit_per_minute,
                "enable_dup_suppression": self.config.enable_duplicate_suppression,
            },
        }

    async def close(self) -> None:
        """Close alert sender and cleanup resources."""
        if self._client:
            await self._client.disconnect()
            logger.info("AlertSender closed")
