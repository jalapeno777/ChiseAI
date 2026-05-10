"""Paper trading position tracker.

Tracks open and closed paper trading positions with PnL calculation.
Provides position lifecycle management for paper trading.

For PAPER-LOOP-001: Paper Trading Position Tracker
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from .position_persistence import PositionPersistence

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """A paper trading position.

    Attributes:
        position_id: Unique position identifier
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        side: Position side ("long" or "short")
        entry_price: Entry price
        quantity: Position size in base currency
        unrealized_pnl: Current unrealized PnL
        realized_pnl: Realized PnL on close
        opened_at: Position open timestamp
        closed_at: Position close timestamp (if closed)
        metadata: Additional position metadata
        entry_fees: Entry fees paid
        exit_fees: Exit fees paid
    """

    position_id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_fees: float = 0.0
    exit_fees: float = 0.0

    @property
    def total_fees(self) -> float:
        """Calculate total fees paid (entry + exit)."""
        return self.entry_fees + self.exit_fees

    @property
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.closed_at is None

    @property
    def value(self) -> float:
        """Calculate position value."""
        return self.quantity * self.entry_price

    def calculate_pnl(self, current_price: float, deduct_fees: bool = False) -> float:
        """Calculate unrealized PnL at current price.

        Args:
            current_price: Current market price
            deduct_fees: If True, subtract total fees from result

        Returns:
            Unrealized PnL (gross or net depending on deduct_fees)
        """
        if self.side == "long":
            pnl = (current_price - self.entry_price) * self.quantity
        else:  # short
            pnl = (self.entry_price - current_price) * self.quantity

        if deduct_fees:
            pnl -= self.total_fees

        return pnl


class PaperPositionTracker:
    """Tracks paper trading positions.

    Manages position lifecycle:
    - Opening positions from filled orders
    - Tracking unrealized PnL
    - Closing positions with realized PnL
    - Maintaining position history

    Attributes:
        _open_positions: Dictionary of open positions by ID
        _closed_positions: List of closed positions
        _lock: Async lock for thread safety
        _persistence: Optional Redis persistence manager
    """

    def __init__(
        self,
        enable_persistence: bool = False,
        redis_client: Redis | None = None,
    ) -> None:
        """Initialize the position tracker.

        Args:
            enable_persistence: If True, enables Redis persistence for positions
            redis_client: Optional Redis client to pass to persistence layer.
                When provided with enable_persistence=True, avoids the
                persistence layer creating its own client with potentially
                wrong hostname defaults.
        """
        self._open_positions: dict[str, PaperPosition] = {}
        self._closed_positions: list[PaperPosition] = []
        self._lock = asyncio.Lock()
        self._persistence: PositionPersistence | None = None

        if enable_persistence:
            self._persistence = PositionPersistence(redis_client=redis_client)

        logger.info("PaperPositionTracker initialized")

    async def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        metadata: dict[str, Any] | None = None,
        entry_fees: float = 0.0,
    ) -> PaperPosition:
        """Open a new position.

        Args:
            symbol: Trading pair symbol
            side: Position side ("long" or "short")
            entry_price: Entry price
            quantity: Position size
            metadata: Optional metadata
            entry_fees: Entry fees paid (default 0.0)

        Returns:
            New PaperPosition
        """
        async with self._lock:
            position = PaperPosition(
                position_id=str(uuid.uuid4()),
                symbol=symbol.upper(),
                side=side.lower(),
                entry_price=entry_price,
                quantity=quantity,
                metadata=metadata or {},
                entry_fees=entry_fees,
            )

            self._open_positions[position.position_id] = position

            # Persist to Redis if persistence is enabled
            if self._persistence is not None:
                await self._persistence.persist_position(position)

            logger.info(
                f"Opened position: {position.position_id} "
                f"{symbol} {side} @ {entry_price:.2f} "
                f"qty={quantity:.6f}"
            )

            return position

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_fees: float = 0.0,
    ) -> tuple[PaperPosition, float]:
        """Close a position.

        Args:
            position_id: Position to close
            exit_price: Exit price
            exit_fees: Exit fees paid (default 0.0)

        Returns:
            Tuple of (closed position, realized PnL)

        Raises:
            ValueError: If position not found or already closed
        """
        async with self._lock:
            position = self._open_positions.get(position_id)
            if position is None:
                raise ValueError(f"Position {position_id} not found")

            # Set exit fees
            position.exit_fees = exit_fees

            # Calculate realized PnL with fees deducted
            realized_pnl = position.calculate_pnl(exit_price, deduct_fees=True)
            position.realized_pnl = realized_pnl
            position.unrealized_pnl = 0.0
            position.closed_at = datetime.now(UTC)

            # Move to closed positions
            del self._open_positions[position_id]
            self._closed_positions.append(position)

            # Persist to Redis if persistence is enabled (updates closed state)
            if self._persistence is not None:
                await self._persistence.persist_position(position)

            logger.info(
                f"Closed position: {position_id} "
                f"PnL={realized_pnl:.4f} (net after fees) "
                f"exit={exit_price:.2f} "
                f"fees={position.total_fees:.4f}"
            )

            return position, realized_pnl

    async def get_open_positions(self) -> list[PaperPosition]:
        """Get all open positions.

        Returns:
            List of open positions
        """
        async with self._lock:
            return list(self._open_positions.values())

    async def get_closed_positions(self) -> list[PaperPosition]:
        """Get all closed positions.

        Returns:
            List of closed positions
        """
        async with self._lock:
            return self._closed_positions.copy()

    async def get_position(self, position_id: str) -> PaperPosition | None:
        """Get a specific position by ID.

        Args:
            position_id: Position ID

        Returns:
            Position or None if not found
        """
        async with self._lock:
            return self._open_positions.get(position_id)

    async def update_unrealized_pnl(
        self,
        position_id: str,
        current_price: float,
    ) -> float:
        """Update unrealized PnL for a position.

        Args:
            position_id: Position to update
            current_price: Current market price

        Returns:
            Updated unrealized PnL
        """
        async with self._lock:
            position = self._open_positions.get(position_id)
            if position is None:
                raise ValueError(f"Position {position_id} not found")

            position.unrealized_pnl = position.calculate_pnl(current_price)
            return position.unrealized_pnl

    async def get_portfolio_value(self) -> float:
        """Calculate total portfolio value from open positions.

        Returns:
            Total value of all open positions
        """
        async with self._lock:
            return sum(pos.value for pos in self._open_positions.values())

    async def get_total_pnl(self) -> tuple[float, float]:
        """Get total realized and unrealized PnL.

        Returns:
            Tuple of (realized_pnl, unrealized_pnl)
        """
        async with self._lock:
            realized = sum(pos.realized_pnl for pos in self._closed_positions)
            unrealized = sum(
                pos.unrealized_pnl for pos in self._open_positions.values()
            )
            return realized, unrealized

    async def clear_all(self) -> None:
        """Clear all positions (for testing/reset)."""
        async with self._lock:
            self._open_positions.clear()
            self._closed_positions.clear()
            # Also clear Redis persistence if enabled
            if self._persistence is not None:
                positions = await self._persistence.load_all_positions()
                for pos in positions:
                    await self._persistence.remove_position(pos.position_id)
            logger.info("All positions cleared")

    async def enable_persistence(self, redis_client: Redis | None = None) -> None:
        """Enable Redis persistence for positions.

        Args:
            redis_client: Optional Redis client to use
        """
        async with self._lock:
            self._persistence = PositionPersistence(redis_client)
            logger.info("Position persistence enabled")

    async def recover_from_persistence(self) -> int:
        """Recover positions from Redis persistence.

        Loads all persisted positions from Redis and restores them to the tracker.
        Open positions are restored to _open_positions, closed positions to
        _closed_positions.

        Returns:
            Number of positions recovered
        """
        if self._persistence is None:
            raise RuntimeError(
                "Persistence not enabled. Call enable_persistence first."
            )

        async with self._lock:
            positions = await self._persistence.load_all_positions()

            for position in positions:
                if position.is_open:
                    self._open_positions[position.position_id] = position
                else:
                    self._closed_positions.append(position)

            logger.info(f"Recovered {len(positions)} positions from persistence")
            return len(positions)

    def get_stats(self) -> dict[str, Any]:
        """Get tracker statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "open_positions": len(self._open_positions),
            "closed_positions": len(self._closed_positions),
        }
