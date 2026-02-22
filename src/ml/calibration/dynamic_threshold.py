"""Dynamic Threshold Adjustment Engine for ChiseAI Calibration System.

This module provides the DynamicThresholdEngine class for automatically adjusting
confidence thresholds based on ECE (Expected Calibration Error) monitoring with
daily granularity and enhanced guardrails.

Key Features:
- Velocity limits: Max ±5% change per day per strategy
- 24-hour cooldown period between adjustments
- Oscillation detection: 3+ direction changes in 7 days triggers 48h freeze
- ECE-based adjustment triggers when ECE > 0.10
- Full audit logging for all threshold changes

Acceptance Criteria:
- Max change ±5% per day (velocity limit)
- 24h cooldown between adjustments
- Oscillation detection: 3+ direction changes in 7 days triggers 48h freeze
- ECE-based adjustment when ECE > 0.10
- Manual override pauses auto-adjustment for 7 days
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from confidence.ece import SignalType

logger = logging.getLogger(__name__)


# Threshold adjustment limits
MIN_THRESHOLD: float = 0.40
MAX_THRESHOLD: float = 0.95
MAX_DAILY_CHANGE_PERCENT: float = 0.05  # Max ±5% change per day
ECE_ADJUSTMENT_THRESHOLD: float = 0.10  # ECE > 10% triggers adjustment
MIN_SAMPLES_FOR_ADJUSTMENT: int = 50

# Time constants
COOLDOWN_HOURS: int = 24  # 24-hour cooldown between adjustments
OSCILLATION_WINDOW_DAYS: int = 7  # Window to check for oscillation
OSCILLATION_FREEZE_HOURS: int = 48  # Freeze period after oscillation detected
OSCILLATION_DIRECTION_CHANGES: int = 3  # Min direction changes to trigger oscillation


class ECEProvider(Protocol):
    """Protocol for ECE data providers."""

    async def get_ece_for_strategy(
        self,
        strategy_id: str,
        signal_type: SignalType | None = None,
        days: int = 7,
    ) -> float | None:
        """Get ECE value for a strategy.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type filter (optional)
            days: Number of days to look back

        Returns:
            ECE value or None if not available
        """
        ...


@dataclass(frozen=True)
class ThresholdAdjustmentRecord:
    """Record of a single threshold adjustment.

    Attributes:
        timestamp: When the adjustment was made
        strategy_id: Strategy identifier
        signal_type: Type of signal adjusted
        old_threshold: Previous threshold
        new_threshold: New threshold
        change_amount: Amount of change (can be negative)
        change_percent: Percentage change from old value
        ece_before: ECE value before adjustment
        ece_after: ECE value after adjustment (if available)
        reason: Human-readable reason for the adjustment
        triggered_by: What triggered the adjustment ("ece_high", "manual", etc.)
    """

    timestamp: datetime
    strategy_id: str
    signal_type: SignalType
    old_threshold: float
    new_threshold: float
    change_amount: float
    change_percent: float
    ece_before: float
    ece_after: float | None
    reason: str
    triggered_by: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "strategy_id": self.strategy_id,
            "signal_type": self.signal_type.value,
            "old_threshold": round(self.old_threshold, 4),
            "new_threshold": round(self.new_threshold, 4),
            "change_amount": round(self.change_amount, 4),
            "change_percent": round(self.change_percent, 4),
            "ece_before": round(self.ece_before, 6),
            "ece_after": round(self.ece_after, 6) if self.ece_after else None,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }


@dataclass
class AdjustmentHistory:
    """Tracks adjustment history for oscillation detection.

    Attributes:
        adjustments: List of threshold adjustments
        max_history_days: Maximum days to keep in history
    """

    adjustments: list[ThresholdAdjustmentRecord] = field(default_factory=list)
    max_history_days: int = 30

    def add(self, adjustment: ThresholdAdjustmentRecord) -> None:
        """Add an adjustment to history."""
        self.adjustments.append(adjustment)
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        """Remove adjustments older than max_history_days."""
        cutoff = datetime.now(UTC) - timedelta(days=self.max_history_days)
        self.adjustments = [a for a in self.adjustments if a.timestamp >= cutoff]

    def get_recent_adjustments(
        self,
        strategy_id: str,
        signal_type: SignalType,
        days: int = 7,
    ) -> list[ThresholdAdjustmentRecord]:
        """Get recent adjustments for a specific strategy and signal type.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            days: Number of days to look back

        Returns:
            List of recent adjustments
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return [
            a
            for a in self.adjustments
            if a.strategy_id == strategy_id
            and a.signal_type == signal_type
            and a.timestamp >= cutoff
        ]

    def count_direction_changes(
        self,
        strategy_id: str,
        signal_type: SignalType,
        days: int = 7,
    ) -> int:
        """Count the number of direction changes in recent adjustments.

        A direction change occurs when the adjustment direction flips
        from increase to decrease or vice versa.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type
            days: Number of days to look back

        Returns:
            Number of direction changes
        """
        recent = self.get_recent_adjustments(strategy_id, signal_type, days)
        if len(recent) < 2:
            return 0

        # Sort by timestamp
        sorted_adjustments = sorted(recent, key=lambda a: a.timestamp)

        direction_changes = 0
        for i in range(1, len(sorted_adjustments)):
            prev_direction = 1 if sorted_adjustments[i - 1].change_amount > 0 else -1
            curr_direction = 1 if sorted_adjustments[i].change_amount > 0 else -1
            if prev_direction != curr_direction:
                direction_changes += 1

        return direction_changes


