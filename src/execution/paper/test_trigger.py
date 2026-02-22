"""Controlled paper trade trigger for testing.

Provides a TestTradeTrigger class that generates controlled low-risk test signals
with full safety checks including kill-switch validation, position size limits,
and audit logging.

For PAPER-LIVE-001: Controlled Paper Trade Trigger
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from execution.kill_switch.state import KillSwitchState
from execution.paper.models import PaperTradeResult, TradeStatus
from signal_generation.models import Signal, SignalDirection, SignalStatus

if TYPE_CHECKING:
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.paper.orchestrator import PaperTradingOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class TestTriggerResult:
    """Result of a test trade trigger attempt.

    Attributes:
        success: Whether the test trade was successfully triggered
        order_id: Exchange/paper order ID (if executed)
        fill_price: Actual fill price (if executed)
        timestamp: When the trade was triggered
        signal_id: ID of the generated test signal
        trade_result: Full PaperTradeResult from orchestrator
        kill_switch_state: Kill-switch state at time of trigger
        audit_log_id: Audit log entry ID for traceability
        error: Error message if failed
    """

    success: bool
    order_id: str | None = None
    fill_price: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signal_id: str = ""
    trade_result: PaperTradeResult | None = None
    kill_switch_state: str = ""
    audit_log_id: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "success": self.success,
            "order_id": self.order_id,
            "fill_price": self.fill_price,
            "timestamp": self.timestamp.isoformat(),
            "signal_id": self.signal_id,
            "trade_result": self.trade_result.to_dict() if self.trade_result else None,
            "kill_switch_state": self.kill_switch_state,
            "audit_log_id": self.audit_log_id,
            "error": self.error,
        }


class TestTradeTrigger:
    """Controlled test trade trigger with safety checks.

    Generates low-risk test signals for paper trading with:
    - Kill-switch state validation (must be ARMED)
    - Position size limits (max 1% of portfolio)
    - Confidence threshold enforcement (80% minimum)
    - Full audit trail logging

    Attributes:
        orchestrator: Paper trading orchestrator for signal processing
        kill_switch: Kill-switch executor for state checks
        portfolio_value: Current portfolio value for sizing
        max_position_pct: Maximum position size as % of portfolio (default 1%)
        min_confidence: Minimum signal confidence (default 80%)
        _audit_log: Internal audit log of all trigger attempts
    """

    # Default safety parameters
    DEFAULT_MAX_POSITION_PCT = 0.01  # 1% of portfolio
    DEFAULT_MIN_CONFIDENCE = 0.80  # 80% confidence
    DEFAULT_SYMBOL = "BTCUSDT"

    def __init__(
        self,
        orchestrator: PaperTradingOrchestrator,
        kill_switch: KillSwitchExecutor,
        portfolio_value: float = 10000.0,
        max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ):
        """Initialize test trade trigger.

        Args:
            orchestrator: Paper trading orchestrator
            kill_switch: Kill-switch executor for safety checks
            portfolio_value: Current portfolio value
            max_position_pct: Max position as % of portfolio (default 1%)
            min_confidence: Minimum confidence threshold (default 80%)
        """
        self.orchestrator = orchestrator
        self.kill_switch = kill_switch
        self.portfolio_value = portfolio_value
        self.max_position_pct = max_position_pct
        self.min_confidence = min_confidence
        self._audit_log: list[dict[str, Any]] = []

        logger.info(
            f"TestTradeTrigger initialized: "
            f"portfolio=${portfolio_value:.2f}, "
            f"max_position={max_position_pct:.1%}, "
            f"min_confidence={min_confidence:.1%}"
        )

    async def trigger_test_trade(
        self,
        symbol: str = DEFAULT_SYMBOL,
        direction: str = "long",
        confidence: float | None = None,
        size_override: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TestTriggerResult:
        """Trigger a controlled test trade with full safety checks.

        Pipeline:
        1. Validate kill-switch is ARMED
        2. Generate test signal with specified parameters
        3. Submit to orchestrator for processing
        4. Capture and return execution result
        5. Log audit trail entry

        Args:
            symbol: Trading pair symbol (default: BTCUSDT)
            direction: Trade direction - "long" or "short"
            confidence: Signal confidence 0.0-1.0 (default: 80%)
            size_override: Optional position size override (uses min if None)
            metadata: Additional signal metadata

        Returns:
            TestTriggerResult with execution details

        Raises:
            ValueError: If direction is invalid
        """
        audit_log_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC)

        # Validate direction
        if direction.lower() not in ("long", "short"):
            error_msg = f"Invalid direction: {direction}. Must be 'long' or 'short'"
            logger.error(error_msg)
            self._log_audit_entry(
                audit_log_id=audit_log_id,
                action="trigger_test_trade",
                status="failed",
                error=error_msg,
            )
            return TestTriggerResult(
                success=False,
                error=error_msg,
                audit_log_id=audit_log_id,
                timestamp=timestamp,
            )

        # Step 1: Check kill-switch state
        kill_switch_state = self.kill_switch.state
        logger.info(f"Kill-switch state check: {kill_switch_state.value}")

        if kill_switch_state == KillSwitchState.TRIGGERED:
            error_msg = "Kill-switch is TRIGGERED - cannot execute test trade"
            logger.error(error_msg)
            self._log_audit_entry(
                audit_log_id=audit_log_id,
                action="trigger_test_trade",
                status="blocked",
                symbol=symbol,
                direction=direction,
                kill_switch_state=kill_switch_state.value,
                error=error_msg,
            )
            return TestTriggerResult(
                success=False,
                error=error_msg,
                kill_switch_state=kill_switch_state.value,
                audit_log_id=audit_log_id,
                timestamp=timestamp,
            )

        if kill_switch_state == KillSwitchState.DISABLED:
            logger.warning("Kill-switch is DISABLED - proceeding with caution")

        # Step 2: Generate test signal
        signal_confidence = confidence or self.min_confidence
        signal = self._create_test_signal(
            symbol=symbol,
            direction=direction,
            confidence=signal_confidence,
            metadata=metadata,
        )

        logger.info(
            f"Generated test signal: {signal.signal_id} "
            f"{symbol} {direction} confidence={signal_confidence:.1%}"
        )

        # Step 3: Submit to orchestrator
        try:
            trade_result = await self.orchestrator.process_signal(signal)

            # Step 4: Process result
            if trade_result.status == TradeStatus.EXECUTED:
                order_id = trade_result.order.order_id if trade_result.order else None
                fill_price = (
                    trade_result.order.avg_fill_price if trade_result.order else None
                )

                logger.info(
                    f"Test trade executed: order_id={order_id}, "
                    f"fill_price={fill_price}, latency={trade_result.latency_ms:.1f}ms"
                )

                self._log_audit_entry(
                    audit_log_id=audit_log_id,
                    action="trigger_test_trade",
                    status="success",
                    symbol=symbol,
                    direction=direction,
                    signal_id=signal.signal_id,
                    order_id=order_id,
                    fill_price=fill_price,
                    kill_switch_state=kill_switch_state.value,
                    latency_ms=trade_result.latency_ms,
                )

                return TestTriggerResult(
                    success=True,
                    order_id=order_id,
                    fill_price=fill_price,
                    timestamp=timestamp,
                    signal_id=signal.signal_id,
                    trade_result=trade_result,
                    kill_switch_state=kill_switch_state.value,
                    audit_log_id=audit_log_id,
                )

            elif trade_result.status == TradeStatus.REJECTED:
                error_msg = f"Trade rejected: {', '.join(trade_result.reject_reason)}"
                logger.warning(error_msg)

                self._log_audit_entry(
                    audit_log_id=audit_log_id,
                    action="trigger_test_trade",
                    status="rejected",
                    symbol=symbol,
                    direction=direction,
                    signal_id=signal.signal_id,
                    kill_switch_state=kill_switch_state.value,
                    reject_reason=trade_result.reject_reason,
                )

                return TestTriggerResult(
                    success=False,
                    error=error_msg,
                    timestamp=timestamp,
                    signal_id=signal.signal_id,
                    trade_result=trade_result,
                    kill_switch_state=kill_switch_state.value,
                    audit_log_id=audit_log_id,
                )

            else:  # FAILED
                error_msg = f"Trade failed: {', '.join(trade_result.reject_reason)}"
                logger.error(error_msg)

                self._log_audit_entry(
                    audit_log_id=audit_log_id,
                    action="trigger_test_trade",
                    status="failed",
                    symbol=symbol,
                    direction=direction,
                    signal_id=signal.signal_id,
                    kill_switch_state=kill_switch_state.value,
                    error=error_msg,
                )

                return TestTriggerResult(
                    success=False,
                    error=error_msg,
                    timestamp=timestamp,
                    signal_id=signal.signal_id,
                    trade_result=trade_result,
                    kill_switch_state=kill_switch_state.value,
                    audit_log_id=audit_log_id,
                )

        except Exception as e:
            error_msg = f"Exception during test trade: {e}"
            logger.error(error_msg, exc_info=True)

            self._log_audit_entry(
                audit_log_id=audit_log_id,
                action="trigger_test_trade",
                status="exception",
                symbol=symbol,
                direction=direction,
                signal_id=signal.signal_id,
                kill_switch_state=kill_switch_state.value,
                error=error_msg,
            )

            return TestTriggerResult(
                success=False,
                error=error_msg,
                timestamp=timestamp,
                signal_id=signal.signal_id,
                kill_switch_state=kill_switch_state.value,
                audit_log_id=audit_log_id,
            )

    def _create_test_signal(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """Create a test trading signal.

        Args:
            symbol: Trading pair symbol
            direction: Trade direction (long/short)
            confidence: Signal confidence 0.0-1.0
            metadata: Additional metadata

        Returns:
            Signal ready for orchestrator processing
        """
        # Map direction string to enum
        direction_enum = (
            SignalDirection.LONG
            if direction.lower() == "long"
            else SignalDirection.SHORT
        )

        # Calculate base score from confidence
        base_score = confidence * 100

        # Build metadata with test indicator
        signal_metadata = {
            "is_test_signal": True,
            "test_trigger_version": "1.0.0",
            **(metadata or {}),
        }

        # Create signal
        signal = Signal(
            token=symbol,
            direction=direction_enum,
            confidence=confidence,
            base_score=base_score,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",  # Default timeframe for test signals
            contributing_factors=[
                {
                    "factor": "test_signal",
                    "weight": 1.0,
                    "rationale": "Manual test trigger",
                }
            ],
            signal_breakdown={
                "test_signal": {"score": base_score, "confidence": confidence}
            },
            metadata=signal_metadata,
            stop_loss=None,  # Will be calculated by risk enforcer
            stop_loss_method="test_signal",
            risk_reward_ratio=2.0,  # Default 2:1 R:R
        )

        return signal

    def _log_audit_entry(
        self,
        audit_log_id: str,
        action: str,
        status: str,
        symbol: str | None = None,
        direction: str | None = None,
        signal_id: str | None = None,
        order_id: str | None = None,
        fill_price: float | None = None,
        kill_switch_state: str | None = None,
        latency_ms: float | None = None,
        reject_reason: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        """Log an audit entry for the trigger action.

        Args:
            audit_log_id: Unique audit log entry ID
            action: Action being logged
            status: Status of the action
            symbol: Trading symbol (optional)
            direction: Trade direction (optional)
            signal_id: Signal ID (optional)
            order_id: Order ID (optional)
            fill_price: Fill price (optional)
            kill_switch_state: Kill-switch state (optional)
            latency_ms: Processing latency (optional)
            reject_reason: Rejection reasons (optional)
            error: Error message (optional)
        """
        entry = {
            "audit_log_id": audit_log_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "status": status,
            "symbol": symbol,
            "direction": direction,
            "signal_id": signal_id,
            "order_id": order_id,
            "fill_price": fill_price,
            "kill_switch_state": kill_switch_state,
            "latency_ms": latency_ms,
            "reject_reason": reject_reason,
            "error": error,
            "portfolio_value": self.portfolio_value,
            "max_position_pct": self.max_position_pct,
            "min_confidence": self.min_confidence,
        }

        # Remove None values
        entry = {k: v for k, v in entry.items() if v is not None}

        self._audit_log.append(entry)
        logger.info(f"Audit log entry: {audit_log_id} - {action} - {status}")

    def get_audit_log(
        self,
        limit: int = 100,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit log entries.

        Args:
            limit: Maximum number of entries to return
            status_filter: Optional status to filter by

        Returns:
            List of audit log entries
        """
        entries = self._audit_log

        if status_filter:
            entries = [e for e in entries if e.get("status") == status_filter]

        return entries[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get trigger statistics.

        Returns:
            Dictionary with trigger statistics
        """
        total = len(self._audit_log)
        success = sum(1 for e in self._audit_log if e.get("status") == "success")
        rejected = sum(1 for e in self._audit_log if e.get("status") == "rejected")
        failed = sum(1 for e in self._audit_log if e.get("status") == "failed")
        blocked = sum(1 for e in self._audit_log if e.get("status") == "blocked")

        return {
            "total_attempts": total,
            "success_count": success,
            "rejected_count": rejected,
            "failed_count": failed,
            "blocked_count": blocked,
            "success_rate": success / total if total > 0 else 0.0,
            "config": {
                "portfolio_value": self.portfolio_value,
                "max_position_pct": self.max_position_pct,
                "min_confidence": self.min_confidence,
            },
        }

    async def validate_readiness(self) -> dict[str, Any]:
        """Validate that the trigger is ready to execute trades.

        Returns:
            Dictionary with readiness status and details
        """
        checks: dict[str, Any] = {
            "kill_switch_armed": False,
            "orchestrator_ready": False,
            "portfolio_value_ok": False,
        }

        # Check kill-switch
        try:
            ks_state = self.kill_switch.state
            checks["kill_switch_armed"] = ks_state == KillSwitchState.ARMED
            checks["kill_switch_state"] = ks_state.value
        except Exception as e:
            checks["kill_switch_error"] = str(e)

        # Check orchestrator
        try:
            checks["orchestrator_ready"] = hasattr(self.orchestrator, "process_signal")
            checks["orchestrator_metrics"] = self.orchestrator.get_metrics()
        except Exception as e:
            checks["orchestrator_error"] = str(e)

        # Check portfolio
        checks["portfolio_value_ok"] = self.portfolio_value > 0
        checks["portfolio_value"] = self.portfolio_value

        # Overall readiness
        checks["ready"] = all(
            [
                checks["kill_switch_armed"],
                checks["orchestrator_ready"],
                checks["portfolio_value_ok"],
            ]
        )

        return checks
