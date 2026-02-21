"""Tests for connection pooling module.

Tests for ST-NS-026: Connection Pooling for Exchange APIs
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from data.exchange.pooling import (
    AdaptiveRateLimiter,
    CompositeRateLimiter,
    ExchangeConnectionPool,
    PoolHealthMonitor,
    PoolMetrics,
    PooledBitgetClient,
    PooledBybitClient,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
)


class TestPoolMetrics:
    """Tests for PoolMetrics dataclass."""

    def test_initial_state(self):
        """Test initial metrics state."""
        metrics = PoolMetrics()
        assert metrics.pool_size == 0
        assert metrics.active_connections == 0
        assert metrics.idle_connections == 0
        assert metrics.total_requests == 0
        assert metrics.success_rate == 100.0
        assert metrics.pool_utilization == 0.0

    def test_record_response_time(self):
        """Test recording response times."""
        metrics = PoolMetrics()

        metrics.record_response_time(100.0)
        metrics.record_response_time(200.0)

        assert metrics.avg_response_time_ms == 150.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = PoolMetrics()

        metrics.total_requests = 100
        metrics.successful_requests = 95
        metrics.failed_requests = 5

        assert metrics.success_rate == 95.0

    def test_pool_utilization(self):
        """Test pool utilization calculation."""
        metrics = PoolMetrics(pool_size=10)
        metrics.active_connections = 7

        assert metrics.pool_utilization == 70.0


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_token(self):
        """Test acquiring a token."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=10)

        wait_time = await limiter.acquire()

        # Should not wait (burst available)
        assert wait_time < 100  # Less than 100ms
        assert limiter.tokens == 9.0

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting occurs."""
        limiter = TokenBucketRateLimiter(
            requests_per_minute=600,  # 10 per second
            burst_size=1,
        )

        # First acquire should be instant
        await limiter.acquire()

        # Second acquire should wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should have waited at least 50ms (half of 100ms interval)
        assert elapsed >= 0.05

    def test_try_acquire(self):
        """Test non-blocking acquire."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=1)

        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False

    def test_get_metrics(self):
        """Test metrics retrieval."""
        limiter = TokenBucketRateLimiter(requests_per_minute=120, burst_size=10)

        metrics = limiter.get_metrics()

        assert metrics["requests_per_minute"] == 120
        assert metrics["burst_size"] == 10
        assert "current_tokens" in metrics


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.mark.asyncio
    async def test_allow_request(self):
        """Test allowing requests."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)

        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is False

    @pytest.mark.asyncio
    async def test_window_expiration(self):
        """Test that old requests expire from window."""
        limiter = SlidingWindowRateLimiter(
            max_requests=1,
            window_seconds=0.1,  # 100ms window
        )

        assert await limiter.allow_request() is True

        # Wait for window to expire
        await asyncio.sleep(0.15)

        # Should be allowed again
        assert await limiter.allow_request() is True

    def test_get_metrics(self):
        """Test metrics retrieval."""
        limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60.0)

        metrics = limiter.get_metrics()

        assert metrics["max_requests"] == 100
        assert metrics["window_seconds"] == 60.0


class TestAdaptiveRateLimiter:
    """Tests for AdaptiveRateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire(self):
        """Test acquiring permission."""
        limiter = AdaptiveRateLimiter(initial_rpm=60, min_rpm=30, max_rpm=120)

        wait_time = await limiter.acquire()
        assert wait_time < 100  # Should be instant with burst

    def test_report_rate_limit(self):
        """Test reporting rate limit hits."""
        limiter = AdaptiveRateLimiter(
            initial_rpm=120, min_rpm=30, max_rpm=120, backoff_factor=0.5
        )

        initial_rpm = limiter.current_rpm
        limiter.report_rate_limit()

        assert limiter.current_rpm < initial_rpm
        assert limiter.current_rpm >= 30  # Min RPM

    def test_get_metrics(self):
        """Test metrics include adaptive info."""
        limiter = AdaptiveRateLimiter(initial_rpm=60, min_rpm=30, max_rpm=120)

        metrics = limiter.get_metrics()

        assert metrics["current_rpm"] == 60
        assert metrics["min_rpm"] == 30
        assert metrics["max_rpm"] == 120
        assert metrics["adaptive_enabled"] is True


class TestCompositeRateLimiter:
    """Tests for CompositeRateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_all(self):
        """Test acquiring from all limiters."""
        limiter1 = TokenBucketRateLimiter(requests_per_minute=60, burst_size=10)
        limiter2 = TokenBucketRateLimiter(requests_per_minute=30, burst_size=5)

        composite = CompositeRateLimiter([limiter1, limiter2])

        wait_time = await composite.acquire()

        # Should acquire from both
        assert limiter1.tokens == 9.0
        assert limiter2.tokens == 4.0

    def test_get_metrics(self):
        """Test metrics from all limiters."""
        limiter1 = TokenBucketRateLimiter(requests_per_minute=60, burst_size=10)
        limiter2 = TokenBucketRateLimiter(requests_per_minute=30, burst_size=5)

        composite = CompositeRateLimiter([limiter1, limiter2])

        metrics = composite.get_metrics()

        assert "limiter_0" in metrics
        assert "limiter_1" in metrics


class TestExchangeConnectionPool:
    """Tests for ExchangeConnectionPool."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test pool initialization."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=5, max_connections=10)

        await pool.initialize()

        assert pool._initialized is True
        assert pool._pool.qsize() == 5

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_get_connection(self):
        """Test getting a connection from pool."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=2, max_connections=5)

        await pool.initialize()

        async with pool.get_connection() as conn:
            assert conn is not None
            assert conn.exchange == "test"

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_pool_metrics(self):
        """Test pool metrics tracking."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=2, max_connections=5)

        await pool.initialize()

        metrics = pool.get_metrics()

        assert metrics.pool_size == 2
        assert metrics.idle_connections == 2
        assert metrics.active_connections == 0

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check functionality."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=1, max_connections=2)

        await pool.initialize()

        health = await pool.health_check()

        assert "healthy" in health
        assert "pool_size" in health

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with ExchangeConnectionPool(
            exchange="test", pool_size=1, max_connections=2
        ) as pool:
            assert pool._initialized is True
            metrics = pool.get_metrics()
            assert metrics.pool_size == 1


