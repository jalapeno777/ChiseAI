"""Alert suppression logic for risk threshold alerts.

Prevents alert spam by tracking last alert times and enforcing
minimum intervals between same alert types.

For ST-NS-016: Risk Threshold Alert System
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import RiskAlert

from .types import AlertState

logger = logging.getLogger(__name__)


class AlertSuppressor:
    """Suppresses risk alerts to prevent spam.

    Tracks last alert times per alert type and enforces minimum
    intervals between alerts of the same type.

    Thread-safe for concurrent access.
    """

    def __init__(self, min_interval_seconds: int = 300):
        """Initialize alert suppressor.

        Args:
            min_interval_seconds: Minimum seconds between same alert type
        """
        self.min_interval_seconds = min_interval_seconds
        self._alert_states: dict[str, AlertState] = {}
        self._lock = threading.RLock()

        logger.debug(
            f"AlertSuppressor initialized: min_interval={min_interval_seconds}s"
        )

    def should_send(self, alert: RiskAlert) -> bool:
        """Check if alert should be sent (not suppressed).

        Args:
            alert: Risk alert to check

        Returns:
            True if alert should be sent, False if suppressed
        """
        with self._lock:
            key = alert.alert_key
            now = datetime.now(UTC)

            if key not in self._alert_states:
                # First alert of this type
                self._alert_states[key] = AlertState(
                    last_alert_time=now,
                    alert_count=1,
                    suppressed_count=0,
                )
                logger.debug(f"First alert for {key}, allowing")
                return True

            state = self._alert_states[key]

            if state.last_alert_time is None:
                # Should not happen, but handle gracefully
                state.last_alert_time = now
                state.alert_count += 1
                return True

            # Calculate time since last alert
            elapsed = (now - state.last_alert_time).total_seconds()

            if elapsed >= self.min_interval_seconds:
                # Enough time has passed, allow alert
                state.last_alert_time = now
                state.alert_count += 1
                logger.debug(
                    f"Alert allowed for {key}: {elapsed:.0f}s since last alert"
                )
                return True
            else:
                # Too soon, suppress
                state.suppressed_count += 1
                remaining = self.min_interval_seconds - elapsed
                logger.debug(
                    f"Alert suppressed for {key}: {elapsed:.0f}s since last, "
                    f"{remaining:.0f}s remaining"
                )
                return False

    def force_send(self, alert: RiskAlert) -> None:
        """Force send an alert, bypassing suppression.

        Args:
            alert: Risk alert to force send
        """
        with self._lock:
            key = alert.alert_key
            now = datetime.now(UTC)

            if key not in self._alert_states:
                self._alert_states[key] = AlertState(
                    last_alert_time=now,
                    alert_count=1,
                    suppressed_count=0,
                )
            else:
                self._alert_states[key].last_alert_time = now
                self._alert_states[key].alert_count += 1

            logger.debug(f"Forced alert for {key}")

    def get_state(self, alert_key: str) -> AlertState | None:
        """Get alert state for a given key.

        Args:
            alert_key: Alert key to look up

        Returns:
            AlertState if found, None otherwise
        """
        with self._lock:
            return self._alert_states.get(alert_key)

    def get_time_until_next_allowed(self, alert_key: str) -> float:
        """Get seconds until next alert of this type is allowed.

        Args:
            alert_key: Alert key to check

        Returns:
            Seconds until next alert allowed (0 if allowed now)
        """
        with self._lock:
            if alert_key not in self._alert_states:
                return 0.0

            state = self._alert_states[alert_key]
            if state.last_alert_time is None:
                return 0.0

            elapsed = (datetime.now(UTC) - state.last_alert_time).total_seconds()
            remaining = self.min_interval_seconds - elapsed

            return max(0.0, remaining)

    def reset(self, alert_key: str | None = None) -> None:
        """Reset alert state.

        Args:
            alert_key: Specific key to reset, or None to reset all
        """
        with self._lock:
            if alert_key is None:
                self._alert_states.clear()
                logger.debug("Reset all alert states")
            elif alert_key in self._alert_states:
                del self._alert_states[alert_key]
                logger.debug(f"Reset alert state for {alert_key}")

    def get_stats(self) -> dict:
        """Get suppression statistics.

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            total_alerts = sum(s.alert_count for s in self._alert_states.values())
            total_suppressed = sum(
                s.suppressed_count for s in self._alert_states.values()
            )

            return {
                "min_interval_seconds": self.min_interval_seconds,
                "tracked_alert_types": len(self._alert_states),
                "total_alerts_sent": total_alerts,
                "total_alerts_suppressed": total_suppressed,
                "alert_states": {
                    key: state.to_dict() for key, state in self._alert_states.items()
                },
            }
