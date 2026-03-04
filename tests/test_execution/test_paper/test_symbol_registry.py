"""Tests for Symbol Position Registry.

Tests for SymbolPositionRegistry including atomic operations,
TTL handling, and race condition scenarios.

Part of PAPER-2025-001: One-Trade-Per-Symbol Invariant.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.execution.paper.symbol_registry import SymbolPositionRegistry


class TestSymbolPositionRegistry:
    """Test SymbolPositionRegistry class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.set = AsyncMock()
        mock.get = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock()
        mock.ttl = AsyncMock()
        mock.expire = AsyncMock()
        mock.pipeline = MagicMock(return_value=mock)
        mock.execute = AsyncMock()
        return mock

    @pytest.fixture
    def registry(self, mock_redis):
        """Create a registry with mock Redis."""
        return SymbolPositionRegistry(redis_client=mock_redis, default_ttl_seconds=3600)

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test registry initialization."""
        registry = SymbolPositionRegistry(default_ttl_seconds=1800)

        assert registry._default_ttl_seconds == 1800
        assert registry._redis is None
        assert registry._owns_redis is True

    @pytest.mark.asyncio
    async def test_initialization_with_redis_client(self, mock_redis):
        """Test registry with provided Redis client."""
        registry = SymbolPositionRegistry(redis_client=mock_redis)

        assert registry._redis is mock_redis
        assert registry._owns_redis is False

    @pytest.mark.asyncio
    async def test_make_key_normalization(self, registry):
        """Test key normalization for different symbol formats."""
        # Test uppercase conversion
        assert registry._make_key("btc/usdt") == "paper:symbol_registry:BTC_USDT"
        # Test dash replacement
        assert registry._make_key("BTC-USDT") == "paper:symbol_registry:BTC_USDT"
        # Test already normalized
        assert registry._make_key("BTC_USDT") == "paper:symbol_registry:BTC_USDT"

    @pytest.mark.asyncio
    async def test_try_acquire_symbol_success(self, registry, mock_redis):
        """Test successful symbol acquisition."""
        mock_redis.set.return_value = True

        result = await registry.try_acquire_symbol("BTC/USDT", "pos-123")

        assert result is True
        mock_redis.set.assert_called_once_with(
            "paper:symbol_registry:BTC_USDT", "pos-123", nx=True, ex=3600
        )

    @pytest.mark.asyncio
    async def test_try_acquire_symbol_already_held(self, registry, mock_redis):
        """Test acquisition failure when symbol already held."""
        mock_redis.set.return_value = None  # SET NX returns None when key exists
        mock_redis.get.return_value = "pos-456"

        result = await registry.try_acquire_symbol("BTC/USDT", "pos-123")

        assert result is False
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_acquire_symbol_custom_ttl(self, registry, mock_redis):
        """Test acquisition with custom TTL."""
        mock_redis.set.return_value = True

        result = await registry.try_acquire_symbol(
            "BTC/USDT", "pos-123", ttl_seconds=7200
        )

        assert result is True
        mock_redis.set.assert_called_once_with(
            "paper:symbol_registry:BTC_USDT", "pos-123", nx=True, ex=7200
        )

    @pytest.mark.asyncio
    async def test_try_acquire_symbol_empty_values(self, registry):
        """Test acquisition with empty values raises error."""
        with pytest.raises(ValueError, match="symbol and position_id are required"):
            await registry.try_acquire_symbol("", "pos-123")

        with pytest.raises(ValueError, match="symbol and position_id are required"):
            await registry.try_acquire_symbol("BTC/USDT", "")

    @pytest.mark.asyncio
    async def test_release_symbol_success(self, registry, mock_redis):
        """Test successful symbol release."""
        mock_redis.get.return_value = "pos-123"
        mock_redis.delete.return_value = 1

        result = await registry.release_symbol("BTC/USDT", "pos-123")

        assert result is True
        mock_redis.get.assert_called_once_with("paper:symbol_registry:BTC_USDT")
        mock_redis.delete.assert_called_once_with("paper:symbol_registry:BTC_USDT")

    @pytest.mark.asyncio
    async def test_release_symbol_not_held(self, registry, mock_redis):
        """Test release when symbol not held."""
        mock_redis.get.return_value = None

        result = await registry.release_symbol("BTC/USDT", "pos-123")

        assert result is False
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_symbol_wrong_position(self, registry, mock_redis):
        """Test release with wrong position_id."""
        mock_redis.get.return_value = "pos-456"  # Different position

        result = await registry.release_symbol("BTC/USDT", "pos-123")

        assert result is False
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_symbol_empty_values(self, registry):
        """Test release with empty values raises error."""
        with pytest.raises(ValueError, match="symbol and position_id are required"):
            await registry.release_symbol("", "pos-123")

        with pytest.raises(ValueError, match="symbol and position_id are required"):
            await registry.release_symbol("BTC/USDT", "")

    @pytest.mark.asyncio
    async def test_get_position_for_symbol_exists(self, registry, mock_redis):
        """Test getting position for held symbol."""
        mock_redis.get.return_value = "pos-123"

        result = await registry.get_position_for_symbol("BTC/USDT")

        assert result == "pos-123"
        mock_redis.get.assert_called_once_with("paper:symbol_registry:BTC_USDT")

    @pytest.mark.asyncio
    async def test_get_position_for_symbol_not_exists(self, registry, mock_redis):
        """Test getting position for unheld symbol."""
        mock_redis.get.return_value = None

        result = await registry.get_position_for_symbol("BTC/USDT")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_position_for_symbol_empty(self, registry):
        """Test getting position with empty symbol raises error."""
        with pytest.raises(ValueError, match="symbol is required"):
            await registry.get_position_for_symbol("")

    @pytest.mark.asyncio
    async def test_get_all_active_symbols(self, registry, mock_redis):
        """Test getting all active symbols."""
        mock_redis.keys.return_value = [
            "paper:symbol_registry:BTC_USDT",
            "paper:symbol_registry:ETH_USDT",
        ]
        # Create a mock pipeline that supports chaining
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=["pos-123", "pos-456"])
        mock_pipe.get = MagicMock(return_value=mock_pipe)  # Return self for chaining
        mock_redis.pipeline.return_value = mock_pipe

        result = await registry.get_all_active_symbols()

        assert result == {"BTC/USDT": "pos-123", "ETH/USDT": "pos-456"}
        mock_redis.keys.assert_called_once_with("paper:symbol_registry:*")

    @pytest.mark.asyncio
    async def test_get_all_active_symbols_empty(self, registry, mock_redis):
        """Test getting all active symbols when none exist."""
        mock_redis.keys.return_value = []

        result = await registry.get_all_active_symbols()

        assert result == {}

    @pytest.mark.asyncio
    async def test_extend_ttl_success(self, registry, mock_redis):
        """Test successful TTL extension."""
        mock_redis.ttl.return_value = 1800  # 30 minutes remaining
        mock_redis.expire.return_value = True

        result = await registry.extend_ttl("BTC/USDT", 3600)

        assert result is True
        mock_redis.ttl.assert_called_once_with("paper:symbol_registry:BTC_USDT")
        mock_redis.expire.assert_called_once_with(
            "paper:symbol_registry:BTC_USDT", 5400
        )  # 1800 + 3600

    @pytest.mark.asyncio
    async def test_extend_ttl_key_not_found(self, registry, mock_redis):
        """Test TTL extension when key doesn't exist."""
        mock_redis.ttl.return_value = -2  # Key doesn't exist

        result = await registry.extend_ttl("BTC/USDT", 3600)

        assert result is False
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_extend_ttl_no_ttl_set(self, registry, mock_redis):
        """Test TTL extension when key has no TTL."""
        mock_redis.ttl.return_value = -1  # Key exists but has no TTL

        result = await registry.extend_ttl("BTC/USDT", 3600)

        assert result is False
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_extend_ttl_negative_seconds(self, registry):
        """Test TTL extension with negative seconds raises error."""
        with pytest.raises(ValueError, match="additional_seconds must be non-negative"):
            await registry.extend_ttl("BTC/USDT", -100)

    @pytest.mark.asyncio
    async def test_extend_ttl_empty_symbol(self, registry):
        """Test TTL extension with empty symbol raises error."""
        with pytest.raises(ValueError, match="symbol is required"):
            await registry.extend_ttl("", 100)

    @pytest.mark.asyncio
    async def test_clear_all(self, registry, mock_redis):
        """Test clearing all registry entries."""
        mock_redis.keys.return_value = [
            "paper:symbol_registry:BTC_USDT",
            "paper:symbol_registry:ETH_USDT",
        ]
        mock_redis.delete.return_value = 2

        result = await registry.clear_all()

        assert result == 2
        mock_redis.delete.assert_called_once_with(
            "paper:symbol_registry:BTC_USDT", "paper:symbol_registry:ETH_USDT"
        )

    @pytest.mark.asyncio
    async def test_clear_all_empty(self, registry, mock_redis):
        """Test clearing when no entries exist."""
        mock_redis.keys.return_value = []

        result = await registry.clear_all()

        assert result == 0
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_owned_redis(self, mock_redis):
        """Test closing Redis connection when owned."""
        registry = SymbolPositionRegistry(redis_client=None, default_ttl_seconds=3600)
        registry._redis = mock_redis

        await registry.close()

        mock_redis.close.assert_called_once()
        assert registry._redis is None

    @pytest.mark.asyncio
    async def test_close_not_owned_redis(self, mock_redis):
        """Test not closing Redis when not owned."""
        registry = SymbolPositionRegistry(redis_client=mock_redis)

        await registry.close()

        mock_redis.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_stats(self, registry):
        """Test getting registry stats."""
        stats = registry.get_stats()

        assert stats["key_prefix"] == "paper:symbol_registry"
        assert stats["default_ttl_seconds"] == 3600
        assert stats["owns_redis_connection"] is False


