"""Portfolio state management data models.

Defines core dataclasses for Position, PortfolioState, and PortfolioSnapshot
used in real-time portfolio tracking and state management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PositionDirection(Enum):
    """Position direction enumeration."""

    LONG = "LONG"
    SHORT = "SHORT"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


class PositionStatus(Enum):
    """Position status enumeration."""

    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"  # Order submitted but not confirmed

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class Position:
    """A trading position with real-time PnL tracking.

    Attributes:
        position_id: Unique position identifier (UUID)
        token: Trading pair token (e.g., "BTC", "ETH")
        direction: Position direction (LONG/SHORT)
        entry_price: Entry price when position opened
        quantity: Position size in base token units
        current_price: Current market price for PnL calculation
        unrealized_pnl: Unrealized profit/loss in quote currency
        realized_pnl: Realized profit/loss (for partially closed positions)
        timestamp: Position open timestamp (Unix ms)
        last_update: Last update timestamp (Unix ms)
        status: Position status (open/closed/pending)
        leverage: Leverage used (1.0 = spot, 2.0+ = margin)
        margin_used: Margin allocated to this position
        metadata: Additional position metadata
    """

    position_id: str
    token: str
    direction: PositionDirection
    entry_price: float
    quantity: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: int = 0
    last_update: int = 0
    status: PositionStatus = PositionStatus.OPEN
    leverage: float = 1.0
    margin_used: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize values, calculate PnL."""
        # Ensure timestamps are set
        if self.timestamp == 0:
            self.timestamp = int(datetime.now().timestamp() * 1000)
        if self.last_update == 0:
            self.last_update = self.timestamp

        # Normalize leverage
        self.leverage = max(1.0, self.leverage)

        # Calculate unrealized PnL if current_price is set
        if self.current_price > 0:
            self._calculate_unrealized_pnl()

        # Calculate margin used if not set
        if self.margin_used == 0 and self.quantity > 0:
            notional_value = self.entry_price * self.quantity
            self.margin_used = notional_value / self.leverage

    def _calculate_unrealized_pnl(self) -> None:
        """Calculate unrealized PnL based on current price."""
        if self.direction == PositionDirection.LONG:
            price_diff = self.current_price - self.entry_price
        else:  # SHORT
            price_diff = self.entry_price - self.current_price

        self.unrealized_pnl = price_diff * self.quantity * self.leverage

    def update_price(self, new_price: float, timestamp: int | None = None) -> None:
        """Update current price and recalculate PnL.

        Args:
            new_price: New market price
            timestamp: Optional timestamp for the price update
        """
        self.current_price = new_price
        self._calculate_unrealized_pnl()
        self.last_update = timestamp or int(datetime.now().timestamp() * 1000)

    def close_position(self, exit_price: float, timestamp: int | None = None) -> float:
        """Close the position and calculate realized PnL.

        Args:
            exit_price: Price at which position is closed
            timestamp: Optional close timestamp

        Returns:
            Realized PnL amount
        """
        self.current_price = exit_price
        self._calculate_unrealized_pnl()
        self.realized_pnl = self.unrealized_pnl
        self.unrealized_pnl = 0.0
        self.status = PositionStatus.CLOSED
        self.last_update = timestamp or int(datetime.now().timestamp() * 1000)
        return self.realized_pnl

    @property
    def notional_value(self) -> float:
        """Calculate notional value of position."""
        return self.current_price * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized PnL as percentage."""
        if self.entry_price == 0:
            return 0.0

        if self.direction == PositionDirection.LONG:
            price_diff_pct = (self.current_price - self.entry_price) / self.entry_price
        else:
            price_diff_pct = (self.entry_price - self.current_price) / self.entry_price

        return price_diff_pct * self.leverage * 100

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.direction == PositionDirection.LONG

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.direction == PositionDirection.SHORT

    @property
    def is_open(self) -> bool:
        """Check if position is open."""
        return self.status == PositionStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.status == PositionStatus.CLOSED

    def to_dict(self) -> dict[str, Any]:
        """Convert position to dictionary for serialization."""
        return {
            "position_id": self.position_id,
            "token": self.token,
            "direction": self.direction.value,
            "entry_price": round(self.entry_price, 8),
            "quantity": round(self.quantity, 8),
            "current_price": round(self.current_price, 8),
            "unrealized_pnl": round(self.unrealized_pnl, 8),
            "realized_pnl": round(self.realized_pnl, 8),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
            "notional_value": round(self.notional_value, 8),
            "timestamp": self.timestamp,
            "last_update": self.last_update,
            "status": self.status.value,
            "leverage": self.leverage,
            "margin_used": round(self.margin_used, 8),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        """Create Position from dictionary.

        Args:
            data: Dictionary with position data

        Returns:
            Position instance
        """
        direction = PositionDirection(data.get("direction", "LONG"))
        status = PositionStatus(data.get("status", "open"))

        return cls(
            position_id=data["position_id"],
            token=data["token"],
            direction=direction,
            entry_price=data["entry_price"],
            quantity=data["quantity"],
            current_price=data.get("current_price", 0.0),
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            realized_pnl=data.get("realized_pnl", 0.0),
            timestamp=data.get("timestamp", 0),
            last_update=data.get("last_update", 0),
            status=status,
            leverage=data.get("leverage", 1.0),
            margin_used=data.get("margin_used", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Balance:
    """Account balance for a specific token.

    Attributes:
        token: Token symbol (e.g., "USDT", "BTC")
        free: Available/free balance
        locked: Locked/used balance (in orders, margin, etc.)
        total: Total balance (free + locked)
        last_update: Last update timestamp (Unix ms)
    """

    token: str
    free: float = 0.0
    locked: float = 0.0
    last_update: int = 0

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        if self.last_update == 0:
            self.last_update = int(datetime.now().timestamp() * 1000)

    @property
    def total(self) -> float:
        """Calculate total balance."""
        return self.free + self.locked

    def to_dict(self) -> dict[str, Any]:
        """Convert balance to dictionary."""
        return {
            "token": self.token,
            "free": round(self.free, 8),
            "locked": round(self.locked, 8),
            "total": round(self.total, 8),
            "last_update": self.last_update,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Balance:
        """Create Balance from dictionary."""
        return cls(
            token=data["token"],
            free=data.get("free", 0.0),
            locked=data.get("locked", 0.0),
            last_update=data.get("last_update", 0),
        )


@dataclass
class PortfolioState:
    """Complete portfolio state with positions and balances.

    Attributes:
        portfolio_id: Unique portfolio identifier
        positions: Dictionary of position_id -> Position
        balances: Dictionary of token -> Balance
        margin_used: Total margin used across all positions
        available_equity: Available equity for new positions
        total_equity: Total portfolio equity
        unrealized_pnl: Total unrealized PnL across all positions
        realized_pnl: Total realized PnL (session cumulative)
        timestamp: State timestamp (Unix ms)
        last_update: Last update timestamp (Unix ms)
        metadata: Additional portfolio metadata
    """

    portfolio_id: str
    positions: dict[str, Position] = field(default_factory=dict)
    balances: dict[str, Balance] = field(default_factory=dict)
    margin_used: float = 0.0
    available_equity: float = 0.0
    total_equity: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: int = 0
    last_update: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize timestamps and recalculate totals."""
        if self.timestamp == 0:
            self.timestamp = int(datetime.now().timestamp() * 1000)
        if self.last_update == 0:
            self.last_update = self.timestamp

        self._recalculate_totals()

    def _recalculate_totals(self) -> None:
        """Recalculate portfolio totals from positions and balances.

        CRITICAL-4 FIX: Include both OPEN and PENDING positions in unrealized PnL.
        PENDING positions are orders that have been submitted but not yet confirmed
        by the exchange. They represent real exposure that should be tracked for
        accurate portfolio valuation and risk management.
        """
        # Calculate margin used from open and pending positions
        self.margin_used = sum(
            pos.margin_used
            for pos in self.positions.values()
            if pos.status in (PositionStatus.OPEN, PositionStatus.PENDING)
        )

        # Calculate unrealized PnL from open and pending positions
        # PENDING positions are included because they represent real exposure
        # that will become open once confirmed by the exchange
        self.unrealized_pnl = sum(
            pos.unrealized_pnl
            for pos in self.positions.values()
            if pos.status in (PositionStatus.OPEN, PositionStatus.PENDING)
        )

        # Note: realized_pnl is managed by add_position/remove_position
        # to properly track PnL from positions that have been removed.
        # _recalculate_totals only handles open position calculations.

        # Calculate total equity from balances
        total_balance = sum(bal.total for bal in self.balances.values())
        self.total_equity = total_balance + self.unrealized_pnl
        self.available_equity = total_balance - self.margin_used

    def add_position(self, position: Position) -> None:
        """Add a new position to the portfolio.

        Args:
            position: Position to add
        """
        self.positions[position.position_id] = position
        self._recalculate_totals()
        self.last_update = int(datetime.now().timestamp() * 1000)

    def update_position(self, position_id: str, **kwargs) -> Position | None:
        """Update an existing position.

        Args:
            position_id: ID of position to update
            **kwargs: Fields to update

        Returns:
            Updated Position or None if not found
        """
        if position_id not in self.positions:
            return None

        position = self.positions[position_id]

        # Update allowed fields
        if "current_price" in kwargs:
            position.update_price(kwargs["current_price"])
        if "status" in kwargs:
            position.status = PositionStatus(kwargs["status"])
        if "realized_pnl" in kwargs:
            position.realized_pnl = kwargs["realized_pnl"]

        self._recalculate_totals()
        self.last_update = int(datetime.now().timestamp() * 1000)
        return position

    def remove_position(self, position_id: str) -> Position | None:
        """Remove a position from the portfolio.

        Args:
            position_id: ID of position to remove

        Returns:
            Removed Position or None if not found
        """
        if position_id not in self.positions:
            return None

        position = self.positions.pop(position_id)
        if position.realized_pnl != 0:
            self.realized_pnl += position.realized_pnl

        self._recalculate_totals()
        self.last_update = int(datetime.now().timestamp() * 1000)
        return position

    def update_balance(
        self, token: str, free: float | None = None, locked: float | None = None
    ) -> Balance:
        """Update or create a balance entry.

        Args:
            token: Token symbol
            free: Free balance amount (optional)
            locked: Locked balance amount (optional)

        Returns:
            Updated Balance
        """
        if token not in self.balances:
            self.balances[token] = Balance(token=token)

        balance = self.balances[token]
        if free is not None:
            balance.free = free
        if locked is not None:
            balance.locked = locked
        balance.last_update = int(datetime.now().timestamp() * 1000)

        self._recalculate_totals()
        self.last_update = int(datetime.now().timestamp() * 1000)
        return balance

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [pos for pos in self.positions.values() if pos.is_open]

    def get_positions_by_token(self, token: str) -> list[Position]:
        """Get positions for a specific token."""
        return [pos for pos in self.positions.values() if pos.token == token]

    def get_position_summary(self) -> dict[str, Any]:
        """Get summary of all positions."""
        open_positions = self.get_open_positions()
        return {
            "total_positions": len(self.positions),
            "open_positions": len(open_positions),
            "long_positions": len([p for p in open_positions if p.is_long]),
            "short_positions": len([p for p in open_positions if p.is_short]),
            "total_unrealized_pnl": round(self.unrealized_pnl, 8),
            "total_realized_pnl": round(self.realized_pnl, 8),
            "total_margin_used": round(self.margin_used, 8),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert portfolio state to dictionary."""
        return {
            "portfolio_id": self.portfolio_id,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "balances": {k: v.to_dict() for k, v in self.balances.items()},
            "margin_used": round(self.margin_used, 8),
            "available_equity": round(self.available_equity, 8),
            "total_equity": round(self.total_equity, 8),
            "unrealized_pnl": round(self.unrealized_pnl, 8),
            "realized_pnl": round(self.realized_pnl, 8),
            "timestamp": self.timestamp,
            "last_update": self.last_update,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioState:
        """Create PortfolioState from dictionary."""
        positions = {
            k: Position.from_dict(v) for k, v in data.get("positions", {}).items()
        }
        balances = {
            k: Balance.from_dict(v) for k, v in data.get("balances", {}).items()
        }

        return cls(
            portfolio_id=data["portfolio_id"],
            positions=positions,
            balances=balances,
            margin_used=data.get("margin_used", 0.0),
            available_equity=data.get("available_equity", 0.0),
            total_equity=data.get("total_equity", 0.0),
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            realized_pnl=data.get("realized_pnl", 0.0),
            timestamp=data.get("timestamp", 0),
            last_update=data.get("last_update", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PortfolioSnapshot:
    """Historical snapshot of portfolio state for trend analysis.

    Attributes:
        snapshot_id: Unique snapshot identifier
        portfolio_id: Reference to portfolio
        timestamp: Snapshot timestamp (Unix ms)
        total_equity: Total equity at snapshot time
        available_equity: Available equity at snapshot time
        margin_used: Margin used at snapshot time
        unrealized_pnl: Unrealized PnL at snapshot time
        realized_pnl: Realized PnL at snapshot time
        position_count: Number of open positions
        balance_summary: Summary of balances by token
        metadata: Additional snapshot metadata
    """

    snapshot_id: str
    portfolio_id: str
    timestamp: int
    total_equity: float
    available_equity: float
    margin_used: float
    unrealized_pnl: float
    realized_pnl: float
    position_count: int
    balance_summary: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_portfolio_state(
        cls,
        snapshot_id: str,
        state: PortfolioState,
        timestamp: int | None = None,
    ) -> PortfolioSnapshot:
        """Create a snapshot from a PortfolioState.

        Args:
            snapshot_id: Unique snapshot ID
            state: Portfolio state to snapshot
            timestamp: Optional timestamp (defaults to now)

        Returns:
            PortfolioSnapshot instance
        """
        return cls(
            snapshot_id=snapshot_id,
            portfolio_id=state.portfolio_id,
            timestamp=timestamp or int(datetime.now().timestamp() * 1000),
            total_equity=state.total_equity,
            available_equity=state.available_equity,
            margin_used=state.margin_used,
            unrealized_pnl=state.unrealized_pnl,
            realized_pnl=state.realized_pnl,
            position_count=len(state.get_open_positions()),
            balance_summary={k: v.total for k, v in state.balances.items()},
            metadata={"source": "portfolio_state"},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp,
            "total_equity": round(self.total_equity, 8),
            "available_equity": round(self.available_equity, 8),
            "margin_used": round(self.margin_used, 8),
            "unrealized_pnl": round(self.unrealized_pnl, 8),
            "realized_pnl": round(self.realized_pnl, 8),
            "position_count": self.position_count,
            "balance_summary": self.balance_summary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioSnapshot:
        """Create PortfolioSnapshot from dictionary."""
        return cls(
            snapshot_id=data["snapshot_id"],
            portfolio_id=data["portfolio_id"],
            timestamp=data["timestamp"],
            total_equity=data["total_equity"],
            available_equity=data["available_equity"],
            margin_used=data["margin_used"],
            unrealized_pnl=data["unrealized_pnl"],
            realized_pnl=data["realized_pnl"],
            position_count=data["position_count"],
            balance_summary=data.get("balance_summary", {}),
            metadata=data.get("metadata", {}),
        )
