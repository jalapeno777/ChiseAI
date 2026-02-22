"""Tests for order idempotency module.

For ST-LAUNCH-003: Order Idempotency
"""

from __future__ import annotations

import asyncio
import re
import time
from unittest.mock import AsyncMock

import pytest

from execution.order_idempotency import (
    IDEMPOTENCY_KEY_PREFIX,
    IDEMPOTENCY_TTL_SECONDS,
    DuplicateOrderException,
    IdempotencyConfig,
    IdempotencyStore,
    build_idempotency_key,
    generate_client_order_id,
    get_default_store,
    parse_client_order_id,
    reset_default_store,
)


class TestClientOrderIdGeneration:
    """Test client order ID generation."""

    def test_generate_client_order_id_format(self):
        """Test that generated IDs follow the correct format."""
        client_id = generate_client_order_id("BTCUSDT")

        # Format should be: timestamp_symbol_random
        parts = client_id.split("_")
        assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}: {client_id}"

        timestamp, symbol, random_part = parts

        # Timestamp should be 13 digits (milliseconds)
        assert len(timestamp) == 13, (
            f"Timestamp should be 13 digits, got {len(timestamp)}"
        )
        assert timestamp.isdigit(), f"Timestamp should be numeric, got {timestamp}"

        # Symbol should match
        assert symbol == "BTCUSDT"

        # Random part should be 8 characters by default
        assert len(random_part) == 8, (
            f"Random part should be 8 chars, got {len(random_part)}"
        )

    def test_generate_client_order_id_custom_length(self):
        """Test generation with custom random length."""
        client_id = generate_client_order_id("ETHUSDT", id_length=12)
        parts = client_id.split("_")
        assert len(parts[2]) == 12

    def test_generate_client_order_id_uniqueness(self):
        """Test that generated IDs are unique."""
        ids = [generate_client_order_id("BTCUSDT") for _ in range(100)]
        assert len(set(ids)) == 100, "Generated IDs should be unique"

    def test_generate_client_order_id_timestamp_monotonic(self):
        """Test that timestamps are monotonically increasing."""
        ids = [generate_client_order_id("BTCUSDT") for _ in range(10)]
        timestamps = [int(id.split("_")[0]) for id in ids]

        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], "Timestamps should be monotonic"

    def test_generate_client_order_id_different_symbols(self):
        """Test generation for different symbols."""
        btc_id = generate_client_order_id("BTCUSDT")
        eth_id = generate_client_order_id("ETHUSDT")

        assert "BTCUSDT" in btc_id
        assert "ETHUSDT" in eth_id
        assert btc_id != eth_id


class TestParseClientOrderId:
    """Test parsing client order IDs."""

    def test_parse_valid_client_order_id(self):
        """Test parsing a valid client order ID."""
        client_id = "1704067200000_BTCUSDT_a3f9b2c1"
        parsed = parse_client_order_id(client_id)

        assert parsed["timestamp"] == "1704067200000"
        assert parsed["symbol"] == "BTCUSDT"
        assert parsed["random"] == "a3f9b2c1"

    def test_parse_invalid_format(self):
        """Test parsing an invalid client order ID."""
        with pytest.raises(ValueError) as exc_info:
            parse_client_order_id("invalid_format")

        assert "Invalid client order ID format" in str(exc_info.value)

    def test_parse_empty_string(self):
        """Test parsing an empty string."""
        with pytest.raises(ValueError):
            parse_client_order_id("")

    def test_parse_too_many_parts(self):
        """Test parsing ID with too many parts."""
        with pytest.raises(ValueError):
            parse_client_order_id("1704067200000_BTCUSDT_a3f9b2c1_extra")


