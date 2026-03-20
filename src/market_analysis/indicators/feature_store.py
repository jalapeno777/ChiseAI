"""Redis-backed feature store for indicator caching."""

import fnmatch
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from tools.redis_state import (
    redis_state_hdel,
    redis_state_hexists,
    redis_state_hget,
    redis_state_hgetall,
    redis_state_hset,
)

logger = logging.getLogger(__name__)


class FeatureStore:
    """Redis-backed caching store for indicator features.

    Provides TTL-based caching with batch operations for efficient
    indicator feature storage and retrieval.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, prefix: str = "indicator", default_ttl: int | None = None):
        """Initialize feature store.

        Args:
            prefix: Key prefix for namespacing
            default_ttl: Default TTL in seconds (None = use DEFAULT_TTL_SECONDS)
        """
        self.prefix = prefix
        self.default_ttl = default_ttl or self.DEFAULT_TTL_SECONDS
        self._local_cache: dict[str, Any] = {}
        self._local_expiry: dict[str, datetime] = {}

    def _make_key(self, key: str) -> str:
        """Create namespaced key."""
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        # Check local cache first
        if key in self._local_cache:
            if datetime.now(UTC) < self._local_expiry[key]:
                return self._local_cache[key]
            else:
                del self._local_cache[key]
                del self._local_expiry[key]

        # Check Redis
        namespaced = self._make_key(key)
        try:
            value = redis_state_hget("feature_store", namespaced)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis get failed for {namespaced}: {e}")

        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = use default)

        Returns:
            True if successful
        """
        ttl = ttl or self.default_ttl
        namespaced = self._make_key(key)

        # Update local cache
        self._local_cache[key] = value
        self._local_expiry[key] = datetime.now(UTC) + timedelta(seconds=ttl)

        # Update Redis
        try:
            redis_state_hset(
                "feature_store", namespaced, json.dumps(value), expire_seconds=ttl
            )
            return True
        except Exception as e:
            logger.warning(f"Redis set failed for {namespaced}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        namespaced = self._make_key(key)

        # Remove from local cache
        self._local_cache.pop(key, None)
        self._local_expiry.pop(key, None)

        # Remove from Redis
        try:
            redis_state_hdel("feature_store", namespaced)
            return True
        except Exception as e:
            logger.warning(f"Redis delete failed for {namespaced}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired
        """
        # Check local cache
        if key in self._local_cache:
            if datetime.now(UTC) < self._local_expiry[key]:
                return True

        # Check Redis
        namespaced = self._make_key(key)
        try:
            return redis_state_hexists("feature_store", namespaced)
        except Exception as e:
            logger.warning(f"Redis exists check failed for {namespaced}: {e}")
            return False

    def mget(self, keys: list[str]) -> dict[str, Any | None]:
        """Batch get multiple values.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary mapping keys to values (None if not found)
        """
        return {key: self.get(key) for key in keys}

    def mset(self, mapping: dict[str, Any], ttl: int | None = None) -> dict[str, bool]:
        """Batch set multiple values.

        Args:
            mapping: Dictionary of key-value pairs
            ttl: TTL in seconds (None = use default)

        Returns:
            Dictionary mapping keys to success status
        """
        return {key: self.set(key, value, ttl) for key, value in mapping.items()}

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern (glob matching).

        Args:
            pattern: Key pattern to match (glob pattern, e.g., "key*" or "query:*")

        Returns:
            Number of keys invalidated
        """
        count = 0
        # Invalidate from local cache
        keys_to_remove = [k for k in self._local_cache if fnmatch.fnmatch(k, pattern)]
        removed_namespaced = set()
        for key in keys_to_remove:
            self.delete(key)
            removed_namespaced.add(self._make_key(key))
            count += 1

        # Invalidate from Redis
        try:
            all_fields = redis_state_hgetall("feature_store")
            if all_fields:
                for field in all_fields:
                    # Strip prefix to get original key for matching
                    if field.startswith(self.prefix + ":"):
                        original_key = field[len(self.prefix) + 1 :]
                    else:
                        original_key = field
                    if (
                        fnmatch.fnmatch(original_key, pattern)
                        and field not in removed_namespaced
                    ):
                        # Delete from Redis
                        redis_state_hdel("feature_store", field)
                        # Remove from local cache if present
                        self._local_cache.pop(original_key, None)
                        self._local_expiry.pop(original_key, None)
                        count += 1
        except Exception as e:
            logger.warning(
                f"Redis pattern invalidation failed for pattern '{pattern}': {e}"
            )

        return count