class TestPoolHealthMonitor:
    """Tests for PoolHealthMonitor."""

    @pytest.mark.asyncio
    async def test_add_pool(self):
        """Test adding a pool to monitor."""
        monitor = PoolHealthMonitor()
        pool = ExchangeConnectionPool(exchange="test", pool_size=1)

        monitor.add_pool("test_pool", pool)

        assert "test_pool" in monitor._pools
        assert "test_pool" in monitor._history

    @pytest.mark.asyncio
    async def test_check_health(self):
        """Test health check."""
        monitor = PoolHealthMonitor()
        pool = ExchangeConnectionPool(exchange="test", pool_size=1)

        await pool.initialize()
        monitor.add_pool("test_pool", pool)

        results = await monitor.check_health()

        assert "test_pool" in results
        assert hasattr(results["test_pool"], "healthy")

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_alert_callback(self):
        """Test alert callback registration."""
        monitor = PoolHealthMonitor()
        callback = MagicMock()

        monitor.on_alert(callback)

        assert callback in monitor._alert_callbacks


class TestPooledBybitClient:
    """Tests for PooledBybitClient."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test client initialization."""
        client = PooledBybitClient(api_key="test_key", api_secret="test_secret")

        assert client.exchange == "bybit"
        assert client.api_key == "test_key"
        assert client.base_url == PooledBybitClient.DEFAULT_BASE_URL

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with PooledBybitClient() as client:
            assert client._pool._initialized is True

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test metrics retrieval."""
        async with PooledBybitClient() as client:
            metrics = client.get_metrics()
            assert isinstance(metrics, PoolMetrics)


class TestPooledBitgetClient:
    """Tests for PooledBitgetClient."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test client initialization."""
        client = PooledBitgetClient(
            api_key="test_key", api_secret="test_secret", passphrase="test_pass"
        )

        assert client.exchange == "bitget"
        assert client.api_key == "test_key"
        assert client.passphrase == "test_pass"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with PooledBitgetClient() as client:
            assert client._pool._initialized is True


class TestRateLimitCompliance:
    """Tests for rate limit compliance."""

    @pytest.mark.asyncio
    async def test_bybit_rate_limit(self):
        """Test Bybit rate limit configuration."""
        client = PooledBybitClient()

        # Bybit should have 120 RPM limit
        assert client._pool.rate_limiter.requests_per_minute == 120
        assert client._pool.rate_limiter.burst_size == 10

    @pytest.mark.asyncio
    async def test_bitget_rate_limit(self):
        """Test Bitget rate limit configuration."""
        client = PooledBitgetClient()

        # Bitget should have 60 RPM limit
        assert client._pool.rate_limiter.requests_per_minute == 60
        assert client._pool.rate_limiter.burst_size == 5


class TestLatencyImprovement:
    """Tests to verify latency improvements."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """Test that connections are reused."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=2, max_connections=5)

        await pool.initialize()

        # Use a connection
        async with pool.get_connection() as conn1:
            pass

        # Get another connection (should be same one returned)
        async with pool.get_connection() as conn2:
            pass

        # Both should be from the pool (reused)
        metrics = pool.get_metrics()
        assert metrics.total_requests >= 2

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_pool_wait_time_tracking(self):
        """Test that pool tracks wait times."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=1, max_connections=1)

        await pool.initialize()

        # Make a request to populate metrics
        async with pool.get_connection():
            pass

        metrics = pool.get_metrics()
        # Wait time should be tracked
        assert hasattr(metrics, "total_wait_time_ms")

        await pool.close_all()


class TestBenchmark:
    """Benchmark tests for latency verification."""

    @pytest.mark.asyncio
    async def test_simulated_latency(self):
        """Simulate latency benchmark.

        This test verifies the pool can handle requests efficiently.
        Real latency tests require actual API access.
        """
        pool = ExchangeConnectionPool(
            exchange="test",
            pool_size=5,
            max_connections=10,
            rate_limit={
                "requests_per_minute": 6000,
                "burst_size": 100,
            },  # High limit for testing
        )

        await pool.initialize()

        # Simulate multiple requests
        times = []
        for _ in range(10):
            start = time.monotonic()
            async with pool.get_connection():
                # No sleep - just measure connection acquisition overhead
                pass
            elapsed = (time.monotonic() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # Should be fast with connection pooling
        # Target: <20ms average for connection acquisition (no rate limiting)
        assert avg_time < 20, f"Average latency {avg_time}ms exceeds 20ms threshold"

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        pool = ExchangeConnectionPool(exchange="test", pool_size=5, max_connections=10)

        await pool.initialize()

        async def make_request():
            async with pool.get_connection():
                await asyncio.sleep(0.01)
                return True

        # Make 20 concurrent requests
        tasks = [make_request() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        assert all(results)

        metrics = pool.get_metrics()
        assert metrics.total_requests == 20

        await pool.close_all()
