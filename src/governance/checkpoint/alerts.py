"""Checkpoint alert system for governance monitoring.

This module provides alert classes for detecting and reporting
anomalous conditions in the trading system.

Alerts:
- ActionableZeroAlert: Detects when signals are generated but none are actionable
  for a sustained period, indicating potential filtering or strategy issues.

Story: BATCH3-ACTIONABLE-ZERO-002
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlertResult:
    """Result of an alert check.

    Attributes:
        alert_name: Name of the alert that was checked
        triggered: Whether the alert condition was met
        suppressed: Whether the alert was suppressed (already fired recently)
        message: Human-readable alert message
        severity: Alert severity level (INFO, WARNING, CRITICAL)
        metadata: Additional context about the alert
        timestamp: When the check was performed
    """

    alert_name: str
    triggered: bool
    suppressed: bool = False
    message: str = ""
    severity: str = "INFO"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)


class ActionableZeroAlert:
    """Alert for detecting actionable-zero conditions.

    This alert fires when signals are being generated but none are actionable
    for a sustained period (3 consecutive 15-minute windows = 45 minutes).

    Threshold Configuration:
        - CONSECUTIVE_WINDOWS: Number of consecutive windows with actionable=0
          before alerting (default: 3 = 45 minutes)
        - SUPPRESSION_INTERVAL: Minimum time between alerts (default: 1 hour)

    Redis State:
        Stored at key: bmad:chiseai:checkpoint:actionable_zero_alert
        Fields:
            - consecutive_windows: Count of consecutive actionable-zero windows
            - last_alert_time: ISO timestamp of last alert (for suppression)
            - last_check_time: ISO timestamp of last check
            - window_signals: JSON array of signal counts per window

    Alert Message Format:
        🚨 ACTIONABLE-ZERO ALERT
        Signals generated: N (15m window)
        Actionable signals: 0
        Duration: 45+ minutes
        Possible causes:
        - Confidence thresholds too high
        - Market conditions not matching strategy criteria
        - Signal filtering logic issue
    """

    # Alert configuration
    ALERT_NAME = "actionable_zero"
    REDIS_KEY = "bmad:chiseai:checkpoint:actionable_zero_alert"

    # Thresholds
    DEFAULT_CONSECUTIVE_WINDOWS = 3  # 3 x 15m = 45 minutes
    DEFAULT_SUPPRESSION_HOURS = 1

    # Severity levels
    SEVERITY_INFO = "INFO"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_CRITICAL = "CRITICAL"

    def __init__(
        self,
        redis_client: Any | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        consecutive_windows: int | None = None,
        suppression_hours: int | None = None,
    ):
        """Initialize the actionable-zero alert.

        Args:
            redis_client: Optional Redis client instance
            redis_host: Redis host (defaults to env or host.docker.internal)
            redis_port: Redis port (defaults to env or 6380)
            consecutive_windows: Number of consecutive windows before alerting
            suppression_hours: Minimum hours between alerts
        """
        self._redis = redis_client
        self._redis_host = redis_host or os.getenv(
            "MONITORING_REDIS_HOST", os.getenv("REDIS_HOST", "host.docker.internal")
        )
        self._redis_port = redis_port or int(
            os.getenv("MONITORING_REDIS_PORT", os.getenv("REDIS_PORT", "6380"))
        )
        self._consecutive_windows = consecutive_windows or int(
            os.getenv(
                "ACTIONABLE_ZERO_CONSECUTIVE_WINDOWS", self.DEFAULT_CONSECUTIVE_WINDOWS
            )
        )
        self._suppression_hours = suppression_hours or int(
            os.getenv(
                "ACTIONABLE_ZERO_SUPPRESSION_HOURS", self.DEFAULT_SUPPRESSION_HOURS
            )
        )

    def _get_redis(self) -> Any | None:
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            import redis as redis_lib

            self._redis = redis_lib.Redis(
                host=self._redis_host,
                port=self._redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            return self._redis
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def _load_state(self) -> dict[str, Any]:
        """Load alert state from Redis.

        Returns:
            Dictionary with state fields, or empty dict if no state exists
        """
        r = self._get_redis()
        if not r:
            return {}

        try:
            state = r.hgetall(self.REDIS_KEY)
            if not state:
                return {}

            # Parse JSON fields
            if "window_signals" in state:
                try:
                    state["window_signals"] = json.loads(state["window_signals"])
                except json.JSONDecodeError:
                    state["window_signals"] = []

            # Parse integer fields
            if "consecutive_windows" in state:
                try:
                    state["consecutive_windows"] = int(state["consecutive_windows"])
                except ValueError:
                    state["consecutive_windows"] = 0

            return state
        except Exception as e:
            logger.error(f"Failed to load alert state: {e}")
            return {}

    def _save_state(self, state: dict[str, Any]) -> bool:
        """Save alert state to Redis.

        Args:
            state: Dictionary with state fields to save

        Returns:
            True if saved successfully, False otherwise
        """
        r = self._get_redis()
        if not r:
            return False

        try:
            # Convert list to JSON
            save_state = state.copy()
            if "window_signals" in save_state and isinstance(
                save_state["window_signals"], list
            ):
                save_state["window_signals"] = json.dumps(save_state["window_signals"])

            r.hset(self.REDIS_KEY, mapping=save_state)
            return True
        except Exception as e:
            logger.error(f"Failed to save alert state: {e}")
            return False

    def _is_suppressed(self, state: dict[str, Any]) -> bool:
        """Check if alert should be suppressed.

        Args:
            state: Current alert state

        Returns:
            True if alert should be suppressed, False otherwise
        """
        last_alert_str = state.get("last_alert_time")
        if not last_alert_str:
            return False

        try:
            last_alert = datetime.fromisoformat(last_alert_str)
            now = datetime.now(UTC)
            elapsed = now - last_alert
            suppression_interval = timedelta(hours=self._suppression_hours)

            return elapsed < suppression_interval
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse last_alert_time: {e}")
            return False

    def _build_alert_message(
        self, signals_15m: int, consecutive_windows: int, duration_minutes: int
    ) -> str:
        """Build the alert message.

        Args:
            signals_15m: Number of signals in the current 15m window
            consecutive_windows: Number of consecutive actionable-zero windows
            duration_minutes: Total duration in minutes

        Returns:
            Formatted alert message
        """
        return (
            f"🚨 ACTIONABLE-ZERO ALERT\n"
            f"Signals generated: {signals_15m} (15m window)\n"
            f"Actionable signals: 0\n"
            f"Duration: {duration_minutes}+ minutes ({consecutive_windows} consecutive windows)\n"
            f"Possible causes:\n"
            f"- Confidence thresholds too high\n"
            f"- Market conditions not matching strategy criteria\n"
            f"- Signal filtering logic issue"
        )

    def check(self, signals_15m: int, actionable_15m: int) -> AlertResult:
        """Check the actionable-zero condition.

        This method implements the alert logic:
        1. If signals > 0 and actionable == 0: increment consecutive counter
        2. If consecutive >= threshold and not suppressed: fire alert
        3. If actionable > 0: reset consecutive counter

        Args:
            signals_15m: Number of signals generated in the 15m window
            actionable_15m: Number of actionable signals in the 15m window

        Returns:
            AlertResult with the check outcome
        """
        now = datetime.now(UTC)
        state = self._load_state()

        # Initialize state if empty
        if not state:
            state = {
                "consecutive_windows": 0,
                "window_signals": [],
            }

        consecutive = int(state.get("consecutive_windows", 0))
        window_signals = state.get("window_signals", [])
        if not isinstance(window_signals, list):
            window_signals = []

        # Check condition: signals > 0 but actionable == 0
        if signals_15m > 0 and actionable_15m == 0:
            consecutive += 1
            window_signals.append(signals_15m)

            # Keep only recent window history (for debugging)
            if len(window_signals) > 10:
                window_signals = window_signals[-10:]

            # Update state
            state["consecutive_windows"] = consecutive
            state["window_signals"] = window_signals
            state["last_check_time"] = now.isoformat()

            # Check if threshold reached
            if consecutive >= self._consecutive_windows:
                # Check suppression
                if self._is_suppressed(state):
                    self._save_state(state)
                    return AlertResult(
                        alert_name=self.ALERT_NAME,
                        triggered=True,
                        suppressed=True,
                        message=f"Actionable-zero condition detected ({consecutive} windows) - suppressed",
                        severity=self.SEVERITY_WARNING,
                        metadata={
                            "consecutive_windows": consecutive,
                            "signals_15m": signals_15m,
                            "threshold": self._consecutive_windows,
                            "suppressed": True,
                        },
                        timestamp=now,
                    )

                # Fire alert
                duration_minutes = consecutive * 15
                message = self._build_alert_message(
                    signals_15m, consecutive, duration_minutes
                )

                # Update last alert time
                state["last_alert_time"] = now.isoformat()
                self._save_state(state)

                return AlertResult(
                    alert_name=self.ALERT_NAME,
                    triggered=True,
                    suppressed=False,
                    message=message,
                    severity=self.SEVERITY_CRITICAL,
                    metadata={
                        "consecutive_windows": consecutive,
                        "signals_15m": signals_15m,
                        "threshold": self._consecutive_windows,
                        "duration_minutes": duration_minutes,
                        "suppressed": False,
                    },
                    timestamp=now,
                )

            # Threshold not yet reached
            self._save_state(state)
            return AlertResult(
                alert_name=self.ALERT_NAME,
                triggered=False,
                suppressed=False,
                message=f"Actionable-zero count: {consecutive}/{self._consecutive_windows}",
                severity=self.SEVERITY_INFO,
                metadata={
                    "consecutive_windows": consecutive,
                    "signals_15m": signals_15m,
                    "threshold": self._consecutive_windows,
                },
                timestamp=now,
            )

        else:
            # Reset condition: actionable signals detected or no signals
            if consecutive > 0:
                logger.info(
                    f"Actionable-zero condition cleared after {consecutive} windows "
                    f"(actionable={actionable_15m}, signals={signals_15m})"
                )

            # Reset state
            state["consecutive_windows"] = 0
            state["window_signals"] = []
            state["last_check_time"] = now.isoformat()
            self._save_state(state)

            return AlertResult(
                alert_name=self.ALERT_NAME,
                triggered=False,
                suppressed=False,
                message="Actionable-zero condition not present",
                severity=self.SEVERITY_INFO,
                metadata={
                    "consecutive_windows": 0,
                    "signals_15m": signals_15m,
                    "actionable_15m": actionable_15m,
                    "previous_consecutive": consecutive,
                },
                timestamp=now,
            )

    def get_state(self) -> dict[str, Any]:
        """Get current alert state.

        Returns:
            Dictionary with current state
        """
        return self._load_state()

    def reset_state(self) -> bool:
        """Reset alert state to initial values.

        Returns:
            True if reset successfully, False otherwise
        """
        r = self._get_redis()
        if not r:
            return False

        try:
            r.delete(self.REDIS_KEY)
            logger.info(f"Reset actionable-zero alert state")
            return True
        except Exception as e:
            logger.error(f"Failed to reset alert state: {e}")
            return False

    def manual_suppression_clear(self) -> bool:
        """Manually clear the suppression state.

        This allows the next actionable-zero condition to trigger an alert
        even if within the suppression window.

        Returns:
            True if cleared successfully, False otherwise
        """
        state = self._load_state()
        if "last_alert_time" in state:
            del state["last_alert_time"]
            return self._save_state(state)
        return True
