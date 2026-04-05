"""Signal deduplication module.

Provides Redis-backed signal deduplication to prevent duplicate signals
from being processed multiple times within a configurable time window.

Thread-safe implementation suitable for clustered deployments.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


# Redis key patterns for dedup state
_DEDUP_KEY_PREFIX = "chiseai:dedup:signals"
_DEDUP_SEEN_KEY = f"{_DEDUP_KEY_PREFIX}:seen"


@dataclass
class DedupResult:
    """Result of a deduplication check.

    Attributes:
        is_duplicate: True if signal was a duplicate
        signal_id: The signal's unique identifier
        window_start: Start of the dedup window (if duplicate)
        window_end: End of the dedup window (if duplicate)
    """

    is_duplicate: bool
    signal_id: str
    window_start: float | None = None
    window_end: float | None = None


class SignalDeduper:
    """Redis-backed signal deduplicator.

    Prevents duplicate signals from being processed multiple times
    within a configurable time window using Redis for state tracking.

    Thread-safe for concurrent access from multiple processes/nodes.

    Attributes:
        dedup_window_seconds: Time window for deduplication (default 60s)
        redis_host: Redis host address
        redis_port: Redis port
        redis_db: Redis database number
    """

    DEFAULT_DEDUP_WINDOW_SECONDS = 60.0

    def __init__(
        self,
        dedup_window_seconds: float | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int | None = None,
    ):
        """Initialize signal deduplicator.

        Args:
            dedup_window_seconds: Deduplication window in seconds (default 60)
            redis_host: Redis host (defaults to host.docker.internal)
            redis_port: Redis port (defaults to 6380)
            redis_db: Redis DB number (defaults to 0)
        """
        self.dedup_window_seconds = (
            dedup_window_seconds
            if dedup_window_seconds is not None
            else self.DEFAULT_DEDUP_WINDOW_SECONDS
        )
        self.redis_host = redis_host or "host.docker.internal"
        self.redis_port = redis_port or 6380
        self.redis_db = redis_db if redis_db is not None else 0

        self._redis_client: Any | None = None
        self._local_cache: dict[str, float] = {}  # signal_id -> expiry time
        self._cache_lock = threading.Lock()
        self._initialized = False

    def _get_redis_client(self) -> Any | None:
        """Get or create Redis client.

        Returns:
            Redis client or None if connection fails
        """
        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis

            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            # Test connection
            client.ping()
            self._redis_client = client
            logger.debug("Redis dedup client connected")
            return client
        except Exception as e:
            logger.warning(f"SignalDeduper: Redis connection failed: {e}")
            return None

    def _prune_local_cache(self) -> None:
        """Remove expired entries from local cache."""
        now = time.time()
        with self._cache_lock:
            expired = [sid for sid, exp in self._local_cache.items() if exp <= now]
            for sid in expired:
                del self._local_cache[sid]

    def _check_local_cache(self, signal_id: str) -> bool:
        """Check if signal_id is in local cache and not expired.

        Args:
            signal_id: Signal identifier to check

        Returns:
            True if duplicate found in local cache
        """
        self._prune_local_cache()
        with self._cache_lock:
            if signal_id in self._local_cache:
                return True
        return False

    def _add_to_local_cache(self, signal_id: str) -> None:
        """Add signal_id to local cache with expiry.

        Args:
            signal_id: Signal identifier to cache
        """
        expiry = time.time() + self.dedup_window_seconds
        with self._cache_lock:
            self._local_cache[signal_id] = expiry

    def _check_redis(self, signal_id: str) -> tuple[bool, float | None, float | None]:
        """Check Redis for duplicate signal.

        Args:
            signal_id: Signal identifier to check

        Returns:
            Tuple of (is_duplicate, window_start, window_end)
        """
        client = self._get_redis_client()
        if client is None:
            return False, None, None

        try:
            key = f"{_DEDUP_SEEN_KEY}:{signal_id}"
            now = time.time()
            window_end = now + self.dedup_window_seconds

            # Use SET NX EX (set if not exists with expiry)
            # Returns True if key was set (not duplicate), None if key exists (duplicate)
            was_set = client.set(key, now, nx=True, ex=int(self.dedup_window_seconds))

            if was_set:
                # Key was set - not a duplicate
                return False, None, None
            else:
                # Key exists - this is a duplicate
                # Get the original timestamp for window info
                try:
                    original_ts = float(client.get(key))
                    window_start = original_ts
                    return True, window_start, window_end
                except (TypeError, ValueError):
                    # Key expired between check - treat as not duplicate
                    return False, None, None

        except Exception as e:
            logger.warning(f"SignalDeduper: Redis check failed: {e}")
            return False, None, None

    def is_duplicate(self, signal: Signal) -> DedupResult:
        """Check if a signal is a duplicate.

        First checks local cache for fast path, then falls back to Redis
        for cluster-safe deduplication.

        Args:
            signal: Signal to check for duplication

        Returns:
            DedupResult with duplicate status and metadata
        """
        signal_id = signal.signal_id
        if not signal_id:
            logger.warning("SignalDeduper: Signal missing signal_id, allowing through")
            return DedupResult(is_duplicate=False, signal_id="")

        # Fast path: check local cache first
        if self._check_local_cache(signal_id):
            now = time.time()
            return DedupResult(
                is_duplicate=True,
                signal_id=signal_id,
                window_start=now - self.dedup_window_seconds,
                window_end=now,
            )

        # Cluster-safe path: check Redis
        is_dup, window_start, window_end = self._check_redis(signal_id)

        if is_dup:
            return DedupResult(
                is_duplicate=True,
                signal_id=signal_id,
                window_start=window_start,
                window_end=window_end,
            )

        # Not a duplicate - add to local cache for fast future checks
        self._add_to_local_cache(signal_id)

        return DedupResult(is_duplicate=False, signal_id=signal_id)

    def mark_seen(self, signal: Signal) -> bool:
        """Explicitly mark a signal as seen (for batch processing).

        Args:
            signal: Signal to mark as seen

        Returns:
            True if successfully marked, False otherwise
        """
        signal_id = signal.signal_id
        if not signal_id:
            return False

        client = self._get_redis_client()
        if client is None:
            # Fall back to local cache only
            self._add_to_local_cache(signal_id)
            return True

        try:
            key = f"{_DEDUP_SEEN_KEY}:{signal_id}"
            now = time.time()
            client.set(key, now, ex=int(self.dedup_window_seconds))
            self._add_to_local_cache(signal_id)
            return True
        except Exception as e:
            logger.warning(f"SignalDeduper: Failed to mark seen: {e}")
            # Fall back to local cache
            self._add_to_local_cache(signal_id)
            return True

    def clear(self, signal_id: str | None = None) -> int:
        """Clear deduplication state.

        Args:
            signal_id: Specific signal to clear, or None to clear all

        Returns:
            Number of entries cleared
        """
        if signal_id:
            # Clear specific signal
            with self._cache_lock:
                if signal_id in self._local_cache:
                    del self._local_cache[signal_id]

            client = self._get_redis_client()
            if client:
                try:
                    key = f"{_DEDUP_SEEN_KEY}:{signal_id}"
                    client.delete(key)
                except Exception as e:
                    logger.warning(f"SignalDeduper: Failed to clear key: {e}")
            return 1
        else:
            # Clear all (local cache only - Redis uses TTL)
            with self._cache_lock:
                count = len(self._local_cache)
                self._local_cache.clear()
            return count

    def get_stats(self) -> dict[str, Any]:
        """Get deduplication statistics.

        Returns:
            Dictionary with dedup stats
        """
        with self._cache_lock:
            local_count = len(self._local_cache)

        client = self._get_redis_client()
        redis_keys = 0
        if client:
            with contextlib.suppress(Exception):
                redis_keys = len(
                    list(client.scan_iter(f"{_DEDUP_SEEN_KEY}:*", count=1000))
                )

        return {
            "dedup_window_seconds": self.dedup_window_seconds,
            "local_cache_entries": local_count,
            "redis_keys": redis_keys,
            "redis_available": client is not None,
        }


def filter_duplicates(
    signals: list[Signal], deduper: SignalDeduper | None = None
) -> tuple[list[Signal], list[DedupResult]]:
    """Filter duplicate signals from a list.

    Args:
        signals: List of signals to filter
        deduper: SignalDeduper instance (creates default if None)

    Returns:
        Tuple of (unique_signals, dedup_results)
    """
    if deduper is None:
        deduper = SignalDeduper()

    unique_signals = []
    dedup_results = []

    for signal in signals:
        result = deduper.is_duplicate(signal)
        dedup_results.append(result)
        if not result.is_duplicate:
            unique_signals.append(signal)

    return unique_signals, dedup_results
