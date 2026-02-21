"""Confidence threshold calibration module.

Provides dynamic and fixed threshold management for trading signal confidence scores.
Supports automatic threshold adjustment based on ECE (Expected Calibration Error) metrics
and maintains full audit trail of all threshold changes.

Key Features:
- Dynamic threshold adjustment based on calibration metrics
- Fixed threshold mode for manual override
- Full audit trail of threshold changes
- Mode switching with configurable per-strategy settings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from confidence.ece_tracker import ECEHistoryPoint

logger = logging.getLogger(__name__)


class ThresholdMode(str, Enum):
    """Operating mode for threshold calibration.

    DYNAMIC: Automatically adjust threshold based on ECE metrics
    FIXED: Use manually specified threshold without automatic adjustment
    """

    DYNAMIC = "dynamic"
    FIXED = "fixed"


@dataclass(frozen=True)
class ThresholdConfig:
    """Configuration for threshold calibration.

    Attributes:
        strategy_id: Unique identifier for the strategy
        mode: Operating mode (DYNAMIC or FIXED)
        current_threshold: Current confidence threshold (0.0-1.0)
        min_threshold: Minimum allowed threshold (default 0.40 = 40%)
        max_threshold: Maximum allowed threshold (default 0.95 = 95%)
        adjustment_step_up: Step size for increasing threshold (default 0.05 = 5%)
        adjustment_step_down: Step size for decreasing threshold (default 0.03 = 3%)
        ece_high_threshold: ECE value that triggers threshold increase (default 0.15)
        ece_low_threshold: ECE value that triggers threshold decrease (default 0.05)
        created_at: When this config was created
        updated_at: When this config was last updated
    """

    strategy_id: str
    mode: ThresholdMode
    current_threshold: float
    min_threshold: float = 0.40
    max_threshold: float = 0.95
    adjustment_step_up: float = 0.05
    adjustment_step_down: float = 0.03
    ece_high_threshold: float = 0.15
    ece_low_threshold: float = 0.05
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self):
        """Validate threshold configuration."""
        if not 0.0 <= self.current_threshold <= 1.0:
            msg = f"current_threshold must be in [0, 1], got {self.current_threshold}"
            raise ValueError(msg)
        if not 0.0 <= self.min_threshold <= 1.0:
            msg = f"min_threshold must be in [0, 1], got {self.min_threshold}"
            raise ValueError(msg)
        if not 0.0 <= self.max_threshold <= 1.0:
            msg = f"max_threshold must be in [0, 1], got {self.max_threshold}"
            raise ValueError(msg)
        if self.min_threshold >= self.max_threshold:
            msg = f"min_threshold ({self.min_threshold}) must be < max_threshold ({self.max_threshold})"
            raise ValueError(msg)
        if not self.min_threshold <= self.current_threshold <= self.max_threshold:
            msg = (
                f"current_threshold ({self.current_threshold}) must be between "
                f"min ({self.min_threshold}) and max ({self.max_threshold})"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class ThresholdAdjustment:
    """Record of a single threshold adjustment.

    Attributes:
        timestamp: When the adjustment was made
        strategy_id: Strategy identifier
        old_value: Previous threshold value
        new_value: New threshold value
        reason: Human-readable reason for the adjustment
        ece_before: ECE value before adjustment (if applicable)
        ece_after: ECE value after adjustment (if measured)
        adjustment_type: Type of adjustment ("auto", "manual", "mode_switch")
        triggered_by: What triggered the adjustment ("ece_high", "ece_low", "manual", etc.)
    """

    timestamp: datetime
    strategy_id: str
    old_value: float
    new_value: float
    reason: str
    ece_before: float | None = None
    ece_after: float | None = None
    adjustment_type: str = "auto"
    triggered_by: str = "unknown"

    @property
    def change_amount(self) -> float:
        """Calculate the change amount."""
        return self.new_value - self.old_value

    @property
    def change_percent(self) -> float:
        """Calculate the change as a percentage of old value."""
        if self.old_value == 0:
            return 0.0
        return (self.change_amount / self.old_value) * 100


@dataclass(frozen=True)
class CalibrationResult:
    """Result of a calibration operation.

    Attributes:
        strategy_id: Strategy identifier
        ece_before: ECE before calibration
        ece_after: ECE after calibration (if available)
        threshold_before: Threshold before calibration
        threshold_after: Threshold after calibration
        adjustment_made: Whether an adjustment was actually made
        adjustment_reason: Reason for the adjustment (or why no adjustment was made)
        recommended_action: Recommended action ("increase", "decrease", "maintain")
        confidence_improvement: Expected confidence improvement from adjustment
    """

    strategy_id: str
    ece_before: float
    ece_after: float | None
    threshold_before: float
    threshold_after: float
    adjustment_made: bool
    adjustment_reason: str
    recommended_action: str
    confidence_improvement: float

    @property
    def ece_improvement(self) -> float | None:
        """Calculate ECE improvement (decrease is positive)."""
        if self.ece_after is None:
            return None
        return self.ece_before - self.ece_after

    @property
    def is_better_calibrated(self) -> bool | None:
        """Check if calibration improved (ECE decreased)."""
        if self.ece_after is None:
            return None
        return self.ece_after < self.ece_before


@dataclass(frozen=True)
class ModeSwitchRecord:
    """Record of a mode switch operation.

    Attributes:
        timestamp: When the switch occurred
        strategy_id: Strategy identifier
        old_mode: Previous mode
        new_mode: New mode
        reason: Human-readable reason for the switch
        old_threshold: Threshold before switch
        new_threshold: Threshold after switch (if changed)
    """

    timestamp: datetime
    strategy_id: str
    old_mode: ThresholdMode
    new_mode: ThresholdMode
    reason: str
    old_threshold: float
    new_threshold: float


class ThresholdCalibrator:
    """Calibrates confidence thresholds based on ECE metrics.

    Implements dynamic threshold adjustment algorithm:
    - If ECE > 0.15: Increase threshold by 5% to be more selective
    - If ECE < 0.05 AND win rate < 50%: Decrease threshold by 3% to be less selective

    The goal is to maintain calibration while maximizing signal throughput.

    Example:
        >>> calibrator = ThresholdCalibrator()
        >>> config = ThresholdConfig(
        ...     strategy_id="grid_btc_1h",
        ...     mode=ThresholdMode.DYNAMIC,
        ...     current_threshold=0.65
        ... )
        >>> ece_history = [...]  # ECEHistoryPoint objects
        >>> result = await calibrator.calibrate("grid_btc_1h", ece_history, win_rate=0.45)
        >>> print(f"Adjusted: {result.adjustment_made}, New threshold: {result.threshold_after}")
    """

    def __init__(
        self,
        default_min_threshold: float = 0.40,
        default_max_threshold: float = 0.95,
        default_step_up: float = 0.05,
        default_step_down: float = 0.03,
        default_ece_high: float = 0.15,
        default_ece_low: float = 0.05,
    ):
        """Initialize threshold calibrator.

        Args:
            default_min_threshold: Default minimum threshold (default 0.40)
            default_max_threshold: Default maximum threshold (default 0.95)
            default_step_up: Default step size for increasing threshold (default 0.05)
            default_step_down: Default step size for decreasing threshold (default 0.03)
            default_ece_high: Default ECE threshold for high calibration error (default 0.15)
            default_ece_low: Default ECE threshold for low calibration error (default 0.05)
        """
        self.default_min_threshold = default_min_threshold
        self.default_max_threshold = default_max_threshold
        self.default_step_up = default_step_up
        self.default_step_down = default_step_down
        self.default_ece_high = default_ece_high
        self.default_ece_low = default_ece_low

    def calculate_adjustment(
        self,
        current_threshold: float,
        ece: float,
        win_rate: float | None = None,
        config: ThresholdConfig | None = None,
    ) -> tuple[float, str, str]:
        """Calculate the recommended threshold adjustment.

        Args:
            current_threshold: Current threshold value
            ece: Current ECE value
            win_rate: Optional win rate for low-ECE scenarios
            config: Optional threshold configuration for custom thresholds

        Returns:
            Tuple of (new_threshold, reason, action)
        """
        min_thresh = config.min_threshold if config else self.default_min_threshold
        max_thresh = config.max_threshold if config else self.default_max_threshold
        step_up = config.adjustment_step_up if config else self.default_step_up
        step_down = config.adjustment_step_down if config else self.default_step_down
        ece_high = config.ece_high_threshold if config else self.default_ece_high
        ece_low = config.ece_low_threshold if config else self.default_ece_low

        # High ECE: increase threshold to be more selective
        if ece > ece_high:
            new_threshold = min(current_threshold + step_up, max_thresh)
            reason = f"ECE ({ece:.4f}) exceeds high threshold ({ece_high}), increasing selectivity"
            action = "increase"
            return new_threshold, reason, action

        # Low ECE but poor win rate: decrease threshold to capture more signals
        if ece < ece_low and win_rate is not None and win_rate < 0.50:
            new_threshold = max(current_threshold - step_down, min_thresh)
            reason = (
                f"ECE ({ece:.4f}) below low threshold ({ece_low}) with "
                f"poor win rate ({win_rate:.2%}), decreasing selectivity"
            )
            action = "decrease"
            return new_threshold, reason, action

        # No adjustment needed
        return (
            current_threshold,
            "No adjustment needed - calibration within acceptable range",
            "maintain",
        )

    async def calibrate(
        self,
        strategy_id: str,
        ece_history: Sequence[ECEHistoryPoint],
        win_rate: float | None = None,
        config: ThresholdConfig | None = None,
    ) -> CalibrationResult:
        """Calibrate threshold based on ECE history.

        Args:
            strategy_id: Strategy identifier
            ece_history: Sequence of ECE history points
            win_rate: Optional win rate for low-ECE scenarios
            config: Optional threshold configuration

        Returns:
            CalibrationResult with adjustment details
        """
        if not ece_history:
            logger.warning(f"No ECE history for strategy {strategy_id}")
            return CalibrationResult(
                strategy_id=strategy_id,
                ece_before=0.0,
                ece_after=None,
                threshold_before=config.current_threshold if config else 0.65,
                threshold_after=config.current_threshold if config else 0.65,
                adjustment_made=False,
                adjustment_reason="No ECE history available",
                recommended_action="maintain",
                confidence_improvement=0.0,
            )

        # Use most recent ECE value
        current_ece = ece_history[-1].ece
        current_threshold = config.current_threshold if config else 0.65

        # Calculate adjustment
        new_threshold, reason, action = self.calculate_adjustment(
            current_threshold=current_threshold,
            ece=current_ece,
            win_rate=win_rate,
            config=config,
        )

        adjustment_made = new_threshold != current_threshold

        # Estimate confidence improvement (simplified model)
        confidence_improvement = 0.0
        if adjustment_made:
            # Rough estimate: 5% threshold increase -> ~3% ECE decrease
            threshold_change = abs(new_threshold - current_threshold)
            if action == "increase":
                confidence_improvement = threshold_change * 0.6  # 60% efficiency
            else:
                confidence_improvement = (
                    threshold_change * 0.4
                )  # 40% efficiency for decreases

        return CalibrationResult(
            strategy_id=strategy_id,
            ece_before=current_ece,
            ece_after=None,  # Will be measured after adjustment takes effect
            threshold_before=current_threshold,
            threshold_after=new_threshold,
            adjustment_made=adjustment_made,
            adjustment_reason=reason,
            recommended_action=action,
            confidence_improvement=confidence_improvement,
        )

    def set_fixed_threshold(
        self,
        strategy_id: str,
        value: float,
        reason: str,
        config: ThresholdConfig | None = None,
    ) -> tuple[ThresholdConfig, ThresholdAdjustment]:
        """Set a fixed threshold value.

        Args:
            strategy_id: Strategy identifier
            value: New threshold value
            reason: Reason for the manual adjustment
            config: Optional existing config to update

        Returns:
            Tuple of (updated_config, adjustment_record)
        """
        old_threshold = config.current_threshold if config else 0.65

        # Clamp to bounds
        min_thresh = config.min_threshold if config else self.default_min_threshold
        max_thresh = config.max_threshold if config else self.default_max_threshold
        clamped_value = max(min_thresh, min(value, max_thresh))

        if clamped_value != value:
            logger.warning(
                f"Threshold {value} clamped to {clamped_value} within bounds "
                f"[{min_thresh}, {max_thresh}]"
            )

        # Create new config
        new_config = ThresholdConfig(
            strategy_id=strategy_id,
            mode=ThresholdMode.FIXED,
            current_threshold=clamped_value,
            min_threshold=min_thresh,
            max_threshold=max_thresh,
            created_at=config.created_at if config else datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Create adjustment record
        adjustment = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id=strategy_id,
            old_value=old_threshold,
            new_value=clamped_value,
            reason=reason,
            ece_before=None,
            ece_after=None,
            adjustment_type="manual",
            triggered_by="manual_override",
        )

        logger.info(
            f"Set fixed threshold for {strategy_id}: {old_threshold:.2%} -> {clamped_value:.2%}"
        )

        return new_config, adjustment

    def switch_mode(
        self,
        strategy_id: str,
        new_mode: ThresholdMode,
        reason: str,
        current_config: ThresholdConfig | None = None,
        new_threshold: float | None = None,
    ) -> tuple[ThresholdConfig, ModeSwitchRecord]:
        """Switch between dynamic and fixed modes.

        Args:
            strategy_id: Strategy identifier
            new_mode: Mode to switch to
            reason: Reason for the mode switch
            current_config: Optional current configuration
            new_threshold: Optional new threshold value (for fixed mode)

        Returns:
            Tuple of (updated_config, mode_switch_record)
        """
        old_mode = current_config.mode if current_config else ThresholdMode.DYNAMIC
        old_threshold = current_config.current_threshold if current_config else 0.65

        # Determine new threshold
        if new_threshold is not None:
            final_threshold = new_threshold
        elif current_config is not None:
            final_threshold = current_config.current_threshold
        else:
            final_threshold = 0.65

        # Clamp to bounds
        min_thresh = (
            current_config.min_threshold
            if current_config
            else self.default_min_threshold
        )
        max_thresh = (
            current_config.max_threshold
            if current_config
            else self.default_max_threshold
        )
        final_threshold = max(min_thresh, min(final_threshold, max_thresh))

        # Create new config
        new_config = ThresholdConfig(
            strategy_id=strategy_id,
            mode=new_mode,
            current_threshold=final_threshold,
            min_threshold=min_thresh,
            max_threshold=max_thresh,
            created_at=(
                current_config.created_at if current_config else datetime.now(UTC)
            ),
            updated_at=datetime.now(UTC),
        )

        # Create mode switch record
        mode_switch = ModeSwitchRecord(
            timestamp=datetime.now(UTC),
            strategy_id=strategy_id,
            old_mode=old_mode,
            new_mode=new_mode,
            reason=reason,
            old_threshold=old_threshold,
            new_threshold=final_threshold,
        )

        logger.info(
            f"Switched mode for {strategy_id}: {old_mode.value} -> {new_mode.value}, "
            f"threshold: {old_threshold:.2%} -> {final_threshold:.2%}"
        )

        return new_config, mode_switch


class ThresholdManager:
    """Manages threshold configurations for multiple strategies.

    Provides centralized management of threshold configurations with
    support for both dynamic and fixed modes, full audit trails, and
    per-strategy customization.

    Example:
        >>> manager = ThresholdManager()
        >>> manager.register_strategy("grid_btc_1h", ThresholdMode.DYNAMIC, 0.65)
        >>> threshold = manager.get_threshold("grid_btc_1h")
        >>> config, record = manager.switch_mode("grid_btc_1h", ThresholdMode.FIXED, "Testing")
    """

    def __init__(self, calibrator: ThresholdCalibrator | None = None):
        """Initialize threshold manager.

        Args:
            calibrator: Optional custom calibrator instance
        """
        self._calibrator = calibrator or ThresholdCalibrator()
        self._configs: dict[str, ThresholdConfig] = {}
        self._adjustments: dict[str, list[ThresholdAdjustment]] = {}
        self._mode_switches: dict[str, list[ModeSwitchRecord]] = {}

    def register_strategy(
        self,
        strategy_id: str,
        mode: ThresholdMode,
        initial_threshold: float = 0.65,
        min_threshold: float | None = None,
        max_threshold: float | None = None,
    ) -> ThresholdConfig:
        """Register a new strategy with threshold configuration.

        Args:
            strategy_id: Unique strategy identifier
            mode: Initial threshold mode
            initial_threshold: Initial threshold value (default 0.65)
            min_threshold: Minimum threshold (uses default if None)
            max_threshold: Maximum threshold (uses default if None)

        Returns:
            Created ThresholdConfig
        """
        config = ThresholdConfig(
            strategy_id=strategy_id,
            mode=mode,
            current_threshold=initial_threshold,
            min_threshold=(
                min_threshold
                if min_threshold is not None
                else self._calibrator.default_min_threshold
            ),
            max_threshold=(
                max_threshold
                if max_threshold is not None
                else self._calibrator.default_max_threshold
            ),
        )

        self._configs[strategy_id] = config
        self._adjustments[strategy_id] = []
        self._mode_switches[strategy_id] = []

        logger.info(
            f"Registered strategy {strategy_id} with mode={mode.value}, "
            f"threshold={initial_threshold:.2%}"
        )

        return config

    def get_threshold(self, strategy_id: str) -> float:
        """Get current threshold for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Current threshold value

        Raises:
            KeyError: If strategy is not registered
        """
        if strategy_id not in self._configs:
            raise KeyError(f"Strategy {strategy_id} not registered")
        return self._configs[strategy_id].current_threshold

    def get_config(self, strategy_id: str) -> ThresholdConfig:
        """Get full configuration for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            ThresholdConfig for the strategy

        Raises:
            KeyError: If strategy is not registered
        """
        if strategy_id not in self._configs:
            raise KeyError(f"Strategy {strategy_id} not registered")
        return self._configs[strategy_id]

    def update_threshold(
        self,
        strategy_id: str,
        new_threshold: float,
        reason: str,
        ece_before: float | None = None,
        ece_after: float | None = None,
        adjustment_type: str = "manual",
        triggered_by: str = "manual",
    ) -> ThresholdAdjustment:
        """Update threshold for a strategy.

        Args:
            strategy_id: Strategy identifier
            new_threshold: New threshold value
            reason: Reason for the update
            ece_before: ECE before adjustment
            ece_after: ECE after adjustment
            adjustment_type: Type of adjustment
            triggered_by: What triggered the adjustment

        Returns:
            ThresholdAdjustment record

        Raises:
            KeyError: If strategy is not registered
        """
        if strategy_id not in self._configs:
            raise KeyError(f"Strategy {strategy_id} not registered")

        old_config = self._configs[strategy_id]
        old_threshold = old_config.current_threshold

        # Clamp to bounds
        clamped_threshold = max(
            old_config.min_threshold, min(new_threshold, old_config.max_threshold)
        )

        # Create new config
        new_config = ThresholdConfig(
            strategy_id=strategy_id,
            mode=old_config.mode,
            current_threshold=clamped_threshold,
            min_threshold=old_config.min_threshold,
            max_threshold=old_config.max_threshold,
            adjustment_step_up=old_config.adjustment_step_up,
            adjustment_step_down=old_config.adjustment_step_down,
            ece_high_threshold=old_config.ece_high_threshold,
            ece_low_threshold=old_config.ece_low_threshold,
            created_at=old_config.created_at,
            updated_at=datetime.now(UTC),
        )

        self._configs[strategy_id] = new_config

        # Record adjustment
        adjustment = ThresholdAdjustment(
            timestamp=datetime.now(UTC),
            strategy_id=strategy_id,
            old_value=old_threshold,
            new_value=clamped_threshold,
            reason=reason,
            ece_before=ece_before,
            ece_after=ece_after,
            adjustment_type=adjustment_type,
            triggered_by=triggered_by,
        )

        self._adjustments[strategy_id].append(adjustment)

        logger.info(
            f"Updated threshold for {strategy_id}: {old_threshold:.2%} -> {clamped_threshold:.2%}"
        )

        return adjustment

    def switch_mode(
        self,
        strategy_id: str,
        new_mode: ThresholdMode,
        reason: str,
        new_threshold: float | None = None,
    ) -> tuple[ThresholdConfig, ModeSwitchRecord]:
        """Switch mode for a strategy.

        Args:
            strategy_id: Strategy identifier
            new_mode: New mode to switch to
            reason: Reason for the switch
            new_threshold: Optional new threshold value

        Returns:
            Tuple of (updated_config, mode_switch_record)

        Raises:
            KeyError: If strategy is not registered
        """
        if strategy_id not in self._configs:
            raise KeyError(f"Strategy {strategy_id} not registered")

        current_config = self._configs[strategy_id]

        new_config, mode_switch = self._calibrator.switch_mode(
            strategy_id=strategy_id,
            new_mode=new_mode,
            reason=reason,
            current_config=current_config,
            new_threshold=new_threshold,
        )

        self._configs[strategy_id] = new_config
        self._mode_switches[strategy_id].append(mode_switch)

        return new_config, mode_switch

    def get_adjustment_history(self, strategy_id: str) -> list[ThresholdAdjustment]:
        """Get adjustment history for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of threshold adjustments
        """
        return self._adjustments.get(strategy_id, []).copy()

    def get_mode_switch_history(self, strategy_id: str) -> list[ModeSwitchRecord]:
        """Get mode switch history for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            List of mode switch records
        """
        return self._mode_switches.get(strategy_id, []).copy()

    def get_all_strategies(self) -> list[str]:
        """Get list of all registered strategy IDs.

        Returns:
            List of strategy IDs
        """
        return list(self._configs.keys())

    def is_registered(self, strategy_id: str) -> bool:
        """Check if a strategy is registered.

        Args:
            strategy_id: Strategy identifier

        Returns:
            True if registered, False otherwise
        """
        return strategy_id in self._configs

    async def run_calibration(
        self,
        strategy_id: str,
        ece_history: Sequence[ECEHistoryPoint],
        win_rate: float | None = None,
    ) -> CalibrationResult:
        """Run calibration for a strategy.

        Only runs if strategy is in DYNAMIC mode.

        Args:
            strategy_id: Strategy identifier
            ece_history: ECE history points
            win_rate: Optional win rate

        Returns:
            CalibrationResult

        Raises:
            KeyError: If strategy is not registered
        """
        if strategy_id not in self._configs:
            raise KeyError(f"Strategy {strategy_id} not registered")

        config = self._configs[strategy_id]

        # Only calibrate in dynamic mode
        if config.mode == ThresholdMode.FIXED:
            return CalibrationResult(
                strategy_id=strategy_id,
                ece_before=ece_history[-1].ece if ece_history else 0.0,
                ece_after=None,
                threshold_before=config.current_threshold,
                threshold_after=config.current_threshold,
                adjustment_made=False,
                adjustment_reason="Strategy is in FIXED mode - no automatic adjustment",
                recommended_action="maintain",
                confidence_improvement=0.0,
            )

        # Run calibration
        result = await self._calibrator.calibrate(
            strategy_id=strategy_id,
            ece_history=ece_history,
            win_rate=win_rate,
            config=config,
        )

        # If adjustment was made, update the config and record it
        if result.adjustment_made:
            self.update_threshold(
                strategy_id=strategy_id,
                new_threshold=result.threshold_after,
                reason=result.adjustment_reason,
                ece_before=result.ece_before,
                adjustment_type="auto",
                triggered_by=result.recommended_action,
            )

        return result

    def unregister_strategy(self, strategy_id: str) -> bool:
        """Unregister a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            True if unregistered, False if not found
        """
        if strategy_id not in self._configs:
            return False

        del self._configs[strategy_id]
        del self._adjustments[strategy_id]
        del self._mode_switches[strategy_id]

        logger.info(f"Unregistered strategy {strategy_id}")
        return True
