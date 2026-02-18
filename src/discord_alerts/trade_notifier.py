"""Trade notification integration for Discord.

Provides Discord webhook notifications for paper trading events including
trade opens and closes with rich embed formatting.

For PAPER-LIVE-001: Discord Trade Notification Integration
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from portfolio.state_management.models import Position
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class TradeNotificationResult:
    """Result of a trade notification attempt.

    Attributes:
        success: Whether notification was sent successfully
        message_id: Discord message ID (if available)
        timestamp: When notification was sent
        error: Error message if failed
    """

    success: bool
    message_id: str | None = None
    timestamp: datetime | None = None
    error: str | None = None


class TradeNotifier:
    """Discord trade notifier for paper trading events.

    Sends rich embed notifications for:
    - Trade opens (position created)
    - Trade closes (position closed with PnL)

    Uses Discord webhook for delivery with retry logic.

    Attributes:
        webhook_url: Discord webhook URL
        session: aiohttp ClientSession for HTTP requests
    """

    # Emoji mappings
    DIRECTION_EMOJIS = {
        "LONG": "🟢",
        "SHORT": "🔴",
    }

    PNL_EMOJIS = {
        "profit": "🟢",
        "loss": "🔴",
        "neutral": "⚪",
    }

    TRADE_EMOJIS = {
        "open": "🚀",
        "close": "🏁",
    }

    def __init__(self, webhook_url: str | None = None) -> None:
        """Initialize trade notifier.

        Args:
            webhook_url: Discord webhook URL
                (reads from DISCORD_WEBHOOK_URL env if None)
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self._session: aiohttp.ClientSession | None = None

        if not self.webhook_url:
            logger.warning(
                "TradeNotifier initialized without webhook URL. "
                "Set DISCORD_WEBHOOK_URL environment variable."
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session.

        Returns:
            ClientSession instance
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30.0)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def send_trade_open_notification(
        self,
        signal: Signal,
        position: Position,
    ) -> TradeNotificationResult:
        """Send notification when a paper trade opens.

        Args:
            signal: The trading signal that triggered the position
            position: The opened position

        Returns:
            TradeNotificationResult with delivery status
        """
        if not self.webhook_url:
            return TradeNotificationResult(
                success=False,
                error="No webhook URL configured",
            )

        try:
            embed = self._build_open_embed(signal, position)
            payload = {"embeds": [embed]}

            return await self._send_webhook(payload)

        except Exception as e:
            logger.error(f"Failed to send trade open notification: {e}")
            return TradeNotificationResult(
                success=False,
                error=str(e),
            )

    async def send_trade_close_notification(
        self,
        position: Position,
        pnl: float,
        exit_price: float | None = None,
    ) -> TradeNotificationResult:
        """Send notification when a position closes with PnL.

        Args:
            position: The closed position
            pnl: Realized profit/loss amount
            exit_price: Optional exit price (uses position.current_price if None)

        Returns:
            TradeNotificationResult with delivery status
        """
        if not self.webhook_url:
            return TradeNotificationResult(
                success=False,
                error="No webhook URL configured",
            )

        try:
            embed = self._build_close_embed(position, pnl, exit_price)
            payload = {"embeds": [embed]}

            return await self._send_webhook(payload)

        except Exception as e:
            logger.error(f"Failed to send trade close notification: {e}")
            return TradeNotificationResult(
                success=False,
                error=str(e),
            )

    def _build_open_embed(
        self,
        signal: Signal,
        position: Position,
    ) -> dict[str, Any]:
        """Build Discord embed for trade open notification.

        Args:
            signal: The trading signal
            position: The opened position

        Returns:
            Discord embed dictionary
        """
        direction = position.direction.value
        direction_emoji = self.DIRECTION_EMOJIS.get(direction, "📊")
        trade_emoji = self.TRADE_EMOJIS["open"]

        # Title
        title = f"{trade_emoji} Trade Opened: {position.token}"

        # Description with key details
        confidence_pct = getattr(signal, "confidence", 0.0) * 100
        base_token = position.token.split("/")[0]
        description_lines = [
            f"{direction_emoji} **Direction:** {direction}",
            f"💰 **Entry Price:** ${position.entry_price:,.2f}",
            f"📊 **Position Size:** {position.quantity:,.4f} {base_token}",
        ]

        # Add confidence if available
        if confidence_pct > 0:
            description_lines.append(f"🎯 **Confidence:** {confidence_pct:.1f}%")

        # Add leverage if > 1
        if position.leverage > 1.0:
            description_lines.append(f"⚡ **Leverage:** {position.leverage:.1f}x")

        description = "\n".join(description_lines)

        # Build fields
        fields = []

        # Notional value
        notional = position.entry_price * position.quantity
        fields.append(
            {
                "name": "💵 Notional Value",
                "value": f"${notional:,.2f}",
                "inline": True,
            }
        )

        # Margin used
        if position.margin_used > 0:
            fields.append(
                {
                    "name": "🔒 Margin Used",
                    "value": f"${position.margin_used:,.2f}",
                    "inline": True,
                }
            )

        # Signal ID reference
        signal_id = getattr(signal, "signal_id", "unknown")
        fields.append(
            {
                "name": "📋 Signal ID",
                "value": f"`{signal_id[:8]}...`",
                "inline": True,
            }
        )

        # Color based on direction
        color = 0x00FF00 if direction == "LONG" else 0xFF0000

        # Timestamp
        timestamp = datetime.now(UTC).isoformat()

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": timestamp,
            "footer": {
                "text": f"Position ID: {position.position_id[:8]}... | Paper Trading"
            },
        }

    def _build_close_embed(
        self,
        position: Position,
        pnl: float,
        exit_price: float | None = None,
    ) -> dict[str, Any]:
        """Build Discord embed for trade close notification.

        Args:
            position: The closed position
            pnl: Realized profit/loss
            exit_price: Optional exit price

        Returns:
            Discord embed dictionary
        """
        direction = position.direction.value
        direction_emoji = self.DIRECTION_EMOJIS.get(direction, "📊")
        trade_emoji = self.TRADE_EMOJIS["close"]

        # Determine PnL emoji
        if pnl > 0:
            pnl_emoji = self.PNL_EMOJIS["profit"]
        elif pnl < 0:
            pnl_emoji = self.PNL_EMOJIS["loss"]
        else:
            pnl_emoji = self.PNL_EMOJIS["neutral"]

        # Title
        title = f"{trade_emoji} Trade Closed: {position.token}"

        # Exit price
        close_price = exit_price if exit_price is not None else position.current_price

        # Description
        base_token = position.token.split("/")[0]
        description_lines = [
            f"{direction_emoji} **Direction:** {direction}",
            f"💰 **Entry:** ${position.entry_price:,.2f} "
            f"→ **Exit:** ${close_price:,.2f}",
            f"📊 **Position Size:** {position.quantity:,.4f} {base_token}",
        ]
        description = "\n".join(description_lines)

        # Build fields
        fields = []

        # Realized PnL (highlighted)
        pnl_prefix = "+" if pnl > 0 else ""
        fields.append(
            {
                "name": f"{pnl_emoji} Realized PnL",
                "value": f"**{pnl_prefix}${pnl:,.2f}**",
                "inline": True,
            }
        )

        # PnL Percentage
        if position.entry_price > 0 and close_price > 0:
            if direction == "LONG":
                price_change_pct = (
                    (close_price - position.entry_price) / position.entry_price
                ) * 100
            else:  # SHORT
                price_change_pct = (
                    (position.entry_price - close_price) / position.entry_price
                ) * 100

            # Apply leverage
            total_return_pct = price_change_pct * position.leverage
            fields.append(
                {
                    "name": "📈 Return",
                    "value": f"{total_return_pct:+.2f}%",
                    "inline": True,
                }
            )

        # Duration
        if position.timestamp > 0:
            duration_ms = position.last_update - position.timestamp
            duration_str = self._format_duration(duration_ms)
            fields.append(
                {
                    "name": "⏱️ Duration",
                    "value": duration_str,
                    "inline": True,
                }
            )

        # Color based on PnL
        if pnl > 0:
            color = 0x00FF00  # Green for profit
        elif pnl < 0:
            color = 0xFF0000  # Red for loss
        else:
            color = 0x808080  # Gray for neutral

        # Timestamp
        timestamp = datetime.now(UTC).isoformat()

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": timestamp,
            "footer": {
                "text": f"Position ID: {position.position_id[:8]}... | Paper Trading"
            },
        }

    def _format_duration(self, duration_ms: int) -> str:
        """Format duration in milliseconds to human-readable string.

        Args:
            duration_ms: Duration in milliseconds

        Returns:
            Formatted duration string
        """
        seconds = duration_ms // 1000
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24

        if days > 0:
            return f"{days}d {hours % 24}h"
        elif hours > 0:
            return f"{hours}h {minutes % 60}m"
        elif minutes > 0:
            return f"{minutes}m {seconds % 60}s"
        else:
            return f"{seconds}s"

    async def _send_webhook(
        self,
        payload: dict[str, Any],
    ) -> TradeNotificationResult:
        """Send payload to Discord webhook.

        Args:
            payload: JSON payload to send

        Returns:
            TradeNotificationResult with delivery status
        """
        session = await self._get_session()

        if not self.webhook_url:
            return TradeNotificationResult(
                success=False,
                error="No webhook URL configured",
            )

        webhook_url = self.webhook_url  # type: ignore[assignment]
        async with session.post(webhook_url, json=payload) as resp:
            if resp.status == 204:
                # Success - Discord returns 204 No Content
                logger.info("Trade notification sent successfully")
                return TradeNotificationResult(
                    success=True,
                    timestamp=datetime.now(UTC),
                )
            elif resp.status == 429:
                # Rate limited
                retry_after = resp.headers.get("Retry-After", "5")
                error_msg = f"Rate limited by Discord. Retry after {retry_after}s"
                logger.warning(error_msg)
                return TradeNotificationResult(
                    success=False,
                    error=error_msg,
                )
            else:
                body = await resp.text()
                error_msg = f"Discord webhook error: HTTP {resp.status} - {body}"
                logger.error(error_msg)
                return TradeNotificationResult(
                    success=False,
                    error=error_msg,
                )

    async def health_check(self) -> dict[str, Any]:
        """Check notifier health.

        Returns:
            Health status dictionary
        """
        return {
            "healthy": self.webhook_url is not None,
            "webhook_configured": self.webhook_url is not None,
            "session_active": self._session is not None and not self._session.closed,
        }
