"""Layer 2: Confluence Aggregator for ICT signals.

This module implements Layer 2 of the two-layer scoring system. It aggregates
Layer 1 scores from multiple ICT signals (CVD, FVG, Order Block) to produce:
- Final confluence score (0.0 - 1.0)
- Consensus direction
- Contributing factors breakdown

The aggregation uses signal weights from EP-ICT-004 validation:
- CVD: 100% validation → weight 1.0
- FVG: 100% validation → weight 1.0
- Order Block: 80.77% validation → weight 0.85

BOS and CHoCH are EXCLUDED per BL-BOS-CHOCH-001.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.confluence.layer1_signal_scorer import Layer1Score

from market_analysis.confluence.layer1_signal_scorer import Layer1SignalDirection
from market_analysis.confluence.signal_aggregator import SignalDirection
from market_analysis.confluence.signal_weights import (
    get_signal_weight,
)


@dataclass
class Layer2ConfluenceResult:
    """Result of Layer 2 confluence aggregation.

    Attributes:
        confluence_score: Final confluence score (0.0-1.0)
        direction: Consensus direction (LONG/SHORT/NEUTRAL)
        confidence: Overall confidence (0.0-1.0)
        contributing_signals: List of Layer1Scores that contributed
        signal_breakdown: Breakdown by signal type
        direction_breakdown: Direction weights for LONG/SHORT/NEUTRAL
        weights_applied: Weights used for each signal
        timestamp: Calculation timestamp
    """

    confluence_score: float
    direction: SignalDirection
    confidence: float
    contributing_signals: list[Layer1Score] = field(default_factory=list)
    signal_breakdown: dict[str, Any] = field(default_factory=dict)
    direction_breakdown: dict[str, float] = field(default_factory=dict)
    weights_applied: dict[str, float] = field(default_factory=dict)
    timestamp: int | None = None

    def __post_init__(self) -> None:
        """Validate and clamp values."""
        self.confluence_score = max(0.0, min(1.0, self.confluence_score))
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_strong_signal(self) -> bool:
        """Check if this represents a strong trading signal.

        Returns:
            True if confluence_score >= 0.7 and confidence >= 0.5
        """
        return self.confluence_score >= 0.7 and self.confidence >= 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "confluence_score": round(self.confluence_score, 3),
            "direction": str(self.direction),
            "confidence": round(self.confidence, 3),
            "is_strong_signal": self.is_strong_signal,
            "contributing_signals": [s.to_dict() for s in self.contributing_signals],
            "signal_breakdown": self.signal_breakdown,
            "direction_breakdown": {
                k: round(v, 3) for k, v in self.direction_breakdown.items()
            },
            "weights_applied": {
                k: round(v, 3) for k, v in self.weights_applied.items()
            },
            "timestamp": self.timestamp,
        }


class Layer2ConfluenceAggregator:
    """Aggregates Layer 1 signals into confluence score.

    This aggregator takes individual ICT signals (CVD, FVG, Order Block) from
    Layer 1 scoring and combines them using validated weights to produce a
    unified confluence score.

    Signal weights (from EP-ICT-004 validation):
        - CVD: 1.0 (100% validated)
        - FVG: 1.0 (100% validated)
        - Order Block: 0.85 (80.77% validated)

    Excluded signals (per BL-BOS-CHOCH-001):
        - BOS (Break of Structure)
        - CHoCH (Change of Character)
    """

    def __init__(
        self,
        min_signals: int = 1,
        min_confluence_threshold: float = 0.3,
        enable_feature_flags: bool = True,
    ):
        """Initialize Layer 2 aggregator.

        Args:
            min_signals: Minimum number of signals required for valid confluence
            min_confluence_threshold: Minimum confluence score to consider valid
            enable_feature_flags: Whether to check feature flags for signal types
        """
        self.min_signals = min_signals
        self.min_confluence_threshold = min_confluence_threshold
        self.enable_feature_flags = enable_feature_flags
        self._feature_flags: dict[str, bool] = {
            "cvd_enabled": True,
            "fvg_enabled": True,
            "order_block_enabled": True,
        }

    def set_feature_flag(self, signal_type: str, enabled: bool) -> None:
        """Set feature flag for a signal type.

        Args:
            signal_type: The signal type (cvd, fvg, order_block)
            enabled: Whether the signal type is enabled
        """
        flag_key = f"{signal_type}_enabled"
        if flag_key in self._feature_flags:
            self._feature_flags[flag_key] = enabled

    def is_signal_enabled(self, signal_type: str) -> bool:
        """Check if a signal type is enabled via feature flag.

        Args:
            signal_type: The signal type to check

        Returns:
            True if enabled (or if feature flags disabled)
        """
        if not self.enable_feature_flags:
            return True
        flag_key = f"{signal_type}_enabled"
        return self._feature_flags.get(flag_key, True)

    def aggregate(
        self,
        layer1_scores: list[Layer1Score],
        timestamp: int | None = None,
    ) -> Layer2ConfluenceResult:
        """Aggregate Layer 1 scores into confluence result.

        Args:
            layer1_scores: List of Layer1Scores from Layer 1 scoring
            timestamp: Optional timestamp for the calculation

        Returns:
            Layer2ConfluenceResult with aggregated score and direction
        """
        if not layer1_scores:
            return Layer2ConfluenceResult(
                confluence_score=0.5,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                timestamp=timestamp,
            )

        # Filter by feature flags if enabled
        filtered_scores = [
            s for s in layer1_scores if self.is_signal_enabled(s.signal_type)
        ]

        if len(filtered_scores) < self.min_signals:
            return Layer2ConfluenceResult(
                confluence_score=0.5,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                contributing_signals=filtered_scores,
                timestamp=timestamp,
            )

        # Calculate weighted scores
        weighted_scores = self._calculate_weighted_scores(filtered_scores)

        # Determine consensus direction
        direction, direction_confidence = self._determine_direction(weighted_scores)

        # Calculate confluence score
        confluence_score = self._calculate_confluence_score(weighted_scores, direction)

        # Calculate confidence
        confidence = self._calculate_confidence(weighted_scores, direction_confidence)

        # Build signal breakdown
        signal_breakdown = self._build_signal_breakdown(filtered_scores)

        # Build direction breakdown
        direction_breakdown = self._build_direction_breakdown(weighted_scores)

        return Layer2ConfluenceResult(
            confluence_score=confluence_score,
            direction=direction,
            confidence=confidence,
            contributing_signals=filtered_scores,
            signal_breakdown=signal_breakdown,
            direction_breakdown=direction_breakdown,
            weights_applied={
                s.signal_type: get_signal_weight(s.signal_type) for s in filtered_scores
            },
            timestamp=timestamp,
        )

    def _calculate_weighted_scores(
        self,
        scores: list[Layer1Score],
    ) -> list[dict[str, Any]]:
        """Calculate weighted scores for each signal.

        Args:
            scores: List of Layer1Scores

        Returns:
            List of dicts with signal and weight info
        """
        weighted = []
        for score in scores:
            signal_weight = get_signal_weight(score.signal_type)
            if signal_weight > 0:
                weighted_score = score.weighted_score * signal_weight
                weighted.append(
                    {
                        "score": score,
                        "signal_weight": signal_weight,
                        "weighted_score": weighted_score,
                        "direction": score.direction,
                        "signal_type": score.signal_type,
                    }
                )
        return weighted

    def _determine_direction(
        self,
        weighted_scores: list[dict[str, Any]],
    ) -> tuple[SignalDirection, float]:
        """Determine consensus direction from weighted signals.

        Args:
            weighted_scores: List of weighted signal dicts

        Returns:
            Tuple of (direction, confidence in direction)
        """
        from market_analysis.confluence.layer1_signal_scorer import (
            Layer1SignalDirection,
        )

        long_weight = 0.0
        short_weight = 0.0
        neutral_weight = 0.0

        for ws in weighted_scores:
            direction = ws["direction"]
            weighted_score = ws["weighted_score"]

            if direction == Layer1SignalDirection.BULLISH:
                long_weight += weighted_score
            elif direction == Layer1SignalDirection.BEARISH:
                short_weight += weighted_score
            else:
                neutral_weight += weighted_score

        total_weight = long_weight + short_weight + neutral_weight
        if total_weight == 0:
            return SignalDirection.NEUTRAL, 0.0

        # Normalize
        long_ratio = long_weight / total_weight
        short_ratio = short_weight / total_weight
        neutral_ratio = neutral_weight / total_weight

        # Determine direction
        if long_ratio > short_ratio and long_ratio > neutral_ratio:
            return SignalDirection.LONG, long_ratio
        elif short_ratio > long_ratio and short_ratio > neutral_ratio:
            return SignalDirection.SHORT, short_ratio
        else:
            return SignalDirection.NEUTRAL, neutral_ratio

    def _calculate_confluence_score(
        self,
        weighted_scores: list[dict[str, Any]],
        direction: SignalDirection,
    ) -> float:
        """Calculate final confluence score.

        Args:
            weighted_scores: List of weighted signal dicts
            direction: Consensus direction

        Returns:
            Confluence score (0.0-1.0)
        """
        from market_analysis.confluence.layer1_signal_scorer import (
            Layer1SignalDirection,
        )

        if not weighted_scores:
            return 0.5

        # Calculate agreement score
        agreeing_weight = sum(
            ws["weighted_score"]
            for ws in weighted_scores
            if (
                ws["direction"] == Layer1SignalDirection.BULLISH
                and direction == SignalDirection.LONG
            )
            or (
                ws["direction"] == Layer1SignalDirection.BEARISH
                and direction == SignalDirection.SHORT
            )
            or (
                ws["direction"] == Layer1SignalDirection.NEUTRAL
                and direction == SignalDirection.NEUTRAL
            )
        )
        total_weight = sum(ws["weighted_score"] for ws in weighted_scores)

        if total_weight == 0:
            return 0.5

        agreement_ratio = agreeing_weight / total_weight

        # Calculate average strength
        avg_strength = sum(ws["score"].strength for ws in weighted_scores) / len(
            weighted_scores
        )

        # Calculate average confidence
        avg_confidence = sum(ws["score"].confidence for ws in weighted_scores) / len(
            weighted_scores
        )

        # Signal count bonus (more signals = higher confidence)
        count_bonus = min(0.1, len(weighted_scores) * 0.02)

        # Combine factors
        base_score = agreement_ratio
        multiplier = (avg_strength + avg_confidence) / 2
        confluence = base_score * multiplier + count_bonus

        # Neutral direction compresses score toward 0.5
        if direction == SignalDirection.NEUTRAL:
            confluence = 0.5 + (confluence - 0.5) * 0.5

        return max(0.0, min(1.0, confluence))

    def _calculate_confidence(
        self,
        weighted_scores: list[dict[str, Any]],
        direction_confidence: float,
    ) -> float:
        """Calculate overall confidence.

        Args:
            weighted_scores: List of weighted signal dicts
            direction_confidence: Confidence in direction determination

        Returns:
            Confidence score (0.0-1.0)
        """
        if not weighted_scores:
            return 0.0

        # Average signal confidence
        avg_confidence = sum(ws["score"].confidence for ws in weighted_scores) / len(
            weighted_scores
        )

        # Signal count factor
        count_factor = min(1.0, len(weighted_scores) / 3)

        # Combine
        confidence = (
            avg_confidence * 0.5 + direction_confidence * 0.3 + count_factor * 0.2
        )

        return max(0.0, min(1.0, confidence))

    def _build_signal_breakdown(
        self,
        scores: list[Layer1Score],
    ) -> dict[str, Any]:
        """Build breakdown by signal type.

        Args:
            scores: List of Layer1Scores

        Returns:
            Breakdown dictionary
        """
        breakdown: dict[str, dict[str, Any]] = {}
        for score in scores:
            signal_type = score.signal_type
            if signal_type not in breakdown:
                breakdown[signal_type] = {
                    "count": 0,
                    "total_weighted_score": 0.0,
                    "avg_strength": 0.0,
                    "avg_confidence": 0.0,
                    "directions": [],
                }
            breakdown[signal_type]["count"] += 1
            breakdown[signal_type]["total_weighted_score"] += score.weighted_score
            breakdown[signal_type]["directions"].append(score.direction.value)

        # Calculate averages
        for signal_type, data in breakdown.items():
            count = data["count"]
            data["avg_strength"] = (
                sum(s.strength for s in scores if s.signal_type == signal_type) / count
            )
            data["avg_confidence"] = (
                sum(s.confidence for s in scores if s.signal_type == signal_type)
                / count
            )

        return breakdown

    def _build_direction_breakdown(
        self,
        weighted_scores: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Build breakdown by direction.

        Args:
            weighted_scores: List of weighted signal dicts

        Returns:
            Dictionary with direction weights
        """
        long = sum(
            ws["weighted_score"]
            for ws in weighted_scores
            if ws["direction"] == Layer1SignalDirection.BULLISH
        )
        short = sum(
            ws["weighted_score"]
            for ws in weighted_scores
            if ws["direction"] == Layer1SignalDirection.BEARISH
        )
        neutral = sum(
            ws["weighted_score"]
            for ws in weighted_scores
            if ws["direction"] == Layer1SignalDirection.NEUTRAL
        )

        total = long + short + neutral
        if total == 0:
            return {"long": 0.0, "short": 0.0, "neutral": 0.0}

        return {
            "long": long / total,
            "short": short / total,
            "neutral": neutral / total,
        }


# Import for type hint
from market_analysis.confluence.layer1_signal_scorer import Layer1Score  # noqa: E402