class TestBuildIdempotencyKey:
    """Test building idempotency keys."""

    def test_build_key_default_prefix(self):
        """Test building key with default prefix."""
        key = build_idempotency_key("BTCUSDT", "1704067200000_BTCUSDT_a3f9b2c1")

        expected = f"{IDEMPOTENCY_KEY_PREFIX}:BTCUSDT:1704067200000_BTCUSDT_a3f9b2c1"
        assert key == expected

    def test_build_key_custom_prefix(self):
        """Test building key with custom prefix."""
        key = build_idempotency_key(
            "ETHUSDT", "1704067200000_ETHUSDT_b4g0c3d2", prefix="custom:prefix"
        )

        assert key == "custom:prefix:ETHUSDT:1704067200000_ETHUSDT_b4g0c3d2"

    def test_per_token_namespace(self):
        """Test that different tokens have different namespaces."""
        btc_key = build_idempotency_key("BTCUSDT", "1704067200000_BTCUSDT_a3f9b2c1")
        eth_key = build_idempotency_key("ETHUSDT", "1704067200000_BTCUSDT_a3f9b2c1")

        # Same client ID but different symbols = different keys
        assert btc_key != eth_key
        assert "BTCUSDT" in btc_key
        assert "ETHUSDT" in eth_key


class TestDuplicateOrderException:
    """Test DuplicateOrderException."""

    def test_exception_attributes(self):
        """Test exception has correct attributes."""
        exc = DuplicateOrderException("test_id_123", "BTCUSDT")

        assert exc.client_order_id == "test_id_123"
        assert exc.symbol == "BTCUSDT"
        assert "test_id_123" in exc.message
        assert "BTCUSDT" in exc.message

    def test_exception_custom_message(self):
        """Test exception with custom message."""
        custom_msg = "Custom error message"
        exc = DuplicateOrderException("test_id", "BTCUSDT", message=custom_msg)

        assert exc.message == custom_msg
        assert str(exc) == custom_msg

    def test_exception_raised(self):
        """Test that exception can be raised and caught."""
        with pytest.raises(DuplicateOrderException) as exc_info:
            raise DuplicateOrderException("dup_id", "ETHUSDT")

        assert exc_info.value.client_order_id == "dup_id"
        assert exc_info.value.symbol == "ETHUSDT"


