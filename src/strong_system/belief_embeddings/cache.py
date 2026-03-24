"""Cache module for belief embeddings.

Provides BeliefCache class with LRU eviction and TTL support for
intelligent caching of frequent belief queries.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import numpy as np

from .vector import BeliefVector

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with TTL support.

    Attributes:
        value: The cached value
        expires_at: Unix timestamp when entry expires (None for no expiry)
        access_count: Number of times this entry has been accessed
        created_at: Unix timestamp when entry was created
    """

    value: T
    expires_at: float | None = None
    access_count: int = field(default=0)
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class CacheMetrics:
    """Metrics for cache performance monitoring.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        evictions: Number of entries evicted
        total_requests: Total number of cache requests
        hit_rate: Cache hit rate (0.0 to 1.0)
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1
        self.total_requests += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1
        self.total_requests += 1

    def record_eviction(self) -> None:
        """Record a cache eviction."""
        self.evictions += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
            "hit_rate": self.hit_rate,
        }


class BeliefCache:
    """LRU cache for belief vectors with TTL support.

    Provides intelligent caching for frequent belief queries with:
    - LRU (Least Recently Used) eviction policy
    - TTL (Time To Live) support for cache entries
    - Thread-safe operations
    - Cache hit/miss tracking

    Attributes:
        max_size: Maximum number of entries in cache
        default_ttl: Default TTL in seconds (None for no expiry)
        metrics: Cache performance metrics
    """

    def __init__(self, max_size: int = 1000, default_ttl: float | None = None):
        """Initialize the belief cache.

        Args:
            max_size: Maximum number of entries (default: 1000)
            default_ttl: Default TTL in seconds (default: None = no expiry)

        Raises:
            ValueError: If max_size is not positive
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry[Any]] = OrderedDict()
        self._lock = threading.RLock()
        self.metrics = CacheMetrics()

    def _make_key(self, key: str | np.ndarray) -> str:
        """Convert key to string representation.

        Args:
            key: String key or numpy array

        Returns:
            String representation of the key
        """
        if isinstance(key, np.ndarray):
            # Use hash of array data as key
            return f"vec_{hash(key.tobytes())}"
        return str(key)

    def get(self, key: str | np.ndarray, default: T | None = None) -> T | None:
        """Get a value from the cache.

        Args:
            key: Cache key (string or numpy array)
            default: Default value if key not found or expired

        Returns:
            Cached value or default
        """
        str_key = self._make_key(key)

        with self._lock:
            entry = self._cache.get(str_key)

            if entry is None:
                self.metrics.record_miss()
                return default

            if entry.is_expired():
                # Remove expired entry
                del self._cache[str_key]
                self.metrics.record_miss()
                return default

            # Move to end (most recently used)
            self._cache.move_to_end(str_key)
            entry.access_count += 1
            self.metrics.record_hit()
            return entry.value

    def set(
        self,
        key: str | np.ndarray,
        value: T,
        ttl: float | None = None,
    ) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key (string or numpy array)
            value: Value to cache
            ttl: TTL in seconds (overrides default_ttl if provided)
        """
        str_key = self._make_key(key)
        effective_ttl = ttl if ttl is not None else self.default_ttl

        with self._lock:
            # Calculate expiry time
            expires_at = None
            if effective_ttl is not None:
                expires_at = time.time() + effective_ttl

            # Create new entry
            entry = CacheEntry(value=value, expires_at=expires_at)

            # If key exists, update it and move to end
            if str_key in self._cache:
                self._cache.move_to_end(str_key)
                self._cache[str_key] = entry
                return

            # Evict oldest entry if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            # Add new entry
            self._cache[str_key] = entry

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self.metrics.record_eviction()

    def delete(self, key: str | np.ndarray) -> bool:
        """Delete a key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        str_key = self._make_key(key)

        with self._lock:
            if str_key in self._cache:
                del self._cache[str_key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def get_belief(self, key: str) -> BeliefVector | None:
        """Get a belief vector from cache.

        Convenience method for type-safe belief retrieval.

        Args:
            key: Belief ID or cache key

        Returns:
            BeliefVector if found and not expired, None otherwise
        """
        result = self.get(key)
        if isinstance(result, BeliefVector):
            return result
        return None

    def set_belief(
        self,
        belief: BeliefVector,
        ttl: float | None = None,
    ) -> None:
        """Cache a belief vector.

        Convenience method for caching beliefs by their ID.

        Args:
            belief: BeliefVector to cache
            ttl: TTL in seconds (overrides default_ttl if provided)
        """
        self.set(belief.belief_id, belief, ttl=ttl)

    def get_search_results(self, query_vector: np.ndarray) -> list[Any] | None:
        """Get cached search results for a query vector.

        Args:
            query_vector: Query vector to look up

        Returns:
            List of search results if cached, None otherwise
        """
        result = self.get(query_vector)
        if isinstance(result, list):
            return result
        return None

    def set_search_results(
        self,
        query_vector: np.ndarray,
        results: list[Any],
        ttl: float | None = None,
    ) -> None:
        """Cache search results for a query vector.

        Args:
            query_vector: Query vector
            results: Search results to cache
            ttl: TTL in seconds (overrides default_ttl if provided)
        """
        self.set(query_vector, results, ttl=ttl)

    def keys(self) -> list[str]:
        """Get all non-expired keys in the cache.

        Returns:
            List of cache keys
        """
        with self._lock:
            # Remove expired entries first
            expired_keys = [k for k, entry in self._cache.items() if entry.is_expired()]
            for k in expired_keys:
                del self._cache[k]

            return list(self._cache.keys())

    def values(self) -> list[Any]:
        """Get all non-expired values in the cache.

        Returns:
            List of cached values
        """
        with self._lock:
            # Remove expired entries first
            expired_keys = [k for k, entry in self._cache.items() if entry.is_expired()]
            for k in expired_keys:
                del self._cache[k]

            return [entry.value for entry in self._cache.values()]

    def items(self) -> list[tuple[str, Any]]:
        """Get all non-expired key-value pairs.

        Returns:
            List of (key, value) tuples
        """
        with self._lock:
            # Remove expired entries first
            expired_keys = [k for k, entry in self._cache.items() if entry.is_expired()]
            for k in expired_keys:
                del self._cache[k]

            return [(k, entry.value) for k, entry in self._cache.items()]

    def __len__(self) -> int:
        """Return the number of entries in the cache."""
        with self._lock:
            # Remove expired entries first
            expired_keys = [k for k, entry in self._cache.items() if entry.is_expired()]
            for k in expired_keys:
                del self._cache[k]

            return len(self._cache)

    def __contains__(self, key: str | np.ndarray) -> bool:
        """Check if a key is in the cache."""
        str_key = self._make_key(key)

        with self._lock:
            entry = self._cache.get(str_key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[str_key]
                return False
            return True

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [k for k, entry in self._cache.items() if entry.is_expired()]
            for k in expired_keys:
                del self._cache[k]
                self.metrics.record_eviction()

            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            # Clean up expired entries for accurate count
            self.cleanup_expired()

            total_accesses = sum(entry.access_count for entry in self._cache.values())

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "utilization": len(self._cache) / self.max_size
                if self.max_size > 0
                else 0,
                "default_ttl": self.default_ttl,
                "metrics": self.metrics.to_dict(),
                "total_access_count": total_accesses,
            }

    def memoize(
        self,
        ttl: float | None = None,
        key_func: Callable[..., str] | None = None,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to memoize function results.

        Args:
            ttl: TTL for cached results
            key_func: Optional function to generate cache key from arguments

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            def wrapper(*args: Any, **kwargs: Any) -> T:
                # Generate cache key
                if key_func is not None:
                    cache_key = key_func(*args, **kwargs)
                else:
                    # Default: use function name and arguments
                    key_parts = [func.__name__]
                    key_parts.extend(str(arg) for arg in args)
                    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                    cache_key = "|".join(key_parts)

                # Try to get from cache
                result = self.get(cache_key)
                if result is not None:
                    return result

                # Compute and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl=ttl)
                return result

            return wrapper

        return decorator
