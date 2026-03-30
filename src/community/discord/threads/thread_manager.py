"""Thread management for Discord community discussions."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ThreadStatus(Enum):
    """Status of a discussion thread."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    LOCKED = "locked"


@dataclass
class ThreadMetadata:
    """Metadata for a Discord thread."""

    signal_id: str
    signal_type: str | None = None
    symbol: str | None = None
    direction: str | None = None
    confidence: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    archived_at: datetime | None = None
    status: ThreadStatus = ThreadStatus.ACTIVE
    message_count: int = 0
    participant_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "status": self.status.value,
            "message_count": self.message_count,
            "participant_ids": self.participant_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThreadMetadata":
        """Create metadata from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        archived_at = data.get("archived_at")
        if isinstance(archived_at, str):
            archived_at = datetime.fromisoformat(archived_at)
        status = data.get("status", "active")
        if isinstance(status, str):
            status = ThreadStatus(status)
        return cls(
            signal_id=data["signal_id"],
            signal_type=data.get("signal_type"),
            symbol=data.get("symbol"),
            direction=data.get("direction"),
            confidence=data.get("confidence"),
            created_at=created_at or datetime.now(UTC),
            archived_at=archived_at,
            status=status or ThreadStatus.ACTIVE,
            message_count=data.get("message_count", 0),
            participant_ids=data.get("participant_ids", []),
        )


def generate_thread_name(
    symbol: str | None,
    direction: str | None,
    confidence: float | None,
    signal_type: str = "SIGNAL",
) -> str:
    """Generate a thread name following the convention: Signal: SYMBOL-DIRECTION-CONFIDENCE.

    Args:
        symbol: Trading symbol (e.g., 'BTC', 'ETH')
        direction: Trade direction ('LONG', 'SHORT', 'BUY', 'SELL')
        confidence: Confidence score (0.0 to 1.0)
        signal_type: Type of signal (default: 'SIGNAL')

    Returns:
        Thread name string (max 100 characters for Discord)
    """
    parts = [signal_type]

    if symbol:
        parts.append(symbol.upper())

    if direction:
        parts.append(direction.upper())

    if confidence is not None:
        # Format confidence as percentage
        conf_pct = int(confidence * 100)
        parts.append(f"{conf_pct}%")

    name = "-".join(parts)

    # Discord thread name limit is 100 characters
    return name[:100]


class ThreadManager:
    """Manages Discord threads for community discussions.

    Handles automatic thread creation for signals, archival after expiry,
    and metadata storage in Redis.
    """

    def __init__(
        self,
        redis_client: Any = None,
        default_archive_after_days: int = 7,
        thread_channel_id: str | None = None,
    ):
        """Initialize ThreadManager.

        Args:
            redis_client: Redis client for metadata storage
            default_archive_after_days: Days before auto-archiving threads
            thread_channel_id: Default channel ID for creating threads
        """
        self._redis = redis_client
        self._default_archive_days = default_archive_after_days
        self._thread_channel_id = thread_channel_id
        self._metadata_cache: dict[str, ThreadMetadata] = {}

    def _get_redis_key(self, thread_id: str) -> str:
        """Get Redis key for thread metadata."""
        return f"community:discord:thread:{thread_id}"

    def _get_signal_threads_key(self, signal_id: str) -> str:
        """Get Redis key for signal's threads mapping."""
        return f"community:discord:signal:{signal_id}:threads"

    async def create_thread_for_signal(
        self,
        signal_id: str,
        symbol: str | None = None,
        direction: str | None = None,
        confidence: float | None = None,
        signal_type: str = "SIGNAL",
        channel_id: str | None = None,
        auto_archive_duration: int | None = None,
    ) -> tuple[str, ThreadMetadata]:
        """Create a new thread for a signal.

        Args:
            signal_id: Unique signal identifier
            symbol: Trading symbol
            direction: Trade direction
            confidence: Confidence score (0.0 to 1.0)
            signal_type: Type of signal
            channel_id: Channel to create thread in (uses default if None)
            auto_archive_duration: Minutes before auto-archive (uses default if None)

        Returns:
            Tuple of (thread_id, thread_metadata)
        """
        import uuid

        thread_id = str(uuid.uuid4())[:8]
        thread_name = generate_thread_name(symbol, direction, confidence, signal_type)

        metadata = ThreadMetadata(
            signal_id=signal_id,
            signal_type=signal_type,
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            status=ThreadStatus.ACTIVE,
        )

        # Store metadata
        await self._store_metadata(thread_id, metadata)

        # Map signal to thread
        if self._redis:
            try:
                from tools.redis_state import redis_state_set

                signal_threads_key = self._get_signal_threads_key(signal_id)
                redis_state_set(signal_threads_key, thread_id)
            except Exception as e:
                logger.warning(f"Failed to map signal to thread in Redis: {e}")

        logger.info(
            f"Created thread for signal {signal_id}: {thread_name} (id={thread_id})"
        )

        return thread_id, metadata

    async def _store_metadata(self, thread_id: str, metadata: ThreadMetadata) -> None:
        """Store thread metadata in Redis and cache."""
        self._metadata_cache[thread_id] = metadata

        if self._redis:
            try:
                import json

                from tools.redis_state import redis_state_set

                key = self._get_redis_key(thread_id)
                redis_state_set(key, json.dumps(metadata.to_dict()))
            except Exception as e:
                logger.warning(f"Failed to store thread metadata in Redis: {e}")

    async def get_metadata(self, thread_id: str) -> ThreadMetadata | None:
        """Retrieve thread metadata.

        Args:
            thread_id: Discord thread ID

        Returns:
            ThreadMetadata or None if not found
        """
        # Check cache first
        if thread_id in self._metadata_cache:
            return self._metadata_cache[thread_id]

        if not self._redis:
            return None

        try:
            import json

            from tools.redis_state import redis_state_get

            key = self._get_redis_key(thread_id)
            data = redis_state_get(key)
            if data:
                metadata = ThreadMetadata.from_dict(json.loads(data))
                self._metadata_cache[thread_id] = metadata
                return metadata
        except Exception as e:
            logger.warning(f"Failed to retrieve thread metadata from Redis: {e}")

        return None

    async def archive_thread(self, thread_id: str, reason: str | None = None) -> bool:
        """Archive a thread.

        Args:
            thread_id: Discord thread ID
            reason: Optional reason for archival

        Returns:
            True if archived successfully
        """
        metadata = await self.get_metadata(thread_id)
        if not metadata:
            logger.warning(f"Thread {thread_id} not found for archival")
            return False

        metadata.status = ThreadStatus.ARCHIVED
        metadata.archived_at = datetime.now(UTC)

        await self._store_metadata(thread_id, metadata)

        logger.info(f"Archived thread {thread_id}" + (f": {reason}" if reason else ""))
        return True

    async def update_message_count(self, thread_id: str, count: int) -> None:
        """Update message count for a thread.

        Args:
            thread_id: Discord thread ID
            count: New message count
        """
        metadata = await self.get_metadata(thread_id)
        if metadata:
            metadata.message_count = count
            await self._store_metadata(thread_id, metadata)

    async def add_participant(self, thread_id: str, user_id: str) -> None:
        """Add a participant to a thread.

        Args:
            thread_id: Discord thread ID
            user_id: Discord user ID
        """
        metadata = await self.get_metadata(thread_id)
        if metadata and user_id not in metadata.participant_ids:
            metadata.participant_ids.append(user_id)
            await self._store_metadata(thread_id, metadata)

    async def get_threads_for_signal(self, signal_id: str) -> list[str]:
        """Get all thread IDs for a signal.

        Args:
            signal_id: Signal identifier

        Returns:
            List of thread IDs
        """
        if not self._redis:
            return []

        try:
            from tools.redis_state import redis_state_get

            key = self._get_signal_threads_key(signal_id)
            thread_id = redis_state_get(key)
            if thread_id:
                return [thread_id]
        except Exception as e:
            logger.warning(f"Failed to get threads for signal {signal_id}: {e}")

        return []

    async def list_active_threads(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ThreadMetadata]:
        """List active threads.

        Args:
            limit: Maximum number of threads to return
            offset: Number of threads to skip

        Returns:
            List of active thread metadata
        """
        if not self._redis:
            return list(self._metadata_cache.values())

        try:
            import json

            from tools.redis_state import redis_state_get, redis_state_scan_keys

            pattern = "community:discord:thread:*"
            keys = redis_state_scan_keys(pattern, count=limit + offset)
            threads = []

            for key in keys[offset : offset + limit]:
                key.split(":")[-1]  # thread_id for future use
                data = redis_state_get(key)
                if data:
                    metadata = ThreadMetadata.from_dict(json.loads(data))
                    if metadata.status == ThreadStatus.ACTIVE:
                        threads.append(metadata)

            return threads
        except Exception as e:
            logger.warning(f"Failed to list active threads: {e}")
            return []

    async def cleanup_expired_threads(self, max_age_days: int | None = None) -> int:
        """Archive threads older than max_age_days.

        Args:
            max_age_days: Maximum age in days (uses default if None)

        Returns:
            Number of threads archived
        """
        from datetime import timedelta

        max_age = max_age_days or self._default_archive_days
        cutoff = datetime.now(UTC) - timedelta(days=max_age)
        archived_count = 0

        active_threads = await self.list_active_threads(limit=1000)

        for metadata in active_threads:
            if metadata.created_at and metadata.created_at < cutoff:
                # Find thread ID from cache
                for thread_id, cached in self._metadata_cache.items():
                    if cached.signal_id == metadata.signal_id:
                        if await self.archive_thread(thread_id, "Expired"):
                            archived_count += 1
                        break

        logger.info(f"Archived {archived_count} expired threads")
        return archived_count
