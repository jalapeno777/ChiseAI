"""Redis caching layer for path analysis results."""

import hashlib
import json
import time
from typing import Any, Dict, Optional


class PathAnalysisCache:
    """Cache for path analysis results using Redis."""

    DEFAULT_TTL = 3600  # 1 hour in seconds
    KEY_PREFIX = "path_analysis"

    def __init__(self, redis_client=None, ttl: int = DEFAULT_TTL):
        """
        Initialize cache.

        Args:
            redis_client: Optional Redis client. If None, uses in-memory cache.
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self._redis = redis_client
        self._ttl = ttl
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._memory_timestamps: Dict[str, float] = {}

    def _make_key(
        self, pr_number: Optional[int], commit_sha: Optional[str], file_list_hash: str
    ) -> str:
        """Generate cache key."""
        if commit_sha:
            return f"{self.KEY_PREFIX}:{pr_number or 'unknown'}:{commit_sha[:8]}"
        return f"{self.KEY_PREFIX}:{pr_number or 'unknown'}:{file_list_hash}"

    @staticmethod
    def _hash_file_list(files: list) -> str:
        """Create hash of file list for cache key."""
        content = json.dumps(sorted(files), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(
        self, pr_number: Optional[int], commit_sha: Optional[str], files: list
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis result.

        Args:
            pr_number: Pull request number
            commit_sha: Git commit SHA
            files: List of file paths

        Returns:
            Cached result dict or None if not found/expired
        """
        file_hash = self._hash_file_list(files)
        key = self._make_key(pr_number, commit_sha, file_hash)

        if self._redis:
            try:
                import redis

                if isinstance(self._redis, redis.Redis):
                    data = self._redis.get(key)
                    if data:
                        return json.loads(data)
            except Exception:
                pass  # Fall through to memory cache

        # Check memory cache
        if key in self._memory_cache:
            timestamp = self._memory_timestamps.get(key, 0)
            if time.time() - timestamp < self._ttl:
                return self._memory_cache[key]
            else:
                # Expired, clean up
                del self._memory_cache[key]
                del self._memory_timestamps[key]

        return None

    def set(
        self,
        pr_number: Optional[int],
        commit_sha: Optional[str],
        files: list,
        result: Dict[str, Any],
    ) -> bool:
        """
        Cache analysis result.

        Args:
            pr_number: Pull request number
            commit_sha: Git commit SHA
            files: List of file paths
            result: Analysis result to cache

        Returns:
            True if cached successfully
        """
        file_hash = self._hash_file_list(files)
        key = self._make_key(pr_number, commit_sha, file_hash)

        # Add metadata
        result_with_meta = result.copy()
        result_with_meta["_cached_at"] = time.time()
        result_with_meta["_ttl"] = self._ttl

        if self._redis:
            try:
                import redis

                if isinstance(self._redis, redis.Redis):
                    self._redis.setex(key, self._ttl, json.dumps(result_with_meta))
                    return True
            except Exception:
                pass  # Fall through to memory cache

        # Store in memory
        self._memory_cache[key] = result_with_meta
        self._memory_timestamps[key] = time.time()
        return True

    def invalidate(
        self, pr_number: Optional[int], commit_sha: Optional[str] = None
    ) -> int:
        """
        Invalidate cache entries for a PR.

        Args:
            pr_number: Pull request number
            commit_sha: Optional specific commit SHA to invalidate

        Returns:
            Number of entries invalidated
        """
        count = 0

        if self._redis:
            try:
                import redis

                if isinstance(self._redis, redis.Redis):
                    if commit_sha:
                        key = f"{self.KEY_PREFIX}:{pr_number}:{commit_sha[:8]}"
                        self._redis.delete(key)
                        count += 1
                    else:
                        # Pattern delete for all commits of this PR
                        pattern = f"{self.KEY_PREFIX}:{pr_number}:*"
                        for key in self._redis.scan_iter(match=pattern):
                            self._redis.delete(key)
                            count += 1
            except Exception:
                pass

        # Clean memory cache
        keys_to_delete = []
        for key in self._memory_cache:
            if f":{pr_number}:" in key:
                if commit_sha is None or commit_sha[:8] in key:
                    keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._memory_cache[key]
            del self._memory_timestamps[key]
            count += 1

        return count

    def clear(self) -> None:
        """Clear all cached entries."""
        if self._redis:
            try:
                import redis

                if isinstance(self._redis, redis.Redis):
                    pattern = f"{self.KEY_PREFIX}:*"
                    for key in self._redis.scan_iter(match=pattern):
                        self._redis.delete(key)
            except Exception:
                pass

        self._memory_cache.clear()
        self._memory_timestamps.clear()

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        memory_entries = len(self._memory_cache)
        redis_entries = 0

        if self._redis:
            try:
                import redis

                if isinstance(self._redis, redis.Redis):
                    pattern = f"{self.KEY_PREFIX}:*"
                    redis_entries = sum(1 for _ in self._redis.scan_iter(match=pattern))
            except Exception:
                pass

        return {
            "memory_entries": memory_entries,
            "redis_entries": redis_entries,
            "total_entries": memory_entries + redis_entries,
            "ttl_seconds": self._ttl,
        }
