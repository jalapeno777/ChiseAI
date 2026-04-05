"""Tests for position persistence functionality."""

from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from src.execution.paper.position_persistence import PositionPersistence
from src.execution.paper.position_tracker import PaperPosition, PaperPositionTracker


class TestPositionPersistence:
    """Test position persistence to Redis."""

    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        import os

        redis_url = os.getenv("REDIS_URL", "redis://host.docker.internal:6380")
        client = Redis.from_url(redis_url, decode_responses=True)
        yield client
        # Cleanup: delete all test keys
        keys = await client.keys("paper:position:*")
        if keys:
            await client.delete(*keys)
        await client.aclose()

    @pytest.fixture
    async def tracker_with_persistence(self, redis_client):
        """Create tracker with persistence enabled."""
        tracker = PaperPositionTracker()
        await tracker.enable_persistence(redis_client)
        yield tracker
        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_open_position_persists_to_redis(
        self, tracker_with_persistence, redis_client
    ):
        """Test that opening a position persists to Redis."""
        # Arrange
        tracker = tracker_with_persistence

        # Act
        position = await tracker.open_position(
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
        )

        # Assert
        assert position.position_id is not None
        # Verify in Redis
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 1
        data = await redis_client.get(keys[0])
        assert position.position_id in data

    @pytest.mark.asyncio
    async def test_close_position_updates_persistence(
        self, tracker_with_persistence, redis_client
    ):
        """Test that closing a position updates Redis."""
        # Arrange
        tracker = tracker_with_persistence
        position = await tracker.open_position("BTC/USDT", "long", 50000.0, 0.1)

        # Act
        closed_pos, pnl = await tracker.close_position(
            position.position_id, exit_price=51000.0
        )

        # Assert
        assert closed_pos.closed_at is not None
        # Verify in Redis - should have only 1 key (closed position)
        # The old open key should be deleted to prevent stale open-key resurrection
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 1
        # The closed position should be stored with "closed:" prefix
        closed_keys = [k for k in keys if ":closed:" in k]
        assert len(closed_keys) == 1
        data = await redis_client.get(closed_keys[0])
        assert '"is_open": false' in data

    @pytest.mark.asyncio
    async def test_recover_from_persistence(self, redis_client):
        """Test recovering positions after restart."""
        # Arrange - create tracker, add positions, then "restart"
        tracker1 = PaperPositionTracker()
        await tracker1.enable_persistence(redis_client)

        pos1 = await tracker1.open_position("BTC/USDT", "long", 50000.0, 0.1)
        pos2 = await tracker1.open_position("ETH/USDT", "short", 3000.0, 1.0)

        # Simulate restart - create new tracker instance
        tracker2 = PaperPositionTracker()
        await tracker2.enable_persistence(redis_client)

        # Act - recover from persistence
        recovered_count = await tracker2.recover_from_persistence()

        # Assert
        assert recovered_count == 2
        open_positions = await tracker2.get_open_positions()
        assert len(open_positions) == 2
        symbols = {p.symbol for p in open_positions}
        assert symbols == {"BTC/USDT", "ETH/USDT"}

    @pytest.mark.asyncio
    async def test_recover_includes_closed_positions(self, redis_client):
        """Test that recovered positions include closed positions."""
        # Arrange
        tracker1 = PaperPositionTracker()
        await tracker1.enable_persistence(redis_client)

        open_pos = await tracker1.open_position("BTC/USDT", "long", 50000.0, 0.1)
        closed_pos, _ = await tracker1.close_position(
            open_pos.position_id, exit_price=51000.0
        )

        # Simulate restart
        tracker2 = PaperPositionTracker()
        await tracker2.enable_persistence(redis_client)

        # Act
        recovered_count = await tracker2.recover_from_persistence()

        # Assert - only 1 position was created and closed, so only 1 key exists
        # (the old open key is deleted when position is closed to prevent resurrection)
        assert recovered_count == 1
        open_positions = await tracker2.get_open_positions()
        closed_positions = await tracker2.get_closed_positions()
        assert len(open_positions) == 0
        assert len(closed_positions) == 1
        assert closed_positions[0].symbol == "BTC/USDT"
        assert closed_positions[0].closed_at is not None

    @pytest.mark.asyncio
    async def test_constructor_enable_persistence_flag(self, redis_client):
        """Test that enable_persistence=True in constructor works."""
        # Arrange & Act
        tracker = PaperPositionTracker(enable_persistence=True)

        # Assert
        position = await tracker.open_position("BTC/USDT", "long", 50000.0, 0.1)

        # Verify persisted
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 1

        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_persistence_without_enable_does_not_persist(self, redis_client):
        """Test that tracker without persistence doesn't write to Redis."""
        # Arrange
        tracker = PaperPositionTracker()  # No persistence enabled

        # Act
        position = await tracker.open_position("BTC/USDT", "long", 50000.0, 0.1)

        # Assert
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 0

        await tracker.clear_all()

    @pytest.mark.asyncio
    async def test_remove_position_from_persistence(
        self, tracker_with_persistence, redis_client
    ):
        """Test removing a position from persistence."""
        # Arrange
        tracker = tracker_with_persistence
        position = await tracker.open_position("BTC/USDT", "long", 50000.0, 0.1)

        # Act
        persistence = tracker._persistence
        await persistence.remove_position(position.position_id)

        # Assert
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 0

    @pytest.mark.asyncio
    async def test_serialize_deserialize_roundtrip(self):
        """Test that position serialization is reversible."""
        # Arrange
        original_pos = PaperPosition(
            position_id="test-123",
            symbol="BTC/USDT",
            side="long",
            entry_price=50000.0,
            quantity=0.1,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            opened_at=datetime.now(UTC),
            metadata={"strategy": "test"},
            entry_fees=5.0,
            exit_fees=0.0,
        )

        # Create persistence instance
        persistence = PositionPersistence()

        # Act - serialize
        serialized = persistence._serialize_position(original_pos)
        # Deserialize
        restored = persistence._deserialize_position(serialized)

        # Assert
        assert restored.position_id == original_pos.position_id
        assert restored.symbol == original_pos.symbol
        assert restored.side == original_pos.side
        assert restored.entry_price == original_pos.entry_price
        assert restored.quantity == original_pos.quantity
        assert restored.metadata == original_pos.metadata
        assert restored.entry_fees == original_pos.entry_fees

    @pytest.mark.asyncio
    async def test_recover_from_persistence_without_enable_raises(self, redis_client):
        """Test that calling recover without enabling persistence raises."""
        # Arrange
        tracker = PaperPositionTracker()  # No persistence

        # Act & Assert
        with pytest.raises(RuntimeError, match="Persistence not enabled"):
            await tracker.recover_from_persistence()


