"""Redis-backed cache for signal metadata.

Provides caching layer for signal delivery metadata to reduce
database lookups and improve delivery latency.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


@dataclass
class SignalMetadataEntry:
    """Metadata entry for a delivered signal.

    Attributes:
        signal_id: Unique signal identifier
        delivered: Whether signal was delivered
        delivery_time: When signal was delivered
        latency_ms: Delivery latency in milliseconds
        target: Delivery target identifier
        retry_count: Number of retries
        metadata: Additional metadata
    """

    signal_id: str
    delivered: bool = False
    delivery_time: datetime | None = None
    latency_ms: float = 0.0
    target: str = "default"
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "delivered": self.delivered,
            "delivery_time": self.delivery_time.isoformat()
            if self.delivery_time
            else None,
            "latency_ms": round(self.latency_ms, 2),
            "target": self.target,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalMetadataEntry":
        """Create from dictionary.

        Args:
            data: Dictionary with entry data

        Returns:
            SignalMetadataEntry instance
        """
        delivery_time = None
        if data.get("delivery_time"):
            delivery_time = datetime.fromisoformat(data["delivery_time"])

        return cls(
            signal_id=data["signal_id"],
            delivered=data.get("delivered", False),
            delivery_time=delivery_time,
            latency_ms=data.get("latency_ms", 0.0),
            target=data.get("target", "default"),
            retry_count=data.get("retry_count", 0),
            metadata=data.get("metadata", {}),
        )


class SignalMetadataCache:
    """Redis-backed cache for signal delivery metadata.

    Provides fast lookup for signal delivery status and metadata,
    reducing database queries and improving delivery latency.

    Example:
        cache = SignalMetadataCache(redis_client)
        await cache.set("sig-123", {"delivered": True, "latency_ms": 50})
        entry = await cache.get("sig-123")
        if entry and entry.delivered:
            print("Signal already delivered")
    """

    KEY_PREFIX = "chiseai:signal:metadata:"
    DEFAULT_TTL = 3600  # 1 hour

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = DEFAULT_TTL,
    ):
        """Initialize signal metadata cache.

        Args:
            redis_client: Async Redis client
            ttl_seconds: Cache TTL in seconds (default: 1 hour)
        """
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds

    def _build_key(self, signal_id: str) -> str:
        """Build cache key for signal.

        Args:
            signal_id: Signal identifier

        Returns:
            Full cache key
        """
        return f"{self.KEY_PREFIX}{signal_id}"

    async def get(self, signal_id: str) -> SignalMetadataEntry | None:
        """Get signal metadata from cache.

        Args:
            signal_id: Signal identifier

        Returns:
            SignalMetadataEntry or None if not found
        """
        key = self._build_key(signal_id)

        try:
            data = await self.redis.get(key)

            if data is not None:
                parsed = json.loads(data)
                return SignalMetadataEntry.from_dict(parsed)

            return None

        except Exception as e:
            logger.warning(f"Cache get error for signal {signal_id}: {e}")
            return None

    async def set(
        self,
        signal_id: str,
        metadata: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set signal metadata in cache.

        Args:
            signal_id: Signal identifier
            metadata: Metadata to cache
            ttl_seconds: Optional custom TTL

        Returns:
            True if successful
        """
        key = self._build_key(signal_id)
        ttl = ttl_seconds or self.ttl_seconds

        try:
            # Create entry
            entry = SignalMetadataEntry(
                signal_id=signal_id,
                delivered=metadata.get("delivered", False),
                delivery_time=datetime.now(UTC) if metadata.get("delivered") else None,
                latency_ms=metadata.get("latency_ms", 0.0),
                target=metadata.get("target", "default"),
                retry_count=metadata.get("retry_count", 0),
                metadata=metadata.get("metadata", {}),
            )

            # Store in Redis
            await self.redis.setex(
                key,
                ttl,
                json.dumps(entry.to_dict()),
            )

            return True

        except Exception as e:
            logger.warning(f"Cache set error for signal {signal_id}: {e}")
            return False

    async def delete(self, signal_id: str) -> bool:
        """Delete signal metadata from cache.

        Args:
            signal_id: Signal identifier

        Returns:
            True if deleted
        """
        key = self._build_key(signal_id)

        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Cache delete error for signal {signal_id}: {e}")
            return False

    async def exists(self, signal_id: str) -> bool:
        """Check if signal metadata exists in cache.

        Args:
            signal_id: Signal identifier

        Returns:
            True if exists
        """
        key = self._build_key(signal_id)

        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.warning(f"Cache exists error for signal {signal_id}: {e}")
            return False

    async def get_batch(
        self,
        signal_ids: list[str],
    ) -> dict[str, SignalMetadataEntry | None]:
        """Get multiple signal metadata entries.

        Args:
            signal_ids: List of signal identifiers

        Returns:
            Dictionary of signal_id -> entry (or None if not found)
        """
        if not signal_ids:
            return {}

        keys = [self._build_key(sid) for sid in signal_ids]

        try:
            values = await self.redis.mget(keys)

            result: dict[str, SignalMetadataEntry | None] = {}
            for signal_id, data in zip(signal_ids, values):
                if data is not None:
                    parsed = json.loads(data)
                    result[signal_id] = SignalMetadataEntry.from_dict(parsed)
                else:
                    result[signal_id] = None

            return result

        except Exception as e:
            logger.warning(f"Cache batch get error: {e}")
            return {sid: None for sid in signal_ids}

    async def mark_delivered(
        self,
        signal_id: str,
        latency_ms: float,
        target: str = "default",
    ) -> bool:
        """Mark signal as delivered.

        Args:
            signal_id: Signal identifier
            latency_ms: Delivery latency
            target: Delivery target

        Returns:
            True if successful
        """
        return await self.set(
            signal_id,
            {
                "delivered": True,
                "latency_ms": latency_ms,
                "target": target,
            },
        )

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        try:
            # Count keys with our prefix
            pattern = f"{self.KEY_PREFIX}*"
            cursor = 0
            count = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                count += len(keys)
                if cursor == 0:
                    break

            return {
                "cached_signals": count,
                "ttl_seconds": self.ttl_seconds,
            }

        except Exception as e:
            return {
                "cached_signals": 0,
                "error": str(e),
            }

    async def clear_all(self) -> int:
        """Clear all cached signal metadata.

        Returns:
            Number of keys deleted
        """
        pattern = f"{self.KEY_PREFIX}*"
        deleted_count = 0

        try:
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
                if cursor == 0:
                    break

        except Exception as e:
            logger.warning(f"Cache clear error: {e}")

        return deleted_count
