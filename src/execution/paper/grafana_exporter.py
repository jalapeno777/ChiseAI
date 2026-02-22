"""Grafana exporter for paper trading metrics.

Exports paper trading metrics to InfluxDB for Grafana dashboard visibility:
- Position metrics (open positions, unrealized PnL, etc.)
- Portfolio summary (total value, drawdown, etc.)
- Trade execution metrics (fills, signals, etc.)

For PAPER-LOOP-001: Grafana Paper Trading Integration
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portfolio.paper_models import PaperPosition

logger = logging.getLogger(__name__)


@dataclass
class PaperTradeResult:
    """Result of a paper trade execution.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading pair symbol
        side: Trade side (buy/sell)
        quantity: Trade quantity
        price: Execution price
        timestamp: Trade timestamp
        pnl: Realized PnL (for closing trades)
        signal_confidence: Signal confidence score (0-1)
        signal_metadata: Additional signal metadata
    """

    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    pnl: float = 0.0
    signal_confidence: float = 0.0
    signal_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "pnl": self.pnl,
            "signal_confidence": self.signal_confidence,
            "signal_metadata": self.signal_metadata,
        }


@dataclass
class PaperTradingMetrics:
    """Metrics for paper trading.

    Attributes:
        timestamp: When metrics were captured
        portfolio_value: Current portfolio value
        open_positions: Number of open positions
        total_pnl: Total realized PnL
        unrealized_pnl: Total unrealized PnL
        drawdown_pct: Current drawdown percentage
        win_count: Number of winning trades
        loss_count: Number of losing trades
        total_trades: Total number of trades
    """

    timestamp: datetime
    portfolio_value: float
    open_positions: int
    total_pnl: float
    unrealized_pnl: float
    drawdown_pct: float
    win_count: int = 0
    loss_count: int = 0
    total_trades: int = 0

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.win_count / self.total_trades) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "portfolio_value": self.portfolio_value,
            "open_positions": self.open_positions,
            "total_pnl": self.total_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "drawdown_pct": self.drawdown_pct,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
        }


class PaperTradingGrafanaExporter:
    """Export paper trading metrics to InfluxDB for Grafana.

    This exporter provides methods to export paper trading state and metrics
    to InfluxDB for real-time Grafana dashboard visibility.

    Metrics exported:
    - paper_positions: Individual position metrics
    - paper_portfolio: Portfolio summary metrics
    - paper_trades: Trade execution metrics
    - paper_signals: Signal confidence distribution

    Usage:
        exporter = PaperTradingGrafanaExporter(influxdb_client)
        await exporter.export_position(position)
        await exporter.export_portfolio_summary(...)
        await exporter.export_trade(trade_result)
    """

    DEFAULT_INTERVAL = 5.0  # seconds between periodic exports

    def __init__(
        self,
        influxdb_client: Any | None = None,
        measurement_prefix: str = "paper",
        bucket: str = "chiseai",
        org: str = "chiseai",
        interval: float = DEFAULT_INTERVAL,
    ) -> None:
        """Initialize Grafana exporter.

        Args:
            influxdb_client: InfluxDB client (optional)
            measurement_prefix: Prefix for measurement names
            bucket: InfluxDB bucket name
            org: InfluxDB organization
            interval: Export interval in seconds for periodic exports
        """
        self._client = influxdb_client
        self.prefix = measurement_prefix
        self._bucket = bucket
        self._org = org
        self._interval = interval
        self._write_api = None

        # Statistics
        self._export_count = 0
        self._last_export_time: datetime | None = None
        self._failed_exports = 0

        # Trade tracking for win/loss calculation
        self._win_count = 0
        self._loss_count = 0
        self._total_trades = 0

        # Signal confidence tracking
        self._signal_confidences: list[float] = []

        logger.info(
            f"PaperTradingGrafanaExporter initialized: "
            f"prefix={measurement_prefix}, interval={interval}s"
        )

    async def _get_write_api(self) -> Any:
        """Get or create InfluxDB write API."""
        if self._write_api is None and self._client is not None:
            self._write_api = self._client.write_api()
        return self._write_api

    async def export_position(self, position: PaperPosition) -> bool:
        """Export position metrics to InfluxDB.

        Args:
            position: PaperPosition to export

        Returns:
            True if export successful
        """
        try:
            point = self._create_position_point(position)

            write_api = await self._get_write_api()
            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=point,
                )

            self._export_count += 1
            self._last_export_time = datetime.now(UTC)

            logger.debug(
                f"Exported position: {position.symbol} "
                f"side={position.side}, pnl={position.unrealized_pnl:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export position: {e}")
            self._failed_exports += 1
            return False

    def _create_position_point(self, position: PaperPosition) -> Any:
        """Create InfluxDB point for position metrics.

        Args:
            position: PaperPosition to convert

        Returns:
            InfluxDB Point or dict fallback
        """
        try:
            from influxdb_client import Point

            point = Point(f"{self.prefix}_positions")
            point = point.tag("symbol", position.symbol)
            point = point.tag("side", position.side)
            point = point.tag("position_id", position.position_id)

            # Fields
            point = point.field("quantity", position.quantity)
            point = point.field("entry_price", position.entry_price)
            point = point.field("current_price", position.current_price)
            point = point.field("unrealized_pnl", position.unrealized_pnl)
            point = point.field("realized_pnl", position.realized_pnl)
            point = point.field("unrealized_pnl_pct", position.unrealized_pnl_pct)
            point = point.field("notional_value", position.notional_value)
            point = point.field("market_value", position.market_value)
            point = point.field("leverage", position.leverage)
            point = point.field("is_open", 1.0 if position.is_open else 0.0)

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            # Fallback to dict if influxdb_client not available
            return {
                "measurement": f"{self.prefix}_positions",
                "tags": {
                    "symbol": position.symbol,
                    "side": position.side,
                    "position_id": position.position_id,
                },
                "fields": {
                    "quantity": position.quantity,
                    "entry_price": position.entry_price,
                    "current_price": position.current_price,
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                    "unrealized_pnl_pct": position.unrealized_pnl_pct,
                    "notional_value": position.notional_value,
                    "market_value": position.market_value,
                    "leverage": position.leverage,
                    "is_open": 1.0 if position.is_open else 0.0,
                },
                "time": datetime.now(UTC).isoformat(),
            }

    async def export_portfolio_summary(
        self,
        portfolio_value: float,
        open_positions: int,
        total_pnl: float,
        drawdown_pct: float,
        unrealized_pnl: float = 0.0,
    ) -> bool:
        """Export portfolio summary metrics.

        Args:
            portfolio_value: Current total portfolio value
            open_positions: Number of open positions
            total_pnl: Total realized PnL
            drawdown_pct: Current drawdown percentage
            unrealized_pnl: Total unrealized PnL

        Returns:
            True if export successful
        """
        try:
            point = self._create_portfolio_point(
                portfolio_value=portfolio_value,
                open_positions=open_positions,
                total_pnl=total_pnl,
                drawdown_pct=drawdown_pct,
                unrealized_pnl=unrealized_pnl,
            )

            write_api = await self._get_write_api()
            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=point,
                )

            self._export_count += 1
            self._last_export_time = datetime.now(UTC)

            logger.debug(
                f"Exported portfolio summary: value={portfolio_value:.2f}, "
                f"positions={open_positions}, pnl={total_pnl:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export portfolio summary: {e}")
            self._failed_exports += 1
            return False

    def _create_portfolio_point(
        self,
        portfolio_value: float,
        open_positions: int,
        total_pnl: float,
        drawdown_pct: float,
        unrealized_pnl: float,
    ) -> Any:
        """Create InfluxDB point for portfolio metrics.

        Args:
            portfolio_value: Current portfolio value
            open_positions: Number of open positions
            total_pnl: Total realized PnL
            drawdown_pct: Current drawdown percentage
            unrealized_pnl: Total unrealized PnL

        Returns:
            InfluxDB Point or dict fallback
        """
        try:
            from influxdb_client import Point

            point = Point(f"{self.prefix}_portfolio")
            point = point.tag("metric_type", "summary")

            # Fields
            point = point.field("portfolio_value", portfolio_value)
            point = point.field("open_positions", float(open_positions))
            point = point.field("total_pnl", total_pnl)
            point = point.field("unrealized_pnl", unrealized_pnl)
            point = point.field("drawdown_pct", drawdown_pct)
            point = point.field("win_count", float(self._win_count))
            point = point.field("loss_count", float(self._loss_count))
            point = point.field("total_trades", float(self._total_trades))

            # Calculate win rate
            if self._total_trades > 0:
                win_rate = (self._win_count / self._total_trades) * 100
            else:
                win_rate = 0.0
            point = point.field("win_rate", win_rate)

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            return {
                "measurement": f"{self.prefix}_portfolio",
                "tags": {"metric_type": "summary"},
                "fields": {
                    "portfolio_value": portfolio_value,
                    "open_positions": float(open_positions),
                    "total_pnl": total_pnl,
                    "unrealized_pnl": unrealized_pnl,
                    "drawdown_pct": drawdown_pct,
                    "win_count": float(self._win_count),
                    "loss_count": float(self._loss_count),
                    "total_trades": float(self._total_trades),
                    "win_rate": (self._win_count / max(self._total_trades, 1)) * 100,
                },
                "time": datetime.now(UTC).isoformat(),
            }

    async def export_trade(self, trade: PaperTradeResult) -> bool:
        """Export trade execution metrics.

        Args:
            trade: PaperTradeResult to export

        Returns:
            True if export successful
        """
        try:
            point = self._create_trade_point(trade)

            write_api = await self._get_write_api()
            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=point,
                )

            # Update trade statistics
            self._total_trades += 1
            if trade.pnl > 0:
                self._win_count += 1
            elif trade.pnl < 0:
                self._loss_count += 1

            # Track signal confidence
            if trade.signal_confidence > 0:
                self._signal_confidences.append(trade.signal_confidence)
                # Keep only last 1000 confidences
                if len(self._signal_confidences) > 1000:
                    self._signal_confidences = self._signal_confidences[-1000:]

            self._export_count += 1
            self._last_export_time = datetime.now(UTC)

            logger.debug(
                f"Exported trade: {trade.symbol} side={trade.side}, pnl={trade.pnl:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export trade: {e}")
            self._failed_exports += 1
            return False

    def _create_trade_point(self, trade: PaperTradeResult) -> Any:
        """Create InfluxDB point for trade metrics.

        Args:
            trade: PaperTradeResult to convert

        Returns:
            InfluxDB Point or dict fallback
        """
        try:
            from influxdb_client import Point

            point = Point(f"{self.prefix}_trades")
            point = point.tag("symbol", trade.symbol)
            point = point.tag("side", trade.side)
            point = point.tag("trade_id", trade.trade_id)

            # Determine if win/loss/neutral
            if trade.pnl > 0:
                outcome = "win"
            elif trade.pnl < 0:
                outcome = "loss"
            else:
                outcome = "neutral"
            point = point.tag("outcome", outcome)

            # Fields
            point = point.field("quantity", trade.quantity)
            point = point.field("price", trade.price)
            point = point.field("pnl", trade.pnl)
            point = point.field("signal_confidence", trade.signal_confidence)

            point = point.time(trade.timestamp)
            return point

        except ImportError:
            return {
                "measurement": f"{self.prefix}_trades",
                "tags": {
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "trade_id": trade.trade_id,
                    "outcome": (
                        "win"
                        if trade.pnl > 0
                        else ("loss" if trade.pnl < 0 else "neutral")
                    ),
                },
                "fields": {
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "pnl": trade.pnl,
                    "signal_confidence": trade.signal_confidence,
                },
                "time": trade.timestamp.isoformat(),
            }

    async def export_signal_confidence_distribution(self) -> bool:
        """Export signal confidence distribution metrics.

        Creates histogram buckets for signal confidence values.

        Returns:
            True if export successful
        """
        try:
            if not self._signal_confidences:
                return True

            # Create confidence buckets
            buckets = {
                "0.0-0.2": 0,
                "0.2-0.4": 0,
                "0.4-0.6": 0,
                "0.6-0.8": 0,
                "0.8-1.0": 0,
            }

            for conf in self._signal_confidences:
                if conf < 0.2:
                    buckets["0.0-0.2"] += 1
                elif conf < 0.4:
                    buckets["0.2-0.4"] += 1
                elif conf < 0.6:
                    buckets["0.4-0.6"] += 1
                elif conf < 0.8:
                    buckets["0.6-0.8"] += 1
                else:
                    buckets["0.8-1.0"] += 1

            points = []
            for bucket_range, count in buckets.items():
                point = self._create_signal_confidence_point(bucket_range, count)
                points.append(point)

            write_api = await self._get_write_api()
            if write_api is not None:
                write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=points,
                )

            self._export_count += 1
            self._last_export_time = datetime.now(UTC)

            logger.debug("Exported signal confidence distribution")
            return True

        except Exception as e:
            logger.error(f"Failed to export signal confidence: {e}")
            self._failed_exports += 1
            return False

    def _create_signal_confidence_point(self, bucket_range: str, count: int) -> Any:
        """Create InfluxDB point for signal confidence.

        Args:
            bucket_range: Confidence bucket range (e.g., "0.0-0.2")
            count: Number of signals in this bucket

        Returns:
            InfluxDB Point or dict fallback
        """
        try:
            from influxdb_client import Point

            point = Point(f"{self.prefix}_signals")
            point = point.tag("bucket", bucket_range)

            # Fields
            point = point.field("count", float(count))

            point = point.time(datetime.now(UTC))
            return point

        except ImportError:
            return {
                "measurement": f"{self.prefix}_signals",
                "tags": {"bucket": bucket_range},
                "fields": {"count": float(count)},
                "time": datetime.now(UTC).isoformat(),
            }

    async def export_all_positions(self, positions: list[PaperPosition]) -> bool:
        """Export all positions in a batch.

        Args:
            positions: List of PaperPosition to export

        Returns:
            True if all exports successful
        """
        results = []
        for position in positions:
            result = await self.export_position(position)
            results.append(result)

        return all(results) if results else True

    async def start_periodic_export(
        self,
        portfolio_value_fn: Any,
        open_positions_fn: Any,
        total_pnl_fn: Any,
        drawdown_fn: Any,
    ) -> None:
        """Start periodic portfolio summary export.

        Args:
            portfolio_value_fn: Callable that returns current portfolio value
            open_positions_fn: Callable that returns number of open positions
            total_pnl_fn: Callable that returns total PnL
            drawdown_fn: Callable that returns current drawdown percentage
        """
        self._running = True

        async def export_loop():
            while self._running:
                try:
                    await self.export_portfolio_summary(
                        portfolio_value=portfolio_value_fn(),
                        open_positions=open_positions_fn(),
                        total_pnl=total_pnl_fn(),
                        drawdown_pct=drawdown_fn(),
                    )
                    await self.export_signal_confidence_distribution()
                    await asyncio.sleep(self._interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Periodic export error: {e}")
                    await asyncio.sleep(self._interval)

        self._export_task = asyncio.create_task(export_loop())
        logger.info("Paper trading periodic export started")

    async def stop_periodic_export(self) -> None:
        """Stop periodic export loop."""
        self._running = False

        if hasattr(self, "_export_task") and self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Exporter stop wait failed: %s", exc)

        logger.info("Paper trading periodic export stopped")

    def get_stats(self) -> dict[str, Any]:
        """Get exporter statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "export_count": self._export_count,
            "last_export_time": (
                self._last_export_time.isoformat() if self._last_export_time else None
            ),
            "failed_exports": self._failed_exports,
            "interval": self._interval,
            "measurement_prefix": self.prefix,
            "win_count": self._win_count,
            "loss_count": self._loss_count,
            "total_trades": self._total_trades,
            "win_rate": (self._win_count / max(self._total_trades, 1)) * 100,
            "signal_confidence_count": len(self._signal_confidences),
        }

    def get_metrics(self) -> PaperTradingMetrics:
        """Get current metrics snapshot.

        Returns:
            PaperTradingMetrics with current state
        """
        return PaperTradingMetrics(
            timestamp=datetime.now(UTC),
            portfolio_value=0.0,  # Would need to be populated by caller
            open_positions=0,
            total_pnl=0.0,
            unrealized_pnl=0.0,
            drawdown_pct=0.0,
            win_count=self._win_count,
            loss_count=self._loss_count,
            total_trades=self._total_trades,
        )