class TestIdempotencyConfig:
    """Test IdempotencyConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = IdempotencyConfig()

        assert config.ttl_seconds == IDEMPOTENCY_TTL_SECONDS  # 24 hours
        assert config.key_prefix == IDEMPOTENCY_KEY_PREFIX
        assert config.id_length == 8

    def test_custom_config(self):
        """Test custom configuration."""
        config = IdempotencyConfig(
            ttl_seconds=3600, key_prefix="custom:prefix", id_length=12
        )

        assert config.ttl_seconds == 3600
        assert config.key_prefix == "custom:prefix"
        assert config.id_length == 12


class TestIdempotencyStoreLocal:
    """Test IdempotencyStore with local fallback (no Redis)."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        store = IdempotencyStore(redis_client=None)
        yield store
        store.clear_local_store()

    @pytest.mark.asyncio
    async def test_check_duplicate_not_exists(self, store):
        """Test checking for non-existent order."""
        is_dup = await store.check_duplicate("BTCUSDT", "test_id_123")
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_mark_submitted(self, store):
        """Test marking order as submitted."""
        result = await store.mark_submitted("BTCUSDT", "test_id_123")
        assert result is True

        # Now check duplicate
        is_dup = await store.check_duplicate("BTCUSDT", "test_id_123")
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, store):
        """Test that duplicates are detected."""
        # First submission
        await store.mark_submitted("BTCUSDT", "order_1")

        # Check duplicate
        is_dup = await store.check_duplicate("BTCUSDT", "order_1")
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_per_token_isolation(self, store):
        """Test that different tokens are isolated."""
        # Submit for BTC
        await store.mark_submitted("BTCUSDT", "shared_id")

        # Check for ETH - should NOT be duplicate
        is_dup = await store.check_duplicate("ETHUSDT", "shared_id")
        assert is_dup is False

        # Check for BTC - should be duplicate
        is_dup = await store.check_duplicate("BTCUSDT", "shared_id")
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_validate_and_mark_success(self, store):
        """Test validate_and_mark for new order."""
        # Should not raise
        await store.validate_and_mark("BTCUSDT", "new_order_123")

        # Verify it was marked
        is_dup = await store.check_duplicate("BTCUSDT", "new_order_123")
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_validate_and_mark_duplicate(self, store):
        """Test validate_and_mark raises on duplicate."""
        await store.mark_submitted("BTCUSDT", "dup_order")

        with pytest.raises(DuplicateOrderException) as exc_info:
            await store.validate_and_mark("BTCUSDT", "dup_order")

        assert exc_info.value.client_order_id == "dup_order"
        assert exc_info.value.symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_remove_order(self, store):
        """Test removing an order from store."""
        await store.mark_submitted("BTCUSDT", "removable_order")

        # Verify it exists
        assert await store.check_duplicate("BTCUSDT", "removable_order") is True

        # Remove it
        result = await store.remove("BTCUSDT", "removable_order")
        assert result is True

        # Verify it's gone
        assert await store.check_duplicate("BTCUSDT", "removable_order") is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_order(self, store):
        """Test removing an order that doesn't exist."""
        result = await store.remove("BTCUSDT", "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_local_store(self, store):
        """Test clearing the local store."""
        await store.mark_submitted("BTCUSDT", "order_1")
        await store.mark_submitted("ETHUSDT", "order_2")

        store.clear_local_store()

        # Both should be gone
        assert await store.check_duplicate("BTCUSDT", "order_1") is False
        assert await store.check_duplicate("ETHUSDT", "order_2") is False

    @pytest.mark.asyncio
    async def test_custom_ttl(self, store):
        """Test that custom TTL is accepted."""
        result = await store.mark_submitted(
            "BTCUSDT", "custom_ttl_order", ttl_seconds=60
        )
        assert result is True


class TestIdempotencyStoreWithRedis:
    """Test IdempotencyStore with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.exists = AsyncMock(return_value=0)
        return redis

    @pytest.fixture
    def store(self, mock_redis):
        """Create store with mock Redis."""
        return IdempotencyStore(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_check_duplicate_with_redis(self, store, mock_redis):
        """Test duplicate check uses Redis."""
        mock_redis.exists.return_value = 0

        is_dup = await store.check_duplicate("BTCUSDT", "test_id")

        assert is_dup is False
        mock_redis.exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_duplicate_redis_returns_exists(self, store, mock_redis):
        """Test duplicate detection when Redis returns exists."""
        mock_redis.exists.return_value = 1

        is_dup = await store.check_duplicate("BTCUSDT", "dup_id")

        assert is_dup is True

    @pytest.mark.asyncio
    async def test_mark_submitted_with_redis(self, store, mock_redis):
        """Test marking order uses Redis SETEX."""
        await store.mark_submitted("BTCUSDT", "test_id")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == IDEMPOTENCY_TTL_SECONDS  # TTL

    @pytest.mark.asyncio
    async def test_mark_submitted_custom_ttl(self, store, mock_redis):
        """Test custom TTL is passed to Redis."""
        await store.mark_submitted("BTCUSDT", "test_id", ttl_seconds=3600)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600

    @pytest.mark.asyncio
    async def test_remove_with_redis(self, store, mock_redis):
        """Test removing order uses Redis DEL."""
        result = await store.remove("BTCUSDT", "test_id")

        assert result is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_fallback_to_local(self, store, mock_redis):
        """Test fallback to local store on Redis failure."""
        mock_redis.exists.side_effect = Exception("Redis connection failed")

        # Should fallback to local store (returns False = not duplicate)
        is_dup = await store.check_duplicate("BTCUSDT", "test_id")
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_redis_setex_failure_fallback(self, store, mock_redis):
        """Test fallback when Redis SETEX fails."""
        mock_redis.setex.side_effect = Exception("Redis write failed")

        # Should still succeed via local fallback
        result = await store.mark_submitted("BTCUSDT", "test_id")
        assert result is True


class TestIdempotencyStoreConcurrency:
    """Test concurrent access to idempotency store."""

    @pytest.mark.asyncio
    async def test_concurrent_mark_submitted(self):
        """Test concurrent submissions don't corrupt state."""
        store = IdempotencyStore(redis_client=None)

        # Submit many orders concurrently
        tasks = [store.mark_submitted("BTCUSDT", f"order_{i}") for i in range(100)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)

        # All should be marked
        for i in range(100):
            assert await store.check_duplicate("BTCUSDT", f"order_{i}") is True

        store.clear_local_store()


class TestDefaultStoreSingleton:
    """Test default store singleton pattern."""

    def test_get_default_store_creates_singleton(self):
        """Test that get_default_store returns the same instance."""
        reset_default_store()

        store1 = get_default_store()
        store2 = get_default_store()

        assert store1 is store2

    def test_reset_default_store(self):
        """Test resetting the default store."""
        store1 = get_default_store()
        reset_default_store()
        store2 = get_default_store()

        assert store1 is not store2

    def test_default_store_with_redis(self):
        """Test creating default store with Redis client."""
        reset_default_store()
        mock_redis = AsyncMock()

        store = get_default_store(redis_client=mock_redis)
        assert store.redis is mock_redis


class TestIdempotencyConstants:
    """Test module constants."""

    def test_ttl_value(self):
        """Test that TTL is 24 hours."""
        assert IDEMPOTENCY_TTL_SECONDS == 86400  # 24 * 60 * 60

    def test_key_prefix(self):
        """Test key prefix value."""
        assert IDEMPOTENCY_KEY_PREFIX == "order:idempotency"


class TestIntegrationScenarios:
    """Integration-style tests for common scenarios."""

    @pytest.mark.asyncio
    async def test_order_submission_flow(self):
        """Test complete order submission flow."""
        store = IdempotencyStore(redis_client=None)

        # Generate client order ID
        symbol = "BTCUSDT"
        client_id = generate_client_order_id(symbol)

        # Validate and mark
        await store.validate_and_mark(symbol, client_id)

        # Attempting to submit again should fail
        with pytest.raises(DuplicateOrderException):
            await store.validate_and_mark(symbol, client_id)

        # But a new ID should work
        client_id_2 = generate_client_order_id(symbol)
        await store.validate_and_mark(symbol, client_id_2)

        store.clear_local_store()

    @pytest.mark.asyncio
    async def test_multiple_symbols_same_id(self):
        """Test that same ID can be used for different symbols."""
        store = IdempotencyStore(redis_client=None)

        shared_id = "shared_client_id"

        # Submit for BTC
        await store.mark_submitted("BTCUSDT", shared_id)

        # Should be able to submit for ETH with same ID
        is_dup = await store.check_duplicate("ETHUSDT", shared_id)
        assert is_dup is False

        await store.mark_submitted("ETHUSDT", shared_id)

        # Now both should be marked
        assert await store.check_duplicate("BTCUSDT", shared_id) is True
        assert await store.check_duplicate("ETHUSDT", shared_id) is True

        store.clear_local_store()

    @pytest.mark.asyncio
    async def test_failed_order_retry(self):
        """Test that failed orders can be retried after removal."""
        store = IdempotencyStore(redis_client=None)

        client_id = "retry_test_id"
        symbol = "BTCUSDT"

        # Mark as submitted (simulating a submission)
        await store.mark_submitted(symbol, client_id)

        # Order "fails" - remove from store
        await store.remove(symbol, client_id)

        # Can now resubmit
        is_dup = await store.check_duplicate(symbol, client_id)
        assert is_dup is False

        await store.mark_submitted(symbol, client_id)

        store.clear_local_store()


class TestRandomComponent:
    """Test random component properties."""

    def test_random_alphanumeric(self):
        """Test that random component is alphanumeric."""
        client_id = generate_client_order_id("BTCUSDT")
        random_part = client_id.split("_")[2]

        assert re.match(r"^[a-z0-9]+$", random_part)

    def test_random_length_varies(self):
        """Test different random lengths."""
        for length in [4, 8, 12, 16]:
            client_id = generate_client_order_id("BTCUSDT", id_length=length)
            random_part = client_id.split("_")[2]
            assert len(random_part) == length

    def test_random_entropy(self):
        """Test that random component has sufficient entropy."""
        # Generate many IDs and check for collisions
        ids = [generate_client_order_id("BTCUSDT") for _ in range(1000)]
        random_parts = [id.split("_")[2] for id in ids]

        # Should have very few collisions with 8 chars of base36
        unique_randoms = len(set(random_parts))
        assert unique_randoms >= 995  # Allow very few collisions