class TestPositionPersistenceEdgeCases:
    """Edge case tests for position persistence."""

    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        import os

        redis_url = os.getenv("REDIS_URL", "redis://host.docker.internal:6380")
        client = Redis.from_url(redis_url, decode_responses=True)
        yield client
        keys = await client.keys("paper:position:*")
        if keys:
            await client.delete(*keys)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_recover_empty_persistence(self, redis_client):
        """Test recovering when no positions exist in Redis."""
        # Arrange
        tracker = PaperPositionTracker()
        await tracker.enable_persistence(redis_client)

        # Act
        recovered_count = await tracker.recover_from_persistence()

        # Assert
        assert recovered_count == 0
        open_positions = await tracker.get_open_positions()
        assert len(open_positions) == 0

    @pytest.mark.asyncio
    async def test_position_with_minimal_data_serializes(self):
        """Test serialization of position with only required fields."""
        # Arrange
        position = PaperPosition(
            position_id="test-min",
            symbol="ETH/USDT",
            side="short",
            entry_price=2000.0,
            quantity=1.0,
        )

        persistence = PositionPersistence()

        # Act
        serialized = persistence._serialize_position(position)
        restored = persistence._deserialize_position(serialized)

        # Assert
        assert restored.position_id == position.position_id
        assert restored.symbol == position.symbol
        assert restored.entry_fees == 0.0
        assert restored.exit_fees == 0.0

    @pytest.mark.asyncio
    async def test_closed_position_does_not_resurrect_on_recovery(self, redis_client):
        """REGRESSION TEST: Verify closed positions don't resurrect on restart.

        This test verifies the fix for the stale open-key resurrection bug where:
        1. A position is opened and persisted to Redis
        2. The position is closed, persisted with 'closed:' prefix
        3. On restart, the old open key should NOT cause the closed position to resurrect

        Before the fix:
        - Both open and closed keys existed in Redis
        - load_all_positions() would load both
        - The stale open key would incorrectly resurrect the position as open

        After the fix:
        - Only the closed key exists after closing
        - Recovery correctly restores position as closed
        """
        # Arrange - Create tracker, open and close a position
        tracker1 = PaperPositionTracker()
        await tracker1.enable_persistence(redis_client)

        open_pos = await tracker1.open_position("BTC/USDT", "long", 50000.0, 0.1)
        position_id = open_pos.position_id

        # Close the position
        closed_pos, pnl = await tracker1.close_position(position_id, exit_price=51000.0)
        assert closed_pos.is_open is False

        # Verify in Redis - should have only 1 key (closed)
        keys = await redis_client.keys("paper:position:*")
        assert len(keys) == 1
        assert ":closed:" in keys[0]

        # Simulate restart by creating new tracker
        tracker2 = PaperPositionTracker()
        await tracker2.enable_persistence(redis_client)

        # Act - Recover from persistence
        recovered_count = await tracker2.recover_from_persistence()

        # Assert - Only 1 position recovered, and it's correctly closed
        assert recovered_count == 1
        open_positions = await tracker2.get_open_positions()
        closed_positions = await tracker2.get_closed_positions()

        assert len(open_positions) == 0, "Closed position should NOT resurrect as open"
        assert len(closed_positions) == 1, "Closed position should be recovered"
        assert closed_positions[0].position_id == position_id
        assert closed_positions[0].is_open is False
        assert closed_positions[0].closed_at is not None
