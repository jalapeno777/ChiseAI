"""Kill-switch executor for emergency position closure.

Provides the KillSwitchExecutor class that handles kill-switch
triggering, position closure, and state management for risk control.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .state import (
    CloseResult,
    CloseStatus,
    KillSwitchConfig,
    KillSwitchLogEntry,
    KillSwitchResult,
    KillSwitchState,
)

if TYPE_CHECKING:
    from data.exchange.bybit_connector import BybitConnector
    from data.exchange.bitget_connector import BitgetConnector
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
    ):
        """Initialize kill-switch executor.

        Args:
            bybit_connector: Bybit exchange connector
            bitget_connector: Bitget exchange connector
            position_tracker: Portfolio position tracker
            influxdb_client: Optional InfluxDB client for metrics
            config: Kill-switch configuration
            drawdown_monitor: Optional drawdown monitor
        """
        self.bybit_connector = bybit_connector
        self.bitget_connector = bitget_connector
        self.position_tracker = position_tracker
        self.influxdb_client = influxdb_client
        self.config = config or KillSwitchConfig()
        self.drawdown_monitor = drawdown_monitor

        self._state = KillSwitchState.ARMED
        self._triggered_at: datetime | None = None
        self._triggered_by: str = ""
        self._trigger_reason: str = ""
        self._reauthorized_at: datetime | None = None
        self._reauthorized_by: str = ""
        self._last_result: KillSwitchResult | None = None
        self._log_history: list[KillSwitchLogEntry] = []
        self._state_lock = asyncio.Lock()

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
                    "Cannot arm kill-switch: currently triggered, reauthorization required"
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
                    "Cannot disable kill-switch: triggered state requires reauthorization"
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
            old_state = self._state
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

        Args:
            reason: Reason for kill-switch activation
            triggered_by: Alert or condition that triggered the kill-switch
            environment: Trading environment ("live", "paper", "demo")

        Returns:
            KillSwitchResult with execution details
        """
        async with self._state_lock:
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

            # Update state to triggered
            self._state = KillSwitchState.TRIGGERED
            self._triggered_at = datetime.now(UTC)
            self._triggered_by = str(triggered_by) if triggered_by else "manual"
            self._trigger_reason = reason

            # Get drawdown info if available
            drawdown_pct = 0.0
            portfolio_value = 0.0
            if self.drawdown_monitor:
                metrics = self.drawdown_monitor.calculate_rolling_drawdown()
                drawdown_pct = metrics.current_drawdown_pct
                current_value = self.drawdown_monitor.get_current_value()
                if current_value:
                    portfolio_value = current_value

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

            await self._write_state_to_influxdb()

        # Close all positions (outside lock to allow concurrent operations)
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        close_results = await self.close_all_positions(environment)

        # Calculate totals
        positions_closed = sum(
            1 for r in close_results if r.status == CloseStatus.SUCCESS
        )
        total_pnl = sum(r.pnl for r in close_results)

        # Build result
        result = KillSwitchResult(
            success=positions_closed > 0 or len(close_results) == 0,
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
                "triggered_at": (
                    self._triggered_at.isoformat() if self._triggered_at else None
                ),
            },
        )

        self._last_result = result

        # Log completion
        self._log_event(
            "complete",
            f"Kill-switch execution complete: {positions_closed} positions closed, PnL={total_pnl:.2f}",
            drawdown_pct=drawdown_pct,
            portfolio_value=portfolio_value,
            metadata=result.to_dict(),
        )

        await self._write_result_to_influxdb(result)

        logger.critical(
            f"Kill-switch execution complete: {positions_closed} positions, "
            f"PnL={total_pnl:.2f}, drawdown={drawdown_pct:.2f}%"
        )

        return result

    async def close_all_positions(self, environment: str = "live") -> list[CloseResult]:
        """Close all open positions via market orders.

        Args:
            environment: Trading environment ("live", "paper", "demo")

        Returns:
            List of CloseResult for each position
        """
        results: list[CloseResult] = []

        # Get positions from tracker if available
        positions = []
        if self.position_tracker and self.position_tracker.state:
            positions = [
                p for p in self.position_tracker.state.positions.values() if p.is_open
            ]

        if not positions:
            logger.info("No open positions to close")
            return results

        logger.critical(f"Closing {len(positions)} positions via kill-switch")

        # Close each position
        for position in positions:
            result = await self._close_single_position(position, environment)
            results.append(result)

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

        return results

    async def _close_single_position(
        self, position: Any, environment: str
    ) -> CloseResult:
        """Close a single position via market order.

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
                pnl = 0.0
                if self.position_tracker:
                    pnl = (
                        await self.position_tracker.close_position(
                            position_id=position.position_id,
                            exit_price=exec_price,
                        )
                        or 0.0
                    )

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

        # All retries failed
        return CloseResult(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=0.0,
            status=CloseStatus.FAILED,
            error=f"Failed after {self.config.max_close_retries} attempts: {last_error}",
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
