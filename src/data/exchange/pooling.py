"""
Connection pooling for exchange data connectors.

Provides connection pool management for efficient resource utilization
when connecting to exchange APIs.
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
import time

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Configuration for connection pool."""

    max_connections: int = 10
    min_connections: int = 2
    connection_timeout: float = 30.0
    idle_timeout: float = 300.0
    max_retries: int = 3
    retry_delay: float = 1.0


class ConnectionPool:
    """Generic connection pool for exchange connectors."""

    def __init__(self, config: Optional[PoolConfig] = None):
        """
        Initialize connection pool.

        Args:
            config: Pool configuration
        """
        self.config = config or PoolConfig()
        self._connections: asyncio.Queue = asyncio.Queue()
        self._in_use: set = set()
        self._lock = asyncio.Lock()
        self._total_connections: int = 0
        self._closed: bool = False
        self._connection_factory: Optional[callable] = None

    def set_connection_factory(self, factory: callable) -> None:
        """Set the factory function for creating connections."""
        self._connection_factory = factory

    async def initialize(self) -> None:
        """Initialize the pool with minimum connections."""
        if self._connection_factory is None:
            raise ValueError("Connection factory not set")

        async with self._lock:
            for _ in range(self.config.min_connections):
                try:
                    conn = await self._connection_factory()
                    await self._connections.put(conn)
                    self._total_connections += 1
                except Exception as e:
                    logger.error(f"Failed to create initial connection: {e}")

    async def acquire(self) -> Any:
        """
        Acquire a connection from the pool.

        Returns:
            Connection object

        Raises:
            RuntimeError: If pool is closed or max connections reached
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        async with self._lock:
            # Try to get from pool first
            if not self._connections.empty():
                conn = await self._connections.get()
                self._in_use.add(id(conn))
                return conn

            # Create new connection if under limit
            if self._total_connections < self.config.max_connections:
                if self._connection_factory:
                    conn = await self._connection_factory()
                    self._total_connections += 1
                    self._in_use.add(id(conn))
                    return conn

            raise RuntimeError("Max connections reached")

    async def release(self, conn: Any) -> None:
        """
        Release a connection back to the pool.

        Args:
            conn: Connection to release
        """
        conn_id = id(conn)

        async with self._lock:
            if conn_id in self._in_use:
                self._in_use.remove(conn_id)

                if not self._closed:
                    await self._connections.put(conn)

    @asynccontextmanager
    async def connection(self):
        """Context manager for acquiring and releasing connections."""
        conn = None
        try:
            conn = await self.acquire()
            yield conn
        finally:
            if conn is not None:
                await self.release(conn)

    async def close(self) -> None:
        """Close all connections in the pool."""
        async with self._lock:
            self._closed = True

            # Close all available connections
            while not self._connections.empty():
                try:
                    conn = await self._connections.get()
                    if hasattr(conn, "close"):
                        await conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")

            self._total_connections = 0
            self._in_use.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "total_connections": self._total_connections,
            "available_connections": self._connections.qsize(),
            "in_use_connections": len(self._in_use),
            "max_connections": self.config.max_connections,
            "closed": self._closed,
        }


class PooledConnector:
    """Mixin for connectors that use connection pooling."""

    _pools: Dict[str, ConnectionPool] = {}

    @classmethod
    def get_pool(
        cls, exchange: str, config: Optional[PoolConfig] = None
    ) -> ConnectionPool:
        """
        Get or create connection pool for an exchange.

        Args:
            exchange: Exchange name
            config: Pool configuration

        Returns:
            Connection pool
        """
        if exchange not in cls._pools:
            cls._pools[exchange] = ConnectionPool(config)
        return cls._pools[exchange]

    @classmethod
    async def close_all_pools(cls) -> None:
        """Close all connection pools."""
        for pool in cls._pools.values():
            await pool.close()
        cls._pools.clear()

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all pools."""
        return {exchange: pool.get_stats() for exchange, pool in cls._pools.items()}


class RateLimiter:
    """Rate limiter for API calls."""

    def __init__(self, calls_per_second: float = 10.0):
        """
        Initialize rate limiter.

        Args:
            calls_per_second: Maximum calls per second
        """
        self.min_interval = 1.0 / calls_per_second
        self._last_call_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a call."""
        async with self._lock:
            if self._last_call_time is not None:
                elapsed = time.time() - self._last_call_time
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)

            self._last_call_time = time.time()


__all__ = [
    "PoolConfig",
    "ConnectionPool",
    "PooledConnector",
    "RateLimiter",
]
