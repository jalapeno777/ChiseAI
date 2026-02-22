"""Signal Outcome models for trade outcome tracking.

This module defines the data structures for capturing and storing
trade outcomes from exchange fill events, enabling signal-to-outcome
matching for ML feedback loops.

For ST-LAUNCH-018: Outcome Capture Service Implementation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class OutcomeType(str, Enum):
    """Type of trade outcome."""

    TP_HIT = "tp_hit"  # Take profit target hit
    SL_HIT = "sl_hit"  # Stop loss triggered
    MANUAL_CLOSE = "manual_close"  # Manual position close
    EXPIRED = "expired"  # Signal expired without execution
    PARTIAL_FILL = "partial_fill"  # Order partially filled
    UNKNOWN = "unknown"  # Unknown outcome type


class SignalOutcomeStatus(str, Enum):
    """Status of signal outcome record."""

    PENDING = "pending"  # Waiting for fill
    FILLED = "filled"  # Complete fill received
    PARTIAL = "partial"  # Partial fill
    ERROR = "error"  # Error processing outcome
    MATCHED = "matched"  # Successfully matched to signal


@dataclass
class SignalOutcome:
    """Trade outcome record linked to a signal.

    Attributes:
        outcome_id: Unique identifier for this outcome
        signal_id: UUID of the originating signal
        order_id: Exchange order ID
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Trade side ("Buy" or "Sell")
        fill_price: Execution price
        fill_quantity: Filled quantity
        fill_timestamp: When the fill occurred (UTC)
        outcome_type: Type of outcome (tp_hit, sl_hit, etc.)
        pnl: Profit/loss amount (optional)
        fee: Trading fee paid (optional)
        status: Processing status
        created_at: When record was created
        metadata: Additional exchange-specific data
    """

    outcome_id: UUID = field(default_factory=uuid4)
    signal_id: UUID | None = None
    order_id: str = ""
    symbol: str = ""
    side: str = ""  # "Buy" or "Sell"
    fill_price: Decimal = field(default_factory=lambda: Decimal("0"))
    fill_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    fill_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    outcome_type: OutcomeType = OutcomeType.UNKNOWN
    pnl: Decimal | None = None
    fee: Decimal | None = None
    status: SignalOutcomeStatus = SignalOutcomeStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize values after initialization."""
        # Ensure UUID types
        if isinstance(self.outcome_id, str):
            self.outcome_id = UUID(self.outcome_id)
        if isinstance(self.signal_id, str) and self.signal_id:
            self.signal_id = UUID(self.signal_id)

        # Normalize side to Title Case
        if self.side:
            self.side = self.side.capitalize()

        # Ensure Decimal types
        if isinstance(self.fill_price, (int, float, str)):
            self.fill_price = Decimal(str(self.fill_price))
        if isinstance(self.fill_quantity, (int, float, str)):
            self.fill_quantity = Decimal(str(self.fill_quantity))
        if self.pnl is not None and isinstance(self.pnl, (int, float, str)):
            self.pnl = Decimal(str(self.pnl))
        if self.fee is not None and isinstance(self.fee, (int, float, str)):
            self.fee = Decimal(str(self.fee))

        # Ensure datetime is timezone-aware
        if self.fill_timestamp.tzinfo is None:
            self.fill_timestamp = self.fill_timestamp.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)

    @property
    def fill_value(self) -> Decimal:
        """Calculate total fill value (price * quantity)."""
        return self.fill_price * self.fill_quantity

    @property
    def is_filled(self) -> bool:
        """Check if outcome represents a complete fill."""
        return self.status == SignalOutcomeStatus.FILLED

    @property
    def has_signal_match(self) -> bool:
        """Check if this outcome is matched to a signal."""
        return self.signal_id is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the outcome
        """
        return {
            "outcome_id": str(self.outcome_id),
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "fill_price": str(self.fill_price),
            "fill_quantity": str(self.fill_quantity),
            "fill_timestamp": self.fill_timestamp.isoformat(),
            "outcome_type": self.outcome_type.value,
            "pnl": str(self.pnl) if self.pnl is not None else None,
            "fee": str(self.fee) if self.fee is not None else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignalOutcome:
        """Create SignalOutcome from dictionary.

        Args:
            data: Dictionary with outcome data

        Returns:
            SignalOutcome instance
        """
        # Parse enums
        outcome_type = data.get("outcome_type", "unknown")
        if isinstance(outcome_type, str):
            try:
                outcome_type = OutcomeType(outcome_type)
            except ValueError:
                outcome_type = OutcomeType.UNKNOWN

        status = data.get("status", "pending")
        if isinstance(status, str):
            try:
                status = SignalOutcomeStatus(status)
            except ValueError:
                status = SignalOutcomeStatus.PENDING

        return cls(
            outcome_id=UUID(data["outcome_id"]) if "outcome_id" in data else uuid4(),
            signal_id=UUID(data["signal_id"]) if data.get("signal_id") else None,
            order_id=data.get("order_id", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            fill_price=Decimal(data.get("fill_price", "0")),
            fill_quantity=Decimal(data.get("fill_quantity", "0")),
            fill_timestamp=(
                datetime.fromisoformat(data["fill_timestamp"])
                if "fill_timestamp" in data
                else datetime.now(UTC)
            ),
            outcome_type=outcome_type,
            pnl=Decimal(data["pnl"]) if data.get("pnl") else None,
            fee=Decimal(data["fee"]) if data.get("fee") else None,
            status=status,
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(UTC)
            ),
            metadata=data.get("metadata", {}),
        )

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to database-compatible dictionary.

        Returns:
            Dictionary suitable for database storage
        """
        return {
            "outcome_id": str(self.outcome_id),
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "fill_price": float(self.fill_price),
            "fill_quantity": float(self.fill_quantity),
            "fill_timestamp": self.fill_timestamp,
            "outcome_type": self.outcome_type.value,
            "pnl": float(self.pnl) if self.pnl is not None else None,
            "fee": float(self.fee) if self.fee is not None else None,
            "status": self.status.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class BybitFillEvent:
    """Raw fill event from Bybit WebSocket.

    Attributes:
        order_id: Bybit order ID
        symbol: Trading pair
        side: Order side (Buy/Sell)
        price: Execution price
        qty: Executed quantity
        exec_time: Execution timestamp (Unix ms)
        exec_type: Execution type
        fee: Trading fee
        fee_rate: Fee rate
    """

    order_id: str
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    exec_time: int  # Unix timestamp in milliseconds
    exec_type: str = ""
    fee: Decimal | None = None
    fee_rate: Decimal | None = None

    @classmethod
    def from_websocket_data(cls, data: dict[str, Any]) -> BybitFillEvent:
        """Parse Bybit WebSocket execution data.

        Args:
            data: Raw WebSocket message data dict

        Returns:
            Parsed BybitFillEvent
        """
        return cls(
            order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            price=Decimal(data.get("price", "0")),
            qty=Decimal(data.get("qty", "0")),
            exec_time=int(data.get("execTime", 0)),
            exec_type=data.get("execType", ""),
            fee=Decimal(data.get("fee", "0")) if data.get("fee") else None,
            fee_rate=Decimal(data.get("feeRate", "0")) if data.get("feeRate") else None,
        )

    def to_signal_outcome(self) -> SignalOutcome:
        """Convert fill event to SignalOutcome.

        Returns:
            SignalOutcome instance from this fill
        """
        return SignalOutcome(
            order_id=self.order_id,
            symbol=self.symbol,
            side=self.side,
            fill_price=self.price,
            fill_quantity=self.qty,
            fill_timestamp=datetime.fromtimestamp(self.exec_time / 1000, tz=UTC),
            fee=self.fee,
            status=SignalOutcomeStatus.FILLED,
        )


@dataclass
class OutcomeMatchResult:
    """Result of matching a fill to a signal.

    Attributes:
        outcome: The matched outcome
        signal_id: UUID of matched signal (if found)
        confidence: Match confidence score (0.0-1.0)
        matched: Whether a match was found
        match_method: How the match was made
        error: Error message if matching failed
    """

    outcome: SignalOutcome
    signal_id: UUID | None = None
    confidence: float = 0.0
    matched: bool = False
    match_method: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "outcome": self.outcome.to_dict(),
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "confidence": self.confidence,
            "matched": self.matched,
            "match_method": self.match_method,
            "error": self.error,
        }
