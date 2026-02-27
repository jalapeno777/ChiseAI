"""Outcome capture integration for execution hot path.

Integrates outcome persistence and alerting into the paper trading
execution pipeline, ensuring G4, G5, and G6 are satisfied.

For ST-FINAL-CLOSURE-001: Blocker Closure
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.alerts.integration import ExecutionAlertIntegration
    from execution.persistence.outcome_persistence import OutcomePersistence
    from execution.paper.models import PaperTradeResult

logger = logging.getLogger(__name__)


@dataclass
class OutcomeCaptureResult:
    """Result of outcome capture operation.

    Attributes:
        success: Whether capture succeeded
        outcome_id: Unique outcome identifier
        correlation_id: Correlation ID for tracing
        discord_message_id: Discord message ID if alerted
        persisted_to: Storage backend used
        errors: List of errors if any
    """

    success: bool
    outcome_id: str | None = None
    correlation_id: str | None = None
    discord_message_id: str | None = None
    persisted_to: str | None = None
    errors: list[str] | None = None


class OutcomeCaptureIntegration:
    """Integrates outcome capture into the execution hot path.

    Combines persistence (G4) and alerting (G5) into a single integration
    point that can be added to the paper trading orchestrator.

    Attributes:
        persistence: OutcomePersistence for canonical storage
        alerts: ExecutionAlertIntegration for Discord notifications
        enabled: Whether capture is enabled
    """

    def __init__(
        self,
        persistence: OutcomePersistence | None = None,
        alerts: ExecutionAlertIntegration | None = None,
        enabled: bool = True,
    ):
        """Initialize outcome capture integration.

        Args:
            persistence: OutcomePersistence instance (created if None)
            alerts: ExecutionAlertIntegration instance (created if None)
            enabled: Whether capture is enabled
        """
        self._persistence = persistence
        self._alerts = alerts
        self.enabled = enabled

        # Track capture statistics
        self._stats = {
            "signals_persisted": 0,
            "orders_persisted": 0,
            "fills_persisted": 0,
            "outcomes_persisted": 0,
            "open_alerts_sent": 0,
            "close_alerts_sent": 0,
            "errors": 0,
        }

        logger.info(f"OutcomeCaptureIntegration initialized: enabled={enabled}")

    def _get_persistence(self) -> OutcomePersistence:
        """Get or create OutcomePersistence."""
        if self._persistence is None:
            from execution.persistence.outcome_persistence import (
                OutcomePersistence,
            )

            self._persistence = OutcomePersistence()
        return self._persistence

    def _get_alerts(self) -> ExecutionAlertIntegration:
        """Get or create ExecutionAlertIntegration."""
        if self._alerts is None:
            from execution.alerts.integration import ExecutionAlertIntegration

            self._alerts = ExecutionAlertIntegration()
        return self._alerts

    async def on_trade_result(
        self,
        result: PaperTradeResult,
    ) -> dict[str, Any]:
        """Handle trade result - persists and alerts.

        This is the main integration point that should be called from
        the paper trading orchestrator after a trade is processed.

        Args:
            result: Paper trade result

        Returns:
            Capture result dictionary
        """
        if not self.enabled:
            return {"captured": False, "reason": "disabled"}

        capture_result = {
            "captured": True,
            "persistence": {},
            "alerts": {},
            "errors": [],
        }

        try:
            # G4: Persist to canonical storage
            persistence = self._get_persistence()
            persist_keys = persistence.persist_trade_result(result)
            capture_result["persistence"] = persist_keys

            # Update stats
            if persist_keys.get("signal"):
                self._stats["signals_persisted"] += 1
            if persist_keys.get("order"):
                self._stats["orders_persisted"] += 1
            if persist_keys.get("fill"):
                self._stats["fills_persisted"] += 1

            logger.debug(
                f"Persisted trade result: signal={persist_keys.get('signal') is not None}, "
                f"order={persist_keys.get('order') is not None}"
            )

        except Exception as e:
            logger.error(f"Failed to persist trade result: {e}")
            capture_result["errors"].append(f"persistence: {e}")
            self._stats["errors"] += 1

        try:
            # G5: Send Discord alerts
            alerts = self._get_alerts()
            alert_results = await alerts.on_trade_result(result)
            capture_result["alerts"] = alert_results

            # Update stats
            if alert_results.get("open", {}).get("sent"):
                self._stats["open_alerts_sent"] += 1
            if alert_results.get("close", {}).get("sent"):
                self._stats["close_alerts_sent"] += 1

        except Exception as e:
            logger.error(f"Failed to send alerts: {e}")
            capture_result["errors"].append(f"alerts: {e}")
            self._stats["errors"] += 1

        # Determine overall success
        capture_result["captured"] = len(capture_result["errors"]) == 0

        return capture_result

    async def on_position_closed(
        self,
        position: Any,
        realized_pnl: float,
        outcome: Any | None = None,
    ) -> dict[str, Any]:
        """Handle position closed event.

        Args:
            position: Closed position
            realized_pnl: Realized PnL
            outcome: Optional SignalOutcome

        Returns:
            Capture result dictionary
        """
        if not self.enabled:
            return {"captured": False, "reason": "disabled"}

        capture_result = {
            "captured": True,
            "alerts": {},
            "errors": [],
        }

        try:
            # Create outcome if not provided
            if outcome is None:
                outcome = self._create_outcome_from_position(position, realized_pnl)

            # Persist the outcome
            persistence = self._get_persistence()
            outcome_key = persistence.persist_outcome(outcome)
            capture_result["outcome_key"] = outcome_key

            if outcome_key:
                self._stats["outcomes_persisted"] += 1

            # Send close alert
            alerts = self._get_alerts()
            alert_result = await alerts.on_trade_closed(outcome, realized_pnl, position)
            capture_result["alerts"] = alert_result

            if alert_result.get("sent"):
                self._stats["close_alerts_sent"] += 1

        except Exception as e:
            logger.error(f"Failed to capture position close: {e}")
            capture_result["errors"].append(str(e))
            capture_result["captured"] = False
            self._stats["errors"] += 1

        return capture_result

    def _create_outcome_from_position(
        self,
        position: Any,
        realized_pnl: float,
    ) -> Any:
        """Create SignalOutcome from position data.

        Args:
            position: Position object
            realized_pnl: Realized PnL

        Returns:
            SignalOutcome instance
        """
        from decimal import Decimal
        from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        return SignalOutcome(
            order_id=position.position_id,
            symbol=position.symbol,
            side="Buy" if position.side == "long" else "Sell",
            direction=position.side.upper(),
            fill_price=Decimal(str(position.entry_price)),
            fill_quantity=Decimal(str(position.quantity)),
            entry_price=Decimal(str(position.entry_price)),
            exit_price=Decimal(str(position.exit_price))
            if hasattr(position, "exit_price")
            else None,
            position_size=Decimal(str(position.quantity)),
            pnl=Decimal(str(realized_pnl)),
            status=SignalOutcomeStatus.CLOSED,
            metadata=getattr(position, "metadata", {}),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get capture statistics.

        Returns:
            Statistics dictionary
        """
        return self._stats.copy()

    async def health_check(self) -> dict[str, Any]:
        """Check integration health.

        Returns:
            Health status dictionary
        """
        persistence_health = {}
        alerts_health = {}

        try:
            persistence = self._get_persistence()
            persistence_health = persistence.health_check()
        except Exception as e:
            persistence_health = {"error": str(e)}

        try:
            alerts = self._get_alerts()
            alerts_health = await alerts.health_check()
        except Exception as e:
            alerts_health = {"error": str(e)}

        return {
            "enabled": self.enabled,
            "healthy": (
                persistence_health.get("healthy", False)
                and alerts_health.get("enabled", False)
            ),
            "stats": self._stats,
            "persistence": persistence_health,
            "alerts": alerts_health,
        }
