"""Main cache manager for query result caching.

Provides Redis-based caching with automatic TTL management, cache
invalidation, and metrics collection.
"""

from __future__ import annotations

import logging
import pickle  # nosec B403
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from api.cache.metrics import CacheMetricsCollector, CacheMetricsSnapshot
from api.cache.strategies import CacheStrategy, QueryType, TTLStrategy

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    data: Any
    created_at: float
    ttl: int
    query_type: QueryType
    access_count: int = 0

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "data": self.data,
            "created_at": self.created_at,
            "ttl": self.ttl,
            "query_type": self.query_type.name,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        return cls(
            data=data["data"],
            created_at=data["created_at"],
            ttl=data["ttl"],
            query_type=QueryType[data["query_type"]],
            access_count=data.get("access_count", 0),
        )


class QueryCacheManager:
    """Manages query result caching with Redis backend.

    Provides:
    - Automatic cache key generation
    - TTL management by query type
    - Cache hit/miss metrics
    - Bulk invalidation
    - Fallback to in-memory cache when Redis unavailable
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        default_ttl: int = 300,
        ttl_strategy: TTLStrategy | None = None,
        cache_strategy: CacheStrategy | None = None,
        enable_memory_fallback: bool = True,
    ) -> None:
        """Initialize cache manager.

        Args:
            redis_client: Redis client instance (optional)
            default_ttl: Default TTL in seconds
            ttl_strategy: TTL configuration by query type
            cache_strategy: Cache key generation strategy
            enable_memory_fallback: Use in-memory cache if Redis unavailable
        """
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.ttl_strategy = ttl_strategy or TTLStrategy()
        self.cache_strategy = cache_strategy or CacheStrategy(self.ttl_strategy)
        self.metrics = CacheMetricsCollector()
        self._memory_cache: dict[str, CacheEntry] = {}
        self._enable_memory_fallback = enable_memory_fallback
        self._use_memory = redis_client is None

        if self.redis is None and not enable_memory_fallback:
            logger.warning("No Redis client provided and memory fallback disabled")

    def _get_redis(self) -> Any | None:
        """Get Redis client or None if unavailable."""
        if self.redis is None:
            return None
        try:
            # Test connection
            self.redis.ping()
            return self.redis
        except Exception as e:
            logger.debug(f"Redis unavailable: {e}")
            return None

    def _serialize(self, data: Any) -> bytes:
        """Serialize data for storage."""
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize data from storage."""
        return pickle.loads(data)  # nosec B301

    def get(self, query_key: str) -> Any | None:
        """Get cached result by key.

        Args:
            query_key: Cache key

        Returns:
            Cached data or None if not found/expired
        """
        start_time = time.time()

        # Try Redis first
        redis = self._get_redis()
        if redis:
            try:
                data = redis.get(query_key)
                if data:
                    duration_ms = (time.time() - start_time) * 1000
                    self.metrics.record_hit(duration_ms)
                    return self._deserialize(data)
            except Exception as e:
                logger.debug(f"Redis get failed: {e}")

        # Fallback to memory cache
        if self._use_memory or self._enable_memory_fallback:
            entry = self._memory_cache.get(query_key)
            if entry and not entry.is_expired():
                entry.access_count += 1
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.record_hit(duration_ms)
                return entry.data
            elif entry and entry.is_expired():
                del self._memory_cache[query_key]

        duration_ms = (time.time() - start_time) * 1000
        self.metrics.record_miss(duration_ms)
        return None

    def set(
        self,
        query_key: str,
        result: Any,
        ttl: int | None = None,
        query_type: QueryType | None = None,
    ) -> bool:
        """Cache a query result.

        Args:
            query_key: Cache key
            result: Data to cache
            ttl: TTL in seconds (uses default if None)
            query_type: Type of query for TTL determination

        Returns:
            True if cached successfully
        """
        if ttl is None:
            ttl = self.default_ttl

        if query_type is None:
            query_type = QueryType.UNKNOWN

        entry = CacheEntry(
            data=result,
            created_at=time.time(),
            ttl=ttl,
            query_type=query_type,
        )

        # Try Redis first
        redis = self._get_redis()
        if redis:
            try:
                serialized = self._serialize(result)
                redis.setex(query_key, ttl, serialized)
                return True
            except Exception as e:
                logger.debug(f"Redis set failed: {e}")

        # Fallback to memory cache
        if self._use_memory or self._enable_memory_fallback:
            self._memory_cache[query_key] = entry
            return True

        return False

    def get_or_execute(
        self,
        query_key: str,
        query_func: Callable[[], T],
        ttl: int | None = None,
        query_type: QueryType | None = None,
        use_cache: bool = True,
    ) -> T:
        """Get from cache or execute query function.

        Args:
            query_key: Cache key
            query_func: Function to execute on cache miss
            ttl: TTL in seconds
            query_type: Type of query
            use_cache: Whether to use caching

        Returns:
            Query result (from cache or fresh)
        """
        if not use_cache:
            return query_func()

        # Try cache first
        cached = self.get(query_key)
        if cached is not None:
            return cached

        # Execute query
        start_time = time.time()
        result = query_func()
        query_time = (time.time() - start_time) * 1000

        # Cache the result
        self.set(query_key, result, ttl, query_type)

        # Update miss time to include query execution
        self.metrics._miss_response_time_ms += query_time

        return result

    def invalidate(self, pattern: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            pattern: Key pattern to match (None = all)

        Returns:
            Number of entries invalidated
        """
        count = 0

        # Invalidate in Redis
        redis = self._get_redis()
        if redis and pattern:
            try:
                # Use SCAN to find matching keys
                cursor = 0
                while True:
                    cursor, keys = redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        redis.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug(f"Redis invalidation failed: {e}")

        # Invalidate in memory cache
        if pattern:
            import fnmatch

            keys_to_delete = [
                k for k in self._memory_cache if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_delete:
                del self._memory_cache[k]
                count += 1
        else:
            count += len(self._memory_cache)
            self._memory_cache.clear()

        self.metrics.record_eviction()
        return count

    def invalidate_by_query_type(self, query_type: QueryType) -> int:
        """Invalidate all entries of a specific query type.

        Args:
            query_type: Type of queries to invalidate

        Returns:
            Number of entries invalidated
        """
        count = 0

        # Invalidate in memory cache
        keys_to_delete = [
            k for k, v in self._memory_cache.items() if v.query_type == query_type
        ]
        for k in keys_to_delete:
            del self._memory_cache[k]
            count += 1

        # For Redis, we need to scan and check
        redis = self._get_redis()
        if redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = redis.scan(cursor, match="query:*", count=100)
                    for key in keys:
                        try:
                            data = redis.get(key)
                            if data:
                                entry = self._deserialize(data)
                                if (
                                    isinstance(entry, CacheEntry)
                                    and entry.query_type == query_type
                                ):
                                    redis.delete(key)
                                    count += 1
                        except Exception as err:
                            logger.debug(
                                "Failed to inspect cache entry %s: %s", key, err
                            )
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug(f"Redis invalidation by type failed: {e}")

        return count

    def get_metrics(self) -> CacheMetricsSnapshot:
        """Get current cache metrics."""
        return self.metrics.get_snapshot()

    def get_cache_key(self, query: str) -> str:
        """Generate cache key for a query.

        Args:
            query: Query string

        Returns:
            Cache key
        """
        return self.cache_strategy.generate_cache_key(query)

    def get_ttl(self, query: str) -> int:
        """Get TTL for a query.

        Args:
            query: Query string

        Returns:
            TTL in seconds
        """
        return self.cache_strategy.get_ttl(query)

    def should_cache(self, query: str) -> bool:
        """Determine if a query should be cached.

        Args:
            query: Query string

        Returns:
            True if query should be cached
        """
        return self.cache_strategy.should_cache(query)

    def clear_memory_cache(self) -> int:
        """Clear in-memory cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._memory_cache)
        self._memory_cache.clear()
        return count

    def get_memory_cache_size(self) -> int:
        """Get number of entries in memory cache."""
        return len(self._memory_cache)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        metrics = self.get_metrics()
        window = self.metrics.get_window_stats()

        return {
            "metrics": metrics.to_dict(),
            "window": window,
            "memory_cache_size": self.get_memory_cache_size(),
            "using_redis": self._get_redis() is not None,
            "using_memory_fallback": self._use_memory or self._enable_memory_fallback,
        }
