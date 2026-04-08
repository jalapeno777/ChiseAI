"""ICT Session Manager - Redis-backed session state for ICT signal cache.

Session windows:
- London: 08:00-17:00 UTC
- NY: 13:30-18:00 UTC
- Configurable via env vars

Redis key pattern: chiseai:ict:session:{session_id}
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

import redis

logger = logging.getLogger(__name__)

# Redis key prefix for ICT sessions
REDIS_KEY_PREFIX = "chiseai:ict:session"

# Default session windows (UTC)
DEFAULT_LONDON_START = "08:00"
DEFAULT_LONDON_END = "17:00"
DEFAULT_NY_START = "13:30"
DEFAULT_NY_END = "18:00"

# Environment-configurable session windows
LONDON_START = os.getenv("ICT_LONDON_START", DEFAULT_LONDON_START)
LONDON_END = os.getenv("ICT_LONDON_END", DEFAULT_LONDON_END)
NY_START = os.getenv("ICT_NY_START", DEFAULT_NY_START)
NY_END = os.getenv("ICT_NY_END", DEFAULT_NY_END)


class SessionType(Enum):
    """ICT session types."""

    LONDON = "london"
    NY = "ny"
    NONE = "none"


@dataclass
class ICTSession:
    """Represents an active ICT trading session.

    Attributes:
        session_type: Type of session (LONDON, NY, NONE)
        start_time: Session start time (UTC datetime)
        end_time: Session end time (UTC datetime)
        session_id: Unique session identifier (e.g., "london_20260407")
        signals_emitted: Number of signals emitted this session
        duplicate_count: Number of duplicate signals blocked
    """

    session_type: SessionType
    start_time: datetime
    end_time: datetime
    session_id: str
    signals_emitted: int = 0
    duplicate_count: int = 0

    def is_active(self, current_time: datetime | None = None) -> bool:
        """Check if session is currently active.

        Args:
            current_time: Time to check (defaults to now UTC)

        Returns:
            True if current time is within session bounds
        """
        if self.session_type == SessionType.NONE:
            return False
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        return self.start_time <= current_time <= self.end_time

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_type": self.session_type.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "session_id": self.session_id,
            "signals_emitted": self.signals_emitted,
            "duplicate_count": self.duplicate_count,
        }


@dataclass
class ICTSessionStats:
    """Session statistics for reporting."""

    current_session: ICTSession | None
    total_sessions: int
    total_signals: int
    total_duplicates: int
    session_type_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "current_session": (
                self.current_session.to_dict() if self.current_session else None
            ),
            "total_sessions": self.total_sessions,
            "total_signals": self.total_signals,
            "total_duplicates": self.total_duplicates,
            "session_type_counts": self.session_type_counts,
        }


def _parse_time(time_str: str) -> time:
    """Parse time string in HH:MM format.

    Args:
        time_str: Time string (e.g., "08:00")

    Returns:
        time object

    Raises:
        ValueError: If time string is invalid
    """
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time values: {time_str}")
    return time(hour=hour, minute=minute)


def _get_session_for_time(
    current_time: datetime, session_type: SessionType
) -> tuple[time, time]:
    """Get session bounds for a given session type.

    Args:
        current_time: Current UTC time
        session_type: Type of session

    Returns:
        Tuple of (start_time, end_time) as time objects
    """
    if session_type == SessionType.LONDON:
        return _parse_time(LONDON_START), _parse_time(LONDON_END)
    elif session_type == SessionType.NY:
        return _parse_time(NY_START), _parse_time(NY_END)
    else:
        return time(0, 0), time(0, 0)


class ICTSessionManager:
    """Redis-backed session manager for ICT signals.

    Manages trading session state with Redis persistence.
    Session windows are configurable via environment variables.

    Attributes:
        redis_client: Redis client instance
        key_prefix: Redis key prefix for session data
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        key_prefix: str = REDIS_KEY_PREFIX,
    ) -> None:
        """Initialize ICTSessionManager.

        Args:
            redis_client: Redis client instance (creates default if None)
            key_prefix: Redis key prefix for session data
        """
        if redis_client is None:
            self._redis: redis.Redis = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True,
            )
        else:
            self._redis = redis_client
        self._key_prefix = key_prefix
        self._utc = ZoneInfo("UTC")

    def _make_key(self, session_id: str) -> str:
        """Create Redis key for session.

        Args:
            session_id: Session identifier

        Returns:
            Full Redis key
        """
        return f"{self._key_prefix}:{session_id}"

    def _get_session_id_for_time(
        self, session_type: SessionType, current_time: datetime | None = None
    ) -> str:
        """Generate session ID for current time.

        Args:
            session_type: Type of session
            current_time: Current time (defaults to now UTC)

        Returns:
            Session ID string (e.g., "london_20260407")
        """
        if current_time is None:
            current_time = datetime.now(self._utc)
        date_str = current_time.strftime("%Y%m%d")
        return f"{session_type.value}_{date_str}"

    def _get_current_session_type(
        self, current_time: datetime | None = None
    ) -> SessionType:
        """Determine which session type is active.

        Args:
            current_time: Time to check (defaults to now UTC)

        Returns:
            Active session type or NONE
        """
        if current_time is None:
            current_time = datetime.now(self._utc)

        current_time_utc = current_time.astimezone(self._utc)
        current_time_only = current_time_utc.time()

        # Check London session
        london_start = _parse_time(LONDON_START)
        london_end = _parse_time(LONDON_END)
        if london_start <= current_time_only <= london_end:
            return SessionType.LONDON

        # Check NY session
        ny_start = _parse_time(NY_START)
        ny_end = _parse_time(NY_END)
        if ny_start <= current_time_only <= ny_end:
            return SessionType.NY

        return SessionType.NONE

    def get_current_session(self) -> ICTSession | None:
        """Get the current active session.

        Returns:
            Current ICTSession if within a session window, None otherwise
        """
        current_time = datetime.now(self._utc)
        session_type = self._get_current_session_type(current_time)

        if session_type == SessionType.NONE:
            return None

        start_t, end_t = _get_session_for_time(current_time, session_type)

        # Build session start/end datetimes for today
        start_dt = current_time.replace(
            hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0
        )
        end_dt = current_time.replace(
            hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0
        )

        session_id = self._get_session_id_for_time(session_type, current_time)

        # Try to load session state from Redis
        key = self._make_key(session_id)
        data = self._redis.hgetall(key)

        if data:
            signals_emitted = int(data.get("signals_emitted", 0))
            duplicate_count = int(data.get("duplicate_count", 0))
        else:
            signals_emitted = 0
            duplicate_count = 0

        return ICTSession(
            session_type=session_type,
            start_time=start_dt,
            end_time=end_dt,
            session_id=session_id,
            signals_emitted=signals_emitted,
            duplicate_count=duplicate_count,
        )

    def is_duplicate(self, signal_id: str) -> bool:
        """Check if signal_id has already been recorded.

        Args:
            signal_id: Unique signal identifier

        Returns:
            True if signal_id exists in current session
        """
        session = self.get_current_session()
        if session is None:
            # No active session - no duplicates tracked
            return False

        key = self._make_key(f"signals:{session.session_id}")
        return self._redis.sismember(key, signal_id)

    def record_signal(self, signal_id: str) -> None:
        """Record a signal in the current session.

        Args:
            signal_id: Unique signal identifier
        """
        session = self.get_current_session()
        if session is None:
            return

        # Add signal to session's signal set
        signals_key = self._make_key(f"signals:{session.session_id}")
        self._redis.sadd(signals_key, signal_id)
        # Set TTL of 25 hours to handle session boundary cleanup
        self._redis.expire(signals_key, 90000)

        # Increment session signal counter
        session_key = self._make_key(session.session_id)
        self._redis.hincrby(session_key, "signals_emitted", 1)
        self._redis.expire(session_key, 90000)

    def record_duplicate(self, signal_id: str) -> None:
        """Record a duplicate signal in the current session.

        Args:
            signal_id: Duplicate signal identifier
        """
        session = self.get_current_session()
        if session is None:
            return

        session_key = self._make_key(session.session_id)
        self._redis.hincrby(session_key, "duplicate_count", 1)

    def get_session_stats(self) -> dict[str, Any]:
        """Get session statistics.

        Returns:
            Dictionary with session stats
        """
        current_session = self.get_current_session()

        # Scan for all session keys to aggregate stats
        pattern = f"{self._key_prefix}:*"
        total_sessions = 0
        total_signals = 0
        total_duplicates = 0
        session_type_counts: dict[str, int] = {}

        for key in self._redis.scan_iter(match=pattern, count=100):
            # Skip signal sets
            if ":signals:" in key:
                continue

            data = self._redis.hgetall(key)
            if data:
                total_sessions += 1
                total_signals += int(data.get("signals_emitted", 0))
                total_duplicates += int(data.get("duplicate_count", 0))

                # Extract session type from key
                session_key = key.replace(f"{self._key_prefix}:", "")
                session_type = session_key.rsplit("_", 1)[0]
                session_type_counts[session_type] = (
                    session_type_counts.get(session_type, 0) + 1
                )

        stats = ICTSessionStats(
            current_session=current_session,
            total_sessions=total_sessions,
            total_signals=total_signals,
            total_duplicates=total_duplicates,
            session_type_counts=session_type_counts,
        )

        return stats.to_dict()

    def clear_session(self) -> None:
        """Clear the current session data from Redis."""
        session = self.get_current_session()
        if session is None:
            return

        # Delete session state
        session_key = self._make_key(session.session_id)
        self._redis.delete(session_key)

        # Delete signals set
        signals_key = self._make_key(f"signals:{session.session_id}")
        self._redis.delete(signals_key)
