"""Risk alert sender with Discord integration.

Sends risk threshold alerts via Discord webhook with suppression,
retry logic, and proper formatting.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.discord_client import DiscordClient

    from .formatter import RiskAlertFormatter
    from .suppressor import AlertSuppressor
    from .types import RiskAlert

logger = logging.getLogger(__name__)


@dataclass
class RiskAlertSendResult:
    """Result of risk alert send attempt.

    Attributes:
        success: Whether send was successful
        alert_type: Type of alert that was sent
        suppressed: Whether alert was suppressed
        error: Error message if failed
        latency_ms: Time taken to send (ms)
        retries: Number of retry attempts
    """

    success: bool
    alert_type: str
    suppressed: bool = False
    error: str | None = None
    latency_ms: float = 0.0
    retries: int = 0


class RiskAlertSender:
    """Sends risk alerts via Discord with suppression and retry logic.

    Coordinates:
    - Alert suppression to prevent spam
    - Discord client for actual sending
    - Alert formatter for message formatting
    - Retry logic for failed deliveries
    """

    DEFAULT_WEBHOOK_ENV_VAR = "DISCORD_ALERT_WEBHOOK_URL"
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0

    def __init__(
        self,
        webhook_url: str | None = None,
        suppressor: AlertSuppressor | None = None,
        formatter: RiskAlertFormatter | None = None,
        client: DiscordClient | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize risk alert sender.

        Args:
            webhook_url: Discord webhook URL (reads from env if None)
            suppressor: Alert suppressor (created if None)
            formatter: Alert formatter (created if None)
            client: Discord client (created if None)
            max_retries: Maximum retry attempts for failed deliveries
        """
        self.webhook_url = webhook_url or os.getenv(self.DEFAULT_WEBHOOK_ENV_VAR)
        self.max_retries = max_retries

        # Store or create dependencies
        self._suppressor = suppressor
        self._formatter = formatter
        self._client = client

        if not self.webhook_url:
            logger.warning(
                f"No webhook URL provided. Set {self.DEFAULT_WEBHOOK_ENV_VAR} env var."
            )
        else:
            logger.debug("RiskAlertSender initialized")

    def _get_suppressor(self) -> AlertSuppressor:
        """Get or create alert suppressor."""
        if self._suppressor is None:
            from .suppressor import AlertSuppressor

            self._suppressor = AlertSuppressor()
        return self._suppressor

    def _get_formatter(self) -> RiskAlertFormatter:
        """Get or create alert formatter."""
        if self._formatter is None:
            from .formatter import RiskAlertFormatter

            self._formatter = RiskAlertFormatter()
        return self._formatter

    def _get_client(self) -> DiscordClient:
        """Get or create Discord client."""
        if self._client is None:
            from discord_alerts.config import DiscordConfig
            from discord_alerts.discord_client import DiscordClient

            config = DiscordConfig(webhook_url=self.webhook_url)
            self._client = DiscordClient(config)
        return self._client

    async def send_alert(
        self,
        alert: RiskAlert,
        force: bool = False,
    ) -> RiskAlertSendResult:
        """Send a risk alert to Discord.

        Args:
            alert: Risk alert to send
            force: Force send even if suppressed

        Returns:
            RiskAlertSendResult with status
        """
        start_time = time.perf_counter()

        # Check suppression (unless forced)
        if not force:
            suppressor = self._get_suppressor()
            if not suppressor.should_send(alert):
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(f"Alert suppressed: {alert.alert_type.value}")
                return RiskAlertSendResult(
                    success=False,
                    alert_type=alert.alert_type.value,
                    suppressed=True,
                    latency_ms=latency_ms,
                )

        # Format the alert
        formatter = self._get_formatter()
        formatted = formatter.format_alert(alert)

        # Send with retry logic
        result = await self._send_with_retry(
            content=formatted["content"],
            embeds=formatted["embeds"],
        )

        # Record latency
        result.latency_ms = (time.perf_counter() - start_time) * 1000
        result.alert_type = alert.alert_type.value

        # Log result
        if result.success:
            logger.info(
                f"Risk alert sent: {alert.alert_type.value} [{alert.severity.value}] "
                f"({result.latency_ms:.1f}ms)"
            )
        else:
            logger.error(
                f"Risk alert failed: {alert.alert_type.value} - {result.error}"
            )

        return result

    async def send_alerts(
        self,
        alerts: list[RiskAlert],
        force: bool = False,
    ) -> list[RiskAlertSendResult]:
        """Send multiple risk alerts.

        Args:
            alerts: List of risk alerts to send
            force: Force send even if suppressed

        Returns:
            List of RiskAlertSendResults
        """
        results = []
        for alert in alerts:
            result = await self.send_alert(alert, force)
            results.append(result)
        return results

    async def send_kill_switch_alert(
        self,
        alert: RiskAlert,
    ) -> RiskAlertSendResult:
        """Send kill-switch alert immediately (no suppression).

        Args:
            alert: Kill-switch alert to send

        Returns:
            RiskAlertSendResult with status
        """
        # Force send kill-switch alerts
        return await self.send_alert(alert, force=True)

    async def _send_with_retry(
        self,
        content: str,
        embeds: list[dict[str, Any]] | None = None,
    ) -> RiskAlertSendResult:
        """Send message with exponential backoff retry.

        Args:
            content: Message content
            embeds: Optional embeds

        Returns:
            RiskAlertSendResult with status
        """
        if not self.webhook_url:
            return RiskAlertSendResult(
                success=False,
                alert_type="unknown",
                error="No webhook URL configured",
            )

        client = self._get_client()

        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = await client.send_message(
                    content=content,
                    embeds=embeds,
                )

                if result["success"]:
                    return RiskAlertSendResult(
                        success=True,
                        alert_type="unknown",
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
            if attempt < self.max_retries - 1:
                delay = min(
                    self.DEFAULT_RETRY_DELAY * (2**attempt),
                    30.0,  # Max 30 second delay
                )
                logger.debug(f"Retrying in {delay:.1f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)

        # All retries exhausted
        return RiskAlertSendResult(
            success=False,
            alert_type="unknown",
            error=last_error or "Max retries exceeded",
            retries=self.max_retries,
        )

    def get_suppressor_stats(self) -> dict[str, Any]:
        """Get alert suppressor statistics.

        Returns:
            Dictionary with statistics
        """
        suppressor = self._get_suppressor()
        return suppressor.get_stats()

    async def health_check(self) -> dict[str, Any]:
        """Check alert sender health.

        Returns:
            Dictionary with health status
        """
        if not self.webhook_url:
            return {
                "healthy": False,
                "error": "No webhook URL configured",
                "webhook_configured": False,
            }

        try:
            client = self._get_client()
            client_health = await client.health_check()

            return {
                "healthy": client_health.get("healthy", False),
                "webhook_configured": True,
                "client": client_health,
                "suppressor": self.get_suppressor_stats(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "webhook_configured": True,
            }

    async def close(self) -> None:
        """Close alert sender and cleanup resources."""
        if self._client:
            await self._client.disconnect()
            logger.info("RiskAlertSender closed")
