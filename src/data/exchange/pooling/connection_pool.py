"""Connection pooling for exchange APIs.

Provides connection pool management for Bybit and Bitget APIs
with rate limiting, health monitoring, and metrics collection.

For ST-NS-026: Connection Pooling for Exchange APIs
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for connection pool health and performance.

    Attributes:
        pool_size: Total number of connections in pool
        active_connections: Currently in-use connections
        idle_connections: Available connections
        total_requests: Total requests processed
        successful_requests: Successful requests
        failed_requests: Failed requests
        avg_response_time_ms: Average response time in milliseconds
        rate_limit_hits: Number of rate limit responses received
        total_wait_time_ms: Total time waiting for connections
    """

    pool_size: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    rate_limit_hits: int = 0
    total_wait_time_ms: float = 0.0

    # Internal tracking
    _response_times: list[float] = field(default_factory=list, repr=False)
    _wait_times: list[float] = field(default_factory=list, repr=False)

    def record_response_time(self, elapsed_ms: float) -> None:
        """Record a response time measurement."""
        self._response_times.append(elapsed_ms)
        # Keep last 100 measurements for rolling average
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]
        self.avg_response_time_ms = sum(self._response_times) / len(
            self._response_times
        )

    def record_wait_time(self, elapsed_ms: float) -> None:
        """Record a wait time for connection acquisition."""
        self._wait_times.append(elapsed_ms)
        self.total_wait_time_ms = sum(self._wait_times)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def pool_utilization(self) -> float:
        """Calculate pool utilization percentage."""
        if self.pool_size == 0:
            return 0.0
        return (self.active_connections / self.pool_size) * 100


@dataclass(eq=False)
class PooledConnection:
    """A pooled connection wrapper.

    Attributes:
        session: The aiohttp ClientSession
        acquired_at: Timestamp when connection was acquired
        exchange: Exchange name
    """

    session: aiohttp.ClientSession
    acquired_at: float
    exchange: str
    _id: int = field(default_factory=lambda: id(object()), compare=False)

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make an HTTP request using this connection."""
        return await self.session.request(method, url, **kwargs)

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PooledConnection):
            return NotImplemented
        return self._id == other._id


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API requests.

    Implements pre-emptive rate limiting to avoid 429 responses.
    """

    def __init__(self, requests_per_minute: int, burst_size: int | None = None) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst size (defaults to 10% of rate)
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or max(1, requests_per_minute // 10)
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
        self.wait_count = 0

    async def acquire(self) -> float:
        """Acquire a token, waiting if necessary.

        Returns:
            Time waited in milliseconds
        """
        start_time = time.monotonic()

        async with self.lock:
            # Add tokens based on time elapsed
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst_size,
                self.tokens + (elapsed * self.requests_per_minute / 60.0),
            )
            self.last_update = now

            # Wait if no tokens available
            while self.tokens < 1.0:
                self.wait_count += 1
                wait_time = 60.0 / self.requests_per_minute
                await asyncio.sleep(wait_time)

                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + (elapsed * self.requests_per_minute / 60.0),
                )
                self.last_update = now

            self.tokens -= 1.0

        elapsed_ms = (time.monotonic() - start_time) * 1000
        return elapsed_ms

    def get_metrics(self) -> dict[str, Any]:
        """Get rate limiter metrics."""
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "current_tokens": self.tokens,
            "wait_count": self.wait_count,
        }


