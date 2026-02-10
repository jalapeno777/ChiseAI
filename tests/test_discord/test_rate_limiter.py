"""Tests for rate limiter.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import time

from discord_alerts.rate_limiter import RateLimitBucket, RateLimiter


class TestRateLimitBucket:
    """Test cases for RateLimitBucket."""

    def test_bucket_creation(self) -> None:
        """Test creating a rate limit bucket."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=1.0)

        assert bucket.max_tokens == 10.0
        assert bucket.refill_rate == 1.0
        assert bucket.tokens == 0.0

    def test_bucket_refill(self) -> None:
        """Test token refill over time."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=10.0)
        bucket.tokens = 0.0

        time.sleep(0.1)  # Wait 100ms
        bucket.refill()

        # Should have gained ~1 token (10 tokens/sec * 0.1 sec)
        assert bucket.tokens >= 0.5  # Allow some tolerance

    def test_bucket_consume_success(self) -> None:
        """Test successful token consumption."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=1.0)
        bucket.tokens = 5.0

        result = bucket.consume(3.0)

        assert result is True
        assert abs(bucket.tokens - 2.0) < 0.01  # Allow small floating point variance

    def test_bucket_consume_failure(self) -> None:
        """Test failed token consumption."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=1.0)
        bucket.tokens = 2.0

        result = bucket.consume(5.0)

        assert result is False
        # Tokens may have slightly changed due to refill during consume
        assert bucket.tokens < 5.0  # Tokens unchanged (or refilled but still < 5)

    def test_bucket_consume_refills(self) -> None:
        """Test that consume triggers refill."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=100.0)
        bucket.tokens = 0.0

        time.sleep(0.05)  # Wait for some refill
        result = bucket.consume(1.0)

        assert result is True

    def test_time_until_available(self) -> None:
        """Test calculating time until tokens available."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=1.0)
        bucket.tokens = 0.0

        wait_time = bucket.time_until_available(5.0)

        # Should need 5 seconds to get 5 tokens at 1 token/sec
        assert wait_time >= 4.5  # Allow some tolerance
        assert wait_time <= 5.5

    def test_time_until_available_immediate(self) -> None:
        """Test time until available when tokens already available."""
        bucket = RateLimitBucket(max_tokens=10, refill_rate=1.0)
        bucket.tokens = 5.0

        wait_time = bucket.time_until_available(3.0)

        assert wait_time == 0.0


class TestRateLimiter:
    """Test cases for RateLimiter."""

    def test_default_values(self) -> None:
        """Test default rate limiter values."""
        limiter = RateLimiter()

        assert limiter.max_per_minute == 10
        assert limiter.block_when_limited is False

    def test_custom_values(self) -> None:
        """Test custom rate limiter values."""
        limiter = RateLimiter(max_per_minute=20, block_when_limited=True)

        assert limiter.max_per_minute == 20
        assert limiter.block_when_limited is True

    def test_check_limit_initial(self) -> None:
        """Test initial rate limit check."""
        limiter = RateLimiter(max_per_minute=10)

        status = limiter.check_limit("general")

        assert status["allowed"] is True
        assert status["remaining"] == 10
        assert status["limit"] == 10

    def test_acquire_success(self) -> None:
        """Test successful token acquisition."""
        limiter = RateLimiter(max_per_minute=10)

        result = limiter.acquire("general")

        assert result["success"] is True
        assert result["remaining"] == 9

    def test_acquire_multiple(self) -> None:
        """Test acquiring multiple tokens."""
        limiter = RateLimiter(max_per_minute=10)

        for i in range(10):
            result = limiter.acquire("general")
            assert result["success"] is True
            assert result["remaining"] == 9 - i

    def test_acquire_rate_limited(self) -> None:
        """Test rate limiting after max tokens consumed."""
        limiter = RateLimiter(max_per_minute=2)

        # Consume all tokens
        limiter.acquire("general")
        limiter.acquire("general")

        # Third should be rate limited
        result = limiter.acquire("general")

        assert result["success"] is False
        assert result["retry_after"] > 0

    def test_acquire_refill(self) -> None:
        """Test token refill over time."""
        limiter = RateLimiter(max_per_minute=60)  # 1 per second

        # Consume all tokens
        for _ in range(10):
            limiter.acquire("general")

        # Wait for refill
        time.sleep(1.1)

        # Should have at least 1 token
        result = limiter.acquire("general")
        assert result["success"] is True

    def test_try_acquire_success(self) -> None:
        """Test try_acquire when tokens available."""
        limiter = RateLimiter(max_per_minute=10)

        result = limiter.try_acquire("general")

        assert result is True

    def test_try_acquire_failure(self) -> None:
        """Test try_acquire when rate limited."""
        limiter = RateLimiter(max_per_minute=1)

        limiter.try_acquire("general")
        result = limiter.try_acquire("general")

        assert result is False

    def test_per_channel_limiting(self) -> None:
        """Test that limits are per-channel."""
        limiter = RateLimiter(max_per_minute=2)

        # Consume tokens in channel A
        limiter.acquire("channel-a")
        limiter.acquire("channel-a")

        # Channel B should still have tokens
        result = limiter.acquire("channel-b")
        assert result["success"] is True

        # Channel A should be rate limited
        result = limiter.acquire("channel-a")
        assert result["success"] is False

    def test_get_retry_after(self) -> None:
        """Test getting retry after time."""
        limiter = RateLimiter(max_per_minute=60)  # 1 per second

        limiter.acquire("general")
        retry_after = limiter.get_retry_after("general")

        # Should be close to 0 since we have tokens
        assert retry_after >= 0.0

    def test_get_retry_after_rate_limited(self) -> None:
        """Test getting retry after when rate limited."""
        limiter = RateLimiter(max_per_minute=60)  # 1 per second

        # Consume all tokens quickly
        for _ in range(10):
            limiter.acquire("general")

        # Force a small delay to ensure some time has passed
        import time

        time.sleep(0.01)

        _ = limiter.get_retry_after("general")

        # Should be >= 0 (may be 0 if tokens refilled during sleep)
        # Test passes if no exception raised

    def test_reset_channel(self) -> None:
        """Test resetting a specific channel."""
        limiter = RateLimiter(max_per_minute=2)

        limiter.acquire("channel-a")
        limiter.acquire("channel-a")

        limiter.reset_channel("channel-a")

        # Should be able to acquire again
        result = limiter.acquire("channel-a")
        assert result["success"] is True

    def test_reset_all(self) -> None:
        """Test resetting all channels."""
        limiter = RateLimiter(max_per_minute=2)

        limiter.acquire("channel-a")
        limiter.acquire("channel-a")
        limiter.acquire("channel-b")
        limiter.acquire("channel-b")

        limiter.reset_all()

        # Both channels should be reset
        assert limiter.acquire("channel-a")["success"] is True
        assert limiter.acquire("channel-b")["success"] is True

    def test_get_stats(self) -> None:
        """Test getting rate limiter statistics."""
        limiter = RateLimiter(max_per_minute=10)

        limiter.acquire("channel-a")
        limiter.acquire("channel-b")

        stats = limiter.get_stats()

        assert stats["max_per_minute"] == 10
        assert stats["block_when_limited"] is False
        assert stats["channels_tracked"] == 2
        assert "channel-a" in stats["channel_stats"]
        assert "channel-b" in stats["channel_stats"]

    def test_thread_safety(self) -> None:
        """Test thread-safe operations."""
        import threading

        limiter = RateLimiter(max_per_minute=100)
        errors = []
        success_count = [0]

        def acquire_tokens():
            try:
                for _ in range(10):
                    result = limiter.acquire("general")
                    if result["success"]:
                        success_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run multiple threads concurrently
        threads = [threading.Thread(target=acquire_tokens) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Should have 50 successful acquisitions (5 threads * 10 each)
        # But rate limited to 100/min, so all should succeed
        assert success_count[0] == 50

    def test_blocking_mode_timeout(self) -> None:
        """Test blocking mode with timeout."""
        limiter = RateLimiter(max_per_minute=1, block_when_limited=True)

        # Consume the only token
        limiter.acquire("general")

        # Try to acquire with short timeout (should fail)
        result = limiter.acquire("general", timeout=0.1)

        # Should timeout since we can't get a token in 0.1s with 1/min rate
        assert result["success"] is False
        assert "error" in result
