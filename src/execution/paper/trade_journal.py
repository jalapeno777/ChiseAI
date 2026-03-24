"""Trade journal data model for paper trading.

Provides comprehensive trade lifecycle tracking with audit trail support.
Captures entry, fill, and exit details for complete trade analysis.

For PAPER-2025-003: Trade Journal Foundation
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ExitReason(Enum):
    """Reason for trade exit.

    Reasons:
        STOP_LOSS_HIT: Position closed due to stop loss trigger
        TAKE_PROFIT_HIT: Position closed due to take profit trigger
        SIGNAL_REVERSE: Position closed due to opposing signal
        TIME_LIMIT: Position closed due to time limit expiration
        MANUAL_CLOSE: Position manually closed by operator
        KILL_SWITCH: Position closed due to kill switch activation
        RISK_REDUCTION: Position closed as part of risk reduction
    """

    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    SIGNAL_REVERSE = "signal_reverse"
    TIME_LIMIT = "time_limit"
    MANUAL_CLOSE = "manual_close"
    KILL_SWITCH = "kill_switch"
    RISK_REDUCTION = "risk_reduction"


@dataclass
class FillRecord:
    """Record of a single fill event.

    Captures the details of a single fill including price, quantity,
    and associated fees.

    Attributes:
        fill_id: Unique identifier for this fill
        timestamp: When the fill occurred (UTC)
        price: Fill price
        quantity: Quantity filled
        fee: Fee charged for this fill
    """

    fill_id: str
    timestamp: datetime
    price: float
    quantity: float
    fee: float = 0.0

    def __post_init__(self) -> None:
        """Validate fill record data."""
        if self.price <= 0:
            raise ValueError(f"Price must be positive, got: {self.price}")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got: {self.quantity}")
        if self.fee < 0:
            raise ValueError(f"Fee cannot be negative, got: {self.fee}")
        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert fill record to dictionary for serialization.

        Returns:
            Dictionary representation of the fill record
        """
        return {
            "fill_id": self.fill_id,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "quantity": self.quantity,
            "fee": self.fee,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FillRecord:
        """Create FillRecord from dictionary.

        Args:
            data: Dictionary with fill record data

        Returns:
            FillRecord instance
        """
        return cls(
            fill_id=data["fill_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            price=data["price"],
            quantity=data["quantity"],
            fee=data.get("fee", 0.0),
        )


@dataclass
class TradeEvent:
    """Record of a trade lifecycle event.

    Captures significant events during a trade's lifecycle such as
    position updates, risk checks, or manual interventions.

    Attributes:
        event_type: Type of event (e.g., "position_update", "risk_check")
        timestamp: When the event occurred (UTC)
        details: Additional event details
    """

    event_type: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate trade event data."""
        if not self.event_type:
            raise ValueError("event_type cannot be empty")
        # Ensure timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert trade event to dictionary for serialization.

        Returns:
            Dictionary representation of the trade event
        """
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeEvent:
        """Create TradeEvent from dictionary.

        Args:
            data: Dictionary with trade event data

        Returns:
            TradeEvent instance
        """
        return cls(
            event_type=data["event_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details=data.get("details", {}),
        )


@dataclass
class TradeJournalEntry:
    """Complete record of a single trade.

    Captures the full lifecycle of a trade from entry to exit,
    including all fills, events, and PnL calculations.

    Attributes:
        # Entry details
        entry_id: Unique identifier for this journal entry
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Trade side ("buy" or "sell")
        entry_price: Entry price
        entry_time: When the position was entered (UTC)
        position_size: Size of the position

        # Signal provenance
        signal_id: ID of the signal that triggered this trade
        signal_confidence: Confidence score of the signal (0.0-1.0)
        signal_strategy: Name of the strategy that generated the signal

        # Exit details
        exit_price: Exit price (None if position still open)
        exit_time: When the position was closed (UTC) (None if open)
        exit_reason: Reason for exit (None if position still open)
        exit_signal_id: ID of signal that triggered exit (if applicable)

        # PnL
        realized_pnl: Realized profit/loss (0.0 if position still open)
        fees: Total fees paid
        net_pnl: Net PnL after fees (realized_pnl - fees)

        # Lifecycle
        fills: List of fill records
        events: List of trade lifecycle events

        # Audit
        correlation_id: Correlation ID for request tracing
        session_id: Session ID for grouping trades
        created_at: When this journal entry was created (UTC)
    """

    # Entry details
    entry_id: str
    symbol: str
    side: str
    entry_price: float
    entry_time: datetime
    position_size: float

    # Signal provenance
    signal_id: str
    signal_confidence: float
    signal_strategy: str

    # Exit details (None if position still open)
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: ExitReason | None = None
    exit_signal_id: str | None = None

    # PnL
    realized_pnl: float = 0.0
    fees: float = 0.0

    # Lifecycle
    fills: list[FillRecord] = field(default_factory=list)
    events: list[TradeEvent] = field(default_factory=list)

    # Audit
    correlation_id: str = ""
    session_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Test trade flag (P0-KPI-GUARDRAILS-002)
    is_test: bool = False

    def __post_init__(self) -> None:
        """Validate trade journal entry data."""
        # Normalize side to lowercase
        self.side = self.side.lower()
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side}. Must be 'buy' or 'sell'")

        # Validate price and size
        if self.entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got: {self.entry_price}")
        if self.position_size <= 0:
            raise ValueError(
                f"Position size must be positive, got: {self.position_size}"
            )

        # Validate confidence range
        if not 0.0 <= self.signal_confidence <= 1.0:
            raise ValueError(
                f"Signal confidence must be between 0.0 and 1.0, got: {self.signal_confidence}"
            )

        # Ensure timestamps are timezone-aware
        if self.entry_time.tzinfo is None:
            self.entry_time = self.entry_time.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.exit_time is not None and self.exit_time.tzinfo is None:
            self.exit_time = self.exit_time.replace(tzinfo=UTC)

        # Validate exit price if provided
        if self.exit_price is not None and self.exit_price <= 0:
            raise ValueError(f"Exit price must be positive, got: {self.exit_price}")

    @property
    def is_open(self) -> bool:
        """Check if the trade is still open."""
        return self.exit_time is None

    @property
    def is_closed(self) -> bool:
        """Check if the trade is closed."""
        return self.exit_time is not None

    @property
    def net_pnl(self) -> float:
        """Calculate net PnL (realized_pnl - fees)."""
        return self.realized_pnl - self.fees

    @property
    def total_filled_quantity(self) -> float:
        """Calculate total filled quantity from all fills."""
        return sum(fill.quantity for fill in self.fills)

    @property
    def avg_fill_price(self) -> float | None:
        """Calculate average fill price from all fills.

        Returns:
            Average fill price or None if no fills
        """
        if not self.fills:
            return None
        total_value = sum(fill.price * fill.quantity for fill in self.fills)
        total_qty = sum(fill.quantity for fill in self.fills)
        return total_value / total_qty if total_qty > 0 else None

    def add_fill(self, fill: FillRecord) -> None:
        """Add a fill record to this entry.

        Args:
            fill: The fill record to add

        Raises:
            ValueError: If the trade is already closed
        """
        if self.is_closed:
            raise ValueError("Cannot add fill to closed trade")
        self.fills.append(fill)
        self.fees += fill.fee

    def add_event(self, event: TradeEvent) -> None:
        """Add a trade event to this entry.

        Args:
            event: The trade event to add
        """
        self.events.append(event)

    def close(
        self,
        exit_price: float,
        exit_reason: ExitReason,
        realized_pnl: float,
        exit_signal_id: str | None = None,
    ) -> None:
        """Close this trade entry.

        Args:
            exit_price: The exit price
            exit_reason: Reason for closing
            realized_pnl: Realized profit/loss
            exit_signal_id: Optional ID of signal that triggered exit

        Raises:
            ValueError: If the trade is already closed
        """
        if self.is_closed:
            raise ValueError("Trade is already closed")

        if exit_price <= 0:
            raise ValueError(f"Exit price must be positive, got: {exit_price}")

        self.exit_price = exit_price
        self.exit_time = datetime.now(UTC)
        self.exit_reason = exit_reason
        self.realized_pnl = realized_pnl
        self.exit_signal_id = exit_signal_id

    def to_dict(self) -> dict[str, Any]:
        """Convert trade journal entry to dictionary for serialization.

        Returns:
            Dictionary representation of the trade journal entry
        """
        return {
            # Entry details
            "entry_id": self.entry_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat(),
            "position_size": self.position_size,
            # Signal provenance
            "signal_id": self.signal_id,
            "signal_confidence": self.signal_confidence,
            "signal_strategy": self.signal_strategy,
            # Exit details
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "exit_signal_id": self.exit_signal_id,
            # PnL
            "realized_pnl": self.realized_pnl,
            "fees": self.fees,
            "net_pnl": self.net_pnl,
            # Lifecycle
            "fills": [fill.to_dict() for fill in self.fills],
            "events": [event.to_dict() for event in self.events],
            # Audit
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            # Test trade flag
            "is_test": self.is_test,
            # Computed
            "is_open": self.is_open,
            "is_closed": self.is_closed,
            "total_filled_quantity": self.total_filled_quantity,
            "avg_fill_price": self.avg_fill_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeJournalEntry:
        """Create TradeJournalEntry from dictionary.

        Args:
            data: Dictionary with trade journal entry data

        Returns:
            TradeJournalEntry instance
        """
        entry = cls(
            # Entry details
            entry_id=data["entry_id"],
            symbol=data["symbol"],
            side=data["side"],
            entry_price=data["entry_price"],
            entry_time=datetime.fromisoformat(data["entry_time"]),
            position_size=data["position_size"],
            # Signal provenance
            signal_id=data["signal_id"],
            signal_confidence=data["signal_confidence"],
            signal_strategy=data["signal_strategy"],
            # Exit details
            exit_price=data.get("exit_price"),
            exit_time=(
                datetime.fromisoformat(data["exit_time"])
                if data.get("exit_time")
                else None
            ),
            exit_reason=(
                ExitReason(data["exit_reason"]) if data.get("exit_reason") else None
            ),
            exit_signal_id=data.get("exit_signal_id"),
            # PnL
            realized_pnl=data.get("realized_pnl", 0.0),
            fees=data.get("fees", 0.0),
            # Audit
            correlation_id=data.get("correlation_id", ""),
            session_id=data.get("session_id", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            # Test trade flag
            is_test=data.get("is_test", False),
        )

        # Restore fills
        entry.fills = [FillRecord.from_dict(f) for f in data.get("fills", [])]
        entry.events = [TradeEvent.from_dict(e) for e in data.get("events", [])]

        return entry


class TradeJournal:
    """Journal for tracking all trades with full audit trail.

    Provides CRUD operations for trade journal entries with support
    for filtering and querying trade history.

    Attributes:
        _entries: Dictionary of journal entries by entry_id
        _session_id: Current session ID for grouping trades
    """

    def __init__(self, session_id: str = "") -> None:
        """Initialize the trade journal.

        Args:
            session_id: Session ID for grouping trades
        """
        self._entries: dict[str, TradeJournalEntry] = {}
        self._session_id = session_id or str(uuid.uuid4())

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    def create_entry(
        self,
        position: Any,
        signal: Any,
        correlation_id: str = "",
    ) -> TradeJournalEntry:
        """Create a new trade journal entry.

        Args:
            position: The position object (must have symbol, side, entry_price,
                     quantity, position_id attributes)
            signal: The signal object (must have signal_id, confidence,
                   strategy_name or strategy attributes)
            correlation_id: Correlation ID for request tracing

        Returns:
            New TradeJournalEntry

        Raises:
            ValueError: If position or signal is missing required attributes
        """
        # Extract position data
        symbol = getattr(position, "symbol", None)
        side = getattr(position, "side", None)
        entry_price = getattr(position, "entry_price", None)
        quantity = getattr(position, "quantity", None)
        position_id = getattr(position, "position_id", None)

        if not all([symbol, side, entry_price, quantity]):
            raise ValueError(
                "Position must have symbol, side, entry_price, and quantity attributes"
            )

        # Translate position side to order side
        side = side.lower()
        if side in ("long", "buy"):
            side = "buy"
        elif side in ("short", "sell"):
            side = "sell"
        else:
            raise ValueError(
                f"Invalid position side: {side}. Must be 'long', 'short', 'buy', or 'sell'"
            )

        # Extract signal data
        signal_id = getattr(signal, "signal_id", None)
        confidence = getattr(signal, "confidence", None)
        strategy = getattr(signal, "strategy_name", getattr(signal, "strategy", None))

        if not all([signal_id, confidence is not None]):
            raise ValueError("Signal must have signal_id and confidence attributes")

        entry = TradeJournalEntry(
            entry_id=position_id or str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_time=datetime.now(UTC),
            position_size=quantity,
            signal_id=signal_id,
            signal_confidence=confidence,
            signal_strategy=strategy or "unknown",
            correlation_id=correlation_id,
            session_id=self._session_id,
        )

        self._entries[entry.entry_id] = entry
        return entry

    def record_fill(self, entry_id: str, fill_event: FillRecord) -> TradeJournalEntry:
        """Record a fill for a trade entry.

        Args:
            entry_id: ID of the trade entry
            fill_event: The fill record to add

        Returns:
            Updated TradeJournalEntry

        Raises:
            KeyError: If entry_id not found
            ValueError: If the trade is already closed
        """
        entry = self._entries[entry_id]
        entry.add_fill(fill_event)
        return entry

    def close_entry(
        self,
        entry_id: str,
        exit_price: float,
        exit_reason: ExitReason,
        pnl: float,
        exit_signal_id: str | None = None,
    ) -> TradeJournalEntry:
        """Close a trade entry.

        Args:
            entry_id: ID of the trade entry to close
            exit_price: The exit price
            exit_reason: Reason for closing
            pnl: Realized profit/loss
            exit_signal_id: Optional ID of signal that triggered exit

        Returns:
            Updated TradeJournalEntry

        Raises:
            KeyError: If entry_id not found
            ValueError: If the trade is already closed
        """
        entry = self._entries[entry_id]
        entry.close(exit_price, exit_reason, pnl, exit_signal_id)
        return entry

    def get_entry(self, entry_id: str) -> TradeJournalEntry | None:
        """Get a specific trade entry by ID.

        Args:
            entry_id: ID of the trade entry

        Returns:
            TradeJournalEntry or None if not found
        """
        return self._entries.get(entry_id)

    def list_entries(
        self,
        symbol: str | None = None,
        side: str | None = None,
        is_open: bool | None = None,
        exit_reason: ExitReason | None = None,
        signal_strategy: str | None = None,
        session_id: str | None = None,
        include_test_trades: bool = False,
    ) -> list[TradeJournalEntry]:
        """List trade entries with optional filters.

        Args:
            symbol: Filter by trading symbol
            side: Filter by side ("buy" or "sell")
            is_open: Filter by open/closed status
            exit_reason: Filter by exit reason
            signal_strategy: Filter by signal strategy name
            session_id: Filter by session ID
            include_test_trades: If False, exclude test trades (default: False)

        Returns:
            List of matching TradeJournalEntry objects
        """
        entries = list(self._entries.values())

        if symbol:
            entries = [e for e in entries if e.symbol.upper() == symbol.upper()]

        if side:
            entries = [e for e in entries if e.side == side.lower()]

        if is_open is not None:
            entries = [e for e in entries if e.is_open == is_open]

        if exit_reason is not None:
            entries = [e for e in entries if e.exit_reason == exit_reason]

        if signal_strategy:
            entries = [e for e in entries if e.signal_strategy == signal_strategy]

        if session_id:
            entries = [e for e in entries if e.session_id == session_id]

        if not include_test_trades:
            entries = [e for e in entries if not e.is_test]

        return entries

    def get_all_entries(self) -> list[TradeJournalEntry]:
        """Get all trade entries.

        Returns:
            List of all TradeJournalEntry objects
        """
        return list(self._entries.values())

    def get_open_entries(self) -> list[TradeJournalEntry]:
        """Get all open trade entries.

        Returns:
            List of open TradeJournalEntry objects
        """
        return [e for e in self._entries.values() if e.is_open]

    def get_closed_entries(self) -> list[TradeJournalEntry]:
        """Get all closed trade entries.

        Returns:
            List of closed TradeJournalEntry objects
        """
        return [e for e in self._entries.values() if e.is_closed]

    def get_test_trades(self) -> list[TradeJournalEntry]:
        """Get all test trades.

        Returns:
            List of test TradeJournalEntry objects (is_test=True)
        """
        return [e for e in self._entries.values() if e.is_test]

    def get_production_trades(self) -> list[TradeJournalEntry]:
        """Get all production (non-test) trades.

        Returns:
            List of production TradeJournalEntry objects (is_test=False)
        """
        return [e for e in self._entries.values() if not e.is_test]

    def detect_test_trade(self, entry: TradeJournalEntry) -> bool:
        """Detect if a trade entry is a test trade based on various indicators.

        Test trades are identified by:
        - signal_id starting with "test-" or "TEST-"
        - entry_id containing "test" or "TEST"
        - session_id containing "test" or "TEST"
        - correlation_id containing "test" or "TEST"
        - signal_strategy containing "test" or "e2e"

        Args:
            entry: The trade journal entry to check

        Returns:
            True if this appears to be a test trade
        """
        # Check signal_id
        if entry.signal_id and entry.signal_id.lower().startswith("test-"):
            return True

        # Check entry_id
        if entry.entry_id and "test" in entry.entry_id.lower():
            return True

        # Check session_id
        if entry.session_id and "test" in entry.session_id.lower():
            return True

        # Check correlation_id
        if entry.correlation_id and "test" in entry.correlation_id.lower():
            return True

        # Check signal_strategy
        return bool(entry.signal_strategy and ("test" in entry.signal_strategy.lower() or "e2e" in entry.signal_strategy.lower()))

    def get_stats(self) -> dict[str, Any]:
        """Get journal statistics.

        Returns:
            Dictionary with statistics
        """
        entries = list(self._entries.values())
        closed_entries = [e for e in entries if e.is_closed]

        total_pnl = sum(e.net_pnl for e in closed_entries)
        winning_trades = [e for e in closed_entries if e.net_pnl > 0]
        losing_trades = [e for e in closed_entries if e.net_pnl < 0]

        return {
            "total_entries": len(entries),
            "open_entries": len([e for e in entries if e.is_open]),
            "closed_entries": len(closed_entries),
            "total_pnl": total_pnl,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (
                len(winning_trades) / len(closed_entries) if closed_entries else 0.0
            ),
            "avg_pnl": (total_pnl / len(closed_entries) if closed_entries else 0.0),
            "session_id": self._session_id,
        }

    def clear(self) -> None:
        """Clear all entries (for testing/reset)."""
        self._entries.clear()

    def to_dict(self) -> dict[str, Any]:
        """Convert journal to dictionary for serialization.

        Returns:
            Dictionary representation of the journal
        """
        return {
            "session_id": self._session_id,
            "entries": [entry.to_dict() for entry in self._entries.values()],
            "stats": self.get_stats(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeJournal:
        """Create TradeJournal from dictionary.

        Args:
            data: Dictionary with journal data

        Returns:
            TradeJournal instance
        """
        journal = cls(session_id=data.get("session_id", ""))
        for entry_data in data.get("entries", []):
            entry = TradeJournalEntry.from_dict(entry_data)
            journal._entries[entry.entry_id] = entry
        return journal
