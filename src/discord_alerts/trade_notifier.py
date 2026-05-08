"""Trade notification integration for Discord.

Provides Discord webhook notifications for paper trading events including
trade opens and closes with rich embed formatting. Uses SignalOutcome as
the canonical source of truth for trade data.

For PAPER-LIVE-001: Discord Trade Notification Integration
For RECON-001: Trade Schema Reconciliation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from src.execution.paper.models import PaperOrder
    from src.execution.paper.position_tracker import PaperPosition
    from src.ml.models.signal_outcome import SignalOutcome

logger = logging.getLogger(__name__)


@dataclass
class TradeNotificationResult:
    """Result of a trade notification attempt.

    Attributes:
        success: Whether notification was sent successfully
        message_id: Discord message ID (if available)
        timestamp: When notification was sent
        error: Error message if failed
        retry_count: Number of retry attempts made
        dead_letter_queued: Whether message was queued for later retry
    """

    success: bool
    message_id: str | None = None
    timestamp: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    dead_letter_queued: bool = False


class TradeNotifier:
    """Discord trade notifier for paper trading events.

    Sends rich embed notifications for:
    - Trade opens (position created)
    - Trade closes (position closed with PnL)

    Uses Discord webhook for delivery with exponential backoff retry logic.
    Failed notifications are queued to a dead-letter queue in Redis for later retry.

    Attributes:
        webhook_url: Discord webhook URL
        trading_channel_id: Discord channel ID for trading alerts
        session: aiohttp ClientSession for HTTP requests
        max_retries: Maximum number of retry attempts
        retry_base_delay: Base delay for exponential backoff (seconds)
        retry_max_delay: Maximum delay between retries (seconds)
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

    STATUS_EMOJIS = {
        "pending": "⏳",
        "filled": "✅",
        "partial": "⚡",
        "error": "❌",
        "matched": "🔗",
        "closed": "🔒",
    }

    def __init__(
        self,
        webhook_url: str | None = None,
        trading_channel_id: str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        """Initialize trade notifier.

        Args:
            webhook_url: Discord webhook URL
                (reads from DISCORD_TRADING_WEBHOOK_URL env first,
                then falls back to DISCORD_WEBHOOK_URL if None)
            trading_channel_id: Discord channel ID for #trading
                (reads from DISCORD_TRADING_CHANNEL_ID env if None)
            max_retries: Maximum retry attempts for failed deliveries
            retry_base_delay: Base delay for exponential backoff
            retry_max_delay: Maximum delay for exponential backoff
        """
        # DISCORD-TRADING-001: Use DISCORD_TRADING_WEBHOOK_URL with fallback to DISCORD_WEBHOOK_URL
        self.webhook_url = (
            webhook_url
            or os.getenv("DISCORD_TRADING_WEBHOOK_URL")
            or os.getenv("DISCORD_WEBHOOK_URL")
        )
        self.trading_channel_id = trading_channel_id or os.getenv(
            "DISCORD_TRADING_CHANNEL_ID", "1444447985378398459"
        )
        self._session: aiohttp.ClientSession | None = None
        self._redis_client: Any | None = None

        # Retry configuration
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay

        # Notification throttle: per-symbol minimum interval
        self._notification_min_interval = max(
            int(os.environ.get("NOTIFICATION_MIN_INTERVAL_SECONDS", "30")), 5
        )
        self._last_notification_ts: dict[str, float] = {}

        if not self.webhook_url:
            logger.warning(
                "TradeNotifier initialized without webhook URL. "
                "Set DISCORD_TRADING_WEBHOOK_URL or DISCORD_WEBHOOK_URL environment variable."
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30.0)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get_redis(self) -> Any | None:
        """Get or create Redis client for dead-letter queue."""
        if self._redis_client is None:
            try:
                import redis as redis_lib

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis_client = redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
            except Exception as e:
                logger.debug(f"Redis not available for dead-letter queue: {e}")
        return self._redis_client

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _should_throttle_notification(self, symbol: str) -> bool:
        """Check if a notification for the given symbol should be throttled.

        Args:
            symbol: Trading symbol to check

        Returns:
            True if notification should be skipped due to throttle
        """
        last_ts = self._last_notification_ts.get(symbol, 0.0)
        elapsed = time.time() - last_ts
        if elapsed < self._notification_min_interval:
            logger.info(
                "Notification throttled for %s — %ds since last (min %ds)",
                symbol,
                int(elapsed),
                self._notification_min_interval,
            )
            return True
        return False

    def _record_notification_sent(self, symbol: str) -> None:
        """Record that a notification was sent for a symbol.

        Args:
            symbol: Trading symbol
        """
        self._last_notification_ts[symbol] = time.time()

    @staticmethod
    def create_outcome_from_paper_position(
        position: PaperPosition,
        order: PaperOrder | None = None,
        signal_id: str | None = None,
        pnl: float | None = None,
        exit_price: float | None = None,
    ) -> SignalOutcome:
        """Create a SignalOutcome from a PaperPosition.

        Factory method to convert paper trading position data into
        the canonical SignalOutcome format for Discord notifications.

        Args:
            position: The paper trading position
            order: Optional filled order for additional metadata
            signal_id: Optional signal ID from the originating signal
            pnl: Optional realized PnL (for closed positions)
            exit_price: Optional exit price (for closed positions)

        Returns:
            SignalOutcome populated from position data
        """
        from decimal import Decimal
        from uuid import UUID

        from ml.models.signal_outcome import (
            SignalOutcome,
            SignalOutcomeStatus,
        )

        # Determine direction from position side
        direction = "LONG" if position.side.lower() == "long" else "SHORT"
        side = "Buy" if direction == "LONG" else "Sell"

        # Extract signal_id from metadata if not provided
        if signal_id is None and position.metadata:
            signal_id = position.metadata.get("signal_id")

        # Extract order_id from metadata if available
        order_id = ""
        if position.metadata:
            order_id = position.metadata.get("order_id", "")
        if order and not order_id:
            order_id = order.order_id

        # Determine status based on whether position is closed
        if position.closed_at is not None or exit_price is not None:
            status = SignalOutcomeStatus.CLOSED
        else:
            status = SignalOutcomeStatus.FILLED

        # Build the outcome
        outcome = SignalOutcome(
            outcome_id=UUID(position.position_id) if position.position_id else None,
            signal_id=UUID(signal_id) if signal_id else None,
            order_id=order_id,
            symbol=position.symbol,
            side=side,
            direction=direction,
            fill_price=Decimal(str(position.entry_price)),
            fill_quantity=Decimal(str(position.quantity)),
            entry_price=Decimal(str(position.entry_price)),
            position_size=Decimal(str(position.quantity)),
            status=status,
            metadata=position.metadata or {},
        )

        # Add close data if provided
        if pnl is not None:
            outcome.pnl = Decimal(str(pnl))
        if exit_price is not None:
            outcome.exit_price = Decimal(str(exit_price))
            outcome.exit_time = position.closed_at

        return outcome

    async def send_trade_open_notification(
        self,
        outcome: SignalOutcome,
        llm_decision: dict[str, Any] | None = None,
    ) -> TradeNotificationResult:
        """Send notification when a trade opens.

        Args:
            outcome: The SignalOutcome representing the opened trade
            llm_decision: Optional LLM decision details including:
                - decision: GO/NO-GO
                - confidence: Confidence percentage (0-100)
                - provider: LLM provider name
                - rationale: Brief reasoning
                - position_size: Recommended position size (optional)
                - stop_loss: Recommended stop loss (optional)
                - take_profit: Recommended take profit (optional)

        Returns:
            TradeNotificationResult with delivery status
        """
        if not self.webhook_url:
            return TradeNotificationResult(
                success=False,
                error="No webhook URL configured",
            )

        # Per-symbol notification throttle
        symbol = (outcome.symbol or "unknown").upper().strip()
        if self._should_throttle_notification(symbol):
            return TradeNotificationResult(
                success=False,
                error=f"Notification throttled for {symbol}",
            )

        try:
            embed = self._build_open_embed(outcome, llm_decision)
            payload = {"embeds": [embed]}

            result = await self._send_webhook_with_retry(payload, outcome)
            if result.success:
                self._record_notification_sent(symbol)
            return result

        except Exception as e:
            logger.error(f"Failed to send trade open notification: {e}")
            return TradeNotificationResult(
                success=False,
                error=str(e),
            )

    async def send_trade_close_notification(
        self,
        outcome: SignalOutcome,
        llm_decision: dict[str, Any] | None = None,
    ) -> TradeNotificationResult:
        """Send notification when a trade closes with PnL.

        Args:
            outcome: The SignalOutcome representing the closed trade
            llm_decision: Optional LLM decision details including:
                - decision: GO/NO-GO
                - confidence: Confidence percentage (0-100)
                - provider: LLM provider name
                - rationale: Brief reasoning
                - exit_reason: Reason for exit (optional)
                - realized_pnl: Realized PnL (optional)

        Returns:
            TradeNotificationResult with delivery status
        """
        if not self.webhook_url:
            return TradeNotificationResult(
                success=False,
                error="No webhook URL configured",
            )

        # Per-symbol notification throttle
        symbol = (outcome.symbol or "unknown").upper().strip()
        if self._should_throttle_notification(symbol):
            return TradeNotificationResult(
                success=False,
                error=f"Notification throttled for {symbol}",
            )

        try:
            embed = self._build_close_embed(outcome, llm_decision)
            payload = {"embeds": [embed]}

            result = await self._send_webhook_with_retry(payload, outcome)
            if result.success:
                self._record_notification_sent(symbol)
            return result

        except Exception as e:
            logger.error(f"Failed to send trade close notification: {e}")
            return TradeNotificationResult(
                success=False,
                error=str(e),
            )

    def _build_open_embed(
        self,
        outcome: SignalOutcome,
        llm_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build Discord embed for trade open notification.

        Args:
            outcome: The SignalOutcome for the opened trade
            llm_decision: Optional LLM decision details

        Returns:
            Discord embed dictionary
        """
        direction = outcome.direction or ("LONG" if outcome.side == "Buy" else "SHORT")
        direction_emoji = self.DIRECTION_EMOJIS.get(direction, "📊")
        trade_emoji = self.TRADE_EMOJIS["open"]
        token = outcome.token or outcome.symbol.replace("USDT", "").replace("USD", "")

        # Title with test indicator
        test_prefix = "[TEST] " if outcome.is_test else ""
        title = f"{test_prefix}{trade_emoji} Trade Opened: {token}"

        # Description with key details
        description_lines = [
            f"{direction_emoji} **Direction:** {direction}",
            f"💰 **Entry Price:** ${float(outcome.entry_price):,.2f}",
            f"📊 **Position Size:** {float(outcome.position_size):,.4f} {token}",
        ]

        # Add leverage if > 1
        leverage = float(outcome.leverage) if outcome.leverage else 1.0
        if leverage > 1.0:
            description_lines.append(f"⚡ **Leverage:** {leverage:.1f}x")

        # Add entry reason if available
        if outcome.entry_reason:
            description_lines.append(f"📝 **Entry Reason:** {outcome.entry_reason}")

        description = "\n".join(description_lines)

        # Build fields
        fields = []

        # Notional value
        notional = float(outcome.entry_price) * float(outcome.position_size)
        fields.append(
            {
                "name": "💵 Notional Value",
                "value": f"${notional:,.2f}",
                "inline": True,
            }
        )

        # Margin used (if leverage > 1)
        if leverage > 1.0:
            margin = notional / leverage
            fields.append(
                {
                    "name": "🔒 Margin Used",
                    "value": f"${margin:,.2f}",
                    "inline": True,
                }
            )

        # LLM Decision fields (if available)
        if llm_decision:
            # Add separator for LLM section
            fields.append(
                {
                    "name": "━━━ LLM Decision Details ━━━",
                    "value": "\u200b",  # Zero-width space for separator
                    "inline": False,
                }
            )

            # Decision and confidence
            decision = llm_decision.get("decision", "N/A")
            confidence = llm_decision.get("confidence", 0)
            fields.append(
                {
                    "name": "🤖 LLM Decision",
                    "value": f"**{decision}** (Confidence: {confidence}%)",
                    "inline": True,
                }
            )

            # Provider
            provider = llm_decision.get("provider", "Unknown")
            fields.append(
                {
                    "name": "🔧 Provider",
                    "value": provider,
                    "inline": True,
                }
            )

            # Rationale (truncated if too long)
            rationale = llm_decision.get("rationale", "")
            if rationale:
                # Discord field values have a 1024 char limit, truncate to 200 chars
                rationale_display = (
                    rationale[:200] + "..." if len(rationale) > 200 else rationale
                )
                fields.append(
                    {
                        "name": "💭 Rationale",
                        "value": rationale_display,
                        "inline": False,
                    }
                )

            # Position Size (if recommended by LLM)
            if "position_size" in llm_decision and llm_decision["position_size"]:
                fields.append(
                    {
                        "name": "📏 Recommended Size",
                        "value": f"{llm_decision['position_size']}",
                        "inline": True,
                    }
                )

            # Stop Loss (if recommended)
            if "stop_loss" in llm_decision and llm_decision["stop_loss"]:
                fields.append(
                    {
                        "name": "🛑 Stop Loss",
                        "value": f"${float(llm_decision['stop_loss']):,.2f}",
                        "inline": True,
                    }
                )

            # Take Profit (if recommended)
            if "take_profit" in llm_decision and llm_decision["take_profit"]:
                fields.append(
                    {
                        "name": "🎯 Take Profit",
                        "value": f"${float(llm_decision['take_profit']):,.2f}",
                        "inline": True,
                    }
                )

        # Signal ID reference
        signal_id = str(outcome.signal_id) if outcome.signal_id else "unknown"
        fields.append(
            {
                "name": "📋 Signal ID",
                "value": f"`{signal_id[:8]}...`",
                "inline": True,
            }
        )

        # Order ID
        if outcome.order_id:
            fields.append(
                {
                    "name": "🏷️ Order ID",
                    "value": f"`{outcome.order_id[:12]}...`",
                    "inline": True,
                }
            )

        # Entry time
        entry_time_str = outcome.entry_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        fields.append(
            {
                "name": "🕐 Entry Time",
                "value": entry_time_str,
                "inline": True,
            }
        )

        # Color based on direction
        color = 0x00FF00 if direction == "LONG" else 0xFF0000

        # Timestamp
        timestamp = datetime.now(UTC).isoformat()

        # Footer with test indicator
        test_indicator = "🧪 " if outcome.is_test else ""
        footer_text = f"{test_indicator}Outcome ID: {str(outcome.outcome_id)[:8]}... | Paper Trading"

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": timestamp,
            "footer": {"text": footer_text},
        }

    def _build_close_embed(
        self,
        outcome: SignalOutcome,
        llm_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build Discord embed for trade close notification.

        Args:
            outcome: The SignalOutcome for the closed trade
            llm_decision: Optional LLM decision details

        Returns:
            Discord embed dictionary
        """
        direction = outcome.direction or ("LONG" if outcome.side == "Buy" else "SHORT")
        direction_emoji = self.DIRECTION_EMOJIS.get(direction, "📊")
        trade_emoji = self.TRADE_EMOJIS["close"]
        token = outcome.token or outcome.symbol.replace("USDT", "").replace("USD", "")

        # Determine PnL
        pnl = outcome.pnl or Decimal("0")
        pnl_float = float(pnl)

        # Determine PnL emoji
        if pnl_float > 0:
            pnl_emoji = self.PNL_EMOJIS["profit"]
        elif pnl_float < 0:
            pnl_emoji = self.PNL_EMOJIS["loss"]
        else:
            pnl_emoji = self.PNL_EMOJIS["neutral"]

        # Title with test indicator
        test_prefix = "[TEST] " if outcome.is_test else ""
        title = f"{test_prefix}{trade_emoji} Trade Closed: {token}"

        # Exit price
        exit_price = outcome.exit_price or outcome.fill_price

        # Description
        description_lines = [
            f"{direction_emoji} **Direction:** {direction}",
            f"💰 **Entry:** ${float(outcome.entry_price):,.2f} "
            f"→ **Exit:** ${float(exit_price):,.2f}",
            f"📊 **Position Size:** {float(outcome.position_size):,.4f} {token}",
        ]
        description = "\n".join(description_lines)

        # Build fields
        fields = []

        # Realized PnL (highlighted)
        pnl_prefix = "+" if pnl_float > 0 else ""
        fields.append(
            {
                "name": f"{pnl_emoji} Realized PnL",
                "value": f"**{pnl_prefix}${pnl_float:,.2f}**",
                "inline": True,
            }
        )

        # PnL Percentage
        if float(outcome.entry_price) > 0 and float(exit_price) > 0:
            if direction == "LONG":
                price_change_pct = (
                    (float(exit_price) - float(outcome.entry_price))
                    / float(outcome.entry_price)
                ) * 100
            else:  # SHORT
                price_change_pct = (
                    (float(outcome.entry_price) - float(exit_price))
                    / float(outcome.entry_price)
                ) * 100

            # Apply leverage
            leverage = float(outcome.leverage) if outcome.leverage else 1.0
            total_return_pct = price_change_pct * leverage
            fields.append(
                {
                    "name": "📈 Return",
                    "value": f"{total_return_pct:+.2f}%",
                    "inline": True,
                }
            )

        # Duration
        if outcome.exit_time and outcome.entry_time:
            duration = outcome.exit_time - outcome.entry_time
            duration_str = self._format_duration(duration)
            fields.append(
                {
                    "name": "⏱️ Duration",
                    "value": duration_str,
                    "inline": True,
                }
            )

        # LLM Decision fields (if available)
        if llm_decision:
            # Add separator for LLM section
            fields.append(
                {
                    "name": "━━━ LLM Decision Details ━━━",
                    "value": "\u200b",  # Zero-width space for separator
                    "inline": False,
                }
            )

            # Original decision and confidence
            decision = llm_decision.get("decision", "N/A")
            confidence = llm_decision.get("confidence", 0)
            fields.append(
                {
                    "name": "🤖 Original Decision",
                    "value": f"**{decision}** (Confidence: {confidence}%)",
                    "inline": True,
                }
            )

            # Provider
            provider = llm_decision.get("provider", "Unknown")
            fields.append(
                {
                    "name": "🔧 Provider",
                    "value": provider,
                    "inline": True,
                }
            )

            # Exit reason
            exit_reason = llm_decision.get("exit_reason", "")
            if exit_reason:
                # Discord field values have a 1024 char limit, truncate to 200 chars
                exit_reason_display = (
                    exit_reason[:200] + "..." if len(exit_reason) > 200 else exit_reason
                )
                fields.append(
                    {
                        "name": "🚪 Exit Reason",
                        "value": exit_reason_display,
                        "inline": False,
                    }
                )

        # Leverage
        leverage = float(outcome.leverage) if outcome.leverage else 1.0
        if leverage > 1.0:
            fields.append(
                {
                    "name": "⚡ Leverage",
                    "value": f"{leverage:.1f}x",
                    "inline": True,
                }
            )

        # Signal ID reference
        signal_id = str(outcome.signal_id) if outcome.signal_id else "unknown"
        fields.append(
            {
                "name": "📋 Signal ID",
                "value": f"`{signal_id[:8]}...`",
                "inline": True,
            }
        )

        # Color based on PnL
        if pnl_float > 0:
            color = 0x00FF00  # Green for profit
        elif pnl_float < 0:
            color = 0xFF0000  # Red for loss
        else:
            color = 0x808080  # Gray for neutral

        # Timestamp
        timestamp = datetime.now(UTC).isoformat()

        # Footer with test indicator
        test_indicator = "🧪 " if outcome.is_test else ""
        footer_text = f"{test_indicator}Outcome ID: {str(outcome.outcome_id)[:8]}... | Paper Trading"

        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": timestamp,
            "footer": {"text": footer_text},
        }

    def _format_duration(self, duration: Any) -> str:
        """Format duration to human-readable string.

        Args:
            duration: timedelta or duration in milliseconds

        Returns:
            Formatted duration string
        """
        if hasattr(duration, "total_seconds"):
            # timedelta object
            total_seconds = int(duration.total_seconds())
        else:
            # Assume milliseconds
            total_seconds = int(duration) // 1000

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    async def _send_webhook_with_retry(
        self,
        payload: dict[str, Any],
        outcome: SignalOutcome,
    ) -> TradeNotificationResult:
        """Send payload to Discord webhook with exponential backoff retry.

        Args:
            payload: JSON payload to send
            outcome: SignalOutcome for logging context

        Returns:
            TradeNotificationResult with delivery status
        """
        retry_count = 0
        last_error = None

        while retry_count <= self.max_retries:
            try:
                result = await self._send_webhook(payload)

                if result.success:
                    return TradeNotificationResult(
                        success=True,
                        message_id=result.message_id,
                        timestamp=datetime.now(UTC),
                        retry_count=retry_count,
                    )

                # Check if we should retry
                if result.error and "Rate limited" in result.error:
                    # Rate limit - extract retry-after
                    last_error = result.error
                    retry_count += 1

                    if retry_count <= self.max_retries:
                        # Parse retry-after from error message
                        try:
                            retry_after = float(
                                result.error.split("Retry after ")[-1].split("s")[0]
                            )
                        except (IndexError, ValueError):
                            retry_after = self.retry_base_delay * (2**retry_count)

                        delay = min(retry_after, self.retry_max_delay)
                        logger.warning(
                            f"Rate limited, retrying in {delay}s "
                            f"(attempt {retry_count}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                else:
                    # Other error - use exponential backoff
                    last_error = result.error
                    retry_count += 1

                    if retry_count <= self.max_retries:
                        delay = min(
                            self.retry_base_delay * (2**retry_count),
                            self.retry_max_delay,
                        )
                        logger.warning(
                            f"Webhook failed, retrying in {delay}s "
                            f"(attempt {retry_count}/{self.max_retries}): {result.error}"
                        )
                        await asyncio.sleep(delay)
                        continue

            except Exception as e:
                last_error = str(e)
                retry_count += 1

                if retry_count <= self.max_retries:
                    delay = min(
                        self.retry_base_delay * (2**retry_count),
                        self.retry_max_delay,
                    )
                    logger.warning(
                        f"Exception during webhook, retrying in {delay}s "
                        f"(attempt {retry_count}/{self.max_retries}): {e}"
                    )
                    await asyncio.sleep(delay)
                    continue

        # All retries exhausted - log failure and queue to dead-letter
        logger.error(
            f"Failed to send notification after {retry_count} attempts: {last_error}"
        )

        # Log structured failure
        self._log_notification_failure(outcome, last_error, retry_count)

        # Queue to dead-letter for later retry
        dead_letter_queued = await self._queue_to_dead_letter(
            payload, outcome, last_error
        )

        return TradeNotificationResult(
            success=False,
            error=last_error,
            retry_count=retry_count,
            dead_letter_queued=dead_letter_queued,
        )

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
        # Append ?wait=true to get message ID in response
        if "?" in webhook_url:
            webhook_url_with_wait = f"{webhook_url}&wait=true"
        else:
            webhook_url_with_wait = f"{webhook_url}?wait=true"

        async with session.post(webhook_url_with_wait, json=payload) as resp:
            if resp.status == 200:
                # Success with wait=true - Discord returns message object
                try:
                    message_data = await resp.json()
                    message_id = message_data.get("id")
                    logger.info(
                        f"Trade notification sent successfully: message_id={message_id}"
                    )
                    return TradeNotificationResult(
                        success=True,
                        message_id=message_id,
                        timestamp=datetime.now(UTC),
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse Discord response: {e}")
                    return TradeNotificationResult(
                        success=True,
                        timestamp=datetime.now(UTC),
                    )
            elif resp.status == 204:
                # Success - Discord returns 204 No Content (no wait=true)
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

    def _log_notification_failure(
        self,
        outcome: SignalOutcome,
        error: str,
        retry_count: int,
    ) -> None:
        """Log structured notification failure.

        Args:
            outcome: SignalOutcome that failed to notify
            error: Error message
            retry_count: Number of retry attempts made
        """
        failure_log = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "ERROR",
            "event": "discord_notification_failed",
            "outcome_id": str(outcome.outcome_id),
            "signal_id": str(outcome.signal_id) if outcome.signal_id else None,
            "order_id": outcome.order_id,
            "symbol": outcome.symbol,
            "error": error,
            "retry_count": retry_count,
            "max_retries": self.max_retries,
            "webhook_configured": bool(self.webhook_url),
            "trading_channel_id": self.trading_channel_id,
        }

        # Log as JSON for structured logging
        logger.error(json.dumps(failure_log))

    async def _queue_to_dead_letter(
        self,
        payload: dict[str, Any],
        outcome: SignalOutcome,
        error: str,
    ) -> bool:
        """Queue failed notification to dead-letter queue in Redis.

        Args:
            payload: Original payload that failed
            outcome: SignalOutcome for context
            error: Error message

        Returns:
            True if successfully queued, False otherwise
        """
        try:
            redis = await self._get_redis()
            if redis is None:
                return False

            dead_letter_item = {
                "timestamp": datetime.now(UTC).isoformat(),
                "outcome_id": str(outcome.outcome_id),
                "signal_id": str(outcome.signal_id) if outcome.signal_id else None,
                "symbol": outcome.symbol,
                "payload": payload,
                "error": error,
                "retry_count": 0,
            }

            # Push to Redis list (dead-letter queue)
            queue_key = "chiseai:discord:dead_letter:trade_notifications"
            redis.lpush(queue_key, json.dumps(dead_letter_item))

            # Set TTL on queue (7 days)
            redis.expire(queue_key, 604800)

            logger.info(
                f"Queued failed notification to dead-letter queue: {outcome.outcome_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to queue to dead-letter: {e}")
            return False

    async def process_dead_letter_queue(
        self,
        max_items: int = 10,
    ) -> list[TradeNotificationResult]:
        """Process items from the dead-letter queue.

        Args:
            max_items: Maximum number of items to process

        Returns:
            List of TradeNotificationResult for each processed item
        """
        results = []

        try:
            redis = await self._get_redis()
            if redis is None:
                logger.warning("Redis not available for dead-letter processing")
                return results

            queue_key = "chiseai:discord:dead_letter:trade_notifications"

            for _ in range(max_items):
                # Pop from end of list (oldest first)
                item_json = redis.rpop(queue_key)
                if not item_json:
                    break

                try:
                    item = json.loads(item_json)
                    payload = item.get("payload", {})

                    # Attempt to resend
                    result = await self._send_webhook(payload)

                    if result.success:
                        logger.info(
                            f"Successfully resent dead-letter notification: "
                            f"{item.get('outcome_id')}"
                        )
                    else:
                        # Re-queue if still failing (with incremented retry count)
                        item["retry_count"] = item.get("retry_count", 0) + 1
                        if item["retry_count"] < 5:  # Max 5 dead-letter retries
                            redis.lpush(queue_key, json.dumps(item))
                            logger.warning(
                                f"Re-queued dead-letter item (retry {item['retry_count']}): "
                                f"{item.get('outcome_id')}"
                            )
                        else:
                            logger.error(
                                f"Dead-letter item exhausted retries: {item.get('outcome_id')}"
                            )

                    results.append(result)

                except Exception as e:
                    logger.error(f"Error processing dead-letter item: {e}")
                    results.append(
                        TradeNotificationResult(
                            success=False,
                            error=str(e),
                        )
                    )

        except Exception as e:
            logger.error(f"Error processing dead-letter queue: {e}")

        return results

    async def health_check(self) -> dict[str, Any]:
        """Check notifier health.

        Returns:
            Health status dictionary
        """
        # Check Discord connectivity
        discord_healthy = False
        discord_error = None

        if self.webhook_url:
            try:
                session = await self._get_session()
                async with session.get(self.webhook_url) as resp:
                    # Webhooks return 200 with webhook info on GET
                    discord_healthy = resp.status in (200, 401, 403)
            except Exception as e:
                discord_error = str(e)

        # Check dead-letter queue size
        dead_letter_size = 0
        try:
            redis = await self._get_redis()
            if redis:
                queue_key = "chiseai:discord:dead_letter:trade_notifications"
                dead_letter_size = redis.llen(queue_key) or 0
        except Exception:
            pass

        return {
            "healthy": self.webhook_url is not None and discord_healthy,
            "webhook_configured": self.webhook_url is not None,
            "trading_channel_id": self.trading_channel_id,
            "session_active": self._session is not None and not self._session.closed,
            "discord_reachable": discord_healthy,
            "discord_error": discord_error,
            "retry_config": {
                "max_retries": self.max_retries,
                "base_delay": self.retry_base_delay,
                "max_delay": self.retry_max_delay,
            },
            "dead_letter_queue": {
                "size": dead_letter_size,
                "healthy": dead_letter_size < 100,  # Alert if queue is large
            },
        }