@dataclass
class DynamicThresholdConfig:
    """Configuration for dynamic threshold adjustment.

    Attributes:
        min_threshold: Minimum allowed threshold (default 0.40 = 40%)
        max_threshold: Maximum allowed threshold (default 0.95 = 95%)
        max_daily_change_percent: Max change per day (default 0.05 = 5%)
        ece_threshold: ECE threshold for triggering adjustment (default 0.10)
        cooldown_hours: Hours between adjustments (default 24)
        oscillation_window_days: Days to check for oscillation (default 7)
        oscillation_freeze_hours: Freeze period after oscillation (default 48)
        oscillation_direction_changes: Min direction changes to trigger (default 3)
        min_samples: Minimum samples for valid adjustment (default 50)
    """

    min_threshold: float = MIN_THRESHOLD
    max_threshold: float = MAX_THRESHOLD
    max_daily_change_percent: float = MAX_DAILY_CHANGE_PERCENT
    ece_threshold: float = ECE_ADJUSTMENT_THRESHOLD
    cooldown_hours: int = COOLDOWN_HOURS
    oscillation_window_days: int = OSCILLATION_WINDOW_DAYS
    oscillation_freeze_hours: int = OSCILLATION_FREEZE_HOURS
    oscillation_direction_changes: int = OSCILLATION_DIRECTION_CHANGES
    min_samples: int = MIN_SAMPLES_FOR_ADJUSTMENT

    def __post_init__(self):
        """Validate configuration."""
        if not 0.0 <= self.min_threshold <= 1.0:
            msg = f"min_threshold must be in [0, 1], got {self.min_threshold}"
            raise ValueError(msg)
        if not 0.0 <= self.max_threshold <= 1.0:
            msg = f"max_threshold must be in [0, 1], got {self.max_threshold}"
            raise ValueError(msg)
        if self.min_threshold >= self.max_threshold:
            msg = "min_threshold must be < max_threshold"
            raise ValueError(msg)


