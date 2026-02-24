"""Execution metrics collector.

For ST-EX-001: Collects trade data and pushes KPIs to InfluxDB.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from execution.telemetry.calculator import KPICalculator

if TYPE_CHECKING:
    from execution.telemetry.exporter import ExecutionTelemetryExporter
    from execution.telemetry.metrics import ExecutionMetrics, Trade

logger = logging.getLogger(__name__)


class ExecutionCollector:
    """Collector for execution metrics.

    Collects trade data, calculates KPIs every 60 seconds,
    and pushes to ExecutionTelemetryExporter.
    """

    COLLECTION_INTERVAL = 60  # seconds

    def __init__(
        self,
        exporter: ExecutionTelemetryExporter,
        calculator: KPICalculator | None = None,
        environment: str = "paper",
        portfolio_id: str = "default",
    ):
        """Initialize execution collector.

        Args:
            exporter: Telemetry exporter for InfluxDB writes
            calculator: KPI calculator (creates default if None)
            environment: Trading environment (paper/live)
            portfolio_id: Portfolio identifier
        """
        self.exporter = exporter
        self.calculator = calculator or KPICalculator()
        self.environment = environment
        self.portfolio_id = portfolio_id

        self._trades: list[Trade] = []
        self._open_positions: dict[str, Any] = {}
        self._equity_history: list[tuple[datetime, float]] = []
        self._initial_equity: float = 10000.0
        self._current_equity: float = 10000.0

        self._running = False
        self._collection_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the collector and begin periodic KPI calculation."""
        self._running = True
        self._collection_task = asyncio.create_task(self._collection_loop())
        logger.info(f"ExecutionCollector started ({self.environment})")

    async def stop(self) -> None:
        """Stop the collector."""
        self._running = False

        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._collection_task

        # Final KPI push
        await self._calculate_and_push_kpis()

        logger.info("ExecutionCollector stopped")

    async def _collection_loop(self) -> None:
        """Main collection loop."""
        while self._running:
            try:
                await asyncio.sleep(self.COLLECTION_INTERVAL)
                await self._calculate_and_push_kpis()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Collection loop error: {e}")

    async def _calculate_and_push_kpis(self) -> None:
        """Calculate KPIs and push to exporter."""
        try:
            metrics = await self._calculate_metrics()
            success = await self.exporter.write_metrics(
                metrics, portfolio_id=self.portfolio_id
            )

            if success:
                logger.debug(f"Pushed KPIs: trade_count={metrics.trade_count}")
            else:
                logger.warning("Failed to push KPIs")

        except Exception as e:
            logger.error(f"Failed to calculate/push KPIs: {e}")

    async def _calculate_metrics(self) -> ExecutionMetrics:
        """Calculate current execution metrics.

        Returns:
            ExecutionMetrics with current KPIs
        """
        async with self._lock:
            trades = self._trades.copy()
            equity_curve = [e for _, e in self._equity_history]
            if not equity_curve:
                equity_curve = [self._initial_equity, self._current_equity]

            # Calculate KPIs
            total_pnl = self._current_equity - self._initial_equity
            realized_pnl = sum(t.pnl for t in trades)

            # Calculate unrealized PnL from open positions
            unrealized_pnl = sum(
                pos.get("unrealized_pnl", 0.0) for pos in self._open_positions.values()
            )

            win_rate = self.calculator.calculate_win_rate(trades)
            max_drawdown = self.calculator.calculate_max_drawdown(equity_curve)

            # Calculate Sharpe ratio from returns
            returns = self.calculator.calculate_returns_from_trades(trades)
            sharpe = self.calculator.calculate_sharpe(returns)

            wins = sum(1 for t in trades if t.is_win)
            losses = len(trades) - wins

            from execution.telemetry.metrics import ExecutionMetrics

            return ExecutionMetrics(
                environment=self.environment,
                total_pnl=total_pnl,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                max_drawdown_pct=max_drawdown,
                win_rate=win_rate,
                trade_count=len(trades),
                win_count=wins,
                loss_count=losses,
                sharpe_ratio=sharpe,
            )

    async def add_trade(self, trade: Trade) -> None:
        """Add a completed trade.

        Args:
            trade: Completed trade record
        """
        async with self._lock:
            self._trades.append(trade)
            self._current_equity += trade.pnl
            self._equity_history.append((datetime.now(UTC), self._current_equity))

        logger.debug(f"Added trade: {trade.trade_id}, PnL: {trade.pnl}")

    async def update_position(
        self,
        symbol: str,
        unrealized_pnl: float,
        quantity: float = 0.0,
        side: str = "long",
    ) -> None:
        """Update open position data.

        Args:
            symbol: Trading pair
            unrealized_pnl: Current unrealized PnL
            quantity: Position size
            side: Position side
        """
        async with self._lock:
            if quantity > 0:
                self._open_positions[symbol] = {
                    "symbol": symbol,
                    "unrealized_pnl": unrealized_pnl,
                    "quantity": quantity,
                    "side": side,
                    "updated_at": datetime.now(UTC),
                }
            else:
                self._open_positions.pop(symbol, None)

    async def set_equity(self, equity: float) -> None:
        """Set current equity value.

        Args:
            equity: Current equity value
        """
        async with self._lock:
            self._current_equity = equity
            self._equity_history.append((datetime.now(UTC), equity))

    async def set_initial_equity(self, equity: float) -> None:
        """Set initial equity value.

        Args:
            equity: Initial equity value
        """
        async with self._lock:
            self._initial_equity = equity
            if not self._equity_history:
                self._equity_history.append((datetime.now(UTC), equity))

    def get_stats(self) -> dict[str, Any]:
        """Get collector statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "running": self._running,
            "environment": self.environment,
            "portfolio_id": self.portfolio_id,
            "trade_count": len(self._trades),
            "open_positions": len(self._open_positions),
            "current_equity": self._current_equity,
            "initial_equity": self._initial_equity,
            "total_pnl": self._current_equity - self._initial_equity,
        }

    async def get_trades(self) -> list[Trade]:
        """Get copy of all trades.

        Returns:
            List of trades
        """
        async with self._lock:
            return self._trades.copy()

    async def clear_trades(self) -> None:
        """Clear all trade history."""
        async with self._lock:
            self._trades.clear()
            self._equity_history.clear()
            self._current_equity = self._initial_equity
