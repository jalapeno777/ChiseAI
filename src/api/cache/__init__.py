"""
API caching module for query optimization.

Provides caching mechanisms for API queries to improve performance
and reduce redundant database calls.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, TypeVar

from api.cache.metrics import CacheMetricsCollector, CacheMetricsSnapshot

T = TypeVar("T")


class QueryCache:
    """Cache for API query results."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Initialize query cache.

        Args:
            ttl_seconds: Time to live for cache entries in seconds
            max_size: Maximum number of entries in cache
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: dict[str, dict[str, Any]] = {}

    def _generate_key(self, query_params: dict[str, Any]) -> str:
        """Generate cache key from query parameters."""
        key_data = json.dumps(query_params, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, query_params: dict[str, Any]) -> Any | None:
        """
        Get cached result for query.

        Args:
            query_params: Query parameters

        Returns:
            Cached result or None if not found/expired
        """
        key = self._generate_key(query_params)

        if key not in self._cache:
            return None

        entry = self._cache[key]
        if datetime.now() - entry["timestamp"] > timedelta(seconds=self.ttl_seconds):
            del self._cache[key]
            return None

        return entry["data"]

    def set(self, query_params: dict[str, Any], data: Any) -> None:
        """
        Cache result for query.

        Args:
            query_params: Query parameters
            data: Data to cache
        """
        # Evict oldest entries if cache is full
        if len(self._cache) >= self.max_size:
            oldest_key = min(
                self._cache.keys(), key=lambda k: self._cache[k]["timestamp"]
            )
            del self._cache[oldest_key]

        key = self._generate_key(query_params)
        self._cache[key] = {"data": data, "timestamp": datetime.now()}

    def invalidate(self, pattern: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match keys (not implemented)

        Returns:
            Number of entries invalidated
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        return 0

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
        }


def cached(ttl_seconds: int = 300, max_size: int = 1000):
    """
    Decorator for caching function results.

    Args:
        ttl_seconds: Time to live for cache entries
        max_size: Maximum cache size
    """
    cache = QueryCache(ttl_seconds=ttl_seconds, max_size=max_size)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create key from function name and arguments
            key_data = {"func": func.__name__, "args": args, "kwargs": kwargs}

            # Try to get from cache
            cached_result = cache.get(key_data)
            if cached_result is not None:
                return cached_result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key_data, result)
            return result

        # Attach cache to function for external access
        wrapper.cache = cache  # type: ignore
        return wrapper

    return decorator


# Global cache instance
_global_cache: QueryCache | None = None


def get_global_cache() -> QueryCache:
    """Get or create global query cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = QueryCache()
    return _global_cache


__all__ = [
    "QueryCache",
    "cached",
    "get_global_cache",
    "CacheMetricsCollector",
    "CacheMetricsSnapshot",
]
