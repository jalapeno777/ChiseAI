"""Signal Outcome models for trade outcome tracking.

This module defines the data structures for capturing and storing
trade outcomes from exchange fill events, enabling signal-to-outcome
matching for ML feedback loops.

For ST-LAUNCH-018: Outcome Capture Service Implementation
For RECON-001: Trade Schema Reconciliation
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
    CLOSED = "closed"  # Position closed with realized PnL


class EntryReason(str, Enum):
    """Reason for trade entry."""

    SIGNAL_TRIGGER = "signal_trigger"  # Entry from signal trigger
    MANUAL = "manual"  # Manual entry
    DCA = "dca"  # Dollar-cost averaging entry
    STOP_ENTRY = "stop_entry"  # Stop entry order filled
    LIMIT_ENTRY = "limit_entry"  # Limit entry order filled


@dataclass
class SignalOutcome:
    """Trade outcome record linked to a signal.

    Attributes:
        outcome_id: Unique identifier for this outcome
        signal_id: UUID of the originating signal
        order_id: Exchange order ID
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        token: Token/coin symbol (alias for symbol base, e.g., "BTC")
        side: Trade side ("Buy" or "Sell")
        direction: Position direction ("LONG" or "SHORT")
        fill_price: Execution price
        fill_quantity: Filled quantity
        fill_timestamp: When the fill occurred (UTC)
        outcome_type: Type of outcome (tp_hit, sl_hit, etc.)
        pnl: Profit/loss amount (optional)
        fee: Trading fee paid (optional)
        status: Processing status
        created_at: When record was created
        metadata: Additional exchange-specific data

        # RECON-001: New canonical trade outcome fields
        entry_price: Entry price for the position
        exit_price: Exit price (None if position still open)
        entry_time: When position was entered (UTC)
        exit_time: When position was exited (UTC, None if still open)
        leverage: Leverage used (default 1.0 for spot)
        entry_reason: Reason for entry (signal_trigger, manual, etc.)
        position_size: Position size in base token

        # DISCORD-TRADING-001: Test trade labeling
        is_test: Whether this is a test trade (for test labeling in notifications)

        # ST-VENUE-001: Venue provenance fields
        execution_venue: Where the trade was executed (e.g., "bybit_demo", "local_sim")
        execution_mode: Mode of execution (e.g., "demo", "testnet", "production")
        execution_source: Source component that executed the trade (e.g., "bybit_demo_connector", "paper_trading")
        venue_metadata: Additional venue-specific metadata
    """

    outcome_id: UUID = field(default_factory=uuid4)
    signal_id: UUID | None = None
    order_id: str = ""
    symbol: str = ""
    token: str = ""  # Token/coin symbol (alias for symbol base)
    side: str = ""  # "Buy" or "Sell"
    direction: str = ""  # "LONG" or "SHORT"
    fill_price: Decimal = field(default_factory=lambda: Decimal("0"))
    fill_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    fill_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    outcome_type: OutcomeType = OutcomeType.UNKNOWN
    pnl: Decimal | None = None
    fee: Decimal | None = None
    status: SignalOutcomeStatus = SignalOutcomeStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    # RECON-001: Canonical trade outcome fields
    entry_price: Decimal = field(default_factory=lambda: Decimal("0"))
    exit_price: Decimal | None = None
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    exit_time: datetime | None = None
    leverage: Decimal = field(default_factory=lambda: Decimal("1.0"))
    entry_reason: str = ""  # EntryReason as string for flexibility
    position_size: Decimal = field(default_factory=lambda: Decimal("0"))

    # DISCORD-TRADING-001: Test trade labeling
    is_test: bool = False

    # ST-VENUE-001: Venue provenance fields
    execution_venue: str = ""
    execution_mode: str = ""
    execution_source: str = ""
    venue_metadata: dict[str, Any] = field(default_factory=dict)

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

        # Normalize direction to UPPERCASE
        if self.direction:
            self.direction = self.direction.upper()

        # Ensure Decimal types
        if isinstance(self.fill_price, (int, float, str)):
            self.fill_price = Decimal(str(self.fill_price))
        if isinstance(self.fill_quantity, (int, float, str)):
            self.fill_quantity = Decimal(str(self.fill_quantity))
        if self.pnl is not None and isinstance(self.pnl, (int, float, str)):
            self.pnl = Decimal(str(self.pnl))
        if self.fee is not None and isinstance(self.fee, (int, float, str)):
            self.fee = Decimal(str(self.fee))

        # RECON-001: Ensure new fields are Decimal types
        if isinstance(self.entry_price, (int, float, str)):
            self.entry_price = Decimal(str(self.entry_price))
        if self.exit_price is not None and isinstance(
            self.exit_price, (int, float, str)
        ):
            self.exit_price = Decimal(str(self.exit_price))
        if isinstance(self.leverage, (int, float, str)):
            self.leverage = Decimal(str(self.leverage))
        if isinstance(self.position_size, (int, float, str)):
            self.position_size = Decimal(str(self.position_size))

        # Ensure datetime is timezone-aware
        if self.fill_timestamp.tzinfo is None:
            self.fill_timestamp = self.fill_timestamp.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.entry_time.tzinfo is None:
            self.entry_time = self.entry_time.replace(tzinfo=UTC)
        if self.exit_time is not None and self.exit_time.tzinfo is None:
            self.exit_time = self.exit_time.replace(tzinfo=UTC)

        # Derive token from symbol if not set
        if not self.token and self.symbol:
            # Extract base token from symbol (e.g., "BTCUSDT" -> "BTC")
            for quote in ["USDT", "USD", "BUSD", "USDC"]:
                if self.symbol.endswith(quote):
                    self.token = self.symbol[: -len(quote)]
                    break
            else:
                # Default: use symbol as token
                self.token = self.symbol

        # Derive direction from side if not set
        if not self.direction and self.side:
            self.direction = "LONG" if self.side == "Buy" else "SHORT"

        # Sync entry_price with fill_price if entry_price is default
        if self.entry_price == Decimal("0") and self.fill_price > 0:
            self.entry_price = self.fill_price

        # Sync position_size with fill_quantity if position_size is default
        if self.position_size == Decimal("0") and self.fill_quantity > 0:
            self.position_size = self.fill_quantity

    @property
    def fill_value(self) -> Decimal:
        """Calculate total fill value (price * quantity)."""
        return self.fill_price * self.fill_quantity

    @property
    def position_value(self) -> Decimal:
        """Calculate position value (entry_price * position_size)."""
        return self.entry_price * self.position_size

    @property
    def is_filled(self) -> bool:
        """Check if outcome represents a complete fill."""
        return self.status == SignalOutcomeStatus.FILLED

    @property
    def is_closed(self) -> bool:
        """Check if position is closed (has exit data)."""
        return self.status == SignalOutcomeStatus.CLOSED or self.exit_price is not None

    @property
    def has_signal_match(self) -> bool:
        """Check if this outcome is matched to a signal."""
        return self.signal_id is not None

    @property
    def realized_pnl(self) -> Decimal | None:
        """Calculate realized PnL if position is closed."""
        if self.exit_price is None or self.pnl is None:
            return None
        return self.pnl

    @property
    def unrealized_pnl(self) -> Decimal | None:
        """Calculate unrealized PnL based on current price (if available in metadata)."""
        current_price = self.metadata.get("current_price")
        if current_price is None or self.exit_price is not None:
            return None
        current = Decimal(str(current_price))
        if self.direction == "LONG":
            return (current - self.entry_price) * self.position_size * self.leverage
        else:
            return (self.entry_price - current) * self.position_size * self.leverage

    def detect_is_test(self) -> bool:
        """Detect if this outcome represents a test trade.

        Test trades are identified by:
        - signal_id starting with "test-" or "TEST-"
        - order_id containing "test" or "TEST"
        - metadata flag is_test=True
        - execution_mode is "test" or "testnet"
        - execution_source contains "test" or "e2e"

        Returns:
            True if this is a test trade, False otherwise
        """
        # Check signal_id prefix
        signal_id_str = str(self.signal_id) if self.signal_id else ""
        if signal_id_str.lower().startswith("test-"):
            return True

        # Check order_id
        if self.order_id and "test" in self.order_id.lower():
            return True

        # Check metadata flag
        if self.metadata.get("is_test", False):
            return True

        # Check execution mode
        if self.execution_mode and self.execution_mode.lower() in ("test", "testnet"):
            return True

        # Check execution source
        if self.execution_source and (
            "test" in self.execution_source.lower()
            or "e2e" in self.execution_source.lower()
        ):
            return True

        return False

    def validate_test_labeling(self) -> tuple[bool, str | None]:
        """Validate that test trades are properly labeled.

        Returns:
            Tuple of (is_valid, error_message)
        """
        detected_as_test = self.detect_is_test()

        if detected_as_test and not self.is_test:
            return False, (
                f"Test trade detected but is_test=False: "
                f"signal_id={self.signal_id}, order_id={self.order_id}"
            )

        if self.is_test and not detected_as_test:
            # This is a warning case - trade is marked as test but doesn't
            # have obvious test indicators
            return True, None  # Still valid, just flagged

        return True, None

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
            "token": self.token,
            "side": self.side,
            "direction": self.direction,
            "fill_price": str(self.fill_price),
            "fill_quantity": str(self.fill_quantity),
            "fill_timestamp": self.fill_timestamp.isoformat(),
            "outcome_type": self.outcome_type.value,
            "pnl": str(self.pnl) if self.pnl is not None else None,
            "fee": str(self.fee) if self.fee is not None else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            # RECON-001: New fields
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price) if self.exit_price is not None else None,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": (
                self.exit_time.isoformat() if self.exit_time is not None else None
            ),
            "leverage": str(self.leverage),
            "entry_reason": self.entry_reason,
            "position_size": str(self.position_size),
            # DISCORD-TRADING-001: Test trade labeling
            "is_test": self.is_test,
            # ST-VENUE-001: Venue provenance fields
            "execution_venue": self.execution_venue,
            "execution_mode": self.execution_mode,
            "execution_source": self.execution_source,
            "venue_metadata": self.venue_metadata,
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
            token=data.get("token", ""),
            side=data.get("side", ""),
            direction=data.get("direction", ""),
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
            # RECON-001: New fields
            entry_price=Decimal(data.get("entry_price", "0")),
            exit_price=Decimal(data["exit_price"]) if data.get("exit_price") else None,
            entry_time=(
                datetime.fromisoformat(data["entry_time"])
                if "entry_time" in data
                else datetime.now(UTC)
            ),
            exit_time=(
                datetime.fromisoformat(data["exit_time"])
                if data.get("exit_time")
                else None
            ),
            leverage=Decimal(data.get("leverage", "1.0")),
            entry_reason=data.get("entry_reason", ""),
            position_size=Decimal(data.get("position_size", "0")),
            # DISCORD-TRADING-001: Test trade labeling
            is_test=data.get("is_test", False),
            # ST-VENUE-001: Venue provenance fields
            execution_venue=data.get("execution_venue", ""),
            execution_mode=data.get("execution_mode", ""),
            execution_source=data.get("execution_source", ""),
            venue_metadata=data.get("venue_metadata", {}),
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
            "token": self.token,
            "side": self.side,
            "direction": self.direction,
            "fill_price": float(self.fill_price),
            "fill_quantity": float(self.fill_quantity),
            "fill_timestamp": self.fill_timestamp,
            "outcome_type": self.outcome_type.value,
            "pnl": float(self.pnl) if self.pnl is not None else None,
            "fee": float(self.fee) if self.fee is not None else None,
            "status": self.status.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
            # RECON-001: New fields
            "entry_price": float(self.entry_price),
            "exit_price": (
                float(self.exit_price) if self.exit_price is not None else None
            ),
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "leverage": float(self.leverage),
            "entry_reason": self.entry_reason,
            "position_size": float(self.position_size),
            # DISCORD-TRADING-001: Test trade labeling
            "is_test": self.is_test,
            # ST-VENUE-001: Venue provenance fields
            "execution_venue": self.execution_venue,
            "execution_mode": self.execution_mode,
            "execution_source": self.execution_source,
            "venue_metadata": self.venue_metadata,
        }

    def to_notification_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for Discord notifications.

        Returns:
            Dictionary with notification-friendly formatting
        """
        return {
            "outcome_id": str(self.outcome_id),
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "token": self.token,
            "direction": self.direction,
            "entry_price": float(self.entry_price),
            "exit_price": (
                float(self.exit_price) if self.exit_price is not None else None
            ),
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "pnl": float(self.pnl) if self.pnl is not None else None,
            "leverage": float(self.leverage),
            "position_size": float(self.position_size),
            "entry_reason": self.entry_reason,
            "status": self.status.value,
            "is_closed": self.is_closed,
            # DISCORD-TRADING-001: Test trade labeling
            "is_test": self.is_test,
            # ST-VENUE-001: Venue provenance fields
            "execution_venue": self.execution_venue,
            "execution_mode": self.execution_mode,
            "execution_source": self.execution_source,
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
            # RECON-001: Set canonical fields from fill data
            entry_price=self.price,
            entry_time=datetime.fromtimestamp(self.exec_time / 1000, tz=UTC),
            position_size=self.qty,
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


@dataclass
class ReconciliationResult:
    """Result of trade reconciliation between runtime and persistence.

    Attributes:
        total_executed: Total number of executed trades found
        total_persisted: Total number of persisted outcomes found
        matched_count: Number of trades with matching records
        mismatched_trades: List of executed trades without persistence
        missing_persistence: List of persisted records without execution
        orphaned_records: List of orphaned persistence records
        timestamp: When reconciliation was performed
        errors: List of errors encountered during reconciliation
    """

    total_executed: int = 0
    total_persisted: int = 0
    matched_count: int = 0
    mismatched_trades: list[dict[str, Any]] = field(default_factory=list)
    missing_persistence: list[dict[str, Any]] = field(default_factory=list)
    orphaned_records: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_executed": self.total_executed,
            "total_persisted": self.total_persisted,
            "matched_count": self.matched_count,
            "mismatched_trades": self.mismatched_trades,
            "missing_persistence": self.missing_persistence,
            "orphaned_records": self.orphaned_records,
            "timestamp": self.timestamp.isoformat(),
            "errors": self.errors,
        }

    @property
    def is_consistent(self) -> bool:
        """Check if reconciliation shows consistent state."""
        return (
            self.total_executed == self.total_persisted
            and len(self.mismatched_trades) == 0
            and len(self.missing_persistence) == 0
            and len(self.orphaned_records) == 0
            and len(self.errors) == 0
        )

    def get_summary(self) -> str:
        """Get human-readable summary of reconciliation."""
        lines = [
            "=== Trade Reconciliation Report ===",
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Total Executed: {self.total_executed}",
            f"Total Persisted: {self.total_persisted}",
            f"Matched: {self.matched_count}",
            f"Mismatched: {len(self.mismatched_trades)}",
            f"Missing Persistence: {len(self.missing_persistence)}",
            f"Orphaned Records: {len(self.orphaned_records)}",
            f"Errors: {len(self.errors)}",
            f"Status: {'CONSISTENT' if self.is_consistent else 'INCONSISTENT'}",
        ]
        return "\n".join(lines)
