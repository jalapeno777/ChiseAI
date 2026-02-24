"""Dashboard caching layer for performance optimization.

Provides Redis-backed caching for frequently accessed dashboard data
to ensure fast load times and reduced database load.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheStats:
    """Statistics for cache performance tracking.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        evictions: Number of cache evictions
        total_requests: Total number of cache requests
        avg_hit_time_ms: Average time for cache hits in milliseconds
        avg_miss_time_ms: Average time for cache misses in milliseconds
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0
    avg_hit_time_ms: float = 0.0
    avg_miss_time_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100

    def record_hit(self, latency_ms: float) -> None:
        """Record a cache hit."""
        self.hits += 1
        self.total_requests += 1
        self._update_avg_hit_time(latency_ms)

    def record_miss(self, latency_ms: float) -> None:
        """Record a cache miss."""
        self.misses += 1
        self.total_requests += 1
        self._update_avg_miss_time(latency_ms)

    def _update_avg_hit_time(self, latency_ms: float) -> None:
        """Update average hit time using exponential moving average."""
        if self.hits == 1:
            self.avg_hit_time_ms = latency_ms
        else:
            alpha = 0.1
            self.avg_hit_time_ms = (
                alpha * latency_ms + (1 - alpha) * self.avg_hit_time_ms
            )

    def _update_avg_miss_time(self, latency_ms: float) -> None:
        """Update average miss time using exponential moving average."""
        if self.misses == 1:
            self.avg_miss_time_ms = latency_ms
        else:
            alpha = 0.1
            self.avg_miss_time_ms = (
                alpha * latency_ms + (1 - alpha) * self.avg_miss_time_ms
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate, 2),
            "avg_hit_time_ms": round(self.avg_hit_time_ms, 2),
            "avg_miss_time_ms": round(self.avg_miss_time_ms, 2),
        }


