"""Outcome capture integration for execution hot path.

Integrates outcome persistence and alerting into the paper trading
execution pipeline, ensuring G4, G5, and G6 are satisfied.

For ST-FINAL-CLOSURE-001: Blocker Closure
"""

from __future__ import annotations

import logging
import numbers
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ml.models.signal_outcome import OutcomeType

if TYPE_CHECKING:
    from execution.alerts.integration import ExecutionAlertIntegration
    from execution.paper.models import PaperTradeResult
    from execution.persistence.outcome_persistence import OutcomePersistence

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
        connector_provenance: Provenance info from the connector for SignalOutcome
    """

    def __init__(
        self,
        persistence: OutcomePersistence | None = None,
        alerts: ExecutionAlertIntegration | None = None,
        enabled: bool = True,
        connector_provenance: dict[str, str] | None = None,
    ):
        """Initialize outcome capture integration.

        Args:
            persistence: OutcomePersistence instance (created if None)
            alerts: ExecutionAlertIntegration instance (created if None)
            enabled: Whether capture is enabled
            connector_provenance: Optional provenance dict from connector
        """
        self._persistence = persistence
        self._alerts = alerts
        self.enabled = enabled
        # PAPER-FORENSIC-001: Store connector provenance for SignalOutcome population
        self._connector_provenance = connector_provenance or {}

        # Track capture statistics
        self._stats = {
            "signals_persisted": 0,
            "orders_persisted": 0,
            "fills_persisted": 0,
            "outcomes_persisted": 0,
            "open_alerts_sent": 0,
            "close_alerts_sent": 0,
            "rejections_captured": 0,
            "errors": 0,
        }

        logger.info(
            f"OutcomeCaptureIntegration initialized: enabled={enabled}, "
            f"provenance={self._connector_provenance}"
        )

    def set_connector_provenance(self, provenance: dict[str, str]) -> None:
        """Set connector provenance information.

        PAPER-FORENSIC-001: Allows the orchestrator to set provenance info
        after initialization so SignalOutcome objects get populated correctly.

        Args:
            provenance: Dictionary with execution_venue, execution_mode, execution_source
        """
        self._connector_provenance = provenance or {}
        logger.info(f"[OUTCOME-CAPTURE] Connector provenance set: {provenance}")

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

    async def on_trade_open(
        self,
        outcome: Any,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle trade open event - persists PENDING SignalOutcome.

        Records that a trade was opened with PENDING outcome status.
        This is the integration point called from the paper trading
        orchestrator after a position is opened.

        Args:
            outcome: SignalOutcome with PENDING status
            correlation_id: Correlation ID for tracing

        Returns:
            Capture result dictionary
        """
        if not self.enabled:
            return {"captured": False, "reason": "disabled"}

        capture_result: dict[str, Any] = {
            "captured": True,
            "outcome_key": None,
            "alerts": {},
            "errors": [],
        }

        try:
            # Persist the PENDING outcome to Redis and sync to PostgreSQL
            persistence = self._get_persistence()
            outcome_key = await persistence.persist_outcome_async(
                outcome, correlation_id
            )
            capture_result["outcome_key"] = outcome_key

            if outcome_key:
                self._stats["outcomes_persisted"] += 1

            logger.debug(
                f"[OUTCOME-OPEN] Persisted trade open outcome: "
                f"outcome_id={outcome.outcome_id} symbol={outcome.symbol} "
                f"key={outcome_key} (correlation_id={correlation_id})"
            )

        except Exception as e:
            logger.error(f"Failed to persist trade open outcome: {e}")
            capture_result["errors"].append(str(e))
            capture_result["captured"] = False
            self._stats["errors"] += 1

        try:
            # G5: Send open alert
            alerts = self._get_alerts()
            alert_result = await alerts.on_trade_opened(outcome)
            capture_result["alerts"] = alert_result

            if alert_result.get("sent"):
                self._stats["open_alerts_sent"] += 1

        except Exception as e:
            logger.error(f"Failed to send open alert: {e}")
            capture_result["errors"].append(str(e))
            self._stats["errors"] += 1

        capture_result["captured"] = len(capture_result["errors"]) == 0
        return capture_result

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
        exit_price: float | None = None,
        reason: str = "manual",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle position closed event.

        Args:
            position: Closed position
            realized_pnl: Realized PnL
            outcome: Optional SignalOutcome
            exit_price: Exit price (for outcome creation)
            reason: Reason for closure
            correlation_id: Correlation ID for tracing

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
                outcome = self._create_outcome_from_position(
                    position, realized_pnl, exit_price
                )

            # Persist the outcome to Redis AND sync to PostgreSQL (async)
            persistence = self._get_persistence()
            outcome_key = await persistence.persist_outcome_async(
                outcome, correlation_id
            )
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

    # Alias for backward compatibility with orchestrator
    on_position_close = on_position_closed

    async def on_signal_rejected(
        self,
        signal: Any,
        gate_id: str,
        reason: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Record a signal rejection from a gate.

        Persists a lightweight SignalOutcome with ERROR status and rejection
        metadata so the outcome pipeline has full observability into why
        signals were rejected.

        Args:
            signal: The rejected signal (or signal dict).
            gate_id: Identifier of the rejection gate (e.g. "G1_THROTTLE").
            reason: Human-readable rejection reason.
            correlation_id: Correlation ID for tracing.

        Returns:
            Capture result dictionary.
        """
        if not self.enabled:
            return {"captured": False, "reason": "disabled"}

        capture_result: dict[str, Any] = {
            "captured": True,
            "gate_id": gate_id,
            "errors": [],
        }

        try:
            from decimal import Decimal

            from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

            symbol = getattr(signal, "token", None) or signal.get("token", "unknown")
            direction = getattr(signal, "direction", None) or signal.get(
                "direction", "unknown"
            )

            provenance = self._connector_provenance
            now = datetime.now(tz=UTC)

            side = "Buy" if str(direction).lower() == "long" else "Sell"
            outcome = SignalOutcome(
                order_id=correlation_id or uuid.uuid4().hex[:12],
                symbol=symbol,
                side=side,
                direction=str(direction).upper(),
                fill_price=Decimal("0"),
                fill_quantity=Decimal("0"),
                entry_price=Decimal("0"),
                exit_price=None,
                position_size=Decimal("0"),
                pnl=Decimal("0"),
                outcome_type=OutcomeType.UNKNOWN,
                exit_time=now,
                fee=None,
                status=SignalOutcomeStatus.ERROR,
                metadata={
                    "rejection_gate": gate_id,
                    "rejection_reason": reason,
                    "correlation_id": correlation_id,
                },
                execution_venue=provenance.get("execution_venue", ""),
                execution_mode=provenance.get("execution_mode", ""),
                execution_source=provenance.get("execution_source", ""),
            )

            persistence = self._get_persistence()
            outcome_key = await persistence.persist_outcome_async(
                outcome, correlation_id
            )
            capture_result["outcome_key"] = outcome_key

            if outcome_key:
                self._stats["rejections_captured"] += 1

            logger.info(
                f"[OUTCOME-CAPTURE] Signal rejected at {gate_id}: "
                f"symbol={symbol}, reason={reason}, "
                f"correlation_id={correlation_id}"
            )

        except Exception as e:
            logger.error(f"Failed to capture signal rejection: {e}")
            capture_result["errors"].append(str(e))
            capture_result["captured"] = False
            self._stats["errors"] += 1

        return capture_result

    def _classify_outcome_type(
        self,
        signal: dict[str, Any],
        exit_price: float,
        direction: str,
    ) -> OutcomeType:
        """Classify outcome as TP_HIT, SL_HIT, or MANUAL_CLOSE.

        Args:
            signal: Signal metadata dict with take_profit_price and stop_loss_price
            exit_price: Exit price
            direction: Position direction ("LONG" or "SHORT")

        Returns:
            OutcomeType classification
        """
        if signal is None:
            return OutcomeType.UNKNOWN

        tp_price = signal.get("take_profit_price") or signal.get("take_profit")
        sl_price = signal.get("stop_loss_price") or signal.get("stop_loss")

        if direction == "LONG":
            if tp_price and exit_price >= float(tp_price):
                return OutcomeType.TP_HIT
            elif sl_price and exit_price <= float(sl_price):
                return OutcomeType.SL_HIT
        else:  # SHORT
            if tp_price and exit_price <= float(tp_price):
                return OutcomeType.TP_HIT
            elif sl_price and exit_price >= float(sl_price):
                return OutcomeType.SL_HIT

        return OutcomeType.MANUAL_CLOSE

    def _create_outcome_from_position(
        self,
        position: Any,
        realized_pnl: float,
        exit_price: float | None = None,
    ) -> Any:
        """Create SignalOutcome from position data.

        Args:
            position: Position object
            realized_pnl: Realized PnL
            exit_price: Exit price (optional, uses position.exit_price if not provided)

        Returns:
            SignalOutcome instance
        """
        from decimal import Decimal

        from ml.models.signal_outcome import SignalOutcome, SignalOutcomeStatus

        # Use provided exit_price or fall back to position attribute
        final_exit_price = exit_price
        if final_exit_price is None:
            pos_exit_price = getattr(position, "exit_price", None)
            # Only use if it's a real number (rejects MagicMock, str, dict, etc.)
            if pos_exit_price is not None and isinstance(pos_exit_price, numbers.Real):
                final_exit_price = pos_exit_price

        # PAPER-FORENSIC-001: Populate provenance fields from connector
        provenance = self._connector_provenance
        execution_venue = provenance.get("execution_venue", "")
        execution_mode = provenance.get("execution_mode", "")
        execution_source = provenance.get("execution_source", "")

        logger.debug(
            f"[OUTCOME-CREATE] Creating SignalOutcome with provenance: "
            f"venue={execution_venue}, mode={execution_mode}, source={execution_source}"
        )

        # Normalize position metadata: None → {} for consistent dict access.
        # Preserves explicit None for MANUAL_CLOSE classification below.
        raw_metadata = getattr(position, "metadata", None)
        position_metadata = raw_metadata or {}
        signal_data = {
            "take_profit_price": position_metadata.get("take_profit"),
            "stop_loss_price": position_metadata.get("stop_loss"),
            "direction": position.side.upper(),
        }

        # Classify outcome type based on exit price vs TP/SL levels
        position_direction = position.side.upper()
        outcome_type = OutcomeType.UNKNOWN
        if final_exit_price is not None:
            outcome_type = self._classify_outcome_type(
                signal_data, float(final_exit_price), position_direction
            )

        # Position without metadata always results in MANUAL_CLOSE
        if raw_metadata is None:
            outcome_type = OutcomeType.MANUAL_CLOSE

        # Calculate fee from position metadata or use default rate
        fee_rate = position_metadata.get("fee_rate", 0.001)  # 0.1% default
        exit_time = datetime.now(tz=UTC)
        fee = None
        if final_exit_price is not None:
            fee = (
                Decimal(str(final_exit_price))
                * Decimal(str(position.quantity))
                * Decimal(str(fee_rate))
            )

        return SignalOutcome(
            order_id=position.position_id,
            symbol=position.symbol,
            side="Buy" if position.side == "long" else "Sell",
            direction=position_direction,
            fill_price=Decimal(str(position.entry_price)),
            fill_quantity=Decimal(str(position.quantity)),
            entry_price=Decimal(str(position.entry_price)),
            exit_price=(
                Decimal(str(final_exit_price)) if final_exit_price is not None else None
            ),
            position_size=Decimal(str(position.quantity)),
            pnl=Decimal(str(realized_pnl)),
            outcome_type=outcome_type,
            exit_time=exit_time,
            fee=fee,
            status=SignalOutcomeStatus.CLOSED,
            metadata=position_metadata,
            # PAPER-FORENSIC-001: Populate provenance fields
            execution_venue=execution_venue,
            execution_mode=execution_mode,
            execution_source=execution_source,
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
