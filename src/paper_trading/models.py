"""Paper trading data models.

Pydantic models for paper trading API responses.

For HOTFIX-PAPER-API-001: Paper Trading API Endpoints
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """Order side enumeration."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderState(str, Enum):
    """Order state enumeration."""

    PENDING = "pending"
    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    """Position side enumeration."""

    LONG = "long"
    SHORT = "short"


class PaperPosition(BaseModel):
    """Paper trading position model."""

    symbol: str = Field(..., description="Trading pair symbol (e.g., BTC-USD)")
    side: PositionSide = Field(..., description="Position side (long/short)")
    size: float = Field(..., description="Position size in base currency")
    entry_price: float = Field(..., description="Average entry price")
    mark_price: float | None = Field(None, description="Current mark price")
    unrealized_pnl: float = Field(0.0, description="Unrealized PnL")
    realized_pnl: float = Field(0.0, description="Realized PnL")
    margin: float | None = Field(None, description="Margin used")
    leverage: float = Field(1.0, description="Leverage used")
    created_at: datetime = Field(..., description="Position creation time")
    updated_at: datetime | None = Field(None, description="Last update time")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "margin": self.margin,
            "leverage": self.leverage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PaperOrder(BaseModel):
    """Paper trading order model."""

    order_id: str = Field(..., description="Unique order identifier")
    symbol: str = Field(..., description="Trading pair symbol")
    side: OrderSide = Field(..., description="Order side (buy/sell)")
    order_type: OrderType = Field(..., description="Order type")
    quantity: float = Field(..., description="Order quantity")
    price: float | None = Field(None, description="Order price (None for market)")
    filled_quantity: float = Field(0.0, description="Filled quantity")
    avg_fill_price: float | None = Field(None, description="Average fill price")
    state: OrderState = Field(..., description="Current order state")
    signal_id: str | None = Field(None, description="Associated signal ID")
    correlation_id: str | None = Field(None, description="Correlation ID for tracing")
    created_at: datetime = Field(..., description="Order creation time")
    updated_at: datetime | None = Field(None, description="Last update time")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "avg_fill_price": self.avg_fill_price,
            "state": self.state.value,
            "signal_id": self.signal_id,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


class PaperPnL(BaseModel):
    """Paper trading PnL metrics model."""

    total_realized_pnl: float = Field(0.0, description="Total realized PnL")
    total_unrealized_pnl: float = Field(0.0, description="Total unrealized PnL")
    total_pnl: float = Field(0.0, description="Total PnL (realized + unrealized)")
    win_count: int = Field(0, description="Number of winning trades")
    loss_count: int = Field(0, description="Number of losing trades")
    total_trades: int = Field(0, description="Total number of trades")
    win_rate: float = Field(0.0, description="Win rate percentage")
    avg_win: float = Field(0.0, description="Average winning trade PnL")
    avg_loss: float = Field(0.0, description="Average losing trade PnL")
    profit_factor: float | None = Field(
        None, description="Profit factor (gross profit / gross loss)"
    )
    max_drawdown: float | None = Field(None, description="Maximum drawdown")
    sharpe_ratio: float | None = Field(None, description="Sharpe ratio")
    period_start: datetime | None = Field(None, description="Period start date")
    period_end: datetime | None = Field(None, description="Period end date")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_realized_pnl": self.total_realized_pnl,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_pnl": self.total_pnl,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "period_start": self.period_start.isoformat()
            if self.period_start
            else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


class PaperPortfolio(BaseModel):
    """Paper trading portfolio summary model."""

    portfolio_id: str = Field(..., description="Portfolio identifier")
    balance: float = Field(..., description="Available balance")
    equity: float = Field(..., description="Total equity (balance + positions)")
    margin_used: float = Field(0.0, description="Total margin used")
    margin_available: float = Field(..., description="Available margin")
    open_positions_count: int = Field(0, description="Number of open positions")
    open_orders_count: int = Field(0, description="Number of open orders")
    positions: list[PaperPosition] = Field(
        default_factory=list, description="Open positions"
    )
    recent_orders: list[PaperOrder] = Field(
        default_factory=list, description="Recent orders"
    )
    pnl: PaperPnL | None = Field(None, description="PnL metrics")
    updated_at: datetime | None = Field(None, description="Last update time")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "portfolio_id": self.portfolio_id,
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "margin_available": self.margin_available,
            "open_positions_count": self.open_positions_count,
            "open_orders_count": self.open_orders_count,
            "positions": [p.to_dict() for p in self.positions],
            "recent_orders": [o.to_dict() for o in self.recent_orders],
            "pnl": self.pnl.to_dict() if self.pnl else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Response models for API
class PositionsResponse(BaseModel):
    """Response model for positions endpoint."""

    success: bool = Field(True, description="Whether the request was successful")
    data: dict[str, Any] = Field(..., description="Response data")


class OrdersResponse(BaseModel):
    """Response model for orders endpoint."""

    success: bool = Field(True, description="Whether the request was successful")
    data: dict[str, Any] = Field(..., description="Response data")


class PnLResponse(BaseModel):
    """Response model for PnL endpoint."""

    success: bool = Field(True, description="Whether the request was successful")
    data: dict[str, Any] = Field(..., description="Response data")


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = Field(False, description="Whether the request was successful")
    error: str = Field(..., description="Error message")
