"""Tests for portfolio tracker."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from portfolio.state_management.models import (
    Balance,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionDirection,
    PositionStatus,
)
from portfolio.state_management.tracker import (
    BalanceUpdate,
    PortfolioTracker,
    PortfolioUpdate,
    PositionUpdate,
    PriceUpdate,
)


@pytest.fixture
def mock_storage():
    """Create a mock storage backend."""
    storage = MagicMock()
    storage.store_state = AsyncMock(return_value=True)
    storage.store_snapshot = AsyncMock(return_value=True)
    storage.get_latest_state = AsyncMock(return_value=None)
    storage.get_snapshots = AsyncMock(return_value=[])
    storage.health_check = AsyncMock(return_value=True)
    storage.close = AsyncMock()
    return storage


@pytest.fixture
def tracker(mock_storage):
    """Create a PortfolioTracker with mock storage."""
    return PortfolioTracker(
        portfolio_id="test-portfolio",
        storage=mock_storage,
        max_update_queue_size=1000,
    )


class TestPortfolioTrackerPositionUpdates:
    """Tests for position update handling."""

    @pytest.mark.asyncio
    async def test_handle_new_position(self, tracker, mock_storage):
        """Test handling a new position update."""
        update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
            leverage=1.0,
        )

        position = await tracker.handle_position_update(update)

        assert position.position_id == "pos-1"
        assert position.token == "BTC"
        assert position.direction == PositionDirection.LONG
        assert position.entry_price == 50000.0
        assert position.unrealized_pnl == 1000.0
        assert "pos-1" in tracker.state.positions

    @pytest.mark.asyncio
    async def test_handle_position_update_existing(self, tracker, mock_storage):
        """Test updating an existing position."""
        # First create a position
        update1 = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
            status="open",
        )
        await tracker.handle_position_update(update1)

        # Update with new price
        update2 = PositionUpdate(
            timestamp=1234567900000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=52000.0,
            status="open",
        )
        position = await tracker.handle_position_update(update2)

        assert position.current_price == 52000.0
        assert position.unrealized_pnl == 2000.0
        assert position.last_update == 1234567900000

    @pytest.mark.asyncio
    async def test_handle_position_update_queue(self, tracker, mock_storage):
        """Test that updates are queued for replay."""
        update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )

        await tracker.handle_position_update(update)
        queue = await tracker.get_update_queue()

        assert len(queue) == 1
        assert queue[0].position_id == "pos-1"


class TestPortfolioTrackerBalanceUpdates:
    """Tests for balance update handling."""

    @pytest.mark.asyncio
    async def test_handle_balance_update(self, tracker, mock_storage):
        """Test handling a balance update."""
        update = BalanceUpdate(
            timestamp=1234567890000,
            source="bybit",
            token="USDT",
            free=10000.0,
            locked=2000.0,
        )

        balance = await tracker.handle_balance_update(update)

        assert balance.token == "USDT"
        assert balance.free == 10000.0
        assert balance.locked == 2000.0
        assert "USDT" in tracker.state.balances

    @pytest.mark.asyncio
    async def test_handle_balance_update_existing(self, tracker, mock_storage):
        """Test updating an existing balance."""
        # First update
        update1 = BalanceUpdate(
            timestamp=1234567890000,
            source="bybit",
            token="USDT",
            free=10000.0,
            locked=2000.0,
        )
        await tracker.handle_balance_update(update1)

        # Second update
        update2 = BalanceUpdate(
            timestamp=1234567900000,
            source="bybit",
            token="USDT",
            free=8000.0,
            locked=4000.0,
        )
        balance = await tracker.handle_balance_update(update2)

        assert balance.free == 8000.0
        assert balance.locked == 4000.0


class TestPortfolioTrackerPriceUpdates:
    """Tests for price update handling."""

    @pytest.mark.asyncio
    async def test_handle_price_update(self, tracker, mock_storage):
        """Test handling a price update."""
        # First create a position
        position_update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
            status="open",
        )
        await tracker.handle_position_update(position_update)

        # Update price
        price_update = PriceUpdate(
            timestamp=1234567900000,
            source="bybit",
            token="BTC",
            price=52000.0,
        )
        await tracker.handle_price_update(price_update)

        position = tracker.state.positions["pos-1"]
        assert position.current_price == 52000.0
        assert position.unrealized_pnl == 2000.0

    @pytest.mark.asyncio
    async def test_handle_price_update_no_positions(self, tracker, mock_storage):
        """Test price update when no positions exist."""
        price_update = PriceUpdate(
            timestamp=1234567890000,
            source="bybit",
            token="BTC",
            price=52000.0,
        )

        # Should not raise
        await tracker.handle_price_update(price_update)
        assert len(tracker.state.positions) == 0


class TestPortfolioTrackerClosePosition:
    """Tests for position closing."""

    @pytest.mark.asyncio
    async def test_close_position(self, tracker, mock_storage):
        """Test closing a position."""
        # Create a position
        position_update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )
        await tracker.handle_position_update(position_update)

        # Close position
        realized_pnl = await tracker.close_position("pos-1", 51000.0, 1234567950000)

        assert realized_pnl == 1000.0
        assert tracker.state.positions["pos-1"].status == PositionStatus.CLOSED
        assert tracker.state.realized_pnl == 1000.0

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, tracker, mock_storage):
        """Test closing a non-existent position."""
        realized_pnl = await tracker.close_position("non-existent", 50000.0)

        assert realized_pnl is None


class TestPortfolioTrackerCallbacks:
    """Tests for callback functionality."""

    @pytest.mark.asyncio
    async def test_update_callback(self, tracker, mock_storage):
        """Test update callback registration and notification."""
        callback_called = False
        received_update = None

        def callback(update):
            nonlocal callback_called, received_update
            callback_called = True
            received_update = update

        tracker.register_update_callback(callback)

        update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )
        await tracker.handle_position_update(update)

        assert callback_called is True
        assert received_update.position_id == "pos-1"

    @pytest.mark.asyncio
    async def test_state_callback(self, tracker, mock_storage):
        """Test state callback registration and notification."""
        callback_called = False
        received_state = None

        def callback(state):
            nonlocal callback_called, received_state
            callback_called = True
            received_state = state

        tracker.register_state_callback(callback)

        update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )
        await tracker.handle_position_update(update)

        assert callback_called is True
        assert received_state.portfolio_id == "test-portfolio"


class TestPortfolioTrackerReplay:
    """Tests for update replay functionality."""

    @pytest.mark.asyncio
    async def test_replay_updates(self, tracker, mock_storage):
        """Test replaying updates after connection recovery."""
        # Create some updates
        updates = [
            PositionUpdate(
                timestamp=1234567890000,
                source="bybit",
                position_id="pos-1",
                token="BTC",
                direction="LONG",
                entry_price=50000.0,
                quantity=1.0,
                current_price=51000.0,
                status="open",
            ),
            BalanceUpdate(
                timestamp=1234567890000,
                source="bybit",
                token="USDT",
                free=10000.0,
                locked=2000.0,
            ),
        ]

        await tracker.replay_updates(updates)

        assert "pos-1" in tracker.state.positions
        assert "USDT" in tracker.state.balances

    @pytest.mark.asyncio
    async def test_get_update_queue(self, tracker, mock_storage):
        """Test getting update queue."""
        update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )

        await tracker.handle_position_update(update)
        queue = await tracker.get_update_queue()

        assert len(queue) == 1
        assert isinstance(queue[0], PositionUpdate)


class TestPortfolioTrackerLifecycle:
    """Tests for tracker lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_loads_state(self, tracker, mock_storage):
        """Test that start loads latest state from storage."""
        existing_state = PortfolioState(portfolio_id="test-portfolio")
        existing_state.update_balance("USDT", free=50000.0)
        mock_storage.get_latest_state.return_value = existing_state

        await tracker.start()

        assert tracker.state.balances["USDT"].free == 50000.0
        mock_storage.get_latest_state.assert_called_once_with("test-portfolio")

    @pytest.mark.asyncio
    async def test_stop_persists_state(self, tracker, mock_storage):
        """Test that stop persists final state."""
        tracker.state.update_balance("USDT", free=10000.0)

        await tracker.stop()

        mock_storage.store_state.assert_called_once()
        mock_storage.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_storage):
        """Test async context manager."""
        tracker = PortfolioTracker(
            portfolio_id="test-portfolio",
            storage=mock_storage,
        )

        async with tracker as t:
            assert t is tracker
            assert t.state.portfolio_id == "test-portfolio"

        mock_storage.close.assert_called_once()


