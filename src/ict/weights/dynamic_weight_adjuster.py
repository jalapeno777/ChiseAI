"""Dynamic Weight Adjuster for ICT signals.

Implements time-based weight decay for ICT signals to reduce the influence
of stale signals in confluence calculations.

Weight Multipliers (ST-ICT-023):
    - Recent signals (0-5 minutes): 1.0x multiplier
    - Stale signals (5-15 minutes): 0.8x multiplier
    - Old signals (15-30 minutes): 0.5x multiplier
    - Very old signals (>30 minutes): EXCLUDED from confluence

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Integration:
    - Works with Layer 2 confluence aggregator from EP-ICT-005
    - Uses signal timestamp tracker for age calculations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.confluence.layer1_signal_scorer import Layer1Score


class WeightTier(str, Enum):
    """Weight tiers based on signal age.

    Signals are categorized into tiers based on their age to apply
    appropriate weight multipliers in confluence calculations.
    """

    RECENT = "recent"  # 0-5 minutes: 1.0x multiplier
    STALE = "stale"  # 5-15 minutes: 0.8x multiplier
    OLD = "old"  # 15-30 minutes: 0.5x multiplier
    EXCLUDED = "excluded"  # >30 minutes: excluded from confluence


# Weight tier thresholds in seconds
TIER_THRESHOLDS = {
    WeightTier.RECENT: 5 * 60,  # 5 minutes
    WeightTier.STALE: 15 * 60,  # 15 minutes
    WeightTier.OLD: 30 * 60,  # 30 minutes
}

# Weight multipliers per tier
TIER_MULTIPLIERS = {
    WeightTier.RECENT: 1.0,
    WeightTier.STALE: 0.8,
    WeightTier.OLD: 0.5,
    WeightTier.EXCLUDED: 0.0,  # Excluded
}


@dataclass
class WeightedSignal:
    """A Layer1Score with dynamic weight applied.

    Attributes:
        original_score: The original Layer1Score
        tier: The weight tier based on signal age
        age_seconds: Age of the signal in seconds
        base_weight: Base signal weight from validation
        dynamic_multiplier: Time-based multiplier (0.0-1.0)
        effective_weight: Final weight after applying dynamic multiplier
        is_included: Whether signal should be included in confluence
    """

    original_score: Layer1Score
    tier: WeightTier
    age_seconds: float
    base_weight: float
    dynamic_multiplier: float
    effective_weight: float
    is_included: bool


@dataclass
class DynamicWeightResult:
    """Result of dynamic weight adjustment for multiple signals.

    Attributes:
        weighted_signals: List of signals with weights applied
        included_signals: Signals that should be included in confluence
        excluded_signals: Signals excluded due to age (>30 min)
        average_effective_weight: Average weight of included signals
        total_weight: Sum of effective weights
        excluded_count: Number of signals excluded
    """

    weighted_signals: list[WeightedSignal] = field(default_factory=list)
    included_signals: list[WeightedSignal] = field(default_factory=list)
    excluded_signals: list[WeightedSignal] = field(default_factory=list)
    average_effective_weight: float = 0.0
    total_weight: float = 0.0
    excluded_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "weighted_signals_count": len(self.weighted_signals),
            "included_signals_count": len(self.included_signals),
            "excluded_signals_count": len(self.excluded_signals),
            "average_effective_weight": round(self.average_effective_weight, 3),
            "total_weight": round(self.total_weight, 3),
            "tier_breakdown": {
                tier.value: len([s for s in self.weighted_signals if s.tier == tier])
                for tier in WeightTier
            },
            "excluded_signals": [
                {
                    "signal_type": s.original_score.signal_type,
                    "age_seconds": round(s.age_seconds, 1),
                }
                for s in self.excluded_signals
            ],
        }


class DynamicWeightAdjuster:
    """Applies dynamic time-based weight adjustment to ICT signals.

    This adjuster implements the time-decay algorithm for ICT signals:
    - Signals within 5 minutes: full weight (1.0x)
    - Signals 5-15 minutes old: 0.8x multiplier
    - Signals 15-30 minutes old: 0.5x multiplier
    - Signals older than 30 minutes: excluded from confluence

    BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

    Usage:
        adjuster = DynamicWeightAdjuster()
        result = adjuster.adjust_weights(layer1_scores, current_time=now_ts)
        included = result.included_signals
    """

    def __init__(
        self,
        recent_threshold_seconds: float = TIER_THRESHOLDS[WeightTier.RECENT],
        stale_threshold_seconds: float = TIER_THRESHOLDS[WeightTier.STALE],
        old_threshold_seconds: float = TIER_THRESHOLDS[WeightTier.OLD],
    ):
        """Initialize dynamic weight adjuster.

        Args:
            recent_threshold_seconds: Threshold for RECENT tier (default: 300s = 5min)
            stale_threshold_seconds: Threshold for STALE tier (default: 900s = 15min)
            old_threshold_seconds: Threshold for OLD tier (default: 1800s = 30min)
        """
        self.recent_threshold = recent_threshold_seconds
        self.stale_threshold = stale_threshold_seconds
        self.old_threshold = old_threshold_seconds

    def get_tier_for_age(self, age_seconds: float) -> WeightTier:
        """Get the weight tier for a signal based on its age.

        Args:
            age_seconds: Age of the signal in seconds

        Returns:
            WeightTier corresponding to the signal age
        """
        if age_seconds < 0:
            # Future timestamps treated as recent
            return WeightTier.RECENT
        elif age_seconds < self.recent_threshold:
            return WeightTier.RECENT
        elif age_seconds < self.stale_threshold:
            return WeightTier.STALE
        elif age_seconds < self.old_threshold:
            return WeightTier.OLD
        else:
            return WeightTier.EXCLUDED

    def get_multiplier_for_tier(self, tier: WeightTier) -> float:
        """Get the weight multiplier for a tier.

        Args:
            tier: The weight tier

        Returns:
            Weight multiplier (0.0-1.0)
        """
        return TIER_MULTIPLIERS.get(tier, 0.0)

    def get_multiplier_for_age(self, age_seconds: float) -> float:
        """Get the weight multiplier for a signal based on its age.

        Args:
            age_seconds: Age of the signal in seconds

        Returns:
            Weight multiplier (0.0-1.0)
        """
        tier = self.get_tier_for_age(age_seconds)
        return self.get_multiplier_for_tier(tier)

    def calculate_effective_weight(
        self,
        base_weight: float,
        age_seconds: float,
    ) -> tuple[float, WeightTier, bool]:
        """Calculate the effective weight for a signal.

        Formula:
            effective_weight = base_weight * dynamic_multiplier

        Args:
            base_weight: Base signal weight from validation (0.0-1.0)
            age_seconds: Age of the signal in seconds

        Returns:
            Tuple of (effective_weight, tier, is_included)
        """
        tier = self.get_tier_for_age(age_seconds)
        multiplier = self.get_multiplier_for_tier(tier)
        effective_weight = base_weight * multiplier
        is_included = tier != WeightTier.EXCLUDED

        return effective_weight, tier, is_included

    def adjust_weights(
        self,
        layer1_scores: list[Layer1Score],
        current_time: float | None = None,
    ) -> DynamicWeightResult:
        """Apply dynamic weight adjustment to a list of Layer1 scores.

        Args:
            layer1_scores: List of Layer1Score objects from Layer 1 scoring
            current_time: Current timestamp in seconds (UTC epoch).
                         If None, uses current time.

        Returns:
            DynamicWeightResult with weighted signals categorized
        """
        from market_analysis.confluence.signal_weights import get_signal_weight

        if current_time is None:
            current_time = datetime.now(UTC).timestamp()

        result = DynamicWeightResult()
        included_weights: list[float] = []

        for score in layer1_scores:
            # Skip invalid signal types
            if not self._is_signal_valid(score.signal_type):
                continue

            # Calculate signal age
            signal_time = getattr(score, "timestamp", None) or getattr(
                score, "signal_time", None
            )
            if signal_time is None:
                # No timestamp available, treat as recent
                age_seconds = 0.0
            else:
                age_seconds = current_time - signal_time

            # Get base weight from validation
            base_weight = get_signal_weight(score.signal_type)

            # Calculate effective weight
            (
                effective_weight,
                tier,
                is_included,
            ) = self.calculate_effective_weight(base_weight, age_seconds)

            multiplier = self.get_multiplier_for_tier(tier)

            weighted_signal = WeightedSignal(
                original_score=score,
                tier=tier,
                age_seconds=age_seconds,
                base_weight=base_weight,
                dynamic_multiplier=multiplier,
                effective_weight=effective_weight,
                is_included=is_included,
            )

            result.weighted_signals.append(weighted_signal)

            if is_included:
                result.included_signals.append(weighted_signal)
                included_weights.append(effective_weight)
            else:
                result.excluded_signals.append(weighted_signal)

        # Calculate aggregate metrics
        result.excluded_count = len(result.excluded_signals)
        if included_weights:
            result.average_effective_weight = sum(included_weights) / len(
                included_weights
            )
            result.total_weight = sum(included_weights)

        return result

    def _is_signal_valid(self, signal_type: str) -> bool:
        """Check if signal type is valid.

        Args:
            signal_type: The signal type to check

        Returns:
            True if signal is valid for weight adjustment
        """
        from market_analysis.confluence.signal_weights import ICTSignalType

        return ICTSignalType.is_valid_signal(signal_type)

    def get_tier_info(self) -> dict[str, Any]:
        """Get information about the configured weight tiers.

        Returns:
            Dictionary with tier thresholds and multipliers
        """
        return {
            "tiers": {
                tier.value: {
                    "max_age_seconds": TIER_THRESHOLDS.get(tier),
                    "multiplier": TIER_MULTIPLIERS.get(tier),
                }
                for tier in WeightTier
            },
            "configured_thresholds": {
                "recent_seconds": self.recent_threshold,
                "stale_seconds": self.stale_threshold,
                "old_seconds": self.old_threshold,
            },
        }


# Global adjuster instance
_adjuster_instance: DynamicWeightAdjuster | None = None


def get_weight_adjuster() -> DynamicWeightAdjuster:
    """Get or create the global DynamicWeightAdjuster instance.

    Returns:
        Global DynamicWeightAdjuster instance
    """
    global _adjuster_instance
    if _adjuster_instance is None:
        _adjuster_instance = DynamicWeightAdjuster()
    return _adjuster_instance
