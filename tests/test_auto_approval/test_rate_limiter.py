"""Tests for auto-approval rate limiter."""

from unittest.mock import AsyncMock

import pytest
from src.autonomous_git.auto_approval.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter."""

    def test_init_default_values(self):
        """Test rate limiter initializes with default values."""
        limiter = RateLimiter()

        assert limiter.max_per_hour == 10
        assert limiter.max_consecutive == 3
        assert limiter.consecutive_pause_duration == 300
        assert limiter.redis is None

    def test_init_custom_values(self):
        """Test rate limiter initializes with custom values."""
        limiter = RateLimiter(
            max_per_hour=20,
            max_consecutive=5,
            consecutive_pause_duration=600,
        )

        assert limiter.max_per_hour == 20
        assert limiter.max_consecutive == 5
        assert limiter.consecutive_pause_duration == 600

    @pytest.mark.asyncio
    async def test_check_limits_memory_under_limit(self):
        """Test check_limits passes when under limit (in-memory)."""
        limiter = RateLimiter(max_per_hour=10, max_consecutive=3)

        # First few checks should pass
        for i in range(5):
            result = await limiter.check_limits()
            assert result is True, f"Check {i + 1} should pass"

    @pytest.mark.asyncio
    async def test_check_limits_memory_hourly_exceeded(self):
        """Test check_limits fails when hourly limit exceeded."""
        limiter = RateLimiter(max_per_hour=3, max_consecutive=10)

        # First 3 should pass
        for i in range(3):
            result = await limiter.check_limits()
            assert result is True, f"Check {i + 1} should pass"

        # 4th should fail (exceeds hourly limit)
        result = await limiter.check_limits()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_limits_redis_success(self):
        """Test check_limits with Redis (mocked)."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1  # First increment
        mock_redis.expire = AsyncMock()

        limiter = RateLimiter(
            max_per_hour=10,
            max_consecutive=3,
            redis_client=mock_redis,
        )

        result = await limiter.check_limits()

        assert result is True
        mock_redis.incr.assert_called()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_limits_redis_hourly_exceeded(self):
        """Test check_limits fails when Redis hourly limit exceeded."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 11  # Exceeds limit of 10
        mock_redis.decr = AsyncMock()

        limiter = RateLimiter(
            max_per_hour=10,
            max_consecutive=3,
            redis_client=mock_redis,
        )

        result = await limiter.check_limits()

        assert result is False
        mock_redis.decr.assert_called_once()  # Should decrement after rejection

    @pytest.mark.asyncio
    async def test_check_limits_redis_consecutive_pause(self):
        """Test consecutive limit triggers pause."""
        mock_redis = AsyncMock()
        # First call for hourly, second for consecutive
        mock_redis.incr.side_effect = [1, 4]  # 4 exceeds max_consecutive of 3
        mock_redis.expire = AsyncMock()
        mock_redis.set = AsyncMock()

        limiter = RateLimiter(
            max_per_hour=10,
            max_consecutive=3,
            consecutive_pause_duration=0,  # No sleep for faster tests
            redis_client=mock_redis,
        )

        result = await limiter.check_limits()

        assert result is True  # Still returns True but resets consecutive
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_success(self):
        """Test recording successful approval."""
        mock_redis = AsyncMock()
        limiter = RateLimiter(redis_client=mock_redis)

        await limiter.record_success()

        mock_redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_consecutive(self):
        """Test resetting consecutive count."""
        mock_redis = AsyncMock()
        limiter = RateLimiter(redis_client=mock_redis)

        await limiter.reset_consecutive()

        mock_redis.set.assert_called_once()
        assert limiter._consecutive_count == 0

    @pytest.mark.asyncio
    async def test_get_stats_memory(self):
        """Test getting stats with in-memory storage."""
        limiter = RateLimiter(max_per_hour=10, max_consecutive=3)
        limiter._hourly_count = 5
        limiter._consecutive_count = 2

        stats = await limiter.get_stats()

        assert stats["hourly_count"] == 5
        assert stats["hourly_limit"] == 10
        assert stats["consecutive_count"] == 2
        assert stats["consecutive_limit"] == 3
        assert "current_hour" in stats

    @pytest.mark.asyncio
    async def test_get_stats_redis(self):
        """Test getting stats with Redis."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ["7", "2"]  # hourly, consecutive
        mock_redis.keys = AsyncMock(return_value=["key:2025022110"])

        limiter = RateLimiter(
            max_per_hour=10,
            max_consecutive=3,
            redis_client=mock_redis,
        )

        stats = await limiter.get_stats()

        assert stats["hourly_count"] == 7
        assert stats["consecutive_count"] == 2

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self):
        """Test fallback to in-memory when Redis fails."""
        mock_redis = AsyncMock()
        mock_redis.incr.side_effect = Exception("Redis connection failed")

        limiter = RateLimiter(
            max_per_hour=10,
            max_consecutive=3,
            redis_client=mock_redis,
        )

        # Should not raise, should use in-memory
        result = await limiter.check_limits()
        assert result is True