class TestCriticalBugFixes:
    """Tests for CRITICAL bug fixes (ST-NS-014A)."""

    @pytest.mark.asyncio
    async def test_concurrent_position_updates(self, mock_storage):
        """CRITICAL-1: Test TOCTOU race condition fix with concurrent updates."""
        tracker = PortfolioTracker(
            portfolio_id="test-portfolio",
            storage=mock_storage,
            max_update_queue_size=1000,
        )

        # Create initial position
        update1 = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
            status="open",
        )
        await tracker.handle_position_update(update1)

        # Simulate concurrent updates to the same position
        async def update_price(price):
            update = PositionUpdate(
                timestamp=1234567900000,
                source="bybit",
                position_id="pos-1",
                token="BTC",
                direction="LONG",
                entry_price=50000.0,
                quantity=1.0,
                current_price=price,
                status="open",
            )
            return await tracker.handle_position_update(update)

        # Run concurrent updates
        prices = [51000.0, 52000.0, 53000.0, 54000.0, 55000.0]
        tasks = [update_price(p) for p in prices]
        results = await asyncio.gather(*tasks)

        # All updates should succeed without race conditions
        assert all(r is not None for r in results)
        # Final position should have one of the updated prices
        assert tracker.state.positions["pos-1"].current_price in prices

    @pytest.mark.asyncio
    async def test_storage_failure_recovery(self, tracker, mock_storage):
        """CRITICAL-2: Test storage failure recovery with retry logic."""
        # First call fails, second succeeds
        mock_storage.store_state = AsyncMock(side_effect=[False, True])

        tracker.state.update_balance("USDT", free=10000.0)

        # Should eventually succeed with retry (succeeds on 2nd attempt)
        result = await tracker._persist_state()

        # Should succeed after retry
        assert result is True
        assert mock_storage.store_state.call_count == 2  # Failed once, succeeded once

    @pytest.mark.asyncio
    async def test_close_position_persistence_failure(self, tracker, mock_storage):
        """CRITICAL-2: Test close_position handles persistence failure gracefully."""
        # Create a position
        position_update = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )
        await tracker.handle_position_update(position_update)

        # Make storage fail
        mock_storage.store_state = AsyncMock(return_value=False)

        # Close position - should succeed in memory even if persistence fails
        realized_pnl = await tracker.close_position("pos-1", 51000.0, 1234567950000)

        # Position should be closed in memory
        assert realized_pnl == 1000.0
        assert tracker.state.positions["pos-1"].status == PositionStatus.CLOSED
        assert tracker.state.realized_pnl == 1000.0

    @pytest.mark.asyncio
    async def test_callback_cleanup_on_exception(self, tracker, mock_storage):
        """CRITICAL-3: Test callback cleanup on exception."""
        call_count = {"good": 0, "bad": 0}

        def good_callback(update):
            call_count["good"] += 1

        def bad_callback(update):
            call_count["bad"] += 1
            raise ValueError("Callback error")

        tracker.register_update_callback(good_callback)
        tracker.register_update_callback(bad_callback)

        # First update - bad callback should be removed after exception
        update1 = PositionUpdate(
            timestamp=1234567890000,
            source="bybit",
            position_id="pos-1",
            token="BTC",
            direction="LONG",
            entry_price=50000.0,
            quantity=1.0,
            current_price=51000.0,
            status="open",
        )
        await tracker.handle_position_update(update1)

        assert call_count["good"] == 1
        assert call_count["bad"] == 1

        # Second update - bad callback should be removed
        update2 = PositionUpdate(
            timestamp=1234567900000,
            source="bybit",
            position_id="pos-2",
            token="ETH",
            direction="LONG",
            entry_price=3000.0,
            quantity=10.0,
            current_price=3100.0,
            status="open",
        )
        await tracker.handle_position_update(update2)

        # Good callback should still be called, bad callback removed
        assert call_count["good"] == 2
        assert call_count["bad"] == 1  # Not called again

    def test_callback_unregister(self, tracker):
        """CRITICAL-3: Test explicit callback unregistration."""

        def callback(update):
            pass

        tracker.register_update_callback(callback)
        assert len(tracker._update_callbacks) == 1

        # Unregister
        result = tracker.unregister_update_callback(callback)
        assert result is True
        assert len(tracker._update_callbacks) == 0

        # Unregister non-existent
        result = tracker.unregister_update_callback(callback)
        assert result is False

    def test_callback_weak_reference_cleanup(self, tracker):
        """CRITICAL-3: Test automatic cleanup of dead weak references."""

        class CallbackOwner:
            def __init__(self):
                self.called = False

            def callback(self, update):
                self.called = True

        owner = CallbackOwner()
        tracker.register_update_callback(owner.callback)
        assert len(tracker._update_callbacks) == 1

        # Delete owner - callback should become dead reference
        del owner

        # Force garbage collection
        import gc

        gc.collect()

        # Clean up dead callbacks
        tracker._cleanup_dead_callbacks()
        assert len(tracker._update_callbacks) == 0

    @pytest.mark.asyncio
    async def test_concurrent_snapshot_during_state_mutation(
        self, tracker, mock_storage
    ):
        """CRITICAL-5: Test snapshot consistency during concurrent state mutation."""
        # Create initial state
        tracker.state.update_balance("USDT", free=100000.0)
        position = Position(
            position_id="pos-1",
            token="BTC",
            direction=PositionDirection.LONG,
            entry_price=50000.0,
            quantity=1.0,
            current_price=50000.0,
        )
        tracker.state.add_position(position)

        async def mutate_state():
            """Continuously mutate state."""
            for i in range(50):
                tracker.state.update_balance("USDT", free=100000.0 + i * 100)
                await asyncio.sleep(0.001)

        async def take_snapshots():
            """Take snapshots during mutation."""
            snapshots = []
            for _ in range(10):
                snapshot = await tracker._take_snapshot()
                if snapshot:
                    snapshots.append(snapshot)
                await asyncio.sleep(0.005)
            return snapshots

        # Run mutations and snapshots concurrently
        results = await asyncio.gather(
            mutate_state(), take_snapshots(), return_exceptions=True
        )

        # Check that snapshots are valid (no exceptions)
        snapshots = results[1]
        assert isinstance(snapshots, list)
        assert len(snapshots) > 0

        # All snapshots should have valid structure
        for snapshot in snapshots:
            assert snapshot.snapshot_id is not None
            assert snapshot.portfolio_id == "test-portfolio"
            assert snapshot.total_equity >= 0
            assert snapshot.position_count >= 0
