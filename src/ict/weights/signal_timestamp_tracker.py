"""Signal Timestamp Tracker for ICT signals.

Tracks ICT signal timestamps for dynamic weight adjustment calculations.
Provides Redis-backed storage for signal timestamps to enable time-based
weight decay across the signal generation pipeline.

Integration:
    - Used by DynamicWeightAdjuster for age calculations
    - Integrates with ICT signal registry (ST-ICT-015)
    - Stores timestamps in Redis for cross-process access

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import redis


@dataclass
class TrackedSignal:
    """A tracked ICT signal with timestamp information.

    Attributes:
        signal_id: Unique identifier for the signal
        signal_type: Type of ICT signal (cvd, fvg, order_block)
        token: Trading pair (e.g., BTC/USDT)
        timeframe: Timeframe string (e.g., 1H, 4H)
        timestamp: Unix timestamp when signal was created
        direction: Signal direction (bullish/bearish/neutral)
        confluence_score: Optional confluence score if already calculated
        metadata: Additional signal metadata
    """

    signal_id: str
    signal_type: str
    token: str
    timeframe: str
    timestamp: float
    direction: str = "neutral"
    confluence_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "token": self.token,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "confluence_score": self.confluence_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedSignal:
        """Create from dictionary."""
        return cls(
            signal_id=data["signal_id"],
            signal_type=data["signal_type"],
            token=data["token"],
            timeframe=data["timeframe"],
            timestamp=float(data["timestamp"]),
            direction=data.get("direction", "neutral"),
            confluence_score=data.get("confluence_score"),
            metadata=data.get("metadata", {}),
        )

    def get_age_seconds(self, current_time: float | None = None) -> float:
        """Calculate signal age in seconds.

        Args:
            current_time: Current timestamp (UTC epoch). If None, uses now.

        Returns:
            Age of signal in seconds
        """
        if current_time is None:
            current_time = datetime.now(UTC).timestamp()
        return current_time - self.timestamp


class SignalTimestampTracker:
    """Tracks ICT signal timestamps for dynamic weight adjustment.

    Provides Redis-backed storage and retrieval of signal timestamps
    to enable accurate age calculations for the time-decay algorithm.

    Storage Format:
        Key: ict:signals:tracked:{signal_id}
        Value: JSON serialized TrackedSignal

    Index Keys:
        ict:signals:index:{token}:{timeframe} -> Set of signal_ids

    Usage:
        tracker = SignalTimestampTracker(redis_client)
        tracker.track_signal(signal)
        age = tracker.get_signal_age(signal_id)
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        key_prefix: str = "ict:signals:tracked",
        index_prefix: str = "ict:signals:index",
        ttl_seconds: int = 3600,  # 1 hour default TTL
    ):
        """Initialize signal timestamp tracker.

        Args:
            redis_client: Redis client instance. If None, creates new connection.
            key_prefix: Prefix for signal keys
            index_prefix: Prefix for index keys
            ttl_seconds: Time-to-live for tracked signals (default: 1 hour)
        """
        self.key_prefix = key_prefix
        self.index_prefix = index_prefix
        self.ttl_seconds = ttl_seconds
        self._redis = redis_client

    @property
    def redis(self) -> redis.Redis:
        """Get Redis client, creating if necessary."""
        if self._redis is None:
            import redis

            self._redis = redis.Redis(
                host="host.docker.internal",
                port=6380,
                db=1,
                decode_responses=True,
            )
        return self._redis

    def _signal_key(self, signal_id: str) -> str:
        """Generate Redis key for a signal."""
        return f"{self.key_prefix}:{signal_id}"

    def _index_key(self, token: str, timeframe: str) -> str:
        """Generate Redis key for token/timeframe index."""
        return f"{self.index_prefix}:{token}:{timeframe}"

    def track_signal(self, signal: TrackedSignal) -> bool:
        """Track a new ICT signal.

        Args:
            signal: TrackedSignal to store

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            key = self._signal_key(signal.signal_id)
            value = json.dumps(signal.to_dict())

            # Store signal with TTL
            self.redis.setex(key, self.ttl_seconds, value)

            # Add to index
            index_key = self._index_key(signal.token, signal.timeframe)
            self.redis.sadd(index_key, signal.signal_id)
            self.redis.expire(index_key, self.ttl_seconds)

            logger.debug(f"Tracked signal {signal.signal_id}: {signal.signal_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to track signal {signal.signal_id}: {e}")
            return False

    def get_signal(self, signal_id: str) -> TrackedSignal | None:
        """Retrieve a tracked signal by ID.

        Args:
            signal_id: The signal ID to retrieve

        Returns:
            TrackedSignal if found, None otherwise
        """
        try:
            key = self._signal_key(signal_id)
            data = self.redis.get(key)

            if data is None:
                return None

            return TrackedSignal.from_dict(json.loads(data))

        except Exception as e:
            logger.error(f"Failed to get signal {signal_id}: {e}")
            return None

    def get_signal_age(
        self, signal_id: str, current_time: float | None = None
    ) -> float | None:
        """Get the age of a signal in seconds.

        Args:
            signal_id: The signal ID to check
            current_time: Current timestamp (UTC epoch). If None, uses now.

        Returns:
            Age in seconds if signal found, None otherwise
        """
        signal = self.get_signal(signal_id)
        if signal is None:
            return None
        return signal.get_age_seconds(current_time)

    def get_signals_for_token_timeframe(
        self,
        token: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[TrackedSignal]:
        """Get all tracked signals for a token/timeframe combination.

        Args:
            token: Trading pair (e.g., BTC/USDT)
            timeframe: Timeframe string (e.g., 1H, 4H)
            limit: Maximum number of signals to return

        Returns:
            List of TrackedSignals ordered by timestamp (newest first)
        """
        try:
            index_key = self._index_key(token, timeframe)
            signal_ids = self.redis.srandmember(index_key, count=limit)

            if not signal_ids:
                return []

            signals = []
            for sid in signal_ids:
                signal = self.get_signal(sid)
                if signal is not None:
                    signals.append(signal)

            # Sort by timestamp descending (newest first)
            signals.sort(key=lambda s: s.timestamp, reverse=True)
            return signals

        except Exception as e:
            logger.error(f"Failed to get signals for {token}/{timeframe}: {e}")
            return []

    def remove_signal(self, signal_id: str) -> bool:
        """Remove a tracked signal.

        Args:
            signal_id: The signal ID to remove

        Returns:
            True if removed successfully, False otherwise
        """
        try:
            signal = self.get_signal(signal_id)
            if signal is None:
                return False

            # Remove from index
            index_key = self._index_key(signal.token, signal.timeframe)
            self.redis.srem(index_key, signal_id)

            # Remove signal
            key = self._signal_key(signal_id)
            self.redis.delete(key)

            logger.debug(f"Removed signal {signal_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove signal {signal_id}: {e}")
            return False

    def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """Clean up expired signals from indices.

        Args:
            max_age_seconds: Maximum age for signals to keep

        Returns:
            Number of signals cleaned up
        """
        current_time = datetime.now(UTC).timestamp()
        cleaned = 0

        try:
            # Scan for all index keys
            pattern = f"{self.index_prefix}:*"
            for key in self.redis.scan_iter(match=pattern):
                # Get all signal IDs from this index
                signal_ids = self.redis.smembers(key)

                for sid in signal_ids:
                    age = self.get_signal_age(sid, current_time)
                    if age is not None and age > max_age_seconds:
                        self.remove_signal(sid)
                        cleaned += 1

        except Exception as e:
            logger.error(f"Failed to cleanup expired signals: {e}")

        return cleaned


# Global tracker instance
_tracker_instance: SignalTimestampTracker | None = None


def get_timestamp_tracker() -> SignalTimestampTracker:
    """Get or create the global SignalTimestampTracker instance.

    Returns:
        Global SignalTimestampTracker instance
    """
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SignalTimestampTracker()
    return _tracker_instance
