"""Portfolio tracker for real-time position and balance updates.

Provides the PortfolioTracker class for receiving real-time updates
from exchanges, managing portfolio state, and persisting snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import weakref
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from portfolio.state_management.models import PortfolioState, Position

from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    Position,
    PositionDirection,
    PositionStatus,
)

logger = logging.getLogger(__name__)


class PortfolioUpdate:
    """Base class for portfolio updates.

    Attributes:
        update_type: Type of update (position, balance, price)
        timestamp: Update timestamp (Unix ms)
        source: Source of update (exchange name)
        data: Update data payload
    """

    def __init__(
        self,
        update_type: str,
        timestamp: int,
        source: str,
        data: dict[str, Any],
    ):
        self.update_type = update_type
        self.timestamp = timestamp
        self.source = source
        self.data = data


class PositionUpdate(PortfolioUpdate):
    """Position update from exchange.

    Attributes:
        position_id: Position identifier
        token: Trading pair token
        direction: Position direction
        entry_price: Entry price
        quantity: Position size
        status: Position status
    """

    def __init__(
        self,
        timestamp: int,
        source: str,
        position_id: str,
        token: str,
        direction: str,
        entry_price: float,
        quantity: float,
        status: str = "open",
        current_price: float | None = None,
        leverage: float = 1.0,
        **kwargs,
    ):
        data = {
            "position_id": position_id,
            "token": token,
            "direction": direction,
            "entry_price": entry_price,
            "quantity": quantity,
            "status": status,
            "current_price": current_price,
            "leverage": leverage,
            **kwargs,
        }
        super().__init__("position", timestamp, source, data)
        self.position_id = position_id
        self.token = token
        self.direction = direction
        self.entry_price = entry_price
        self.quantity = quantity
        self.status = status
        self.current_price = current_price
        self.leverage = leverage


class BalanceUpdate(PortfolioUpdate):
    """Balance update from exchange.

    Attributes:
        token: Token symbol
        free: Free/available balance
        locked: Locked/used balance
    """

    def __init__(
        self,
        timestamp: int,
        source: str,
        token: str,
        free: float,
        locked: float,
        **kwargs,
    ):
        data = {
            "token": token,
            "free": free,
            "locked": locked,
            **kwargs,
        }
        super().__init__("balance", timestamp, source, data)
        self.token = token
        self.free = free
        self.locked = locked


class PriceUpdate(PortfolioUpdate):
    """Price update for PnL calculation.

    Attributes:
        token: Token symbol
        price: Current market price
    """

    def __init__(
        self,
        timestamp: int,
        source: str,
        token: str,
        price: float,
        **kwargs,
    ):
        data = {
            "token": token,
            "price": price,
            **kwargs,
        }
        super().__init__("price", timestamp, source, data)
        self.token = token
        self.price = price


class PortfolioStorageInterface(ABC):
    """Abstract interface for portfolio storage backends."""

    @abstractmethod
    async def store_state(self, state: PortfolioState) -> bool:
        """Store portfolio state.

        Args:
            state: Portfolio state to store

        Returns:
            True if storage was successful
        """
        pass

    @abstractmethod
    async def store_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        """Store portfolio snapshot.

        Args:
            snapshot: Portfolio snapshot to store

        Returns:
            True if storage was successful
        """
        pass

    @abstractmethod
    async def get_latest_state(self, portfolio_id: str) -> PortfolioState | None:
        """Get latest portfolio state.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            Latest PortfolioState or None if not found
        """
        pass

    @abstractmethod
    async def get_snapshots(
        self,
        portfolio_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """Get historical snapshots.

        Args:
            portfolio_id: Portfolio identifier
            start_time: Start timestamp (Unix ms)
            end_time: End timestamp (Unix ms)
            limit: Maximum number of snapshots

        Returns:
            List of PortfolioSnapshot
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check storage health.

        Returns:
            True if storage is healthy
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close storage connection."""
        pass


class PortfolioTracker:
    """Tracks portfolio state with real-time updates from exchanges.

    The PortfolioTracker provides:
    - Real-time position tracking with PnL updates
    - Balance tracking across multiple tokens
    - State persistence with fault tolerance
    - Historical snapshot recording
    - Update replay capability for connection failures

    Attributes:
        portfolio_id: Unique portfolio identifier
        state: Current PortfolioState
        storage: Storage backend for persistence
        update_callbacks: List of callbacks for update notifications
        max_update_queue_size: Maximum size of update queue for replay
    """

    def __init__(
        self,
        portfolio_id: str,
        storage: PortfolioStorageInterface | None = None,
        max_update_queue_size: int = 10000,
    ):
        """Initialize portfolio tracker.

        Args:
            portfolio_id: Unique portfolio identifier
            storage: Optional storage backend
            max_update_queue_size: Maximum updates to queue for replay
        """
        self.portfolio_id = portfolio_id
        self.storage = storage
        self.max_update_queue_size = max_update_queue_size

        # Initialize state
        from portfolio.state_management.models import PortfolioState

        self.state = PortfolioState(portfolio_id=portfolio_id)

        # Update queue for replay capability
        self._update_queue: list[PortfolioUpdate] = []
        self._update_lock = asyncio.Lock()

        # CRITICAL-3 FIX: Use weak references to prevent memory leaks
        # Callbacks are stored as weak references to allow garbage collection
        # when the callback owner is no longer referenced elsewhere
        self._update_callbacks: list[weakref.ref] = []
        self._state_callbacks: list[weakref.ref] = []

        # Snapshot interval (default: every 60 seconds)
        self._snapshot_interval_seconds = 60
        self._snapshot_task: asyncio.Task | None = None
        self._running = False

        logger.info(f"Initialized PortfolioTracker for {portfolio_id}")

    def register_update_callback(
        self, callback: Callable[[PortfolioUpdate], None]
    ) -> None:
        """Register a callback for update notifications.

        CRITICAL-3 FIX: Uses weak references to prevent memory leaks.
        The callback will be automatically unregistered when the
        callback owner is garbage collected.

        Args:
            callback: Function to call when updates are received
        """
        self._update_callbacks.append(weakref.ref(callback))

    def register_state_callback(
        self, callback: Callable[[PortfolioState], None]
    ) -> None:
        """Register a callback for state change notifications.

        CRITICAL-3 FIX: Uses weak references to prevent memory leaks.
        The callback will be automatically unregistered when the
        callback owner is garbage collected.

        Args:
            callback: Function to call when state changes
        """
        self._state_callbacks.append(weakref.ref(callback))

    def unregister_update_callback(
        self, callback: Callable[[PortfolioUpdate], None]
    ) -> bool:
        """Unregister an update callback.

        CRITICAL-3 FIX: Explicit callback unregistration for cleanup.

        Args:
            callback: Callback to unregister

        Returns:
            True if callback was found and removed
        """
        for i, ref in enumerate(self._update_callbacks):
            if ref() is callback:
                self._update_callbacks.pop(i)
                return True
        return False

    def unregister_state_callback(
        self, callback: Callable[[PortfolioState], None]
    ) -> bool:
        """Unregister a state callback.

        CRITICAL-3 FIX: Explicit callback unregistration for cleanup.

        Args:
            callback: Callback to unregister

        Returns:
            True if callback was found and removed
        """
        for i, ref in enumerate(self._state_callbacks):
            if ref() is callback:
                self._state_callbacks.pop(i)
                return True
        return False

    def _cleanup_dead_callbacks(self) -> None:
        """Remove dead weak references from callback lists.

        CRITICAL-3 FIX: Cleans up callbacks whose referents have been
        garbage collected.
        """
        self._update_callbacks = [
            ref for ref in self._update_callbacks if ref() is not None
        ]
        self._state_callbacks = [
            ref for ref in self._state_callbacks if ref() is not None
        ]

    def _notify_update(self, update: PortfolioUpdate) -> None:
        """Notify all update callbacks.

        CRITICAL-3 FIX: Handles dead references and auto-unregisters
        callbacks that raise exceptions.
        """
        dead_refs = []
        for ref in self._update_callbacks:
            callback = ref()
            if callback is None:
                dead_refs.append(ref)
                continue
            try:
                callback(update)
            except Exception as e:
                logger.warning(f"Update callback error: {e}")
                dead_refs.append(ref)

        # Remove dead/failed callbacks
        for ref in dead_refs:
            if ref in self._update_callbacks:
                self._update_callbacks.remove(ref)

    def _notify_state_change(self) -> None:
        """Notify all state callbacks.

        CRITICAL-3 FIX: Handles dead references and auto-unregisters
        callbacks that raise exceptions.
        """
        dead_refs = []
        for ref in self._state_callbacks:
            callback = ref()
            if callback is None:
                dead_refs.append(ref)
                continue
            try:
                callback(self.state)
            except Exception as e:
                logger.warning(f"State callback error: {e}")
                dead_refs.append(ref)

        # Remove dead/failed callbacks
        for ref in dead_refs:
            if ref in self._state_callbacks:
                self._state_callbacks.remove(ref)

    async def _queue_update(self, update: PortfolioUpdate) -> None:
        """Add update to queue for replay capability."""
        async with self._update_lock:
            self._update_queue.append(update)
            # Trim queue if it exceeds max size
            if len(self._update_queue) > self.max_update_queue_size:
                self._update_queue = self._update_queue[-self.max_update_queue_size :]

    async def handle_position_update(self, update: PositionUpdate) -> Position:
        """Handle a position update from exchange.

        Args:
            update: Position update data

        Returns:
            Updated or created Position
        """
        await self._queue_update(update)

        # CRITICAL-1 FIX: Use .get() for atomic check-and-use to prevent TOCTOU race condition
        # This ensures the position lookup and retrieval happen atomically
        position = self.state.positions.get(update.position_id)

        if position is not None:
            # Update existing position
            if update.current_price is not None:
                position.update_price(update.current_price, update.timestamp)

            if update.status != position.status.value:
                position.status = PositionStatus(update.status)

            position.last_update = update.timestamp
            logger.debug(f"Updated position {update.position_id}")
        else:
            # Create new position
            position = Position(
                position_id=update.position_id,
                token=update.token,
                direction=PositionDirection(update.direction),
                entry_price=update.entry_price,
                quantity=update.quantity,
                current_price=update.current_price or update.entry_price,
                timestamp=update.timestamp,
                last_update=update.timestamp,
                status=PositionStatus(update.status),
                leverage=update.leverage,
            )
            self.state.add_position(position)
            logger.info(f"Added new position {update.position_id} for {update.token}")

        # Recalculate portfolio totals
        self.state._recalculate_totals()
        self.state.last_update = update.timestamp

        # Notify callbacks
        self._notify_update(update)
        self._notify_state_change()

        return position

    async def handle_balance_update(self, update: BalanceUpdate) -> Balance:
        """Handle a balance update from exchange.

        Args:
            update: Balance update data

        Returns:
            Updated Balance
        """
        await self._queue_update(update)

        # Update balance
        balance = self.state.update_balance(
            token=update.token,
            free=update.free,
            locked=update.locked,
        )

        logger.debug(f"Updated balance for {update.token}: free={update.free}")

        # Notify callbacks
        self._notify_update(update)
        self._notify_state_change()

        return balance

    async def handle_price_update(self, update: PriceUpdate) -> None:
        """Handle a price update for PnL calculation.

        Args:
            update: Price update data
        """
        await self._queue_update(update)

        # Update all positions for this token
        positions_updated = False
        for position in self.state.positions.values():
            if position.token == update.token and position.is_open:
                position.update_price(update.price, update.timestamp)
                positions_updated = True

        if positions_updated:
            self.state._recalculate_totals()
            self.state.last_update = update.timestamp
            self._notify_state_change()
            logger.debug(f"Updated prices for {update.token}: {update.price}")

        # Notify callbacks
        self._notify_update(update)

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        timestamp: int | None = None,
    ) -> float | None:
        """Close a position and calculate realized PnL.

        CRITICAL-2 FIX: Handles persistence failure gracefully by logging
        the failure but keeping the in-memory state consistent. The position
        remains closed in memory even if persistence fails.

        Args:
            position_id: Position to close
            exit_price: Exit price
            timestamp: Optional close timestamp

        Returns:
            Realized PnL or None if position not found
        """
        import time

        if position_id not in self.state.positions:
            logger.warning(f"Position {position_id} not found for closing")
            return None

        position = self.state.positions[position_id]
        ts = timestamp or int(time.time() * 1000)

        realized_pnl = position.close_position(exit_price, ts)
        # Add realized PnL to portfolio total
        self.state.realized_pnl += realized_pnl
        self.state._recalculate_totals()
        self.state.last_update = ts

        # Persist state if storage available
        # CRITICAL-2: Persistence failure is logged but doesn't prevent state update
        if self.storage:
            persist_success = await self._persist_state()
            if not persist_success:
                logger.warning(
                    f"Position {position_id} closed in memory but persistence failed. "
                    f"State will be inconsistent until persistence recovers."
                )

        self._notify_state_change()

        logger.info(f"Closed position {position_id}: realized_pnl={realized_pnl:.4f}")

        return realized_pnl

    async def _persist_state(self) -> bool:
        """Persist current state to storage.

        CRITICAL-2 FIX: Implements retry logic and rollback protection.
        If persistence fails after retries, state changes are not rolled back
        (they're already in memory), but we log the failure for manual recovery.

        Returns:
            True if persistence was successful
        """
        if not self.storage:
            return False

        max_retries = 3
        retry_delay = 0.1  # 100ms initial delay

        for attempt in range(max_retries):
            try:
                success = await self.storage.store_state(self.state)
                if success:
                    logger.debug(f"Persisted state for {self.portfolio_id}")
                    return True
                else:
                    logger.warning(
                        f"Failed to persist state for {self.portfolio_id} "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
            except Exception as e:
                logger.error(
                    f"Error persisting state (attempt {attempt + 1}/{max_retries}): {e}"
                )

            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff

        logger.error(
            f"CRITICAL: Failed to persist state for {self.portfolio_id} after "
            f"{max_retries} attempts. State is in memory but not persisted. "
            f"Manual recovery may be required."
        )
        return False

    async def _take_snapshot(self) -> PortfolioSnapshot | None:
        """Take a snapshot of current state.

        CRITICAL-5 FIX: Uses deepcopy under update lock to ensure consistent state.
        The snapshot captures a point-in-time view of the portfolio state without
        race conditions from concurrent mutations.

        Returns:
            PortfolioSnapshot or None if storage unavailable
        """
        if not self.storage:
            return None

        import copy

        # CRITICAL-5: Lock during snapshot to prevent state mutation
        # Create deep copy to ensure consistent snapshot even if state changes
        async with self._update_lock:
            # Deep copy state to capture consistent snapshot
            state_copy = copy.deepcopy(self.state)

        snapshot = PortfolioSnapshot.from_portfolio_state(
            snapshot_id=str(uuid.uuid4()),
            state=state_copy,
        )

        try:
            success = await self.storage.store_snapshot(snapshot)
            if success:
                logger.debug(f"Stored snapshot {snapshot.snapshot_id}")
                return snapshot
            else:
                logger.warning("Failed to store snapshot")
                return None
        except Exception as e:
            logger.error(f"Error storing snapshot: {e}")
            return None

    async def _snapshot_loop(self) -> None:
        """Background task for periodic snapshots."""
        while self._running:
            try:
                await asyncio.sleep(self._snapshot_interval_seconds)
                if self._running:
                    await self._take_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in snapshot loop: {e}")

    async def start(self, snapshot_interval_seconds: int = 60) -> None:
        """Start the tracker with background snapshot task.

        Args:
            snapshot_interval_seconds: Interval between snapshots
        """
        self._running = True
        self._snapshot_interval_seconds = snapshot_interval_seconds

        # Load latest state from storage if available
        if self.storage:
            try:
                latest_state = await self.storage.get_latest_state(self.portfolio_id)
                if latest_state:
                    self.state = latest_state
                    logger.info(f"Loaded latest state for {self.portfolio_id}")
            except Exception as e:
                logger.warning(f"Could not load latest state: {e}")

        # Start snapshot task
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())
        logger.info(f"Started PortfolioTracker for {self.portfolio_id}")

    async def stop(self) -> None:
        """Stop the tracker and cleanup."""
        self._running = False

        # Cancel snapshot task
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass

        # Final state persistence
        await self._persist_state()

        # Close storage
        if self.storage:
            await self.storage.close()

        logger.info(f"Stopped PortfolioTracker for {self.portfolio_id}")

    async def get_update_queue(self) -> list[PortfolioUpdate]:
        """Get current update queue for replay.

        Returns:
            List of queued updates
        """
        async with self._update_lock:
            return list(self._update_queue)

    async def replay_updates(self, updates: list[PortfolioUpdate]) -> None:
        """Replay updates after connection recovery.

        Args:
            updates: List of updates to replay
        """
        logger.info(f"Replaying {len(updates)} updates")

        for update in updates:
            try:
                if isinstance(update, PositionUpdate):
                    await self.handle_position_update(update)
                elif isinstance(update, BalanceUpdate):
                    await self.handle_balance_update(update)
                elif isinstance(update, PriceUpdate):
                    await self.handle_price_update(update)
            except Exception as e:
                logger.warning(f"Error replaying update: {e}")

        logger.info("Update replay completed")

    async def get_snapshots(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """Get historical snapshots.

        Args:
            start_time: Start timestamp (Unix ms)
            end_time: End timestamp (Unix ms)
            limit: Maximum number of snapshots

        Returns:
            List of PortfolioSnapshot
        """
        if not self.storage:
            return []

        return await self.storage.get_snapshots(
            self.portfolio_id, start_time, end_time, limit
        )

    async def __aenter__(self) -> PortfolioTracker:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()