class ExchangeConnectionPool:
    """Connection pool for exchange API connections.

    Manages a pool of persistent HTTP connections with:
    - Configurable pool size
    - Rate limiting
    - Health monitoring
    - Connection reuse

    Example:
        pool = ExchangeConnectionPool("bybit", pool_size=10)
        async with pool.get_connection() as conn:
            response = await conn.request("GET", "https://api.bybit.com/v5/market/tickers")
    """

    def __init__(
        self,
        exchange: str,
        pool_size: int = 10,
        max_connections: int = 20,
        connection_timeout: int = 30,
        keepalive: bool = True,
        rate_limit: dict[str, int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize connection pool.

        Args:
            exchange: Exchange name (e.g., "bybit", "bitget")
            pool_size: Number of connections to maintain
            max_connections: Maximum connections allowed
            connection_timeout: Connection timeout in seconds
            keepalive: Whether to use keepalive connections
            rate_limit: Rate limit config with "requests_per_minute" and "burst_size"
            headers: Default headers for all connections
        """
        self.exchange = exchange
        self.pool_size = pool_size
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.keepalive = keepalive
        self.headers = headers or {}

        # Rate limiting
        rate_limit = rate_limit or {}
        self.rate_limiter = TokenBucketRateLimiter(
            requests_per_minute=rate_limit.get("requests_per_minute", 60),
            burst_size=rate_limit.get("burst_size", 5),
        )

        # Pool state
        self._pool: asyncio.Queue[PooledConnection] = asyncio.Queue(
            maxsize=max_connections
        )
        self._active: set[PooledConnection] = set()
        self._semaphore = asyncio.Semaphore(max_connections)
        self._metrics = PoolMetrics(pool_size=pool_size)
        self._closed = False
        self._initialized = False

        # Health tracking
        self._last_health_check = 0.0
        self._health_check_interval = 30.0  # seconds

    async def initialize(self) -> None:
        """Initialize the pool with initial connections."""
        if self._initialized:
            return

        logger.info(
            f"Initializing {self.exchange} connection pool (size={self.pool_size})"
        )

        # Create initial connections
        for _ in range(self.pool_size):
            conn = await self._create_connection()
            await self._pool.put(conn)

        self._metrics.idle_connections = self.pool_size
        self._initialized = True
        logger.info(
            f"{self.exchange} pool initialized with {self.pool_size} connections"
        )

    async def _create_connection(self) -> PooledConnection:
        """Create a new pooled connection."""
        timeout = aiohttp.ClientTimeout(total=self.connection_timeout)

        # Configure TCP connector for keepalive
        connector = aiohttp.TCPConnector(
            limit=1,  # One connection per session
            limit_per_host=1,
            enable_cleanup_closed=True,
            force_close=not self.keepalive,
        )

        session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=timeout,
            connector=connector,
        )

        return PooledConnection(
            session=session, acquired_at=0.0, exchange=self.exchange
        )

    def get_connection(self) -> "ConnectionContextManager":
        """Get a connection from the pool.

        Returns:
            ConnectionContextManager for use with 'async with'
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        return ConnectionContextManager(self)

    async def _acquire_connection(self) -> PooledConnection:
        """Acquire a connection from the pool (internal)."""
        start_time = time.monotonic()

        # Apply rate limiting
        wait_time = await self.rate_limiter.acquire()

        # Wait for semaphore (connection slot)
        await self._semaphore.acquire()

        try:
            # Try to get from pool
            try:
                conn = self._pool.get_nowait()
            except asyncio.QueueEmpty:
                # Create new connection if under max
                conn = await self._create_connection()

            conn.acquired_at = time.monotonic()
            self._active.add(conn)

            # Update metrics
            self._metrics.active_connections = len(self._active)
            self._metrics.idle_connections = self._pool.qsize()
            self._metrics.total_requests += 1

            wait_ms = (time.monotonic() - start_time) * 1000
            self._metrics.record_wait_time(wait_ms)

            return conn

        except Exception:
            self._semaphore.release()
            raise

    async def _release_connection(
        self, conn: PooledConnection, healthy: bool = True
    ) -> None:
        """Release a connection back to the pool."""
        self._active.discard(conn)

        if not healthy or self._closed:
            # Close unhealthy connections
            await conn.session.close()
        else:
            # Return to pool
            try:
                self._pool.put_nowait(conn)
            except asyncio.QueueFull:
                # Pool is full, close the connection
                await conn.session.close()

        # Update metrics
        self._metrics.active_connections = len(self._active)
        self._metrics.idle_connections = self._pool.qsize()

        self._semaphore.release()

    def get_metrics(self) -> PoolMetrics:
        """Get current pool metrics."""
        self._metrics.pool_size = self.pool_size
        return self._metrics

    async def close_all(self) -> None:
        """Close all connections in the pool."""
        self._closed = True
        logger.info(f"Closing {self.exchange} connection pool")

        # Close active connections
        for conn in list(self._active):
            await conn.session.close()
        self._active.clear()

        # Close pooled connections
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.session.close()
            except asyncio.QueueEmpty:
                break

        self._metrics.idle_connections = 0
        self._metrics.active_connections = 0
        logger.info(f"{self.exchange} connection pool closed")

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on the pool."""
        now = time.monotonic()

        # Only check periodically
        if now - self._last_health_check < self._health_check_interval:
            return {
                "healthy": True,
                "pool_size": self.pool_size,
                "active": len(self._active),
                "idle": self._pool.qsize(),
                "cached": True,
            }

        self._last_health_check = now

        # Check if we can acquire a connection
        healthy = True
        try:
            async with self.get_connection() as conn:
                # Try a simple request or just verify session is open
                if conn.session.closed:
                    healthy = False
        except Exception as e:
            logger.warning(f"{self.exchange} pool health check failed: {e}")
            healthy = False

        return {
            "healthy": healthy,
            "pool_size": self.pool_size,
            "active": len(self._active),
            "idle": self._pool.qsize(),
            "utilization": self._metrics.pool_utilization,
            "rate_limiter": self.rate_limiter.get_metrics(),
        }

    async def __aenter__(self) -> ExchangeConnectionPool:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close_all()


class ConnectionContextManager:
    """Context manager for pooled connections."""

    def __init__(self, pool: ExchangeConnectionPool) -> None:
        self.pool = pool
        self.conn: PooledConnection | None = None
        self.start_time: float = 0.0

    async def __aenter__(self) -> PooledConnection:
        """Acquire connection."""
        # Ensure pool is initialized
        if not self.pool._initialized:
            await self.pool.initialize()

        self.conn = await self.pool._acquire_connection()
        self.start_time = time.monotonic()
        return self.conn

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Release connection."""
        if self.conn:
            # Record metrics
            elapsed_ms = (time.monotonic() - self.start_time) * 1000
            self.pool._metrics.record_response_time(elapsed_ms)

            if exc_val is None:
                self.pool._metrics.successful_requests += 1
            else:
                self.pool._metrics.failed_requests += 1
                # Check if it's a rate limit error
                if isinstance(exc_val, aiohttp.ClientResponseError):
                    if exc_val.status == 429:
                        self.pool._metrics.rate_limit_hits += 1

            # Release connection
            healthy = exc_val is None
            await self.pool._release_connection(self.conn, healthy)
