"""Execution telemetry metrics dataclasses.

For ST-EX-001: Execution telemetry for paper/live trading metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class OrderStatus(Enum):
    """Order lifecycle status."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class OrderSide(Enum):
    """Order side (buy/sell)."""

    BUY = "buy"
    SELL = "sell"


class PositionSide(Enum):
    """Position side (long/short)."""

    LONG = "long"
    SHORT = "short"


@dataclass
class ExecutionMetrics:
    """Execution performance metrics for KPI tracking.

    Attributes:
        environment: Trading environment (paper/live)
        total_pnl: Total PnL (realized + unrealized)
        realized_pnl: Realized PnL from closed trades
        unrealized_pnl: Unrealized PnL from open positions
        max_drawdown_pct: Maximum drawdown percentage
        win_rate: Win rate as percentage (0-100)
        trade_count: Total number of trades
        win_count: Number of winning trades
        loss_count: Number of losing trades
        sharpe_ratio: Sharpe ratio for risk-adjusted returns
        timestamp: When metrics were calculated
    """

    environment: str  # paper or live
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    max_drawdown_pct: float
    win_rate: float
    trade_count: int
    win_count: int
    loss_count: int
    sharpe_ratio: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "environment": self.environment,
            "total_pnl": self.total_pnl,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "sharpe_ratio": self.sharpe_ratio,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OrderEvent:
    """Order lifecycle event.

    Attributes:
        order_id: Unique order identifier
        symbol: Trading pair (e.g., "BTCUSDT")
        side: Order side (buy/sell)
        status: Order status (pending/filled/partial/cancelled)
        quantity: Order quantity
        price: Order price (or fill price)
        filled_quantity: Filled quantity (for partial fills)
        timestamp: Event timestamp
        environment: Trading environment (paper/live)
    """

    order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    quantity: float
    price: float
    filled_quantity: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    environment: str = "paper"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "status": self.status.value,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
        }


@dataclass
class PositionEvent:
    """Position update event.

    Attributes:
        position_id: Unique position identifier
        symbol: Trading pair (e.g., "BTCUSDT")
        side: Position side (long/short)
        entry_price: Average entry price
        current_price: Current market price
        quantity: Position size
        unrealized_pnl: Current unrealized PnL
        leverage: Leverage multiplier
        timestamp: Event timestamp
        environment: Trading environment (paper/live)
    """

    position_id: str
    symbol: str
    side: PositionSide
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    leverage: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    environment: str = "paper"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "quantity": self.quantity,
            "unrealized_pnl": self.unrealized_pnl,
            "leverage": self.leverage,
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
        }


@dataclass
class Trade:
    """Completed trade record for KPI calculation.

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading pair
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade size
        side: Position side
        pnl: Realized PnL
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        environment: Trading environment
    """

    trade_id: str
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: PositionSide
    pnl: float
    entry_time: datetime
    exit_time: datetime
    environment: str = "paper"

    @property
    def is_win(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0

    @property
    def duration_seconds(self) -> float:
        """Calculate trade duration in seconds."""
        return (self.exit_time - self.entry_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "side": self.side.value,
            "pnl": self.pnl,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "environment": self.environment,
            "is_win": self.is_win,
            "duration_seconds": self.duration_seconds,
        }
