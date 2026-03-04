"""Alert integration for execution hot path.

Integrates Discord trade alerts into the paper trading execution pipeline,
ensuring open alerts, close alerts, and recap messages are sent to #trading.

For ST-FINAL-CLOSURE-001: G5 - #trading Alert Routing Fully Active
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from execution.paper.models import PaperPosition, PaperTradeResult
    from ml.models.signal_outcome import SignalOutcome
logger = logging.getLogger(__name__)


class ExecutionAlertIntegration:
    """Integrates Discord alerts into the execution hot path.
    Coordinates trade notifications with the paper trading pipeline,
    ensuring all trade events generate appropriate Discord alerts.
    Attributes:
        trade_notifier: TradeNotifier instance for Discord webhooks
        alert_sender: AlertSender for signal-based alerts
        enabled: Whether alerts are enabled
    """

    def __init__(
        self,
        trade_notifier: Any | None = None,
        alert_sender: Any | None = None,
        enabled: bool = True,
    ):
        """Initialize execution alert integration.
        Args:
            trade_notifier: TradeNotifier for trade open/close alerts
            alert_sender: AlertSender for signal alerts
            enabled: Whether to send alerts
        """
        self._trade_notifier = trade_notifier
        self._alert_sender = alert_sender
        self.enabled = enabled
        # Track alert statistics
        self._stats = {
            "open_alerts_sent": 0,
            "close_alerts_sent": 0,
            "recap_alerts_sent": 0,
            "errors": 0,
        }
        logger.info(
            f"ExecutionAlertIntegration initialized: enabled={enabled}, "
            f"trade_notifier={trade_notifier is not None}, "
            f"alert_sender={alert_sender is not None}"
        )

    def _get_trade_notifier(self) -> Any:
        """Get or create TradeNotifier."""
        if self._trade_notifier is None:
            from discord_alerts.trade_notifier import TradeNotifier

            self._trade_notifier = TradeNotifier()
        return self._trade_notifier

    def _get_alert_sender(self) -> Any:
        """Get or create AlertSender."""
        if self._alert_sender is None:
            from discord_alerts.alert_sender import AlertSender
            from discord_alerts.config import DiscordConfig

            config = DiscordConfig.from_env()
            self._alert_sender = AlertSender(config)
        return self._alert_sender

    async def on_signal_received(
        self,
        signal: Any,
        result: PaperTradeResult | None = None,
    ) -> dict[str, Any]:
        """Handle signal received event.
        Args:
            signal: Trading signal
            result: Optional trade result if signal was processed
        Returns:
            Alert result dictionary
        """
        if not self.enabled:
            return {"sent": False, "reason": "disabled"}
        try:
            alert_sender = self._get_alert_sender()
            send_result = await alert_sender.send_signal(signal)
            return {
                "sent": send_result.success,
                "message_id": send_result.message_id,
                "channel": send_result.channel,
                "error": send_result.error,
                "suppressed": send_result.suppressed,
            }
        except Exception as e:
            logger.error(f"Failed to send signal alert: {e}")
            self._stats["errors"] += 1
            return {"sent": False, "error": str(e)}

    async def on_trade_opened(
        self,
        outcome: SignalOutcome,
        position: PaperPosition | None = None,
    ) -> dict[str, Any]:
        """Handle trade opened event.
        Sends a Discord notification to #trading when a position is opened.
        Args:
            outcome: Signal outcome for the opened trade
            position: Optional position details
        Returns:
            Alert result dictionary
        """
        if not self.enabled:
            return {"sent": False, "reason": "disabled"}
        try:
            trade_notifier = self._get_trade_notifier()
            # Extract LLM decision from outcome metadata if available
            llm_decision = None
            if outcome.metadata and "llm_decision" in outcome.metadata:
                llm_meta = outcome.metadata["llm_decision"]
                llm_decision = {
                    "decision": llm_meta.get("decision"),
                    "confidence": llm_meta.get("confidence"),
                    "provider": llm_meta.get("provider"),
                    "rationale": llm_meta.get("rationale"),
                    "position_size": llm_meta.get("position_size"),
                    "stop_loss": llm_meta.get("stop_loss"),
                    "take_profit": llm_meta.get("take_profit"),
                }
            result = await trade_notifier.send_trade_open_notification(
                outcome, llm_decision
            )
            if result.success:
                self._stats["open_alerts_sent"] += 1
                logger.info(
                    f"Trade open alert sent: {outcome.symbol} "
                    f"(message_id={result.message_id})"
                )
            else:
                logger.warning(f"Trade open alert failed: {result.error}")
            return {
                "sent": result.success,
                "message_id": result.message_id,
                "error": result.error,
                "dead_letter_queued": result.dead_letter_queued,
            }
        except Exception as e:
            logger.error(f"Failed to send trade open alert: {e}")
            self._stats["errors"] += 1
            return {"sent": False, "error": str(e)}

    async def on_trade_closed(
        self,
        outcome: SignalOutcome,
        realized_pnl: float,
        position: PaperPosition | None = None,
    ) -> dict[str, Any]:
        """Handle trade closed event.
        Sends a Discord notification to #trading when a position is closed.
        Args:
            outcome: Signal outcome for the closed trade
            realized_pnl: Realized PnL from the trade
            position: Optional position details
        Returns:
            Alert result dictionary
        """
        if not self.enabled:
            return {"sent": False, "reason": "disabled"}
        try:
            # Update outcome with PnL if not set
            if outcome.pnl is None:
                from decimal import Decimal

                outcome.pnl = Decimal(str(realized_pnl))
            trade_notifier = self._get_trade_notifier()
            # Extract LLM decision from outcome metadata if available
            llm_decision = None
            if outcome.metadata and "llm_decision" in outcome.metadata:
                llm_decision = {
                    "decision": outcome.metadata.get("decision"),
                    "confidence": outcome.metadata.get("confidence"),
                    "provider": outcome.metadata.get("provider"),
                    "rationale": outcome.metadata.get("rationale"),
                    "position_size": outcome.metadata.get("position_size"),
                    "stop_loss": outcome.metadata.get("stop_loss"),
                    "take_profit": outcome.metadata.get("take_profit"),
                    "exit_reason": outcome.metadata.get("exit_reason"),
                    "realized_pnl": outcome.metadata.get("realized_pnl"),
                }
            result = await trade_notifier.send_trade_close_notification(
                outcome, llm_decision
            )
            if result.success:
                self._stats["close_alerts_sent"] += 1
                logger.info(
                    f"Trade close alert sent: {outcome.symbol} PnL={realized_pnl:.4f} "
                    f"(message_id={result.message_id})"
                )
            else:
                logger.warning(f"Trade close alert failed: {result.error}")
            return {
                "sent": result.success,
                "message_id": result.message_id,
                "error": result.error,
                "dead_letter_queued": result.dead_letter_queued,
            }
        except Exception as e:
            logger.error(f"Failed to send trade close alert: {e}")
            self._stats["errors"] += 1
            return {"sent": False, "error": str(e)}

    async def on_trade_result(
        self,
        result: PaperTradeResult,
    ) -> dict[str, Any]:
        """Handle complete trade result.
        Sends appropriate alerts based on trade status.
        Args:
            result: Paper trade result
        Returns:
            Alert result dictionary
        """
        from execution.paper.models import TradeStatus

        alerts = {
            "signal": None,
            "open": None,
            "close": None,
        }
        # Send signal alert
        if result.signal:
            alerts["signal"] = await self.on_signal_received(result.signal, result)
        # Send trade open/close alerts based on status
        if result.status == TradeStatus.EXECUTED:
            if result.position:
                # Create outcome from result for notification
                outcome = self._create_outcome_from_result(result)
                alerts["open"] = await self.on_trade_opened(outcome, result.position)
        return alerts

    def _create_outcome_from_result(self, result: PaperTradeResult) -> Any:
        """Create SignalOutcome from PaperTradeResult.
        Args:
            result: Paper trade result
        Returns:
            SignalOutcome instance
        """
        from decimal import Decimal
        from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        signal = result.signal
        order = result.order
        position = result.position
        return SignalOutcome(
            signal_id=UUID(signal.signal_id) if signal else None,
            order_id=order.order_id if order else "",
            symbol=order.symbol if order else (signal.token if signal else ""),
            side="Buy" if signal and signal.direction.value == "long" else "Sell",
            direction=signal.direction.value.upper() if signal else "",
            fill_price=Decimal(str(order.avg_fill_price)) if order else Decimal("0"),
            fill_quantity=(
                Decimal(str(order.filled_quantity)) if order else Decimal("0")
            ),
            entry_price=(
                Decimal(str(position.entry_price)) if position else Decimal("0")
            ),
            position_size=Decimal(str(position.quantity)) if position else Decimal("0"),
            status=SignalOutcomeStatus.FILLED,
            metadata={
                "correlation_id": result.correlation_id,
                "signal_confidence": signal.confidence if signal else 0,
            },
        )

    async def send_recap(self, period: str, summary: dict[str, Any]) -> dict[str, Any]:
        """Send trading recap to #trading channel.
        Args:
            period: Period description (e.g., "daily", "weekly")
            summary: Trading summary dictionary
        Returns:
            Alert result dictionary
        """
        if not self.enabled:
            return {"sent": False, "reason": "disabled"}
        try:
            # Build recap embed
            embed = self._build_recap_embed(period, summary)
            payload = {"embeds": [embed]}
            trade_notifier = self._get_trade_notifier()
            result = await trade_notifier._send_webhook(payload)
            if result.success:
                self._stats["recap_alerts_sent"] += 1
                logger.info(f"Recap alert sent: {period}")
            else:
                logger.warning(f"Recap alert failed: {result.error}")
            return {
                "sent": result.success,
                "message_id": result.message_id,
                "error": result.error,
            }
        except Exception as e:
            logger.error(f"Failed to send recap alert: {e}")
            self._stats["errors"] += 1
            return {"sent": False, "error": str(e)}

    def _build_recap_embed(
        self, period: str, summary: dict[str, Any]
    ) -> dict[str, Any]:
        """Build Discord embed for trading recap.
        Args:
            period: Period description
            summary: Trading summary
        Returns:
            Discord embed dictionary
        """
        from datetime import UTC, datetime

        # Extract summary data
        total_trades = summary.get("total_trades", 0)
        winning_trades = summary.get("winning_trades", 0)
        losing_trades = summary.get("losing_trades", 0)
        total_pnl = summary.get("total_pnl", 0.0)
        win_rate = summary.get("win_rate", 0.0)
        # Determine PnL emoji
        if total_pnl > 0:
            pnl_emoji = "🟢"
            color = 0x00FF00
        elif total_pnl < 0:
            pnl_emoji = "🔴"
            color = 0xFF0000
        else:
            pnl_emoji = "⚪"
            color = 0x808080
        # Title
        title = f"📊 {period.title()} Trading Recap"
        # Description
        pnl_prefix = "+" if total_pnl > 0 else ""
        description = f"{pnl_emoji} **Total PnL:** {pnl_prefix}${total_pnl:,.2f}"
        # Fields
        fields = [
            {
                "name": "📈 Total Trades",
                "value": str(total_trades),
                "inline": True,
            },
            {
                "name": "🏆 Win Rate",
                "value": f"{win_rate:.1f}%",
                "inline": True,
            },
            {
                "name": "✅ Winning",
                "value": str(winning_trades),
                "inline": True,
            },
            {
                "name": "❌ Losing",
                "value": str(losing_trades),
                "inline": True,
            },
        ]
        # Timestamp
        timestamp = datetime.now(UTC).isoformat()
        return {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "timestamp": timestamp,
            "footer": {"text": "Paper Trading Recap"},
        }

    def get_stats(self) -> dict[str, Any]:
        """Get alert integration statistics.
        Returns:
            Statistics dictionary
        """
        return self._stats.copy()

    async def health_check(self) -> dict[str, Any]:
        """Check alert integration health.
        Returns:
            Health status dictionary
        """
        trade_notifier_health = {}
        alert_sender_health = {}
        try:
            if self._trade_notifier:
                trade_notifier_health = await self._trade_notifier.health_check()
        except Exception as e:
            trade_notifier_health = {"error": str(e)}
        try:
            if self._alert_sender:
                alert_sender_health = await self._alert_sender.health_check()
        except Exception as e:
            alert_sender_health = {"error": str(e)}
        return {
            "enabled": self.enabled,
            "stats": self._stats,
            "trade_notifier": trade_notifier_health,
            "alert_sender": alert_sender_health,
        }
