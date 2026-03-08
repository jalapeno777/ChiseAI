"""
Redis Hash Cache for Memory Deduplication.

Provides caching of content hashes to prevent near-duplicate ingestion.

Story: ST-GOV-001
"""

import hashlib
import json
from datetime import datetime
from typing import Optional

from src.governance.deduplication.config import DeduplicationConfig


class HashCacheEntry:
    """Represents a cached hash entry with metadata."""

    def __init__(
        self,
        content_hash: str,
        source_id: str,
        collection: str,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ):
        self.content_hash = content_hash
        self.source_id = source_id
        self.collection = collection
        self.timestamp = timestamp or datetime.utcnow()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        """Convert entry to dictionary."""
        return {
            "content_hash": self.content_hash,
            "source_id": self.source_id,
            "collection": self.collection,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HashCacheEntry":
        """Create entry from dictionary."""
        return cls(
            content_hash=data["content_hash"],
            source_id=data["source_id"],
            collection=data["collection"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


class HashCache:
    """
    Redis-based cache for content hashes.

    Prevents near-duplicate ingestion by caching recently seen hashes
    with configurable TTL.
    """

    def __init__(self, config: Optional[DeduplicationConfig] = None):
        self.config = config or DeduplicationConfig()
        self._redis_client = None

    def _get_redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            try:
                from redis import Redis

                self._redis_client = Redis(
                    host="host.docker.internal",
                    port=6380,
                    db=0,
                    decode_responses=True,
                )
            except ImportError:
                raise RuntimeError(
                    "Redis not available. Install with: pip install redis"
                )
        return self._redis_client

    def _make_key(self, content_hash: str) -> str:
        """Create Redis key for a content hash."""
        return f"{self.config.redis_hash_cache_prefix}:{content_hash}"

    def compute_hash(self, content: str | bytes) -> str:
        """
        Compute content hash using configured algorithm.

        Args:
            content: Content to hash (string or bytes)

        Returns:
            Hexadecimal hash string
        """
        if isinstance(content, str):
            content = content.encode("utf-8")

        hasher = hashlib.new(self.config.hash_algorithm)
        hasher.update(content)
        return hasher.hexdigest()

    def is_duplicate(self, content: str | bytes) -> tuple[bool, Optional[str]]:
        """
        Check if content is a known duplicate.

        Args:
            content: Content to check

        Returns:
            Tuple of (is_duplicate, source_id_if_duplicate)
        """
        content_hash = self.compute_hash(content)
        redis_client = self._get_redis_client()
        key = self._make_key(content_hash)

        cached = redis_client.get(key)
        if cached:
            try:
                data = json.loads(cached)
                return True, data.get("source_id")
            except json.JSONDecodeError:
                # Corrupted cache entry, treat as not duplicate
                return False, None

        return False, None

    def add_hash(
        self,
        content: str | bytes,
        source_id: str,
        collection: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Add a content hash to the cache.

        Args:
            content: Content to cache
            source_id: ID of the source (e.g., Qdrant point ID)
            collection: Collection name
            metadata: Optional metadata

        Returns:
            The computed content hash
        """
        content_hash = self.compute_hash(content)
        redis_client = self._get_redis_client()
        key = self._make_key(content_hash)

        entry = HashCacheEntry(
            content_hash=content_hash,
            source_id=source_id,
            collection=collection,
            metadata=metadata,
        )

        redis_client.setex(
            key,
            self.config.redis_hash_cache_ttl,
            json.dumps(entry.to_dict()),
        )

        return content_hash

    def get_entry(self, content_hash: str) -> Optional[HashCacheEntry]:
        """
        Retrieve a cached entry by hash.

        Args:
            content_hash: Hash to look up

        Returns:
            HashCacheEntry if found, None otherwise
        """
        redis_client = self._get_redis_client()
        key = self._make_key(content_hash)

        cached = redis_client.get(key)
        if cached:
            try:
                return HashCacheEntry.from_dict(json.loads(cached))
            except (json.JSONDecodeError, KeyError):
                return None

        return None

    def remove_hash(self, content_hash: str) -> bool:
        """
        Remove a hash from the cache.

        Args:
            content_hash: Hash to remove

        Returns:
            True if removed, False if not found
        """
        redis_client = self._get_redis_client()
        key = self._make_key(content_hash)

        return redis_client.delete(key) > 0

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        redis_client = self._get_redis_client()
        pattern = f"{self.config.redis_hash_cache_prefix}:*"

        # Count keys matching pattern
        keys = list(redis_client.scan_iter(match=pattern))
        count = len(keys)

        # Calculate memory usage (approximate)
        memory_bytes = 0
        for key in keys[:100]:  # Sample first 100
            try:
                memory_bytes += redis_client.memory_usage(key) or 0
            except Exception:
                pass

        if keys:
            memory_bytes = memory_bytes * (count / min(len(keys), 100))

        return {
            "entry_count": count,
            "approx_memory_bytes": int(memory_bytes),
            "ttl_seconds": self.config.redis_hash_cache_ttl,
            "prefix": self.config.redis_hash_cache_prefix,
        }

    def clear_cache(self) -> int:
        """
        Clear all entries from the hash cache.

        Returns:
            Number of entries cleared
        """
        redis_client = self._get_redis_client()
        pattern = f"{self.config.redis_hash_cache_prefix}:*"

        keys = list(redis_client.scan_iter(match=pattern))
        if keys:
            return redis_client.delete(*keys)
        return 0
