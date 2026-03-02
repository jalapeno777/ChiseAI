"""Paper trading order simulator models.

Defines dataclasses for paper orders, fills, and order states.
Mimics real exchange behavior without hitting live APIs.

For PAPER-LOOP-001: Paper Trading Order Simulator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class OrderState(Enum):
    """Order lifecycle states.

    States:
        PENDING: Order submitted, awaiting processing
        PARTIAL: Order partially filled
        FILLED: Order completely filled
        REJECTED: Order rejected (invalid or error)
        CANCELLED: Order cancelled by user
        EXPIRED: Order expired (for time-limited orders)
    """

    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TradeStatus(Enum):
    """Trade execution status.

    Statuses:
        EXECUTED: Trade was successfully executed
        REJECTED: Trade was rejected by risk gate
        FAILED: Trade execution failed
        SKIPPED: Trade skipped (e.g., already in position)
    """

    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrderType(Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"


class OrderSide(Enum):
    """Order side (buy/sell)."""

    BUY = "buy"
    SELL = "sell"


@dataclass
class PaperOrder:
    """A paper trading order.

    Represents an order in the paper trading system with full lifecycle
    tracking from submission through fill or rejection.

    Attributes:
        order_id: Unique order identifier
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Order side - "buy" or "sell"
        order_type: Order type - "market" or "limit"
        quantity: Order quantity in base currency
        price: Order price in quote currency (None for market orders)
        state: Current order state
        filled_quantity: Quantity already filled
        remaining_quantity: Quantity remaining to fill
        created_at: Order creation timestamp (UTC)
        updated_at: Last update timestamp (UTC)
        fills: List of fill events for this order
        reject_reason: Reason for rejection (if rejected)
        metadata: Additional order metadata
    """

    order_id: str
    symbol: str
    side: str  # buy/sell
    order_type: str  # market/limit
    quantity: float
    price: float | None = None  # None for market orders
    state: OrderState = field(default=OrderState.PENDING)
    filled_quantity: float = field(default=0.0)
    remaining_quantity: float = field(default=0.0)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    fills: list[PaperFill] = field(default_factory=list)
    reject_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    avg_fill_price: float | None = None
    filled_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate and normalize order data."""
        if isinstance(self.side, Enum):
            self.side = str(self.side.value)

        if isinstance(self.order_type, Enum):
            self.order_type = str(self.order_type.value)

        # Normalize side to lowercase
        self.side = self.side.lower()
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side}. Must be 'buy' or 'sell'")

        # Normalize order_type to lowercase
        self.order_type = self.order_type.lower()
        if self.order_type not in ("market", "limit"):
            raise ValueError(
                f"Invalid order_type: {self.order_type}. Must be 'market' or 'limit'"
            )

        # Validate quantity
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be positive")

        # Validate price for limit orders
        if self.order_type == "limit" and (self.price is None or self.price <= 0):
            raise ValueError(f"Limit orders require positive price, got: {self.price}")

        # Initialize remaining quantity
        if self.remaining_quantity == 0.0 and self.filled_quantity == 0.0:
            self.remaining_quantity = self.quantity

        # Ensure timestamps are timezone-aware
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=UTC)

        if self.correlation_id:
            self.metadata.setdefault("correlation_id", self.correlation_id)

    def is_active(self) -> bool:
        """Check if order is still active (can be filled)."""
        return self.state in (OrderState.PENDING, OrderState.PARTIAL)

    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.state == OrderState.FILLED

    def is_cancelled(self) -> bool:
        """Check if order was cancelled."""
        return self.state == OrderState.CANCELLED

    def is_rejected(self) -> bool:
        """Check if order was rejected."""
        return self.state == OrderState.REJECTED

    def add_fill(self, fill: PaperFill) -> None:
        """Add a fill to this order and update state.

        Args:
            fill: The fill event to add
        """
        self.fills.append(fill)
        self.filled_quantity += fill.quantity
        self.remaining_quantity = self.quantity - self.filled_quantity

        # Update state based on fill
        if self.remaining_quantity <= 0:
            self.state = OrderState.FILLED
            self.remaining_quantity = 0.0
            self.filled_at = datetime.now(UTC)
        else:
            self.state = OrderState.PARTIAL

        total_value = sum(f.price * f.quantity for f in self.fills)
        self.avg_fill_price = total_value / self.filled_quantity

        self.updated_at = datetime.now(UTC)

    def reject(self, reason: str) -> None:
        """Mark order as rejected.

        Args:
            reason: Reason for rejection
        """
        self.state = OrderState.REJECTED
        self.reject_reason = reason
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> bool:
        """Cancel the order if it can be cancelled.

        Returns:
            True if cancelled, False if already filled or rejected
        """
        if self.state in (OrderState.PENDING, OrderState.PARTIAL):
            self.state = OrderState.CANCELLED
            self.updated_at = datetime.now(UTC)
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary for serialization.

        Returns:
            Dictionary representation of the order
        """
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "state": self.state.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "fills": [f.to_dict() for f in self.fills],
            "reject_reason": self.reject_reason,
            "avg_fill_price": self.avg_fill_price,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "metadata": self.metadata,
            "correlation_id": self.metadata.get("correlation_id", self.correlation_id),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperOrder:
        """Create PaperOrder from dictionary.

        Args:
            data: Dictionary with order data

        Returns:
            PaperOrder instance
        """
        order = cls(
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["order_type"],
            quantity=data["quantity"],
            price=data.get("price"),
            state=OrderState(data.get("state", "pending")),
            filled_quantity=data.get("filled_quantity", 0.0),
            remaining_quantity=data.get("remaining_quantity", 0.0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
            correlation_id=data.get("correlation_id", ""),
            avg_fill_price=data.get("avg_fill_price"),
            filled_at=(
                datetime.fromisoformat(data["filled_at"])
                if data.get("filled_at")
                else None
            ),
        )
        # Restore fills
        order.fills = [PaperFill.from_dict(f) for f in data.get("fills", [])]
        order.reject_reason = data.get("reject_reason")
        return order


@dataclass
class PaperFill:
    """A paper trading fill event.

    Represents a single fill event for an order, capturing
    the executed quantity and price with timestamp.

    Attributes:
        fill_id: Unique fill identifier
        order_id: Reference to parent order
        symbol: Trading pair symbol
        side: Fill side - "buy" or "sell"
        quantity: Filled quantity
        price: Fill price
        timestamp: Fill timestamp (UTC)
        metadata: Additional fill metadata
    """

    fill_id: str
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate fill data."""
        # Normalize side
        self.side = self.side.lower()
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side}. Must be 'buy' or 'sell'")

        # Validate quantity
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be positive")

        # Validate price
        if self.price <= 0:
            raise ValueError(f"Invalid price: {self.price}. Must be positive")

        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

    @property
    def notional_value(self) -> float:
        """Calculate notional value (price * quantity)."""
        return self.price * self.quantity

    def to_dict(self) -> dict[str, Any]:
        """Convert fill to dictionary for serialization.

        Returns:
            Dictionary representation of the fill
        """
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "notional_value": self.notional_value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperFill:
        """Create PaperFill from dictionary.

        Args:
            data: Dictionary with fill data

        Returns:
            PaperFill instance
        """
        return cls(
            fill_id=data["fill_id"],
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=data["quantity"],
            price=data["price"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PaperTradeResult:
    """Result of a paper trade execution.

    Attributes:
        signal: The signal that triggered the trade
        status: Trade execution status (EXECUTED, REJECTED, FAILED)
        order: The placed order (if any)
        position: The opened position (if any)
        reject_reason: List of reasons for rejection
        latency_ms: Total execution latency in milliseconds
        correlation_id: Correlation ID for tracing
    """

    signal: Any
    status: TradeStatus
    order: PaperOrder | None = None
    position: Any | None = None
    reject_reason: list[str] | None = None
    latency_ms: float = 0.0
    correlation_id: str = ""

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.reject_reason is None:
            self.reject_reason = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        from signal_generation.models import Signal

        signal_dict = {}
        if self.signal:
            if isinstance(self.signal, Signal):
                signal_dict = {
                    "signal_id": self.signal.signal_id,
                    "token": self.signal.token,
                    "direction": (
                        self.signal.direction.value
                        if hasattr(self.signal.direction, "value")
                        else str(self.signal.direction)
                    ),
                    "confidence": self.signal.confidence,
                }
            else:
                signal_dict = {"type": str(type(self.signal))}

        position_dict = None
        if self.position:
            if hasattr(self.position, "to_dict"):
                position_dict = self.position.to_dict()
            elif hasattr(self.position, "__dict__"):
                position_dict = {
                    "position_id": getattr(self.position, "position_id", None),
                    "symbol": getattr(self.position, "symbol", None),
                    "side": getattr(self.position, "side", None),
                    "entry_price": getattr(self.position, "entry_price", None),
                    "quantity": getattr(self.position, "quantity", None),
                }

        return {
            "signal": signal_dict,
            "status": (
                self.status.value if hasattr(self.status, "value") else str(self.status)
            ),
            "order": self.order.to_dict() if self.order else None,
            "position": position_dict,
            "reject_reason": (
                [str(r) for r in self.reject_reason] if self.reject_reason else []
            ),
            "latency_ms": self.latency_ms,
            "correlation_id": self.correlation_id,
        }


@dataclass
class RiskAssessment:
    """Compatibility risk assessment model used by orchestrator tests."""

    approved: bool
    violations: list[str] = field(default_factory=list)
    position_size: float = 0.0
    margin_required: float = 0.0
    correlation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