class CacheKeyBuilder:
    """Builder for consistent cache key generation."""

    PREFIX = "chiseai:dashboard:cache"

    @classmethod
    def build_key(
        cls,
        component: str,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Build a cache key from component, identifier, and optional params.

        Args:
            component: Dashboard component name (e.g., "signal_list")
            identifier: Unique identifier (e.g., token, user_id)
            params: Optional parameters that affect the cache key

        Returns:
            Formatted cache key string
        """
        base = f"{cls.PREFIX}:{component}:{identifier}"

        if params:
            # Sort and hash params for consistent keys
            param_str = json.dumps(params, sort_keys=True)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
            base = f"{base}:{param_hash}"

        return base

    @classmethod
    def build_pattern(cls, component: str) -> str:
        """Build a pattern for matching all keys for a component.

        Args:
            component: Dashboard component name

        Returns:
            Pattern string for matching component keys
        """
        return f"{cls.PREFIX}:{component}:*"


class DashboardCache:
    """Redis-backed cache for dashboard data.

    Provides async caching with TTL support, automatic invalidation,
    and performance tracking.

    Example:
        cache = DashboardCache(redis_client)
        await cache.set("signal_list:BTC", signal_data, ttl_seconds=300)
        data = await cache.get("signal_list:BTC")
    """

    # Default TTLs by data type (in seconds)
    DEFAULT_TTLS = {
        "market_summary": 60,  # 1 minute
        "signal_list": 120,  # 2 minutes
        "signal_detail": 300,  # 5 minutes
        "key_levels": 180,  # 3 minutes
        "regime_detection": 240,  # 4 minutes
        "historical_context": 600,  # 10 minutes
        "risk_exposure": 90,  # 1.5 minutes
        "default": 300,  # 5 minutes default
    }

    def __init__(
        self,
        redis_client: aioredis.Redis,
        default_ttl: int = 300,
    ):
        """Initialize dashboard cache.

        Args:
            redis_client: Async Redis client
            default_ttl: Default TTL in seconds (default: 300)
        """
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.stats = CacheStats()

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        start_time = datetime.now(UTC)

        try:
            data = await self.redis.get(key)

            if data is not None:
                latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                self.stats.record_hit(latency_ms)
                return json.loads(data)
            else:
                latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                self.stats.record_miss(latency_ms)
                return None

        except Exception as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            self.stats.record_miss(0)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        data_type: str | None = None,
    ) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl_seconds: TTL in seconds (uses default if not specified)
            data_type: Data type for default TTL lookup

        Returns:
            True if successful, False otherwise
        """
        if ttl_seconds is None:
            if data_type and data_type in self.DEFAULT_TTLS:
                ttl_seconds = self.DEFAULT_TTLS[data_type]
            else:
                ttl_seconds = self.default_ttl

        try:
            serialized = json.dumps(value)
            await self.redis.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            result = await self.redis.delete(key)
            if result > 0:
                self.stats.evictions += 1
                return True
            return False
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False

    async def invalidate_component(self, component: str) -> int:
        """Invalidate all cache entries for a component.

        Args:
            component: Dashboard component name

        Returns:
            Number of keys deleted
        """
        pattern = CacheKeyBuilder.build_pattern(component)
        deleted_count = 0

        try:
            # Scan for matching keys
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                if keys:
                    await self.redis.delete(*keys)
                    deleted_count += len(keys)
                    self.stats.evictions += len(keys)
                if cursor == 0:
                    break

        except Exception as e:
            logger.warning(f"Cache invalidation error for {component}: {e}")

        return deleted_count

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        ttl_seconds: int | None = None,
        data_type: str | None = None,
    ) -> T:
        """Get from cache or compute if not present.

        Args:
            key: Cache key
            compute_fn: Async function to compute value if not cached
            ttl_seconds: TTL for cached value
            data_type: Data type for default TTL lookup

        Returns:
            Cached or computed value
        """
        cached = await self.get(key)
        if cached is not None:
            return cached  # type: ignore

        # Compute value
        if asyncio.iscoroutinefunction(compute_fn):
            value = await compute_fn()  # type: ignore
        else:
            value = compute_fn()

        # Cache and return
        await self.set(key, value, ttl_seconds, data_type)
        return value  # type: ignore[no-any-return]

    def get_stats(self) -> CacheStats:
        """Get current cache statistics.

        Returns:
            CacheStats with current performance metrics
        """
        return self.stats

    async def health_check(self) -> dict[str, Any]:
        """Perform cache health check.

        Returns:
            Health check result with status and stats
        """
        try:
            # Test Redis connectivity
            result = self.redis.ping()
            if asyncio.iscoroutine(result):
                await result
            return {
                "status": "healthy",
                "stats": self.stats.to_dict(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "stats": self.stats.to_dict(),
            }


def cached_query(
    component: str,
    ttl_seconds: int = 300,
    key_params: list[str] | None = None,
) -> Callable:
    """Decorator for caching query results.

    Args:
        component: Dashboard component name
        ttl_seconds: Cache TTL in seconds
        key_params: Parameter names to include in cache key

    Returns:
        Decorated function with caching

    Example:
        @cached_query("signal_list", ttl_seconds=120, key_params=["token"])
        async def get_signals(token: str) -> list[Signal]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get cache instance from first argument if it's a method
            cache: DashboardCache | None = None
            if args and hasattr(args[0], "_cache"):
                cache = args[0]._cache

            if cache is None:
                # No cache available, execute directly
                return await func(*args, **kwargs)

            # Build cache key
            key_parts = {}
            if key_params:
                for param in key_params:
                    if param in kwargs:
                        key_parts[param] = kwargs[param]
                    elif len(args) > 1:
                        # Try to match positional args to key_params
                        param_idx = list(func.__code__.co_varnames).index(param) - 1
                        if 0 <= param_idx < len(args) - 1:
                            key_parts[param] = args[param_idx + 1]

            key = CacheKeyBuilder.build_key(component, func.__name__, key_parts)

            # Get from cache or compute
            return await cache.get_or_compute(
                key,
                lambda: func(*args, **kwargs),
                ttl_seconds=ttl_seconds,
                data_type=component,
            )

        return wrapper

    return decorator
