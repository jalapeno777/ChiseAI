"""Paper trading execution models.

Defines dataclasses for orders and fills used in paper trading simulations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OrderState(Enum):
    """State of a paper trading order."""

    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(Enum):
    """Side of an order."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Type of order."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


@dataclass
class PaperOrder:
    """A paper trading order.

    Attributes:
        order_id: Unique order identifier (UUID)
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        side: Order side (buy/sell)
        order_type: Type of order (market/limit/stop)
        quantity: Order size in base token units
        price: Limit price (for limit orders)
        stop_price: Stop trigger price (for stop orders)
        state: Current order state
        filled_quantity: Amount already filled
        avg_fill_price: Average fill price
        created_at: Order creation timestamp
        updated_at: Last update timestamp
        metadata: Additional order metadata
        correlation_id: ID for tracing across components
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    order_id: str = ""
    state: OrderState = OrderState.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        import uuid

        if not self.order_id:
            self.order_id = str(uuid.uuid4())

        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

        # Validate side and type
        if isinstance(self.side, str):
            self.side = OrderSide(self.side.lower())
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type.lower())

    @property
    def remaining_quantity(self) -> float:
        """Get unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.state == OrderState.FILLED

    @property
    def is_open(self) -> bool:
        """Check if order is still open."""
        return self.state in (OrderState.OPEN, OrderState.PARTIALLY_FILLED)

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary for serialization."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": round(self.quantity, 8),
            "price": round(self.price, 8) if self.price else None,
            "stop_price": round(self.stop_price, 8) if self.stop_price else None,
            "state": self.state.value,
            "filled_quantity": round(self.filled_quantity, 8),
            "avg_fill_price": round(self.avg_fill_price, 8),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
        }


@dataclass
class PaperFill:
    """A fill/execution record for a paper trading order.

    Attributes:
        fill_id: Unique fill identifier (UUID)
        order_id: Reference to parent order
        symbol: Trading pair symbol
        side: Execution side
        quantity: Fill quantity
        price: Execution price
        timestamp: Fill timestamp
        fee: Trading fee amount
        metadata: Additional fill metadata
        correlation_id: ID for tracing
    """

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fill_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    fee: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def __post_init__(self) -> None:
        """Validate and generate ID if needed."""
        import uuid

        if not self.fill_id:
            self.fill_id = str(uuid.uuid4())

        if isinstance(self.side, str):
            self.side = OrderSide(self.side.lower())

    @property
    def notional_value(self) -> float:
        """Calculate notional value of fill."""
        return self.quantity * self.price

    @property
    def total_cost(self) -> float:
        """Calculate total cost including fees."""
        return self.notional_value + self.fee

    def to_dict(self) -> dict[str, Any]:
        """Convert fill to dictionary."""
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": round(self.quantity, 8),
            "price": round(self.price, 8),
            "timestamp": self.timestamp,
            "fee": round(self.fee, 8),
            "notional_value": round(self.notional_value, 8),
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
        }


@dataclass
class RiskAssessment:
    """Risk assessment result for an order.

    Attributes:
        approved: Whether order is approved
        violations: List of risk violations
        position_size: Recommended position size
        stop_loss_price: Recommended stop-loss price
        max_loss_amount: Maximum potential loss
        metadata: Additional assessment data
        correlation_id: ID for tracing
    """

    approved: bool
    violations: list[str] = field(default_factory=list)
    position_size: float = 0.0
    stop_loss_price: float | None = None
    max_loss_amount: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""


class TradeStatus(Enum):
    """Status of a paper trade result."""

    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class PaperTradeResult:
    """Result of processing a signal through paper trading.

    Attributes:
        signal: The original signal
        status: Trade execution status
        order: The filled order (if successful)
        position: The created position (if successful)
        reject_reason: Reasons for rejection
        latency_ms: Total processing latency
        correlation_id: ID for tracing
        timestamp: Result timestamp
    """

    signal: Any  # Signal from signal_generation.models
    status: TradeStatus
    order: PaperOrder | None = None
    position: Any | None = None  # PaperPosition from portfolio.paper_models
    reject_reason: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    correlation_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        """Generate correlation ID if needed."""
        import uuid

        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "signal_id": getattr(self.signal, "signal_id", "unknown"),
            "status": self.status.value,
            "order": self.order.to_dict() if self.order else None,
            "position": getattr(self.position, "to_dict", lambda: None)()
            if self.position
            else None,
            "reject_reason": self.reject_reason,
            "latency_ms": round(self.latency_ms, 3),
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }
