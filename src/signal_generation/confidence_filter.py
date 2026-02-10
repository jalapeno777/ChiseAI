"""Confidence filter for signal threshold enforcement.

Implements the 75% actionable threshold filter for signals.
Signals below 75% are logged but not surfaced as actionable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of confidence filtering.

    Attributes:
        is_actionable: Whether signal meets actionable threshold
        threshold: The confidence threshold used (0.0-1.0)
        confidence: The signal's confidence score
        reason: Explanation of filter decision
    """

    is_actionable: bool
    threshold: float
    confidence: float
    reason: str


class ConfidenceFilter:
    """Filter signals based on confidence threshold.

    Default threshold is 75% (0.75) for actionable signals.
    Signals below threshold are logged but not surfaced.

    Threshold can be configured via:
    1. Constructor parameter
    2. SIGNAL_CONFIDENCE_THRESHOLD environment variable
    3. Default value (0.75)
    """

    DEFAULT_THRESHOLD = 0.75
    MIN_THRESHOLD = 0.50
    MAX_THRESHOLD = 0.95

    def __init__(self, threshold: float | None = None):
        """Initialize confidence filter.

        Args:
            threshold: Optional custom threshold (0.0-1.0).
                If not provided, uses environment variable or default.
        """
        self.threshold = self._resolve_threshold(threshold)
        logger.info(
            f"ConfidenceFilter initialized with threshold: {self.threshold:.0%}"
        )

    def _resolve_threshold(self, override: float | None) -> float:
        """Resolve threshold from override, env var, or default.

        Args:
            override: Optional threshold override

        Returns:
            Resolved threshold value
        """
        if override is not None:
            return self._clamp_threshold(override)

        env_threshold = os.getenv("SIGNAL_CONFIDENCE_THRESHOLD")
        if env_threshold:
            try:
                return self._clamp_threshold(float(env_threshold))
            except ValueError:
                logger.warning(
                    f"Invalid SIGNAL_CONFIDENCE_THRESHOLD: {env_threshold}, "
                    f"using default {self.DEFAULT_THRESHOLD}"
                )

        return self.DEFAULT_THRESHOLD

    def _clamp_threshold(self, threshold: float) -> float:
        """Clamp threshold to valid range.

        Args:
            threshold: Proposed threshold value

        Returns:
            Clamped threshold
        """
        clamped = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, threshold))
        if clamped != threshold:
            logger.warning(
                f"Threshold {threshold} clamped to valid range "
                f"[{self.MIN_THRESHOLD}, {self.MAX_THRESHOLD}]"
            )
        return clamped

    def filter(self, signal: Signal) -> FilterResult:
        """Filter a signal based on confidence threshold.

        Args:
            signal: The signal to filter

        Returns:
            FilterResult with decision and explanation
        """
        confidence = signal.confidence

        if confidence >= self.threshold:
            return FilterResult(
                is_actionable=True,
                threshold=self.threshold,
                confidence=confidence,
                reason=(
                    f"Signal confidence {confidence:.1%} meets threshold "
                    f"{self.threshold:.0%}"
                ),
            )
        else:
            return FilterResult(
                is_actionable=False,
                threshold=self.threshold,
                confidence=confidence,
                reason=(
                    f"Signal confidence {confidence:.1%} below threshold "
                    f"{self.threshold:.0%} - logged only"
                ),
            )

    def should_emit(self, signal: Signal) -> bool:
        """Quick check if signal should be emitted.

        Args:
            signal: The signal to check

        Returns:
            True if signal meets actionable threshold
        """
        return bool(signal.confidence >= self.threshold)

    def log_non_actionable(self, signal: Signal) -> None:
        """Log a non-actionable signal for audit purposes.

        Args:
            signal: The non-actionable signal to log
        """
        logger.info(
            f"Non-actionable signal: {signal.token} [{signal.direction_str}] "
            f"confidence={signal.confidence:.1%} (threshold={self.threshold:.0%})"
        )

    def get_threshold_percent(self) -> float:
        """Get threshold as percentage (0-100)."""
        return self.threshold * 100
