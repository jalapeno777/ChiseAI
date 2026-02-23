"""Safety orchestrator for integrating all safety components.

Provides centralized management of safety features:
- Demo mode validation
- Circuit breaker integration
- Order idempotency
- Kill switch operation
- Full audit trail for all safety events

For ST-LAUNCH-005: Safety Integration & E2E Tests
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from common.circuit_breaker import CircuitBreaker
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.order_idempotency import IdempotencyStore

logger = logging.getLogger(__name__)


class SafetyEventType(Enum):
    """Types of safety events for audit trail."""

    DEMO_MODE_CHECK = auto()
    CIRCUIT_BREAKER_CHECK = auto()
    IDEMPOTENCY_CHECK = auto()
    KILL_SWITCH_TRIGGER = auto()
    KILL_SWITCH_ARM = auto()
    KILL_SWITCH_DISABLE = auto()
    KILL_SWITCH_REAUTHORIZE = auto()
    WEBSOCKET_BLOCKED = auto()
    ORDER_VALIDATED = auto()
    ORDER_REJECTED = auto()
    POSITION_CLOSE_START = auto()
    POSITION_CLOSE_COMPLETE = auto()
    ERROR = auto()


@dataclass
class SafetyEvent:
    """Safety event for audit trail.

    Attributes:
        event_type: Type of safety event
        timestamp: When the event occurred
        message: Human-readable description
        metadata: Additional event context
        success: Whether the operation succeeded
    """

    event_type: SafetyEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "metadata": self.metadata,
            "success": self.success,
        }


@dataclass
class SafetyCheckResult:
    """Result of a safety check.

    Attributes:
        passed: Whether the check passed
        reason: Reason for failure (if any)
        event: Associated safety event
    """

    passed: bool
    reason: str = ""
    event: SafetyEvent | None = None

    @property
    def failed(self) -> bool:
        """Check if the safety check failed."""
        return not self.passed


class ExchangeConnector(Protocol):
    """Protocol for exchange connector interface."""

    config: Any

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Place an order on the exchange."""
        ...

    async def close_position_market(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> dict[str, Any]:
        """Close a position via market order."""
        ...


class SafetyOrchestrator:
    """Orchestrates all safety components for trading operations.

    Provides centralized safety management with:
    - Demo mode validation
    - Circuit breaker state monitoring
    - Order idempotency enforcement
    - Kill switch integration
    - Full audit trail

    Example:
        >>> orchestrator = SafetyOrchestrator(
        ...     idempotency_store=idempotency_store,
        ...     circuit_breaker=circuit_breaker,
        ...     kill_switch_executor=kill_switch_executor,
        ... )
        >>> result = await orchestrator.validate_order(
        ...     symbol="BTCUSDT",
        ...     client_order_id="order_123"
        ... )
        >>> if result.passed:
        ...     # Proceed with order
    """

    def __init__(
        self,
        idempotency_store: IdempotencyStore | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        kill_switch_executor: KillSwitchExecutor | None = None,
        environment: str = "demo",
        enable_audit_trail: bool = True,
    ) -> None:
        """Initialize the safety orchestrator.

        Args:
            idempotency_store: Store for order idempotency tracking
            circuit_breaker: Circuit breaker for service protection
            kill_switch_executor: Executor for kill switch operations
            environment: Trading environment ("demo", "paper", "live")
            enable_audit_trail: Whether to enable event logging
        """
        self._idempotency_store = idempotency_store
        self._circuit_breaker = circuit_breaker
        self._kill_switch_executor = kill_switch_executor
        self._environment = environment
        self._enable_audit_trail = enable_audit_trail

        self._event_log: list[SafetyEvent] = []
        self._websocket_blocked: bool = False

        # Log initialization
        self._log_event(
            SafetyEventType.DEMO_MODE_CHECK,
            f"SafetyOrchestrator initialized in {environment} mode",
            {"environment": environment},
        )

        logger.info(
            f"SafetyOrchestrator initialized: environment={environment}, "
            f"audit_trail={enable_audit_trail}"
        )

    @property
    def environment(self) -> str:
        """Get current trading environment."""
        return self._environment

    @property
    def is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self._environment == "demo"

    @property
    def audit_trail_enabled(self) -> bool:
        """Check if audit trail is enabled."""
        return self._enable_audit_trail

    def _log_event(
        self,
        event_type: SafetyEventType,
        message: str,
        metadata: dict[str, Any] | None = None,
        success: bool = True,
    ) -> SafetyEvent:
        """Log a safety event.

        Args:
            event_type: Type of event
            message: Event description
            metadata: Additional context
            success: Whether the operation succeeded

        Returns:
            The created SafetyEvent
        """
        event = SafetyEvent(
            event_type=event_type,
            message=message,
            metadata=metadata or {},
            success=success,
        )

        if self._enable_audit_trail:
            self._event_log.append(event)

        # Also log to Python logger
        log_method = logger.info if success else logger.error
        log_method(f"[SAFETY] {event_type.name}: {message}")

        return event

    async def validate_demo_mode(
        self,
        connector: ExchangeConnector | None = None,
    ) -> SafetyCheckResult:
        """Validate demo mode environment.

        Ensures that operations are only performed in demo/paper mode
        unless explicitly configured for live trading.

        Args:
            connector: Optional exchange connector to validate

        Returns:
            SafetyCheckResult with validation status
        """
        metadata: dict[str, Any] = {
            "environment": self._environment,
        }

        # Check environment
        if self._environment not in ("demo", "paper", "live"):
            event = self._log_event(
                SafetyEventType.DEMO_MODE_CHECK,
                f"Invalid environment: {self._environment}",
                metadata,
                success=False,
            )
            return SafetyCheckResult(
                passed=False,
                reason=f"Invalid environment: {self._environment}",
                event=event,
            )

        # Validate connector config if provided
        if connector is not None:
            config = getattr(connector, "config", None)
            if config is not None:
                is_demo = getattr(config, "demo", False)
                is_testnet = getattr(config, "testnet", False)
                metadata["connector_demo"] = is_demo
                metadata["connector_testnet"] = is_testnet

                if self._environment == "demo" and not (is_demo or is_testnet):
                    event = self._log_event(
                        SafetyEventType.DEMO_MODE_CHECK,
                        "Demo mode validation failed: connector not in demo/testnet mode",
                        metadata,
                        success=False,
                    )
                    return SafetyCheckResult(
                        passed=False,
                        reason="Connector not configured for demo mode",
                        event=event,
                    )

        event = self._log_event(
            SafetyEventType.DEMO_MODE_CHECK,
            f"Demo mode validation passed for {self._environment}",
            metadata,
        )
        return SafetyCheckResult(passed=True, event=event)

    async def check_circuit_breaker(self) -> SafetyCheckResult:
        """Check if circuit breaker allows operations.

        Returns:
            SafetyCheckResult with circuit breaker status
        """
        if self._circuit_breaker is None:
            event = self._log_event(
                SafetyEventType.CIRCUIT_BREAKER_CHECK,
                "No circuit breaker configured - allowing operation",
                {"state": "NOT_CONFIGURED"},
            )
            return SafetyCheckResult(passed=True, event=event)

        # Get current state
        state = self._circuit_breaker.state
        state_name = state.name if hasattr(state, "name") else str(state)

        metadata = {
            "circuit_breaker_name": getattr(self._circuit_breaker, "name", "unknown"),
            "state": state_name,
        }

        # Check if circuit is open
        if state_name == "OPEN":
            event = self._log_event(
                SafetyEventType.CIRCUIT_BREAKER_CHECK,
                "Circuit breaker OPEN - blocking operation",
                metadata,
                success=False,
            )
            return SafetyCheckResult(
                passed=False,
                reason="Circuit breaker is OPEN",
                event=event,
            )

        # Check if we can execute
        can_execute = self._circuit_breaker.can_execute()
        metadata["can_execute"] = can_execute

        if not can_execute:
            event = self._log_event(
                SafetyEventType.CIRCUIT_BREAKER_CHECK,
                "Circuit breaker blocking execution",
                metadata,
                success=False,
            )
            return SafetyCheckResult(
                passed=False,
                reason="Circuit breaker preventing execution",
                event=event,
            )

        event = self._log_event(
            SafetyEventType.CIRCUIT_BREAKER_CHECK,
            f"Circuit breaker {state_name} - allowing operation",
            metadata,
        )
        return SafetyCheckResult(passed=True, event=event)

    async def check_websocket_allowed(self) -> SafetyCheckResult:
        """Check if WebSocket signals are allowed.

        WebSocket signals should be blocked when circuit breaker is OPEN.

        Returns:
            SafetyCheckResult indicating if WebSocket signals allowed
        """
        # First check circuit breaker
        cb_result = await self.check_circuit_breaker()

        if cb_result.failed:
            self._websocket_blocked = True
            event = self._log_event(
                SafetyEventType.WEBSOCKET_BLOCKED,
                "WebSocket signals blocked by circuit breaker",
                {"reason": cb_result.reason},
                success=False,
            )
            return SafetyCheckResult(
                passed=False,
                reason="WebSocket blocked: circuit breaker OPEN",
                event=event,
            )

        self._websocket_blocked = False
        event = self._log_event(
            SafetyEventType.WEBSOCKET_BLOCKED,
            "WebSocket signals allowed",
            {"circuit_breaker_state": "CLOSED"},
        )
        return SafetyCheckResult(passed=True, event=event)

    async def validate_order_idempotency(
        self,
        symbol: str,
        client_order_id: str,
    ) -> SafetyCheckResult:
        """Validate order idempotency.

        Checks if an order has already been submitted and prevents duplicates.

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID

        Returns:
            SafetyCheckResult with idempotency check status
        """
        if self._idempotency_store is None:
            event = self._log_event(
                SafetyEventType.IDEMPOTENCY_CHECK,
                "No idempotency store configured - allowing order",
                {"symbol": symbol, "client_order_id": client_order_id},
            )
            return SafetyCheckResult(passed=True, event=event)

        metadata = {
            "symbol": symbol,
            "client_order_id": client_order_id,
        }

        try:
            is_duplicate = await self._idempotency_store.check_duplicate(
                symbol, client_order_id
            )

            if is_duplicate:
                event = self._log_event(
                    SafetyEventType.IDEMPOTENCY_CHECK,
                    f"Duplicate order detected: {client_order_id}",
                    metadata,
                    success=False,
                )
                return SafetyCheckResult(
                    passed=False,
                    reason=f"Duplicate order: {client_order_id}",
                    event=event,
                )

            # Mark as submitted
            await self._idempotency_store.mark_submitted(symbol, client_order_id)

            event = self._log_event(
                SafetyEventType.IDEMPOTENCY_CHECK,
                f"Order idempotency validated: {client_order_id}",
                metadata,
            )
            return SafetyCheckResult(passed=True, event=event)

        except Exception as e:
            event = self._log_event(
                SafetyEventType.IDEMPOTENCY_CHECK,
                f"Idempotency check error: {e}",
                {**metadata, "error": str(e)},
                success=False,
            )
            # Fail open - allow order if check fails
            return SafetyCheckResult(
                passed=True,
                reason=f"Idempotency check failed but allowing order: {e}",
                event=event,
            )

    async def validate_order(
        self,
        symbol: str,
        client_order_id: str,
        connector: ExchangeConnector | None = None,
    ) -> SafetyCheckResult:
        """Full order validation with all safety checks.

        Performs:
        1. Demo mode validation
        2. Circuit breaker check
        3. Order idempotency check

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID
            connector: Optional exchange connector

        Returns:
            SafetyCheckResult with full validation status
        """
        # Check demo mode
        demo_result = await self.validate_demo_mode(connector)
        if demo_result.failed:
            return demo_result

        # Check circuit breaker
        cb_result = await self.check_circuit_breaker()
        if cb_result.failed:
            return cb_result

        # Check idempotency
        idempotency_result = await self.validate_order_idempotency(
            symbol, client_order_id
        )
        if idempotency_result.failed:
            return idempotency_result

        # All checks passed
        event = self._log_event(
            SafetyEventType.ORDER_VALIDATED,
            f"Order validated: {symbol} / {client_order_id}",
            {
                "symbol": symbol,
                "client_order_id": client_order_id,
                "environment": self._environment,
            },
        )
        return SafetyCheckResult(passed=True, event=event)

    async def trigger_kill_switch(
        self,
        reason: str,
        triggered_by: str = "manual",
    ) -> dict[str, Any]:
        """Trigger the kill switch.

        Args:
            reason: Reason for kill switch activation
            triggered_by: Source of trigger

        Returns:
            Kill switch result dictionary
        """
        if self._kill_switch_executor is None:
            event = self._log_event(
                SafetyEventType.KILL_SWITCH_TRIGGER,
                "Kill switch trigger attempted but no executor configured",
                {"reason": reason, "triggered_by": triggered_by},
                success=False,
            )
            return {
                "success": False,
                "error": "No kill switch executor configured",
                "event": event.to_dict(),
            }

        # Log trigger attempt
        self._log_event(
            SafetyEventType.KILL_SWITCH_TRIGGER,
            f"Kill switch triggered: {reason}",
            {"reason": reason, "triggered_by": triggered_by},
        )

        # Execute kill switch
        start_time = asyncio.get_event_loop().time()
        result = await self._kill_switch_executor.execute_kill_switch(
            reason=reason,
            triggered_by=triggered_by,
            environment=self._environment,
        )
        elapsed = asyncio.get_event_loop().time() - start_time

        # Log completion
        self._log_event(
            SafetyEventType.POSITION_CLOSE_COMPLETE,
            f"Kill switch completed in {elapsed:.2f}s: "
            f"{result.positions_closed} positions closed",
            {
                "positions_closed": result.positions_closed,
                "total_pnl": result.total_pnl,
                "elapsed_seconds": elapsed,
                "success": result.success,
            },
        )

        return {
            "success": result.success,
            "positions_closed": result.positions_closed,
            "total_pnl": result.total_pnl,
            "elapsed_seconds": elapsed,
            "result": result.to_dict(),
        }

    async def arm_kill_switch(self) -> bool:
        """Arm the kill switch.

        Returns:
            True if successfully armed
        """
        if self._kill_switch_executor is None:
            self._log_event(
                SafetyEventType.KILL_SWITCH_ARM,
                "Arm attempted but no executor configured",
                success=False,
            )
            return False

        result = await self._kill_switch_executor.arm()

        self._log_event(
            SafetyEventType.KILL_SWITCH_ARM,
            f"Kill switch armed: {result}",
            {"success": result},
        )

        return result  # type: ignore[no-any-return]

    async def disable_kill_switch(self) -> bool:
        """Disable the kill switch.

        Returns:
            True if successfully disabled
        """
        if self._kill_switch_executor is None:
            self._log_event(
                SafetyEventType.KILL_SWITCH_DISABLE,
                "Disable attempted but no executor configured",
                success=False,
            )
            return False

        result = await self._kill_switch_executor.disable()

        self._log_event(
            SafetyEventType.KILL_SWITCH_DISABLE,
            f"Kill switch disabled: {result}",
            {"success": result},
        )

        return result  # type: ignore[no-any-return]

    async def reauthorize_kill_switch(self, signed_packet_id: str) -> bool:
        """Reauthorize the kill switch after trigger.

        Args:
            signed_packet_id: Signed authorization packet ID

        Returns:
            True if successfully reauthorized
        """
        if self._kill_switch_executor is None:
            self._log_event(
                SafetyEventType.KILL_SWITCH_REAUTHORIZE,
                "Reauthorize attempted but no executor configured",
                {"signed_packet_id": signed_packet_id},
                success=False,
            )
            return False

        result = await self._kill_switch_executor.reauthorize(signed_packet_id)

        self._log_event(
            SafetyEventType.KILL_SWITCH_REAUTHORIZE,
            f"Kill switch reauthorized: {result}",
            {"signed_packet_id": signed_packet_id, "success": result},
        )

        return result  # type: ignore[no-any-return]

    def get_kill_switch_state(self) -> str | None:
        """Get current kill switch state.

        Returns:
            State name or None if no executor configured
        """
        if self._kill_switch_executor is None:
            return None

        state = self._kill_switch_executor.state
        return state.value if hasattr(state, "value") else str(state)

    def get_audit_trail(
        self,
        event_types: list[SafetyEventType] | None = None,
        limit: int | None = None,
    ) -> list[SafetyEvent]:
        """Get audit trail of safety events.

        Args:
            event_types: Optional filter by event types
            limit: Optional limit on number of events

        Returns:
            List of safety events
        """
        events = self._event_log

        if event_types:
            events = [e for e in events if e.event_type in event_types]

        if limit:
            events = events[-limit:]

        return events

    def get_audit_trail_dicts(
        self,
        event_types: list[SafetyEventType] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit trail as dictionaries.

        Args:
            event_types: Optional filter by event types
            limit: Optional limit on number of events

        Returns:
            List of safety event dictionaries
        """
        events = self.get_audit_trail(event_types, limit)
        return [e.to_dict() for e in events]

    def clear_audit_trail(self) -> None:
        """Clear the audit trail."""
        self._event_log.clear()
        logger.info("Safety audit trail cleared")

    def get_summary(self) -> dict[str, Any]:
        """Get summary of safety orchestrator state.

        Returns:
            Dictionary with current state summary
        """
        return {
            "environment": self._environment,
            "is_demo_mode": self.is_demo_mode,
            "audit_trail_enabled": self._enable_audit_trail,
            "websocket_blocked": self._websocket_blocked,
            "circuit_breaker_configured": self._circuit_breaker is not None,
            "idempotency_store_configured": self._idempotency_store is not None,
            "kill_switch_configured": self._kill_switch_executor is not None,
            "kill_switch_state": self.get_kill_switch_state(),
            "event_count": len(self._event_log),
            "event_types": list(set(e.event_type.name for e in self._event_log)),
        }


# Singleton instance for application-wide use
_default_orchestrator: SafetyOrchestrator | None = None


def get_default_orchestrator(
    idempotency_store: IdempotencyStore | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    kill_switch_executor: KillSwitchExecutor | None = None,
    environment: str = "demo",
) -> SafetyOrchestrator:
    """Get or create the default safety orchestrator instance.

    Args:
        idempotency_store: Optional idempotency store
        circuit_breaker: Optional circuit breaker
        kill_switch_executor: Optional kill switch executor
        environment: Trading environment

    Returns:
        Default SafetyOrchestrator instance
    """
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = SafetyOrchestrator(
            idempotency_store=idempotency_store,
            circuit_breaker=circuit_breaker,
            kill_switch_executor=kill_switch_executor,
            environment=environment,
        )
    return _default_orchestrator


def reset_default_orchestrator() -> None:
    """Reset the default orchestrator instance.

    Useful for testing.
    """
    global _default_orchestrator
    _default_orchestrator = None
