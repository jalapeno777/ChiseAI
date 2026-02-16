"""Dynamic Threshold Adjuster for ChiseAI Calibration System.

This module provides the DynamicThresholdAdjuster class for automatically
adjusting thresholds based on ECE (Expected Calibration Error) monitoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ml.calibration.controller import ThresholdController

logger = logging.getLogger(__name__)


# Threshold adjustment limits
MIN_THRESHOLD: float = 0.40
MAX_THRESHOLD: float = 0.95
MAX_ADJUSTMENT_PER_STEP: float = 0.05  # Max change per adjustment
ECE_DEGRADATION_THRESHOLD: float = 0.15  # ECE > 15% triggers increase
ECE_IMPROVEMENT_THRESHOLD: float = 0.05  # ECE < 5% allows decrease
MIN_SAMPLES_FOR_ADJUSTMENT: int = 30


@dataclass
class ThresholdAdjustment:
    """Record of a threshold adjustment.

    Attributes:
        timestamp: When the adjustment was made
        signal_type: Type of signal adjusted
        old_threshold: Previous threshold
        new_threshold: New threshold
        change_amount: Amount of change
        ece_before: ECE before adjustment
        ece_after: ECE after adjustment (estimated)
        reason: Reason for adjustment
    """

    timestamp: datetime
    signal_type: str
    old_threshold: float
    new_threshold: float
    change_amount: float
    ece_before: float
    ece_after: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "old_threshold": round(self.old_threshold, 4),
            "new_threshold": round(self.new_threshold, 4),
            "change_amount": round(self.change_amount, 4),
            "ece_before": round(self.ece_before, 6),
            "ece_after": round(self.ece_after, 6) if self.ece_after else None,
            "reason": self.reason,
        }


class DynamicThresholdAdjuster:
    """Automatically adjusts thresholds based on ECE monitoring.

    The adjuster monitors ECE (Expected Calibration Error) for each signal type
    and automatically adjusts thresholds to maintain calibration quality.

    Adjustment Logic:
    - If ECE > 0.15 (poor calibration): Increase threshold to filter lower confidence signals
    - If ECE < 0.05 (good calibration): Decrease threshold to allow more signals
    - Changes are capped at +- 0.05 per adjustment to prevent oscillation
    - Threshold bounds: 0.40 (min) to 0.95 (max)

    Example:
        >>> from ml.calibration import ThresholdController, ThresholdMode
        >>> from ml.calibration.optimizer import ThresholdOptimizer
        >>> controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)
        >>> adjuster = DynamicThresholdAdjuster(controller, ece_threshold=0.15)
        >>> # Monitor and adjust
        >>> adjustment = adjuster.monitor_and_adjust()
    """

    def __init__(
        self,
        controller: "ThresholdController",
        ece_threshold: float = 0.15,
        min_samples: int = MIN_SAMPLES_FOR_ADJUSTMENT,
    ):
        """Initialize the dynamic threshold adjuster.

        Args:
            controller: ThresholdController instance to adjust
            ece_threshold: ECE threshold for triggering adjustments
            min_samples: Minimum samples required for valid adjustment
        """
        self.controller = controller
        self.ece_threshold = ece_threshold
        self.min_samples = min_samples

        # Track last adjustment time per signal type
        self._last_adjustment: dict[str, datetime] = {}

        # Track adjustment history
        self._adjustment_history: list[ThresholdAdjustment] = []

        logger.info(
            f"DynamicThresholdAdjuster initialized with ECE threshold {ece_threshold}"
        )

    @property
    def adjustment_history(self) -> list[ThresholdAdjustment]:
        """Get adjustment history."""
        return self._adjustment_history.copy()

    def monitor_and_adjust(
        self,
        signal_types: list[str] | None = None,
    ) -> ThresholdAdjustment | None:
        """Monitor ECE and adjust thresholds if needed.

        Args:
            signal_types: List of signal types to check (default: all)

        Returns:
            ThresholdAdjustment if made, None otherwise
        """
        if signal_types is None:
            signal_types = ["LONG", "SHORT", "SCALP"]

        adjustments_made = []

        for signal_type in signal_types:
            adjustment = self._check_and_adjust(signal_type)
            if adjustment:
                adjustments_made.append(adjustment)

        if len(adjustments_made) == 1:
            return adjustments_made[0]
        elif adjustments_made:
            return adjustments_made[0]  # Return first for backward compatibility

        return None

    def _check_and_adjust(self, signal_type: str) -> ThresholdAdjustment | None:
        """Check ECE for a signal type and adjust if needed.

        Args:
            signal_type: Type of signal to check

        Returns:
            Adjustment if made, None otherwise
        """
        # Check for ECE degradation
        if not self.check_ece_degradation(signal_type):
            return None

        # Get current ECE and threshold
        current_ece = self.controller._last_ece.get(signal_type, 1.0)
        current_threshold = self.controller.get_current_threshold(signal_type)

        # Calculate new threshold
        new_threshold = self.calculate_adjustment(signal_type, current_ece)

        # Apply adjustment if significant
        change = new_threshold - current_threshold
        if abs(change) < 0.01:
            return None

        # Apply the adjustment
        old_threshold = current_threshold
        self.controller.set_threshold(
            signal_type=signal_type,
            value=new_threshold,
            reason=f"ece_degradation: ECE={current_ece:.4f}",
            log_change=True,
        )

        # Record adjustment
        adjustment = ThresholdAdjustment(
            timestamp=datetime.now(timezone.utc),
            signal_type=signal_type,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            change_amount=change,
            ece_before=current_ece,
            ece_after=None,  # Will be updated after next check
            reason=f"ECE degraded to {current_ece:.4f}",
        )

        self._adjustment_history.append(adjustment)
        self._last_adjustment[signal_type] = adjustment.timestamp

        logger.info(
            f"Adjusted threshold for {signal_type}: "
            f"{old_threshold:.2f} -> {new_threshold:.2f} (ECE: {current_ece:.4f})"
        )

        return adjustment

    def check_ece_degradation(self, signal_type: str) -> bool:
        """Check if ECE has degraded beyond threshold.

        Args:
            signal_type: Type of signal to check

        Returns:
            True if ECE exceeds threshold (poor calibration)
        """
        return self.controller.check_ece_degradation(signal_type, self.ece_threshold)

    def calculate_adjustment(
        self,
        signal_type: str,
        current_ece: float,
    ) -> float:
        """Calculate new threshold based on current ECE.

        Args:
            signal_type: Type of signal
            current_ece: Current ECE value

        Returns:
            New threshold value
        """
        current_threshold = self.controller.get_current_threshold(signal_type)

        if current_ece > self.ece_threshold:
            # ECE is too high (poor calibration)
            # Increase threshold to filter lower confidence signals
            # Higher ECE = more aggressive increase
            if current_ece > 0.25:
                adjustment = MAX_ADJUSTMENT_PER_STEP  # Max increase
            elif current_ece > 0.20:
                adjustment = MAX_ADJUSTMENT_PER_STEP * 0.8
            elif current_ece > 0.15:
                adjustment = MAX_ADJUSTMENT_PER_STEP * 0.5
            else:
                adjustment = MAX_ADJUSTMENT_PER_STEP * 0.3

            new_threshold = current_threshold + adjustment

        elif current_ece < ECE_IMPROVEMENT_THRESHOLD:
            # ECE is very low (excellent calibration)
            # Can afford to decrease threshold to allow more signals
            adjustment = MAX_ADJUSTMENT_PER_STEP * 0.3
            new_threshold = current_threshold - adjustment

        else:
            # ECE is acceptable, no adjustment needed
            return current_threshold

        # Clamp to valid range
        new_threshold = max(MIN_THRESHOLD, min(MAX_THRESHOLD, new_threshold))

        return new_threshold

    def get_current_ece(self, signal_type: str) -> float | None:
        """Get current ECE for a signal type.

        Args:
            signal_type: Type of signal

        Returns:
            Current ECE value or None if not available
        """
        return self.controller._last_ece.get(signal_type)

    def get_adjustment_summary(self) -> dict[str, Any]:
        """Get summary of adjustments made.

        Returns:
            Dictionary with adjustment statistics
        """
        if not self._adjustment_history:
            return {
                "total_adjustments": 0,
                "by_signal_type": {},
                "last_adjustment": None,
            }

        by_signal_type: dict[str, int] = {}
        for adj in self._adjustment_history:
            by_signal_type[adj.signal_type] = by_signal_type.get(adj.signal_type, 0) + 1

        return {
            "total_adjustments": len(self._adjustment_history),
            "by_signal_type": by_signal_type,
            "last_adjustment": (
                self._adjustment_history[-1].timestamp.isoformat()
                if self._adjustment_history
                else None
            ),
            "avg_change_amount": float(
                np.mean([abs(a.change_amount) for a in self._adjustment_history])
            ),
        }

    def reset_adjustments(self) -> None:
        """Reset adjustment history."""
        self._adjustment_history.clear()
        self._last_adjustment.clear()
        logger.info("Adjustment history reset")


def calculate_optimal_adjustment(
    current_ece: float,
    current_threshold: float,
    ece_threshold: float = ECE_DEGRADATION_THRESHOLD,
) -> float:
    """Calculate optimal threshold adjustment based on ECE.

    This is a utility function for computing threshold adjustments
    without needing a full controller instance.

    Args:
        current_ece: Current ECE value
        current_threshold: Current threshold value
        ece_threshold: Target ECE threshold

    Returns:
        Adjusted threshold value
    """
    if current_ece > ece_threshold:
        # Poor calibration - increase threshold
        if current_ece > 0.25:
            adjustment = MAX_ADJUSTMENT_PER_STEP
        elif current_ece > 0.20:
            adjustment = MAX_ADJUSTMENT_PER_STEP * 0.8
        elif current_ece > 0.15:
            adjustment = MAX_ADJUSTMENT_PER_STEP * 0.5
        else:
            adjustment = MAX_ADJUSTMENT_PER_STEP * 0.3
    elif current_ece < ECE_IMPROVEMENT_THRESHOLD:
        # Good calibration - can decrease threshold
        adjustment = -MAX_ADJUSTMENT_PER_STEP * 0.3
    else:
        return current_threshold

    new_threshold = current_threshold + adjustment
    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, new_threshold))


__all__ = [
    "DynamicThresholdAdjuster",
    "ThresholdAdjustment",
    "calculate_optimal_adjustment",
    # Constants
    "MIN_THRESHOLD",
    "MAX_THRESHOLD",
    "MAX_ADJUSTMENT_PER_STEP",
    "ECE_DEGRADATION_THRESHOLD",
    "ECE_IMPROVEMENT_THRESHOLD",
    "MIN_SAMPLES_FOR_ADJUSTMENT",
]
