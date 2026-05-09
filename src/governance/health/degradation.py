"""
Degradation Tracker - Graduated health degradation detection (ST-MVP-005).

Provides:
- Sliding-window health score tracking per component
- Rate-of-change (slope) calculation for health trend detection
- Four-level degradation classification: STABLE, MILD, MODERATE, SEVERE
- Redis-backed state persistence with in-memory fallback
- Degradation transition event emission

Story: ST-MVP-005
"""

from __future__ import annotations

import json
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

logger = logging.getLogger(__name__)

# Redis key pattern for degradation state
DEGRADATION_KEY_PREFIX = "bmad:chiseai:health:degradation"
DEGRADATION_TTL_SECONDS = 3600  # 1 hour


class DegradationLevel(Enum):
    """Graduated degradation severity levels."""

    STABLE = "stable"
    MILD_DEGRADATION = "mild_degradation"
    MODERATE_DEGRADATION = "moderate_degradation"
    SEVERE_DEGRADATION = "severe_degradation"


@dataclass
class DegradationEvent:
    """Event emitted when degradation level changes."""

    component: str
    previous_level: DegradationLevel
    new_level: DegradationLevel
    slope: float
    window_scores: list[float]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Convert event to dictionary."""
        return {
            "component": self.component,
            "previous_level": self.previous_level.value,
            "new_level": self.new_level.value,
            "slope": round(self.slope, 4),
            "window_scores": self.window_scores,
            "timestamp": self.timestamp.isoformat(),
        }


class DegradationTracker:
    """Tracks health score degradation trends over a sliding window.

    Maintains a configurable sliding window of health scores and calculates
    the rate of change (slope) to classify degradation severity. Supports
    Redis-backed persistence with graceful fallback to in-memory tracking.

    Usage:
        tracker = DegradationTracker(window_size=5)
        tracker.record("scheduler", 95.0)
        tracker.record("scheduler", 90.0)
        level = tracker.get_level("scheduler")  # DegradationLevel.STABLE
    """

    # Slope thresholds (points per sample)
    # Positive slope = improving; negative = degrading
    SLOPE_STABLE_THRESHOLD = -0.5
    SLOPE_MILD_THRESHOLD = -2.0
    SLOPE_MODERATE_THRESHOLD = -5.0

    def __init__(
        self,
        window_size: int = 5,
        redis_client=None,
    ):
        """Initialize the degradation tracker.

        Args:
            window_size: Number of health score samples to track (default: 5).
            redis_client: Optional Redis client for state persistence.
        """
        self.window_size = window_size
        self.redis_client = redis_client

        # In-memory tracking: component -> deque of scores
        self._windows: dict[str, deque[float]] = {}
        # Current levels per component
        self._levels: dict[str, DegradationLevel] = {}

    def record(self, component: str, score: float) -> DegradationLevel | None:
        """Record a health score sample and update degradation level.

        Args:
            component: Component identifier (e.g., "scheduler", "agent-1").
            score: Health score (0-100).

        Returns:
            New DegradationLevel if level changed, None otherwise.
        """
        # Initialize window if needed
        if component not in self._windows:
            self._windows[component] = deque(maxlen=self.window_size)
            self._levels[component] = DegradationLevel.STABLE

        # Record the score
        self._windows[component].append(score)

        # Need at least 2 samples to calculate slope
        if len(self._windows[component]) < 2:
            self._persist_state(component)
            return None

        # Calculate slope and classify
        previous_level = self._levels[component]
        new_level = self.classify(list(self._windows[component]))

        self._levels[component] = new_level
        self._persist_state(component)

        # Emit event on transition
        if new_level != previous_level:
            slope = self._calculate_slope(list(self._windows[component]))
            event = DegradationEvent(
                component=component,
                previous_level=previous_level,
                new_level=new_level,
                slope=slope,
                window_scores=list(self._windows[component]),
            )
            logger.info(
                f"Degradation transition for {component}: "
                f"{previous_level.value} -> {new_level.value} "
                f"(slope={slope:.2f})"
            )
            return new_level

        return None

    def get_level(self, component: str) -> DegradationLevel:
        """Get current degradation level for a component.

        Args:
            component: Component identifier.

        Returns:
            Current DegradationLevel (STABLE if unknown).
        """
        return self._levels.get(component, DegradationLevel.STABLE)

    def get_slope(self, component: str) -> float | None:
        """Get current slope for a component.

        Args:
            component: Component identifier.

        Returns:
            Current slope value or None if insufficient data.
        """
        window = self._windows.get(component)
        if window is None or len(window) < 2:
            return None
        return self._calculate_slope(list(window))

    def get_window(self, component: str) -> list[float]:
        """Get current score window for a component.

        Args:
            component: Component identifier.

        Returns:
            List of recent health scores (may be empty).
        """
        window = self._windows.get(component)
        return list(window) if window else []

    def classify(self, scores: list[float]) -> DegradationLevel:
        """Classify degradation level from a list of health scores.

        Calculates the slope (rate of change) of the scores using
        least-squares linear regression and maps it to a degradation level.

        Thresholds:
            STABLE:          slope >= -0.5
            MILD_DEGRADATION: -0.5 > slope >= -2.0
            MODERATE_DEGRADATION: -2.0 > slope >= -5.0
            SEVERE_DEGRADATION: slope < -5.0

        Args:
            scores: List of health scores (at least 2 recommended).

        Returns:
            DegradationLevel classification.
        """
        if len(scores) < 2:
            return DegradationLevel.STABLE

        slope = self._calculate_slope(scores)

        if slope >= self.SLOPE_STABLE_THRESHOLD:
            return DegradationLevel.STABLE
        elif slope >= self.SLOPE_MILD_THRESHOLD:
            return DegradationLevel.MILD_DEGRADATION
        elif slope >= self.SLOPE_MODERATE_THRESHOLD:
            return DegradationLevel.MODERATE_DEGRADATION
        else:
            return DegradationLevel.SEVERE_DEGRADATION

    @staticmethod
    def _calculate_slope(scores: list[float]) -> float:
        """Calculate the linear regression slope of scores over time.

        Uses ordinary least squares (OLS) to fit y = mx + b where
        x is the sample index (0, 1, 2, ...) and y is the score.

        Args:
            scores: List of health scores.

        Returns:
            Slope (rate of change per sample). Returns 0.0 if undefined.
        """
        n = len(scores)
        if n < 2:
            return 0.0

        x_indices = list(range(n))
        x_mean = (n - 1) / 2.0
        y_mean = sum(scores) / n

        # Calculate covariance and variance
        numerator = 0.0
        denominator = 0.0
        for i, y in zip(x_indices, scores):
            numerator += (i - x_mean) * (y - y_mean)
            denominator += (i - x_mean) ** 2

        if denominator == 0.0:
            return 0.0

        return numerator / denominator

    def get_all_levels(self) -> dict[str, DegradationLevel]:
        """Get degradation levels for all tracked components.

        Returns:
            Dict mapping component names to their DegradationLevel.
        """
        return dict(self._levels)

    def is_severe(self, component: str) -> bool:
        """Check if a component has severe degradation.

        Args:
            component: Component identifier.

        Returns:
            True if degradation level is SEVERE_DEGRADATION.
        """
        return self.get_level(component) == DegradationLevel.SEVERE_DEGRADATION

    def is_degrading(self, component: str) -> bool:
        """Check if a component has any level of degradation.

        Args:
            component: Component identifier.

        Returns:
            True if degradation level is not STABLE.
        """
        return self.get_level(component) != DegradationLevel.STABLE

    def reset(self, component: str | None = None) -> None:
        """Reset tracking state.

        Args:
            component: Component to reset, or None to reset all.
        """
        if component is None:
            self._windows.clear()
            self._levels.clear()
        else:
            self._windows.pop(component, None)
            self._levels.pop(component, None)

    def _persist_state(self, component: str) -> None:
        """Persist degradation state to Redis.

        Args:
            component: Component identifier.
        """
        if self.redis_client is None:
            return

        try:
            key = f"{DEGRADATION_KEY_PREFIX}:{component}"
            state = {
                "component": component,
                "level": self._levels[component].value,
                "window": list(self._windows[component]),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self.redis_client.setex(
                key,
                DEGRADATION_TTL_SECONDS,
                json.dumps(state),
            )
        except Exception as e:
            logger.debug(f"Failed to persist degradation state for {component}: {e}")

    def restore_state(self, component: str) -> bool:
        """Restore degradation state from Redis.

        Args:
            component: Component identifier.

        Returns:
            True if state was successfully restored.
        """
        if self.redis_client is None:
            return False

        try:
            key = f"{DEGRADATION_KEY_PREFIX}:{component}"
            raw = self.redis_client.get(key)
            if raw is None:
                return False

            state = json.loads(raw)
            level_str = state.get("level", "stable")

            # Restore level
            self._levels[component] = DegradationLevel(level_str)

            # Restore window
            window_data = state.get("window", [])
            self._windows[component] = deque(
                window_data[-self.window_size :],
                maxlen=self.window_size,
            )

            logger.debug(f"Restored degradation state for {component}: {level_str}")
            return True

        except Exception as e:
            logger.debug(f"Failed to restore degradation state for {component}: {e}")
            return False
