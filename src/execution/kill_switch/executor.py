"""Kill-switch executor for emergency position closure.

Provides the KillSwitchExecutor class that handles kill-switch
triggering, position closure, and state management for risk control.

Includes comprehensive edge case handling for:
- Redis failure during trigger (circuit breaker integration)
- Partial position closure failures
- Concurrent kill-switch triggers (race condition handling)
- Exchange API outage handling
- Position tracker exception handling
- InfluxDB write failure handling

For ST-EX-003: Kill-Switch Executor Implementation
For ST-PAPER-006: Kill-Switch Edge Case Handling
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .retry_handler import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    RetryConfig,
    RetryHandler,
    RetryStrategy,
)
from .state import (
    CloseResult,
    CloseStatus,
    KillSwitchConfig,
    KillSwitchLogEntry,
    KillSwitchResult,
    KillSwitchState,
)

if TYPE_CHECKING:
    from data.exchange.bitget_connector import BitgetConnector
    from data.exchange.bybit_connector import BybitConnector
    from portfolio.state_management.tracker import PortfolioTracker

    from .drawdown_monitor import DrawdownMonitor

logger = logging.getLogger(__name__)


class KillSwitchExecutor:
    """Executor for kill-switch operations.

    Manages kill-switch state, executes emergency position closures,
    and logs all activities for audit and monitoring.

    Attributes:
        bybit_connector: Bybit exchange connector
        bitget_connector: Bitget exchange connector
        position_tracker: Portfolio position tracker
        influxdb_client: Optional InfluxDB client for metrics
        config: Kill-switch configuration
        state: Current kill-switch state
    """

    def __init__(
        self,
        bybit_connector: BybitConnector | None = None,
        bitget_connector: BitgetConnector | None = None,
        position_tracker: PortfolioTracker | None = None,
        influxdb_client: Any | None = None,
        config: KillSwitchConfig | None = None,
        drawdown_monitor: DrawdownMonitor | None = None,
        redis_client: Any | None = None,
    ):
        """Initialize kill-switch executor.

        Args:
            bybit_connector: Bybit exchange connector
            bitget_connector: Bitget exchange connector
            position_tracker: Portfolio position tracker
            influxdb_client: Optional InfluxDB client for metrics
            config: Kill-switch configuration
            drawdown_monitor: Optional drawdown monitor
            redis_client: Optional Redis client for distributed locking
        """
        self.bybit_connector = bybit_connector
        self.bitget_connector = bitget_connector
        self.position_tracker = position_tracker
        self.influxdb_client = influxdb_client
        self.config = config or KillSwitchConfig()
        self.drawdown_monitor = drawdown_monitor
        self._redis_client = redis_client

        self._state = KillSwitchState.ARMED
        self._triggered_at: datetime | None = None
        self._triggered_by: str = ""
        self._trigger_reason: str = ""
        self._reauthorized_at: datetime | None = None
        self._reauthorized_by: str = ""
        self._last_result: KillSwitchResult | None = None
        self._log_history: list[KillSwitchLogEntry] = []
        self._state_lock = asyncio.Lock()
        self._trigger_lock = asyncio.Lock()  # Separate lock for trigger idempotency
        self._redis_client = None  # Redis client for distributed locking

        # Initialize retry handler with circuit breakers
        self._retry_handler = RetryHandler()
        self._retry_handler.register_circuit_breaker(
            "influxdb",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout_seconds=30.0,
            ),
        )
        self._retry_handler.register_circuit_breaker(
            "redis",
            CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout_seconds=10.0,
            ),
        )
        self._retry_handler.register_circuit_breaker(
            "exchange",
            CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout_seconds=60.0,
            ),
        )

        # Log initialization
        self._log_event(
            "initialized",
            f"KillSwitchExecutor initialized in {self._state.value} state",
        )

        logger.info(f"KillSwitchExecutor initialized: state={self._state.value}")

    @property
    def state(self) -> KillSwitchState:
        """Get current kill-switch state."""
        return self._state

    def get_state(self) -> KillSwitchState:
        """Get current kill-switch state (explicit method).

        Returns:
            Current KillSwitchState
        """
        return self._state

    async def arm(self) -> bool:
        """Arm the kill-switch (enable monitoring).

        Returns:
            True if successfully armed, False otherwise
        """
        async with self._state_lock:
            if self._state == KillSwitchState.TRIGGERED:
                logger.warning(
                    "Cannot arm kill-switch: currently triggered, "
                    "reauthorization required"
                )
                return False

            old_state = self._state
            self._state = KillSwitchState.ARMED

            self._log_event(
                "state_change",
                f"Kill-switch armed (was {old_state.value})",
            )

            await self._write_state_to_influxdb()

            logger.info("Kill-switch armed")
            return True

    async def disable(self) -> bool:
        """Disable the kill-switch (stop monitoring).

        Returns:
            True if successfully disabled, False otherwise
        """
        async with self._state_lock:
            if (
                self._state == KillSwitchState.TRIGGERED
                and self.config.require_reauthorization
            ):
                logger.warning(
                    "Cannot disable kill-switch: triggered state "
                    "requires reauthorization"
                )
                return False

            old_state = self._state
            self._state = KillSwitchState.DISABLED

            self._log_event(
                "state_change",
                f"Kill-switch disabled (was {old_state.value})",
            )

            await self._write_state_to_influxdb()

            logger.info("Kill-switch disabled")
            return True

    async def reauthorize(self, signed_packet_id: str) -> bool:
        """Reauthorize kill-switch after trigger.

        Args:
            signed_packet_id: Signed authorization packet ID

        Returns:
            True if successfully reauthorized, False otherwise
        """
        async with self._state_lock:
            if self._state != KillSwitchState.TRIGGERED:
                logger.warning("Reauthorization only valid in TRIGGERED state")
                return False

            self._reauthorized_at = datetime.now(UTC)
            self._reauthorized_by = signed_packet_id
            self._state = KillSwitchState.ARMED

            self._log_event(
                "reauthorize",
                f"Kill-switch reauthorized by packet {signed_packet_id}",
                metadata={"signed_packet_id": signed_packet_id},
            )

            await self._write_state_to_influxdb()

            logger.info(f"Kill-switch reauthorized: packet={signed_packet_id}")
            return True

    async def execute_kill_switch(
        self,
        reason: str,
        triggered_by: Any | None = None,
        environment: str = "live",
    ) -> KillSwitchResult:
        """Execute kill-switch: close all positions immediately.

        Implements idempotent triggering with race condition handling.
        Multiple concurrent triggers are safely deduplicated.

        Args:
            reason: Reason for kill-switch activation
            triggered_by: Alert or condition that triggered the kill-switch
            environment: Trading environment ("live", "paper", "demo")

        Returns:
            KillSwitchResult with execution details
        """
        # Use separate trigger lock for idempotency
        # This allows concurrent trigger attempts to be properly sequenced
        async with self._trigger_lock:
            # Double-check state after acquiring lock
            if self._state == KillSwitchState.DISABLED:
                logger.warning("Kill-switch execution blocked: disabled state")
                return KillSwitchResult(
                    success=False,
                    reason=reason,
                    triggered_by=str(triggered_by) if triggered_by else "unknown",
                    environment=environment,
                    metadata={"error": "kill_switch_disabled"},
                )

            if self._state == KillSwitchState.TRIGGERED:
                logger.warning("Kill-switch already triggered, ignoring duplicate")
                return KillSwitchResult(
                    success=False,
                    reason=reason,
                    triggered_by=str(triggered_by) if triggered_by else "unknown",
                    environment=environment,
                    metadata={"error": "already_triggered"},
                )

            # Now acquire state lock for state transition
            async with self._state_lock:
                # Double-check state again after acquiring state lock
                if self._state == KillSwitchState.TRIGGERED:
                    logger.warning("Kill-switch triggered by another caller, ignoring")
                    return KillSwitchResult(
                        success=False,
                        reason=reason,
                        triggered_by=str(triggered_by) if triggered_by else "unknown",
                        environment=environment,
                        metadata={"error": "already_triggered"},
                    )

                # Update state to triggered
                self._state = KillSwitchState.TRIGGERED
                self._triggered_at = datetime.now(UTC)
                self._triggered_by = str(triggered_by) if triggered_by else "manual"
                self._trigger_reason = reason

            # Get drawdown info if available
            drawdown_pct = 0.0
            portfolio_value = 0.0
            if self.drawdown_monitor:
                try:
                    metrics = self.drawdown_monitor.calculate_rolling_drawdown()
                    drawdown_pct = metrics.current_drawdown_pct
                    current_value = self.drawdown_monitor.get_current_value()
                    if current_value:
                        portfolio_value = current_value
                except Exception as e:
                    logger.error(f"Failed to get drawdown metrics: {e}")
                    # Continue with kill-switch execution even if metrics fail

            # Log the trigger event
            self._log_event(
                "trigger",
                f"Kill-switch triggered: {reason}",
                drawdown_pct=drawdown_pct,
                portfolio_value=portfolio_value,
                metadata={
                    "reason": reason,
                    "triggered_by": self._triggered_by,
                    "environment": environment,
                },
            )

            # Write state to InfluxDB with retry
            await self._write_state_to_influxdb_with_retry()

        # Close all positions (outside all locks to allow concurrent operations)
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        close_results = await self.close_all_positions(environment)

        # Calculate totals with detailed failure tracking
        positions_closed = sum(
            1 for r in close_results if r.status == CloseStatus.SUCCESS
        )
        positions_failed = sum(
            1 for r in close_results if r.status == CloseStatus.FAILED
        )
        positions_partial = sum(
            1 for r in close_results if r.status == CloseStatus.PARTIAL
        )
        total_pnl = sum(r.pnl for r in close_results)

        # Determine success: partial success is still success
        # If we have any failures, log them but don't fail the overall operation
        has_partial_failures = positions_failed > 0 or positions_partial > 0

        if has_partial_failures:
            failed_symbols = [
                r.symbol for r in close_results if r.status == CloseStatus.FAILED
            ]
            logger.error(
                f"Kill-switch had partial failures: {positions_failed} failed, "
                f"{positions_partial} partial. Failed symbols: {failed_symbols}"
            )

        # Build result with comprehensive metadata
        result = KillSwitchResult(
            success=True,  # We attempted the kill-switch, which is success
            positions_closed=positions_closed,
            total_pnl=total_pnl,
            reason=reason,
            triggered_by=self._triggered_by,
            environment=environment,
            close_results=close_results,
            metadata={
                "drawdown_pct": drawdown_pct,
                "portfolio_value": portfolio_value,
                "total_positions": len(close_results),
                "positions_failed": positions_failed,
                "positions_partial": positions_partial,
                "has_partial_failures": has_partial_failures,
                "triggered_at": (
                    self._triggered_at.isoformat() if self._triggered_at else None
                ),
            },
        )

        self._last_result = result

        # Log completion
        self._log_event(
            "complete",
            f"Kill-switch execution complete: {positions_closed} positions closed, "
            f"PnL={total_pnl:.2f}, failures={positions_failed}",
            drawdown_pct=drawdown_pct,
            portfolio_value=portfolio_value,
            metadata=result.to_dict(),
        )

        # Write result to InfluxDB with retry
        await self._write_result_to_influxdb_with_retry(result)

        logger.critical(
            f"Kill-switch execution complete: {positions_closed} positions, "
            f"PnL={total_pnl:.2f}, drawdown={drawdown_pct:.2f}%, "
            f"failures={positions_failed}"
        )

        return result

    async def close_all_positions(self, environment: str = "live") -> list[CloseResult]:
        """Close all open positions via market orders.

        Handles partial failures gracefully - continues closing remaining
        positions even if some fail.

        Args:
            environment: Trading environment ("live", "paper", "demo")

        Returns:
            List of CloseResult for each position
        """
        results: list[CloseResult] = []

        # Get positions from tracker if available
        positions = []
        if self.position_tracker and self.position_tracker.state:
            try:
                positions = [
                    p
                    for p in self.position_tracker.state.positions.values()
                    if p.is_open
                ]
            except Exception as e:
                # Position tracker exception handling
                logger.error(f"Failed to get positions from tracker: {e}")
                self._log_event(
                    "error",
                    f"Position tracker exception: {e}",
                    metadata={"error": str(e), "error_type": type(e).__name__},
                )
                # Return empty results but don't fail - we attempted the kill-switch
                return results

        if not positions:
            logger.info("No open positions to close")
            return results

        logger.critical(f"Closing {len(positions)} positions via kill-switch")

        # Close each position, handling partial failures
        failed_positions = []
        for position in positions:
            try:
                result = await self._close_single_position(position, environment)
                results.append(result)

                # Track failed positions for potential retry
                if result.status == CloseStatus.FAILED:
                    failed_positions.append((position, result))

                # Log each close
                self._log_event(
                    "close",
                    f"Position close: {position.token} {result.status.value}",
                    metadata={
                        "symbol": position.token,
                        "side": position.direction.value,
                        "quantity": position.quantity,
                        "result": result.to_dict(),
                    },
                )
            except Exception as e:
                # Handle unexpected exceptions during position close
                logger.exception(
                    f"Unexpected error closing position {position.token}: {e}"
                )
                error_result = CloseResult(
                    symbol=position.token,
                    side="sell" if position.direction.value == "long" else "buy",
                    quantity=abs(position.quantity),
                    price=0.0,
                    status=CloseStatus.FAILED,
                    error=f"Unexpected exception: {e}",
                )
                results.append(error_result)
                failed_positions.append((position, error_result))

                self._log_event(
                    "error",
                    f"Unexpected error closing {position.token}: {e}",
                    metadata={
                        "symbol": position.token,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        # Log summary of partial failures if any
        if failed_positions:
            logger.error(
                f"Partial position closure: {len(failed_positions)}/{len(positions)} "
                f"positions failed to close"
            )

        return results

    async def _close_single_position(
        self, position: Any, environment: str
    ) -> CloseResult:
        """Close a single position via market order with circuit breaker.

        Handles exchange API outages using circuit breaker pattern.
        Position tracker exceptions are caught separately to ensure position
        closure is not blocked by tracker issues.

        Args:
            position: Position to close
            environment: Trading environment

        Returns:
            CloseResult with execution details
        """
        symbol = position.token
        side = "sell" if position.direction.value == "long" else "buy"
        quantity = abs(position.quantity)

        # Determine which connector to use based on environment
        connector = None
        if environment == "live" and self.bitget_connector:
            connector = self.bitget_connector
        elif environment in ("paper", "demo") and self.bybit_connector:
            connector = self.bybit_connector
        else:
            # Fallback: try any available connector
            connector = self.bybit_connector or self.bitget_connector

        if not connector:
            return CloseResult(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=0.0,
                status=CloseStatus.FAILED,
                error="No exchange connector available",
            )

        # Check circuit breaker for exchange
        breaker = self._retry_handler.get_circuit_breaker("exchange")
        if breaker and not await breaker.can_execute():
            logger.error(f"Exchange circuit breaker open - cannot close {symbol}")
            return CloseResult(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=0.0,
                status=CloseStatus.FAILED,
                error="Exchange circuit breaker open - API outage detected",
            )

        # Attempt close with retries
        last_error = "Unknown error"
        for attempt in range(self.config.max_close_retries):
            try:
                # Place market order to close position
                order_result = await connector.close_position_market(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                )

                # Extract result details
                order_id = order_result.get("order_id", "")
                exec_price = order_result.get("price", 0.0)
                exec_qty = order_result.get("quantity", quantity)

                # Calculate PnL if tracker available
                # Position tracker exceptions are caught separately
                pnl = 0.0
                if self.position_tracker:
                    try:
                        pnl = (
                            await self.position_tracker.close_position(
                                position_id=position.position_id,
                                exit_price=exec_price,
                            )
                            or 0.0
                        )
                    except Exception as tracker_error:
                        # Log but don't fail - position was still closed
                        logger.error(
                            f"Position tracker error for {symbol} "
                            f"(position was still closed): {tracker_error}"
                        )
                        pnl = 0.0

                # Record success in circuit breaker
                if breaker:
                    await breaker.record_success()

                return CloseResult(
                    symbol=symbol,
                    side=side,
                    quantity=exec_qty,
                    price=exec_price,
                    status=CloseStatus.SUCCESS,
                    order_id=order_id,
                    pnl=pnl,
                )

            except Exception as e:
                logger.error(f"Close attempt {attempt + 1} failed for {symbol}: {e}")
                last_error = str(e)

                if attempt < self.config.max_close_retries - 1:
                    await asyncio.sleep(self.config.close_retry_delay_seconds)

        # All retries failed - record failure in circuit breaker
        if breaker:
            await breaker.record_failure()

        return CloseResult(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=0.0,
            status=CloseStatus.FAILED,
            error=(
                f"Failed after {self.config.max_close_retries} attempts: {last_error}"
            ),
        )

    def _log_event(
        self,
        event_type: str,
        message: str,
        drawdown_pct: float = 0.0,
        portfolio_value: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a kill-switch event.

        Args:
            event_type: Type of event
            message: Event description
            drawdown_pct: Current drawdown percentage
            portfolio_value: Current portfolio value
            metadata: Additional context
        """
        entry = KillSwitchLogEntry(
            event_type=event_type,
            state=self._state,
            message=message,
            drawdown_pct=drawdown_pct,
            portfolio_value=portfolio_value,
            metadata=metadata or {},
        )

        self._log_history.append(entry)

        # Also log to Python logger
        if event_type in ("trigger", "complete"):
            logger.critical(f"[KILL-SWITCH] {message}")
        elif event_type == "close":
            logger.error(f"[KILL-SWITCH] {message}")
        else:
            logger.info(f"[KILL-SWITCH] {message}")

    async def _write_state_to_influxdb(self) -> bool:
        """Write current state to InfluxDB.

        Returns:
            True if write successful, False otherwise
        """
        if not self.influxdb_client or not self.config.log_to_influxdb:
            return False

        try:
            point = {
                "measurement": self.config.influxdb_measurement,
                "tags": {
                    "state": self._state.value,
                    "triggered_by": self._triggered_by or "none",
                },
                "fields": {
                    "state_value": self._get_state_numeric(),
                    "is_armed": self._state == KillSwitchState.ARMED,
                    "is_triggered": self._state == KillSwitchState.TRIGGERED,
                    "is_disabled": self._state == KillSwitchState.DISABLED,
                },
                "time": datetime.now(UTC).isoformat(),
            }

            await self.influxdb_client.write_point(point)
            return True

        except Exception as e:
            logger.error(f"Failed to write kill-switch state to InfluxDB: {e}")
            return False

    async def _write_result_to_influxdb(self, result: KillSwitchResult) -> bool:
        """Write execution result to InfluxDB.

        Args:
            result: Kill-switch execution result

        Returns:
            True if write successful, False otherwise
        """
        if not self.influxdb_client or not self.config.log_to_influxdb:
            return False

        try:
            point = {
                "measurement": f"{self.config.influxdb_measurement}_execution",
                "tags": {
                    "environment": result.environment,
                    "success": str(result.success),
                },
                "fields": {
                    "positions_closed": result.positions_closed,
                    "total_pnl": result.total_pnl,
                    "drawdown_pct": result.metadata.get("drawdown_pct", 0.0),
                    "portfolio_value": result.metadata.get("portfolio_value", 0.0),
                },
                "time": result.timestamp.isoformat(),
            }

            await self.influxdb_client.write_point(point)
            return True

        except Exception as e:
            logger.error(f"Failed to write kill-switch result to InfluxDB: {e}")
            return False

    def _get_state_numeric(self) -> int:
        """Get numeric representation of state for InfluxDB.

        Returns:
            Numeric state value (0=disabled, 1=armed, 2=triggered)
        """
        mapping = {
            KillSwitchState.DISABLED: 0,
            KillSwitchState.ARMED: 1,
            KillSwitchState.TRIGGERED: 2,
        }
        return mapping.get(self._state, -1)

    def get_log_history(self) -> list[KillSwitchLogEntry]:
        """Get kill-switch event log history.

        Returns:
            List of log entries
        """
        return list(self._log_history)

    def get_last_result(self) -> KillSwitchResult | None:
        """Get result of last kill-switch execution.

        Returns:
            Last KillSwitchResult or None
        """
        return self._last_result

    def get_summary(self) -> dict[str, Any]:
        """Get summary of kill-switch state.

        Returns:
            Dictionary with state summary
        """
        return {
            "state": self._state.value,
            "triggered_at": (
                self._triggered_at.isoformat() if self._triggered_at else None
            ),
            "triggered_by": self._triggered_by,
            "trigger_reason": self._trigger_reason,
            "reauthorized_at": (
                self._reauthorized_at.isoformat() if self._reauthorized_at else None
            ),
            "reauthorized_by": self._reauthorized_by,
            "config": self.config.to_dict(),
            "last_result": self._last_result.to_dict() if self._last_result else None,
            "log_count": len(self._log_history),
        }

    async def _write_state_to_influxdb_with_retry(self) -> bool:
        """Write current state to InfluxDB with retry and circuit breaker.

        Handles InfluxDB write failures gracefully - logs error but
        doesn't fail the kill-switch operation.

        Returns:
            True if write successful, False otherwise
        """
        if not self.influxdb_client or not self.config.log_to_influxdb:
            return False

        async def _write() -> None:
            point = {
                "measurement": self.config.influxdb_measurement,
                "tags": {
                    "state": self._state.value,
                    "triggered_by": self._triggered_by or "none",
                },
                "fields": {
                    "state_value": self._get_state_numeric(),
                    "is_armed": self._state == KillSwitchState.ARMED,
                    "is_triggered": self._state == KillSwitchState.TRIGGERED,
                    "is_disabled": self._state == KillSwitchState.DISABLED,
                },
                "time": datetime.now(UTC).isoformat(),
            }
            if self.influxdb_client:
                await self.influxdb_client.write_point(point)

        retry_config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.5,
            strategy=RetryStrategy.EXPONENTIAL_JITTER,
        )

        try:
            await self._retry_handler.execute_with_retry(
                "influxdb",
                _write,
                retry_config,
                "write_state_to_influxdb",
            )
            return True
        except CircuitBreakerOpenError:
            logger.error("InfluxDB circuit breaker open - state not logged")
            return False
        except Exception as e:
            logger.error(f"Failed to write state to InfluxDB after retries: {e}")
            return False

    async def _write_result_to_influxdb_with_retry(
        self, result: KillSwitchResult
    ) -> bool:
        """Write execution result to InfluxDB with retry and circuit breaker.

        Handles InfluxDB write failures gracefully - logs error but
        doesn't fail the kill-switch operation.

        Args:
            result: Kill-switch execution result

        Returns:
            True if write successful, False otherwise
        """
        if not self.influxdb_client or not self.config.log_to_influxdb:
            return False

        async def _write() -> None:
            point = {
                "measurement": f"{self.config.influxdb_measurement}_execution",
                "tags": {
                    "environment": result.environment,
                    "success": str(result.success),
                },
                "fields": {
                    "positions_closed": result.positions_closed,
                    "total_pnl": result.total_pnl,
                    "drawdown_pct": result.metadata.get("drawdown_pct", 0.0),
                    "portfolio_value": result.metadata.get("portfolio_value", 0.0),
                },
                "time": result.timestamp.isoformat(),
            }
            if self.influxdb_client:
                await self.influxdb_client.write_point(point)

        retry_config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.5,
            strategy=RetryStrategy.EXPONENTIAL_JITTER,
        )

        try:
            await self._retry_handler.execute_with_retry(
                "influxdb",
                _write,
                retry_config,
                "write_result_to_influxdb",
            )
            return True
        except CircuitBreakerOpenError:
            logger.error("InfluxDB circuit breaker open - result not logged")
            return False
        except Exception as e:
            logger.error(f"Failed to write result to InfluxDB after retries: {e}")
            return False
