"""Duplicate alert suppressor.

Prevents duplicate Discord alerts within a configurable time window
using in-memory tracking with thread-safe operations.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _now() -> float:
    """Time provider for records (kept as a function for testability)."""

    return time.time()


@dataclass
class AlertRecord:
    """Record of a sent alert for deduplication.

    Attributes:
        signal_id: Unique signal identifier
        token: Trading pair token
        direction: Signal direction
        timestamp: When the alert was sent
        confidence: Signal confidence at time of alert
    """

    signal_id: str
    token: str
    direction: str
    timestamp: float = field(default_factory=_now)
    confidence: float = 0.0


class DuplicateSuppressor:
    """Suppresses duplicate alerts within a time window.

    Uses in-memory tracking with automatic cleanup of old entries.
    Thread-safe for concurrent access.

    Attributes:
        window_seconds: Deduplication window in seconds
        enable_suppression: Whether suppression is enabled
    """

    DEFAULT_WINDOW_SECONDS = 900  # 15 minutes per requirements

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        enable_suppression: bool = True,
    ):
        """Initialize duplicate suppressor.

        Args:
            window_seconds: Time window for deduplication (default 15 min)
            enable_suppression: Whether to enable suppression
        """
        self.window_seconds = window_seconds
        self.enable_suppression = enable_suppression

        # In-memory storage: key -> AlertRecord
        self._alerts: dict[str, AlertRecord] = {}
        self._lock = threading.RLock()

        logger.debug(
            f"DuplicateSuppressor initialized: window={window_seconds}s, "
            f"enabled={enable_suppression}"
        )

    def _make_key(self, token: str, direction: str) -> str:
        """Create deduplication key from alert parameters.

        Args:
            token: Trading pair token
            direction: Signal direction

        Returns:
            Deduplication key string
        """
        return f"{token}:{direction.upper()}"

    def is_duplicate(
        self,
        token: str,
        direction: str,
        signal_id: str | None = None,
    ) -> bool:
        """Check if an alert would be a duplicate.

        Args:
            token: Trading pair token
            direction: Signal direction
            signal_id: Optional signal ID for exact match

        Returns:
            True if this would be a duplicate, False otherwise
        """
        if not self.enable_suppression:
            return False

        with self._lock:
            # Clean up old entries first
            self._cleanup_old_entries()

            key = self._make_key(token, direction)

            if key not in self._alerts:
                return False

            record = self._alerts[key]
            age = time.time() - record.timestamp

            # Check if within suppression window
            if age > self.window_seconds:
                return False

            # If signal_id provided, check for exact match
            if signal_id and record.signal_id == signal_id:
                logger.debug(
                    f"Exact duplicate detected: {key} (signal_id: {signal_id})"
                )
                return True

            # Same token+direction within window is a duplicate
            logger.debug(
                f"Duplicate detected: {key} (age={age:.1f}s, "
                f"window={self.window_seconds}s)"
            )
            return True

    def record_alert(
        self,
        token: str,
        direction: str,
        signal_id: str,
        confidence: float = 0.0,
    ) -> None:
        """Record an alert as sent.

        Args:
            token: Trading pair token
            direction: Signal direction
            signal_id: Unique signal identifier
            confidence: Signal confidence
        """
        with self._lock:
            key = self._make_key(token, direction)

            self._alerts[key] = AlertRecord(
                signal_id=signal_id,
                token=token,
                direction=direction.upper(),
                confidence=confidence,
            )

            logger.debug(f"Recorded alert: {key} (signal_id: {signal_id})")

    def should_send(
        self,
        token: str,
        direction: str,
        signal_id: str,
        confidence: float = 0.0,
    ) -> bool:
        """Check if alert should be sent and record it.

        This is a convenience method that combines is_duplicate() and
        record_alert() in a thread-safe manner.

        Args:
            token: Trading pair token
            direction: Signal direction
            signal_id: Unique signal identifier
            confidence: Signal confidence

        Returns:
            True if alert should be sent, False if suppressed
        """
        if not self.enable_suppression:
            # Still record for tracking purposes
            self.record_alert(token, direction, signal_id, confidence)
            return True

        with self._lock:
            if self.is_duplicate(token, direction, signal_id):
                return False

            self.record_alert(token, direction, signal_id, confidence)
            return True

    def _cleanup_old_entries(self) -> int:
        """Remove expired entries from the alert history.

        Returns:
            Number of entries removed
        """
        now = time.time()
        cutoff = now - self.window_seconds

        expired_keys = [
            key for key, record in self._alerts.items() if record.timestamp < cutoff
        ]

        for key in expired_keys:
            del self._alerts[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired alert records")

        return len(expired_keys)

    def cleanup(self) -> int:
        """Explicitly clean up old entries.

        Returns:
            Number of entries removed
        """
        with self._lock:
            return self._cleanup_old_entries()

    def clear(self) -> None:
        """Clear all alert records."""
        with self._lock:
            count = len(self._alerts)
            self._alerts.clear()
            logger.debug(f"Cleared {count} alert records")

    def get_stats(self) -> dict[str, Any]:
        """Get suppression statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            self._cleanup_old_entries()

            return {
                "enabled": self.enable_suppression,
                "window_seconds": self.window_seconds,
                "active_records": len(self._alerts),
                "unique_tokens": len(set(r.token for r in self._alerts.values())),
            }

    def get_recent_alerts(
        self,
        token: str | None = None,
        max_age_seconds: float | None = None,
    ) -> list[AlertRecord]:
        """Get recent alert records.

        Args:
            token: Optional token filter
            max_age_seconds: Optional max age filter

        Returns:
            List of recent alert records
        """
        with self._lock:
            self._cleanup_old_entries()

            now = time.time()
            max_age = max_age_seconds or self.window_seconds

            records = []
            for record in self._alerts.values():
                age = now - record.timestamp
                if age <= max_age and (token is None or record.token == token):
                    records.append(record)

            return sorted(records, key=lambda r: r.timestamp, reverse=True)