class DynamicThresholdEngine:
    """Automatically adjusts thresholds based on ECE with daily granularity.

    The engine monitors ECE (Expected Calibration Error) for each strategy
    and signal type, adjusting thresholds to maintain calibration quality.

    Adjustment Logic:
    - If ECE > 0.10 (poor calibration): Increase threshold by up to 5%
    - If ECE < 0.05 (good calibration): Decrease threshold by up to 5%
    - Max change per day: ±5%
    - Cooldown period: 24 hours between adjustments
    - Oscillation detection: 3+ direction changes in 7 days triggers 48h freeze

    Threshold bounds: 0.40 (min) to 0.95 (max)

    Example:
        >>> from ml.calibration.dynamic_threshold import DynamicThresholdEngine
        >>> engine = DynamicThresholdEngine(ece_provider=ece_provider)
        >>> result = await engine.evaluate_and_adjust(
        ...     strategy_id="grid_btc_1h",
        ...     signal_type=SignalType.ENTRY,
        ...     current_threshold=0.65
        ... )
    """

    def __init__(
        self,
        ece_provider: ECEProvider | None = None,
        config: DynamicThresholdConfig | None = None,
    ):
        """Initialize the dynamic threshold engine.

        Args:
            ece_provider: Provider for ECE data
            config: Configuration for adjustment parameters
        """
        self.ece_provider = ece_provider
        self.config = config or DynamicThresholdConfig()
        self._history = AdjustmentHistory()
        self._last_adjustment: dict[tuple[str, SignalType], datetime] = {}
        self._freeze_until: dict[tuple[str, SignalType], datetime] = {}

        logger.info(
            f"DynamicThresholdEngine initialized: "
            f"max_daily_change={self.config.max_daily_change_percent:.1%}, "
            f"ece_threshold={self.config.ece_threshold:.2f}, "
            f"cooldown={self.config.cooldown_hours}h"
        )

    @property
    def adjustment_history(self) -> list[ThresholdAdjustmentRecord]:
        """Get adjustment history."""
        return self._history.adjustments.copy()

    async def evaluate_and_adjust(
        self,
        strategy_id: str,
        signal_type: SignalType,
        current_threshold: float,
    ) -> ThresholdAdjustmentRecord | None:
        """Evaluate ECE and adjust threshold if needed.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type to evaluate
            current_threshold: Current threshold value

        Returns:
            ThresholdAdjustmentRecord if adjustment was made, None otherwise
        """
        # Check if frozen due to oscillation
        if self._is_frozen(strategy_id, signal_type):
            freeze_until = self._freeze_until.get((strategy_id, signal_type))
            logger.debug(
                f"Adjustment blocked for {strategy_id}/{signal_type.value}: "
                f"frozen until {freeze_until}"
            )
            return None

        # Check cooldown period
        if not self._check_cooldown(strategy_id, signal_type):
            return None

        # Get current ECE
        if self.ece_provider is None:
            logger.warning("No ECE provider configured")
            return None

        ece = await self.ece_provider.get_ece_for_strategy(
            strategy_id=strategy_id,
            signal_type=signal_type,
            days=7,
        )

        if ece is None:
            logger.debug(f"No ECE data available for {strategy_id}/{signal_type.value}")
            return None

        # Check if adjustment is needed
        if not self._should_adjust(ece):
            logger.debug(
                f"No adjustment needed for {strategy_id}/{signal_type.value}: "
                f"ECE={ece:.4f}"
            )
            return None

        # Calculate new threshold
        new_threshold = self._calculate_new_threshold(current_threshold, ece)

        # Check if change is significant
        change = new_threshold - current_threshold
        if abs(change) < 0.005:  # Less than 0.5% change is not significant
            logger.debug(
                f"Change too small for {strategy_id}/{signal_type.value}: {change:.4f}"
            )
            return None

        # Apply velocity limit
        change = self._apply_velocity_limit(current_threshold, change)
        new_threshold = current_threshold + change

        # Create adjustment record
        adjustment = ThresholdAdjustmentRecord(
            timestamp=datetime.now(UTC),
            strategy_id=strategy_id,
            signal_type=signal_type,
            old_threshold=current_threshold,
            new_threshold=new_threshold,
            change_amount=change,
            change_percent=(
                (change / current_threshold * 100) if current_threshold > 0 else 0
            ),
            ece_before=ece,
            ece_after=None,
            reason=(
                f"ECE={ece:.4f} "
                f"{'>' if ece > self.config.ece_threshold else '<'} threshold"
            ),
            triggered_by=("ece_high" if ece > self.config.ece_threshold else "ece_low"),
        )

        # Record adjustment
        self._history.add(adjustment)
        self._last_adjustment[(strategy_id, signal_type)] = adjustment.timestamp

        # Check for oscillation after adjustment
        self._check_and_apply_oscillation_freeze(strategy_id, signal_type)

        logger.info(
            f"Threshold adjusted for {strategy_id}/{signal_type.value}: "
            f"{current_threshold:.4f} -> {new_threshold:.4f} "
            f"({change:+.2%}) [ECE={ece:.4f}]"
        )

        return adjustment

    def _is_frozen(self, strategy_id: str, signal_type: SignalType) -> bool:
        """Check if adjustments are frozen due to oscillation.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            True if currently frozen
        """
        freeze_until = self._freeze_until.get((strategy_id, signal_type))
        if freeze_until is None:
            return False
        return datetime.now(UTC) < freeze_until

    def _check_cooldown(self, strategy_id: str, signal_type: SignalType) -> bool:
        """Check if cooldown period has elapsed.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            True if cooldown has elapsed or no previous adjustment
        """
        last_adjustment = self._last_adjustment.get((strategy_id, signal_type))
        if last_adjustment is None:
            return True

        elapsed = datetime.now(UTC) - last_adjustment
        cooldown_required = timedelta(hours=self.config.cooldown_hours)

        if elapsed < cooldown_required:
            remaining = cooldown_required - elapsed
            logger.debug(
                f"Cooldown active for {strategy_id}/{signal_type.value}: "
                f"{remaining.total_seconds() / 3600:.1f}h remaining"
            )
            return False

        return True

    def _should_adjust(self, ece: float) -> bool:
        """Check if adjustment is needed based on ECE.

        Args:
            ece: Current ECE value

        Returns:
            True if adjustment should be made
        """
        return ece > self.config.ece_threshold or ece < 0.05

    def _calculate_new_threshold(self, current_threshold: float, ece: float) -> float:
        """Calculate new threshold based on ECE.

        Args:
            current_threshold: Current threshold value
            ece: Current ECE value

        Returns:
            New threshold value
        """
        if ece > self.config.ece_threshold:
            # ECE is too high (poor calibration)
            # Increase threshold to filter lower confidence signals
            # Scale adjustment based on how far ECE exceeds threshold
            excess = ece - self.config.ece_threshold
            if excess > 0.10:  # ECE > 0.20
                adjustment = self.config.max_daily_change_percent
            elif excess > 0.05:  # ECE > 0.15
                adjustment = self.config.max_daily_change_percent * 0.75
            else:
                adjustment = self.config.max_daily_change_percent * 0.50

            new_threshold = current_threshold + adjustment

        elif ece < 0.05:
            # ECE is very low (excellent calibration)
            # Can afford to decrease threshold to allow more signals
            adjustment = self.config.max_daily_change_percent * 0.5
            new_threshold = current_threshold - adjustment

        else:
            # ECE is acceptable, no adjustment needed
            return current_threshold

        # Clamp to valid range
        new_threshold = max(
            self.config.min_threshold, min(self.config.max_threshold, new_threshold)
        )

        return new_threshold

    def _apply_velocity_limit(
        self, current_threshold: float, proposed_change: float
    ) -> float:
        """Apply velocity limit to proposed change.

        Args:
            current_threshold: Current threshold value
            proposed_change: Proposed change amount

        Returns:
            Change amount within velocity limits
        """
        max_change = current_threshold * self.config.max_daily_change_percent

        if proposed_change > max_change:
            return max_change
        elif proposed_change < -max_change:
            return -max_change

        return proposed_change

    def _check_and_apply_oscillation_freeze(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> bool:
        """Check for oscillation and apply freeze if detected.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            True if oscillation was detected and freeze applied
        """
        direction_changes = self._history.count_direction_changes(
            strategy_id, signal_type, self.config.oscillation_window_days
        )

        if direction_changes >= self.config.oscillation_direction_changes:
            freeze_until = datetime.now(UTC) + timedelta(
                hours=self.config.oscillation_freeze_hours
            )
            self._freeze_until[(strategy_id, signal_type)] = freeze_until

            logger.warning(
                f"Oscillation detected for {strategy_id}/{signal_type.value}: "
                f"{direction_changes} direction changes in "
                f"{self.config.oscillation_window_days} days. "
                f"Freezing adjustments until {freeze_until}"
            )
            return True

        return False

    def get_time_until_next_adjustment(
        self,
        strategy_id: str,
        signal_type: SignalType,
    ) -> timedelta | None:
        """Get time until next adjustment is allowed.

        Args:
            strategy_id: Strategy identifier
            signal_type: Signal type

        Returns:
            Time until next adjustment, or None if adjustment is allowed now
        """
        # Check freeze
        freeze_until = self._freeze_until.get((strategy_id, signal_type))
        if freeze_until and datetime.now(UTC) < freeze_until:
            return freeze_until - datetime.now(UTC)

        # Check cooldown
        last_adjustment = self._last_adjustment.get((strategy_id, signal_type))
        if last_adjustment is None:
            return None

        elapsed = datetime.now(UTC) - last_adjustment
        cooldown = timedelta(hours=self.config.cooldown_hours)

        if elapsed < cooldown:
            return cooldown - elapsed

        return None

    def get_adjustment_summary(self) -> dict[str, Any]:
        """Get summary of adjustments made.

        Returns:
            Dictionary with adjustment statistics
        """
        adjustments = self._history.adjustments

        if not adjustments:
            return {
                "total_adjustments": 0,
                "by_strategy": {},
                "by_signal_type": {},
                "last_adjustment": None,
                "avg_change_magnitude": 0.0,
            }

        by_strategy: dict[str, int] = {}
        by_signal_type: dict[str, int] = {}
        total_change_magnitude = 0.0

        for adj in adjustments:
            by_strategy[adj.strategy_id] = by_strategy.get(adj.strategy_id, 0) + 1
            signal_key = adj.signal_type.value
            by_signal_type[signal_key] = by_signal_type.get(signal_key, 0) + 1
            total_change_magnitude += abs(adj.change_amount)

        return {
            "total_adjustments": len(adjustments),
            "by_strategy": by_strategy,
            "by_signal_type": by_signal_type,
            "last_adjustment": (
                adjustments[-1].timestamp.isoformat() if adjustments else None
            ),
            "avg_change_magnitude": total_change_magnitude / len(adjustments),
            "frozen_strategies": len(self._freeze_until),
        }

    def reset(self) -> None:
        """Reset all state (for testing)."""
        self._history = AdjustmentHistory()
        self._last_adjustment.clear()
        self._freeze_until.clear()
        logger.info("DynamicThresholdEngine reset")


__all__ = [
    "DynamicThresholdEngine",
    "DynamicThresholdConfig",
    "ThresholdAdjustmentRecord",
    "AdjustmentHistory",
    "ECEProvider",
    # Constants
    "MIN_THRESHOLD",
    "MAX_THRESHOLD",
    "MAX_DAILY_CHANGE_PERCENT",
    "ECE_ADJUSTMENT_THRESHOLD",
    "COOLDOWN_HOURS",
    "OSCILLATION_WINDOW_DAYS",
    "OSCILLATION_FREEZE_HOURS",
    "OSCILLATION_DIRECTION_CHANGES",
]