class TestConcurrentAcquisition:
    """Test concurrent acquisition scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire_race_condition(self):
        """Test that only one position can acquire a symbol concurrently."""
        # Create a mock that simulates race condition
        call_count = 0

        async def mock_set(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First caller succeeds, rest fail
            if call_count == 1:
                return True
            return None

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = AsyncMock(return_value="winner")

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        # Try to acquire from multiple coroutines simultaneously
        async def try_acquire(position_id):
            return await registry.try_acquire_symbol("BTC/USDT", position_id)

        results = await asyncio.gather(
            try_acquire("pos-1"),
            try_acquire("pos-2"),
            try_acquire("pos-3"),
            try_acquire("pos-4"),
            try_acquire("pos-5"),
        )

        # Exactly one should succeed
        assert sum(results) == 1
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_acquire_release_acquire_sequence(self):
        """Test acquire → release → acquire sequence."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock(return_value=1)

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        # First acquisition should succeed
        result1 = await registry.try_acquire_symbol("BTC/USDT", "pos-1")
        assert result1 is True

        # Release
        mock_redis.get.return_value = "pos-1"
        released = await registry.release_symbol("BTC/USDT", "pos-1")
        assert released is True

        # Second acquisition should succeed after release
        mock_redis.set.return_value = True
        mock_redis.get.return_value = None
        result2 = await registry.try_acquire_symbol("BTC/USDT", "pos-2")
        assert result2 is True


