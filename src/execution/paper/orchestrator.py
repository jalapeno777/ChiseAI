"""Paper Trading Orchestrator.

Connects all paper trading components into an end-to-end workflow:
signal → risk validation → order placement → position tracking → metrics export.

Targets:
- Signal → Order placement: <500ms
- Order fill simulation: <200ms
- Position tracking update: <100ms
- Total pipeline: <2 seconds
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.trade_notifier import TradeNotifier
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.paper.models import PaperOrder, PaperTradeResult
    from execution.paper.order_simulator import OrderSimulator
    from execution.paper.risk_enforcer import PaperRiskEnforcer
    from execution.paper.signal_consumer import SignalConsumer
    from execution.telemetry.collector import ExecutionCollector
    from portfolio.paper_tracker import PaperPositionTracker
    from signal_generation.models import Signal
    from signal_generation.signal_generator import SignalGenerator

import contextlib

from execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperOrder,
    PaperTradeResult,
    TradeStatus,
)

logger = logging.getLogger(__name__)


class PaperTradingOrchestrator:
    """Orchestrates the end-to-end paper trading workflow.

    Pipeline:
    1. Consume signal from SignalGenerator
    2. Validate via RiskEnforcer
    3. Calculate position size
    4. Place order via OrderSimulator
    5. Track position on fill
    6. Export metrics to telemetry
    7. Check kill-switch conditions

    Attributes:
        signal_generator: Source of trading signals
        order_simulator: Simulates order placement and fills
        position_tracker: Tracks open positions
        risk_enforcer: Validates orders against risk limits
        telemetry: Collects and exports execution metrics
        kill_switch: Emergency position closure
        portfolio_value: Current portfolio value
        running: Whether the orchestrator is active
    """

    # Latency targets in milliseconds
    TARGET_SIGNAL_TO_ORDER_MS = 500
    TARGET_FILL_SIMULATION_MS = 200
    TARGET_POSITION_UPDATE_MS = 100
    TARGET_TOTAL_PIPELINE_MS = 2000

    def __init__(
        self,
        signal_generator: SignalGenerator,
        order_simulator: OrderSimulator,
        position_tracker: PaperPositionTracker,
        risk_enforcer: PaperRiskEnforcer,
        telemetry_collector: ExecutionCollector,
        kill_switch: KillSwitchExecutor,
        portfolio_value: float = 10000.0,
        trade_notifier: TradeNotifier | None = None,
        signal_consumer: SignalConsumer | None = None,
        outcome_capture: Any | None = None,
    ):
        """Initialize paper trading orchestrator.

        Args:
            signal_generator: Source of trading signals
            order_simulator: Order simulation engine
            position_tracker: Position tracking
            risk_enforcer: Risk validation
            telemetry_collector: Metrics collection
            kill_switch: Emergency kill switch
            portfolio_value: Starting portfolio value
            trade_notifier: Optional Discord trade notifier for alerts
            signal_consumer: Optional SignalConsumer for Redis signal bridge
        """
        self.signal_generator = signal_generator
        self.order_simulator = order_simulator
        self.position_tracker = position_tracker
        self.risk_enforcer = risk_enforcer
        self.telemetry = telemetry_collector
        self.kill_switch = kill_switch
        self.portfolio_value = portfolio_value
        self.trade_notifier = trade_notifier
        self._signal_consumer = signal_consumer
        self.outcome_capture = outcome_capture

        self._running = False
        self._signal_queue: asyncio.Queue[Signal] = asyncio.Queue()
        self._processing_task: asyncio.Task | None = None
        self._metrics: dict[str, Any] = {
            "signals_processed": 0,
            "trades_executed": 0,
            "trades_rejected": 0,
            "trades_failed": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
        }
        self._lock = asyncio.Lock()

        logger.info(
            f"PaperTradingOrchestrator initialized: portfolio=${portfolio_value:.2f}"
        )

    async def start(self) -> None:
        """Start the orchestrator and begin processing signals."""
        self._running = True

        # Start telemetry collector
        if self.telemetry:
            await self.telemetry.start()

        # Start signal processing loop
        self._processing_task = asyncio.create_task(self._processing_loop())

        # Start signal consumer if provided
        if self._signal_consumer:
            await self._signal_consumer.start()

        logger.info("PaperTradingOrchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        self._running = False

        # Cancel processing task
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._processing_task

        # Stop signal consumer if running
        if self._signal_consumer:
            await self._signal_consumer.stop()

        # Stop telemetry
        if self.telemetry:
            await self.telemetry.stop()

        logger.info("PaperTradingOrchestrator stopped")

    async def start_consumer(self) -> None:
        """Start the signal consumer independently.

        This allows starting the Redis signal bridge without restarting
        the entire orchestrator.
        """
        if self._signal_consumer:
            await self._signal_consumer.start()
            logger.info("Signal consumer started")
        else:
            logger.warning("No signal consumer configured")

    async def stop_consumer(self) -> None:
        """Stop the signal consumer independently.

        This allows stopping the Redis signal bridge without stopping
        the entire orchestrator.
        """
        if self._signal_consumer:
            await self._signal_consumer.stop()
            logger.info("Signal consumer stopped")
        else:
            logger.warning("No signal consumer configured")

    async def _processing_loop(self) -> None:
        """Main signal processing loop."""
        while self._running:
            try:
                # Get signal from queue with timeout
                signal = await asyncio.wait_for(self._signal_queue.get(), timeout=1.0)

                # Process signal
                result = await self.process_signal(signal)

                # Update metrics
                async with self._lock:
                    self._metrics["signals_processed"] += 1
                    if result.status == TradeStatus.EXECUTED:
                        self._metrics["trades_executed"] += 1
                    elif result.status == TradeStatus.REJECTED:
                        self._metrics["trades_rejected"] += 1
                    elif result.status == TradeStatus.FAILED:
                        self._metrics["trades_failed"] += 1
                    # SKIPPED status doesn't increment any metric - just logged

            except TimeoutError:
                # No signals in queue, continue loop
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                # Continue processing - don't crash the loop

    async def submit_signal(self, signal: Signal) -> None:
        """Submit a signal for processing.

        Args:
            signal: Trading signal to process
        """
        await self._signal_queue.put(signal)
        logger.debug(f"Signal submitted: {signal.token} {signal.direction.value}")

    async def process_signal(self, signal: Signal) -> PaperTradeResult:
        """Process a single signal through the full pipeline.

        Pipeline:
        1. Check kill-switch state
        2. Validate risk constraints
        3. Calculate position size
        4. Create and place order
        5. Track position on fill
        6. Record trade metrics

        Args:
            signal: Trading signal to process

        Returns:
            PaperTradeResult with execution details
        """
        correlation_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        logger.info(
            f"Processing signal: {signal.token} {signal.direction.value} "
            f"(correlation_id={correlation_id})"
        )

        # Always count this as a processed signal
        async with self._lock:
            self._metrics["signals_processed"] += 1

        try:
            # Step 1: Check kill-switch state
            if self.kill_switch.state.value == "triggered":
                logger.warning(
                    f"Signal rejected: kill-switch triggered (correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_rejected"] += 1
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.REJECTED,
                    reject_reason=["Kill-switch triggered"],
                    correlation_id=correlation_id,
                )

            # Step 1.5: Get market price early (needed for position management)
            entry_price = self.order_simulator.market_data.get_price(signal.token)
            if entry_price is None or entry_price <= 0:
                logger.warning(
                    f"No valid market price for {signal.token} (price={entry_price}). "
                    f"Cannot create order (correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_rejected"] += 1
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.REJECTED,
                    reject_reason=[f"No market price available for {signal.token}"],
                    correlation_id=correlation_id,
                )

            # Step 1.6: Check for existing position and close if opposite signal
            current_positions = await self.position_tracker.get_open_positions()
            existing_position = None
            for pos in current_positions:
                if pos.symbol.upper() == signal.token.upper():
                    existing_position = pos
                    break

            if existing_position:
                # Check if position should be closed due to time limit (for burn-in testing)
                position_age_seconds = (
                    datetime.now(UTC) - existing_position.opened_at
                ).total_seconds()

                # Close if position is older than 60 seconds (for burn-in testing)
                if position_age_seconds > 60:
                    await self.close_position(
                        existing_position.position_id, entry_price, reason="time_limit"
                    )
                    logger.info(
                        f"Time-based close: position {existing_position.position_id} "
                        f"after {position_age_seconds:.0f}s"
                    )
                    existing_position = None  # Allow new position to open
                else:
                    # Check if signal is opposite direction
                    current_side = existing_position.side  # "long" or "short"
                    signal_side = signal.direction.value.lower()  # "long" or "short"

                    if current_side != signal_side:
                        # Close existing position
                        await self.close_position(
                            existing_position.position_id, entry_price
                        )
                        logger.info(
                            f"Closed position {existing_position.position_id} for {signal.token} "
                            f"(opposite signal: {current_side} -> {signal_side})"
                        )
                        existing_position = None  # Allow new position to open
                    else:
                        # Same direction - skip this signal
                        logger.debug(
                            f"Already in {signal_side} position for {signal.token}, skipping"
                        )
                        return PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.SKIPPED,
                            correlation_id=correlation_id,
                        )

            # Step 2: Validate risk
            risk_start = time.perf_counter()
            current_positions = await self.position_tracker.get_open_positions()

            assessment = await self.risk_enforcer.validate_order(
                signal=signal,
                portfolio_value=self.portfolio_value,
                current_positions=current_positions,
                entry_price=entry_price,
            )

            (time.perf_counter() - risk_start) * 1000

            if not assessment.approved:
                logger.warning(
                    f"Signal rejected by risk enforcer: {assessment.violations} "
                    f"(correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_rejected"] += 1
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.REJECTED,
                    reject_reason=assessment.violations,
                    correlation_id=correlation_id,
                )

            # Step 4: Create order
            order = self._create_order(
                signal, assessment.position_size, entry_price, correlation_id
            )

            # Step 5: Place order (with latency check)
            order_start = time.perf_counter()
            filled_order = await self.order_simulator.place_order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
            )
            order_latency_ms = (time.perf_counter() - order_start) * 1000

            if order_latency_ms > self.TARGET_SIGNAL_TO_ORDER_MS:
                logger.warning(
                    f"Order placement latency {order_latency_ms:.1f}ms exceeds target "
                    f"{self.TARGET_SIGNAL_TO_ORDER_MS}ms (correlation_id={correlation_id})"
                )

            # Step 5: Handle fill
            if filled_order.state == OrderState.FILLED:
                position_start = time.perf_counter()
                position = await self._open_position(
                    filled_order, signal, correlation_id
                )
                position_latency_ms = (time.perf_counter() - position_start) * 1000

                if position_latency_ms > self.TARGET_POSITION_UPDATE_MS:
                    logger.warning(
                        f"Position update latency {position_latency_ms:.1f}ms exceeds target "
                        f"{self.TARGET_POSITION_UPDATE_MS}ms (correlation_id={correlation_id})"
                    )

                # Step 6: Record trade metrics
                await self._record_trade(position, signal, correlation_id)

                # Calculate total latency
                total_latency_ms = (time.perf_counter() - start_time) * 1000

                # Update running average
                async with self._lock:
                    total_signals = self._metrics["signals_processed"] + 1
                    self._metrics["total_latency_ms"] += total_latency_ms
                    self._metrics["avg_latency_ms"] = (
                        self._metrics["total_latency_ms"] / total_signals
                    )

                if total_latency_ms > self.TARGET_TOTAL_PIPELINE_MS:
                    logger.warning(
                        f"Total pipeline latency {total_latency_ms:.1f}ms exceeds target "
                        f"{self.TARGET_TOTAL_PIPELINE_MS}ms (correlation_id={correlation_id})"
                    )

                logger.info(
                    f"Trade executed: {signal.token} position={position.position_id} "
                    f"latency={total_latency_ms:.1f}ms (correlation_id={correlation_id})"
                )

                async with self._lock:
                    self._metrics["trades_executed"] += 1

                # Wire outcome_capture.on_trade_result() if configured
                if self.outcome_capture:
                    try:
                        result_for_capture = PaperTradeResult(
                            signal=signal,
                            status=TradeStatus.EXECUTED,
                            order=filled_order,
                            position=position,
                            latency_ms=total_latency_ms,
                            correlation_id=correlation_id,
                        )
                        await self.outcome_capture.on_trade_result(result_for_capture)
                    except Exception as e:
                        logger.warning(f"outcome_capture.on_trade_result failed: {e}")

                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.EXECUTED,
                    order=filled_order,
                    position=position,
                    latency_ms=total_latency_ms,
                    correlation_id=correlation_id,
                )
            else:
                # Order not filled
                logger.warning(
                    f"Order not filled: state={filled_order.state.value} "
                    f"(correlation_id={correlation_id})"
                )
                async with self._lock:
                    self._metrics["trades_failed"] += 1
                return PaperTradeResult(
                    signal=signal,
                    status=TradeStatus.FAILED,
                    order=filled_order,
                    reject_reason=[f"Order state: {filled_order.state.value}"],
                    correlation_id=correlation_id,
                )

        except Exception as e:
            # Log error with correlation ID but don't crash
            logger.error(
                f"Error processing signal: {e} (correlation_id={correlation_id})",
                exc_info=True,
            )

            async with self._lock:
                self._metrics["trades_failed"] += 1
            return PaperTradeResult(
                signal=signal,
                status=TradeStatus.FAILED,
                reject_reason=[str(e)],
                correlation_id=correlation_id,
            )

    def _create_order(
        self,
        signal: Signal,
        position_size: float,
        entry_price: float,
        correlation_id: str,
    ) -> PaperOrder:
        """Create an order from a signal.

        Args:
            signal: Trading signal
            position_size: Calculated position size
            entry_price: Entry price for the order
            correlation_id: Correlation ID for tracing

        Returns:
            PaperOrder ready for placement

        Raises:
            ValueError: If entry_price is not positive
        """
        # Validate entry price
        if entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got: {entry_price}")

        # Map signal direction to order side
        side = OrderSide.BUY if signal.direction.value == "long" else OrderSide.SELL

        # Create market order (could be extended for limit orders)
        order = PaperOrder(
            order_id=str(uuid.uuid4()),
            symbol=signal.token,
            side=side.value,  # Use string value, not enum
            order_type=OrderType.MARKET.value,  # Use string value, not enum
            quantity=position_size,
            price=entry_price,  # Set the entry price
        )

        # Store correlation_id and stop-loss in metadata
        order.metadata["correlation_id"] = correlation_id
        if signal.stop_loss:
            order.metadata["stop_loss"] = signal.stop_loss
            order.metadata["stop_loss_method"] = signal.stop_loss_method or "unknown"

        logger.debug(
            f"Created {order.order_type} order: {order.symbol} "
            f"{order.side} {order.quantity} @ ${entry_price:,.2f} "
            f"(value=${order.quantity * entry_price:,.2f})"
        )

        return order

    async def _open_position(
        self,
        filled_order: PaperOrder,
        signal: Signal,
        correlation_id: str,
    ) -> Any:
        """Open a position from a filled order.

        Args:
            filled_order: The filled order
            signal: Original signal
            correlation_id: Correlation ID

        Returns:
            New PaperPosition
        """
        # Determine position side from signal
        side = signal.direction.value  # "long" or "short"

        # Open position via tracker
        position = await self.position_tracker.open_position(
            symbol=filled_order.symbol,
            side=side,
            entry_price=filled_order.avg_fill_price,
            quantity=filled_order.filled_quantity,
            metadata={
                "signal_id": signal.signal_id,
                "order_id": filled_order.order_id,
                "correlation_id": correlation_id,
                "stop_loss": signal.stop_loss,
                "stop_loss_method": signal.stop_loss_method,
                "confidence": signal.confidence,
            },
        )

        logger.debug(f"Opened position: {position.position_id}")

        # Send Discord notification if notifier is configured
        if self.trade_notifier:
            try:
                outcome = self.trade_notifier.create_outcome_from_paper_position(
                    position=position,
                    order=filled_order,
                    signal_id=signal.signal_id,
                )
                result = await self.trade_notifier.send_trade_open_notification(outcome)

                if result.success:
                    logger.info(
                        f"Discord trade open alert sent: position={position.position_id} "
                        f"message_id={result.message_id}"
                    )
                else:
                    logger.warning(
                        f"Discord trade open alert failed: position={position.position_id} "
                        f"error={result.error}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to send Discord trade open notification: {e}",
                    exc_info=True,
                )

        return position

    async def _record_trade(
        self,
        position: Any,
        signal: Signal,
        correlation_id: str,
    ) -> None:
        """Record trade in telemetry.

        Args:
            position: The opened position
            signal: Original signal
            correlation_id: Correlation ID
        """
        try:
            from execution.telemetry.metrics import PositionEvent, PositionSide

            # Create position event for telemetry
            side = PositionSide.LONG if position.side == "long" else PositionSide.SHORT

            event = PositionEvent(
                position_id=position.position_id,
                symbol=position.symbol,
                side=side,
                entry_price=position.entry_price,
                current_price=position.entry_price,
                quantity=position.quantity,
                unrealized_pnl=0.0,
                environment="paper",
            )

            # Update equity
            if self.telemetry:
                await self.telemetry.set_equity(self.portfolio_value)

            logger.debug(f"Recorded position: {event.position_id}")

        except Exception as e:
            # Log error but don't fail the trade
            logger.error(f"Failed to record trade: {e}")

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "manual",
    ) -> tuple[Any, float] | None:
        """Close a position.

        Args:
            position_id: Position to close
            exit_price: Exit price
            reason: Reason for closure

        Returns:
            Tuple of (position, realized_pnl) or None if not found
        """
        try:
            position, realized_pnl = await self.position_tracker.close_position(
                position_id=position_id,
                exit_price=exit_price,
            )

            logger.info(
                f"Closed position {position_id}: PnL={realized_pnl:.4f}, reason={reason}"
            )

            # Update portfolio value
            self.portfolio_value += realized_pnl
            if self.telemetry:
                await self.telemetry.set_equity(self.portfolio_value)

            # Wire outcome_capture.on_position_close() if configured
            if self.outcome_capture:
                try:
                    # Get correlation_id from position metadata if available
                    correlation_id = None
                    if position.metadata:
                        correlation_id = position.metadata.get("correlation_id")
                    await self.outcome_capture.on_position_close(
                        position=position,
                        exit_price=exit_price,
                        realized_pnl=realized_pnl,
                        reason=reason,
                        correlation_id=correlation_id,
                    )
                except Exception as e:
                    logger.warning(f"outcome_capture.on_position_close failed: {e}")

            # Send Discord notification if notifier is configured
            if self.trade_notifier:
                try:
                    outcome = self.trade_notifier.create_outcome_from_paper_position(
                        position=position,
                        signal_id=position.metadata.get("signal_id")
                        if position.metadata
                        else None,
                        pnl=realized_pnl,
                        exit_price=exit_price,
                    )
                    result = await self.trade_notifier.send_trade_close_notification(
                        outcome
                    )

                    if result.success:
                        logger.info(
                            f"Discord trade close alert sent: position={position_id} "
                            f"message_id={result.message_id}"
                        )
                    else:
                        logger.warning(
                            f"Discord trade close alert failed: position={position_id} "
                            f"error={result.error}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to send Discord trade close notification: {e}",
                        exc_info=True,
                    )

            return position, realized_pnl

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            return None

    def get_metrics(self) -> dict[str, Any]:
        """Get orchestrator metrics.

        Returns:
            Dictionary with performance metrics
        """
        return self._metrics.copy()

    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Get current portfolio summary.

        Returns:
            Portfolio summary with positions and PnL
        """
        # Get positions (without price updates for speed)
        open_positions = await self.position_tracker.get_open_positions()
        closed_positions = await self.position_tracker.get_closed_positions()

        total_unrealized = sum(p.unrealized_pnl for p in open_positions)
        total_realized = sum(p.realized_pnl for p in closed_positions)

        return {
            "portfolio_value": self.portfolio_value,
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_pnl": total_unrealized + total_realized,
            "metrics": self._metrics.copy(),
        }