class TestRedisErrorHandling:
    """Test Redis error handling."""

    @pytest.mark.asyncio
    async def test_acquire_redis_error(self):
        """Test handling of Redis error during acquire."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Connection refused"))

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        with pytest.raises(Exception, match="Connection refused"):
            await registry.try_acquire_symbol("BTC/USDT", "pos-123")

    @pytest.mark.asyncio
    async def test_release_redis_error(self):
        """Test handling of Redis error during release."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Connection refused"))

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        with pytest.raises(Exception, match="Connection refused"):
            await registry.release_symbol("BTC/USDT", "pos-123")

    @pytest.mark.asyncio
    async def test_get_position_redis_error(self):
        """Test handling of Redis error during get."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Connection refused"))

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        with pytest.raises(Exception, match="Connection refused"):
            await registry.get_position_for_symbol("BTC/USDT")


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_position_lifecycle(self):
        """Test complete position lifecycle: acquire → verify → extend → release."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ttl = AsyncMock(return_value=1800)
        mock_redis.expire = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        # Acquire symbol
        acquired = await registry.try_acquire_symbol("BTC/USDT", "pos-abc")
        assert acquired is True

        # Verify it's held
        mock_redis.get.return_value = "pos-abc"
        position = await registry.get_position_for_symbol("BTC/USDT")
        assert position == "pos-abc"

        # Extend TTL
        extended = await registry.extend_ttl("BTC/USDT", 3600)
        assert extended is True

        # Release
        released = await registry.release_symbol("BTC/USDT", "pos-abc")
        assert released is True

    @pytest.mark.asyncio
    async def test_multiple_symbols_independent(self):
        """Test that different symbols are independent."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        # Acquire BTC
        btc_acquired = await registry.try_acquire_symbol("BTC/USDT", "pos-btc")
        assert btc_acquired is True

        # Acquire ETH (should succeed independently)
        eth_acquired = await registry.try_acquire_symbol("ETH/USDT", "pos-eth")
        assert eth_acquired is True

        # Verify calls
        assert mock_redis.set.call_count == 2

    @pytest.mark.asyncio
    async def test_symbol_normalization_consistency(self):
        """Test that symbol normalization is consistent."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value="pos-123")
        mock_redis.delete = AsyncMock(return_value=1)

        registry = SymbolPositionRegistry(redis_client=mock_redis)

        # Acquire with lowercase
        await registry.try_acquire_symbol("btc/usdt", "pos-123")
        first_key = mock_redis.set.call_args[0][0]

        # Release with uppercase
        await registry.release_symbol("BTC/USDT", "pos-123")
        second_key = mock_redis.get.call_args[0][0]

        # Keys should be the same
        assert first_key == second_key
        assert first_key == "paper:symbol_registry:BTC_USDT"
