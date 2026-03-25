"""Confluence scoring engine for combining multiple indicator signals.

Calculates a composite confluence score (0-100) from multiple indicator
signals, weighted by timeframe importance and indicator reliability.
Determines signal direction (long/short) and logs contributing factors.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.confluence.indicator_weights import IndicatorWeights
    from market_analysis.confluence.signal_aggregator import (
        AggregatedSignals,
        SignalDirection,
    )

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceScore:
    """Result of confluence scoring calculation.

    Attributes:
        score: Composite confluence score (0-100)
        direction: Signal direction (LONG, SHORT, NEUTRAL)
        confidence: Overall confidence in the score (0.0-1.0)
        contributing_factors: List of factors that contributed to the score
        signal_breakdown: Breakdown by indicator type and timeframe
        timestamp: Timestamp of calculation (ms)
        calculation_time_ms: Time taken to calculate (ms)
        metadata: Additional scoring metadata
        multiplier_applied: Confidence multiplier that was applied (if any)
        multiplier_rationale: Explanation of why multiplier was/wasn't applied
    """

    score: float
    direction: SignalDirection
    confidence: float
    contributing_factors: list[dict[str, Any]] = field(default_factory=list)
    signal_breakdown: dict[str, Any] = field(default_factory=dict)
    timestamp: int | None = None
    calculation_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    multiplier_applied: float | None = None
    multiplier_rationale: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.score = max(0.0, min(100.0, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_valid(self) -> bool:
        """Check if score is valid for trading decisions."""
        return (
            0.0 <= self.score <= 100.0
            and 0.0 <= self.confidence <= 1.0
            and self.direction is not None
        )

    @property
    def is_strong_signal(self, threshold: float = 70.0) -> bool:
        """Check if this is a strong signal for trading.

        Args:
            threshold: Score threshold for strong signal (default: 70)

        Returns:
            True if score >= threshold and confidence is reasonable
        """
        return self.score >= threshold and self.confidence >= 0.5

    @property
    def direction_str(self) -> str:
        """Get direction as string."""
        return str(self.direction)

    def to_dict(self) -> dict[str, Any]:
        """Convert score result to dictionary for serialization/logging."""
        return {
            "score": round(self.score, 2),
            "direction": self.direction_str,
            "confidence": round(self.confidence, 3),
            "contributing_factors": self.contributing_factors,
            "signal_breakdown": self.signal_breakdown,
            "timestamp": self.timestamp,
            "calculation_time_ms": round(self.calculation_time_ms, 3),
            "is_strong_signal": self.is_strong_signal,
            "metadata": self.metadata,
            "multiplier_applied": self.multiplier_applied,
            "multiplier_rationale": self.multiplier_rationale,
        }

    def log_summary(self) -> None:
        """Log a summary of the confluence score."""
        direction_str = self.direction_str.upper()
        calc_time = self.calculation_time_ms
        logger.info(
            f"Confluence Score: {self.score:.1f}/100 [{direction_str}] "
            f"(confidence: {self.confidence:.2%}, calc_time: {calc_time:.2f}ms)"
        )

        if self.contributing_factors:
            logger.info(f"  Contributing factors ({len(self.contributing_factors)}):")
            for factor in self.contributing_factors[:5]:  # Log top 5
                factor_type = factor.get("type", "unknown")
                factor_weight = factor.get("weight", 0.0)
                factor_direction = factor.get("direction", "neutral")
                logger.info(
                    f"    - {factor_type}: weight={factor_weight:.3f}, "
                    f"direction={factor_direction}"
                )


class ConfluenceScorer:
    """Confluence scoring engine for multi-indicator signal aggregation."""

    def __init__(
        self,
        weights: IndicatorWeights | None = None,
        min_score_threshold: float = 50.0,
        conflict_neutral_threshold: float = 0.4,
        min_base_confidence_for_multiplier: float = 0.70,
    ):
        """Initialize confluence scorer.

        Args:
            weights: Indicator weights configuration (default if None)
            min_score_threshold: Minimum score to consider valid (0-100)
            conflict_neutral_threshold: Threshold for conflicting signals (0-1)
            min_base_confidence_for_multiplier: Minimum base confidence (0-1)
                required to apply timeframe multiplier. Multiplier is only
                applied when base confidence >= this threshold to prevent
                amplifying low-confidence signals.
        """
        from market_analysis.confluence.indicator_weights import (
            DEFAULT_WEIGHTS,
        )

        self.weights = weights or DEFAULT_WEIGHTS
        self.min_score_threshold = min_score_threshold
        self.conflict_neutral_threshold = conflict_neutral_threshold
        self.min_base_confidence_for_multiplier = min_base_confidence_for_multiplier

    def calculate_score(
        self,
        aggregated_signals: AggregatedSignals,
        timestamp: int | None = None,
    ) -> ConfluenceScore:
        """Calculate confluence score from aggregated signals.

        Args:
            aggregated_signals: Aggregated signals from multiple indicators
            timestamp: Optional timestamp for the calculation

        Returns:
            ConfluenceScore with composite score and direction
        """
        start_time = time.perf_counter()

        if not aggregated_signals.signals:
            # No signals - return neutral score
            calc_time = (time.perf_counter() - start_time) * 1000
            return ConfluenceScore(
                score=50.0,  # Neutral
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                contributing_factors=[],
                signal_breakdown={},
                timestamp=timestamp,
                calculation_time_ms=calc_time,
                metadata={"reason": "no_signals"},
            )

        # Defensive: skip any signals marked as rate-limited
        filtered_signals = [
            s
            for s in aggregated_signals.signals
            if getattr(getattr(s, "status", None), "value", None) != "rate_limited"
        ]
        if len(filtered_signals) < len(aggregated_signals.signals):
            skipped = len(aggregated_signals.signals) - len(filtered_signals)
            logger.info("Confluence scorer: skipped %d rate-limited signal(s)", skipped)
            if not filtered_signals:
                calc_time = (time.perf_counter() - start_time) * 1000
                return ConfluenceScore(
                    score=50.0,
                    direction=SignalDirection.NEUTRAL,
                    confidence=0.0,
                    contributing_factors=[],
                    signal_breakdown={},
                    timestamp=timestamp,
                    calculation_time_ms=calc_time,
                    metadata={"reason": "all_signals_rate_limited"},
                )
            # Narrow the signals list for downstream scoring
            aggregated_signals.signals = filtered_signals

        # Calculate weighted scores for each signal
        weighted_signals = self._calculate_weighted_signals(aggregated_signals)

        # Determine direction based on weighted agreement
        direction, direction_confidence = self._determine_direction(weighted_signals)

        # Calculate composite score
        score, score_components = self._calculate_composite_score(
            weighted_signals, direction
        )

        # Build contributing factors list
        contributing_factors = self._build_contributing_factors(weighted_signals)

        # Build signal breakdown
        signal_breakdown = self._build_signal_breakdown(weighted_signals)

        # Calculate overall confidence
        confidence = self._calculate_confidence(
            weighted_signals, direction_confidence, aggregated_signals
        )

        # Check for conflicting signals (edge case)
        metadata: dict[str, Any] = {}
        if self._has_conflicting_signals(weighted_signals):
            # Reduce score and confidence for conflicting signals
            score = max(40.0, min(60.0, score))  # Clamp to neutral zone
            confidence *= 0.7
            metadata["warning"] = "conflicting_signals_detected"

        # Apply timeframe confidence multiplier (conditionally)
        # Only apply multiplier if base confidence is high enough to avoid
        # amplifying low-confidence signals (multiplier amplification risk)
        base_confidence = confidence  # Store base confidence before multiplier
        multiplier: float
        multiplier_rationale: str
        if base_confidence >= self.min_base_confidence_for_multiplier:
            multiplier, multiplier_rationale = self._calculate_timeframe_multiplier(
                weighted_signals
            )
            # Apply multiplier to confidence (capped at 1.0)
            confidence = min(1.0, confidence * multiplier)
        else:
            multiplier = 1.0
            multiplier_rationale = (
                f"Multiplier not applied (base confidence {base_confidence:.2%} "
                f"< threshold {self.min_base_confidence_for_multiplier:.0%})"
            )

        # Add multiplier info to metadata
        metadata["multiplier_applied"] = multiplier
        metadata["multiplier_rationale"] = multiplier_rationale
        metadata["base_confidence_before_multiplier"] = round(base_confidence, 4)

        calc_time = (time.perf_counter() - start_time) * 1000

        result = ConfluenceScore(
            score=score,
            direction=direction,
            confidence=confidence,
            contributing_factors=contributing_factors,
            signal_breakdown=signal_breakdown,
            timestamp=timestamp,
            calculation_time_ms=calc_time,
            metadata=metadata,
            multiplier_applied=multiplier,
            multiplier_rationale=multiplier_rationale,
        )

        # Log the result
        result.log_summary()

        return result

    def _calculate_weighted_signals(
        self,
        aggregated_signals: AggregatedSignals,
    ) -> list[dict[str, Any]]:
        """Calculate weighted scores for each signal.

        Args:
            aggregated_signals: Aggregated signals

        Returns:
            List of signal dicts with weights and scores
        """
        weighted = []

        for signal in aggregated_signals.signals:
            # Get combined weight
            weight = self.weights.get_weight(
                signal.indicator_type,
                signal.timeframe,
            )

            # Calculate weighted contribution
            weighted_score = signal.weighted_score * weight

            weighted.append(
                {
                    "signal": signal,
                    "weight": weight,
                    "weighted_score": weighted_score,
                    "direction": signal.direction,
                    "indicator_type": signal.indicator_type,
                    "timeframe": signal.timeframe,
                }
            )

        return weighted

    def _determine_direction(
        self,
        weighted_signals: list[dict[str, Any]],
    ) -> tuple[SignalDirection, float]:
        """Determine dominant direction from weighted signals.

        Args:
            weighted_signals: List of weighted signal dicts

        Returns:
            Tuple of (direction, confidence)
        """
        from market_analysis.confluence.signal_aggregator import SignalDirection

        long_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == SignalDirection.LONG
        )
        short_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == SignalDirection.SHORT
        )
        neutral_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == SignalDirection.NEUTRAL
        )

        total_weight = long_weight + short_weight + neutral_weight
        if total_weight == 0:
            return SignalDirection.NEUTRAL, 0.0

        # Normalize weights
        long_ratio = long_weight / total_weight
        short_ratio = short_weight / total_weight
        neutral_ratio = neutral_weight / total_weight

        # Determine direction
        if long_ratio > short_ratio and long_ratio > neutral_ratio:
            direction = SignalDirection.LONG
            confidence = long_ratio
        elif short_ratio > long_ratio and short_ratio > neutral_ratio:
            direction = SignalDirection.SHORT
            confidence = short_ratio
        else:
            direction = SignalDirection.NEUTRAL
            confidence = neutral_ratio

        return direction, confidence

    def _calculate_composite_score(
        self,
        weighted_signals: list[dict[str, Any]],
        direction: SignalDirection,
    ) -> tuple[float, dict[str, float]]:
        """Calculate composite confluence score.

        Score is based on:
        - Agreement among signals (direction alignment)
        - Signal strength and confidence
        - Number of contributing indicators
        - Timeframe diversity

        Args:
            weighted_signals: List of weighted signal dicts
            direction: Determined direction

        Returns:
            Tuple of (score 0-100, component breakdown)
        """
        from market_analysis.confluence.signal_aggregator import SignalDirection

        if not weighted_signals:
            return 50.0, {}

        # Calculate agreement score (how many signals agree with direction)
        agreeing_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == direction
        )
        total_weight = sum(ws["weighted_score"] for ws in weighted_signals)

        if total_weight == 0:
            return 50.0, {}

        agreement_ratio = agreeing_weight / total_weight

        # Calculate strength score (average weighted strength)
        avg_strength = sum(
            ws["signal"].strength * ws["weight"] for ws in weighted_signals
        ) / sum(ws["weight"] for ws in weighted_signals)

        # Calculate confidence score
        avg_confidence = sum(
            ws["signal"].confidence * ws["weight"] for ws in weighted_signals
        ) / sum(ws["weight"] for ws in weighted_signals)

        # Calculate diversity bonus (signals from different timeframes)
        timeframes = set(ws["timeframe"] for ws in weighted_signals)
        diversity_bonus = min(0.1, len(timeframes) * 0.02)  # Up to 0.1 bonus

        # Calculate indicator type diversity bonus
        indicator_types = set(ws["indicator_type"] for ws in weighted_signals)
        type_bonus = min(0.1, len(indicator_types) * 0.025)  # Up to 0.1 bonus

        # Composite score calculation
        # Base: agreement ratio (0-1)
        # Multipliers: strength, confidence
        # Bonuses: diversity, type variety
        base_score = agreement_ratio
        multiplier = (avg_strength + avg_confidence) / 2
        bonuses = diversity_bonus + type_bonus

        score = (base_score * multiplier + bonuses) * 100

        # Adjust for direction (neutral scores are centered)
        if direction == SignalDirection.NEUTRAL:
            # Neutral scores are centered around 50
            score = 50.0 + (score - 50.0) * 0.5  # Compress range

        # Clamp to valid range
        score = max(0.0, min(100.0, score))

        components = {
            "agreement_ratio": round(agreement_ratio, 3),
            "avg_strength": round(avg_strength, 3),
            "avg_confidence": round(avg_confidence, 3),
            "diversity_bonus": round(diversity_bonus, 3),
            "type_bonus": round(type_bonus, 3),
        }

        return score, components

    def _build_contributing_factors(
        self,
        weighted_signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build list of contributing factors for transparency.

        Args:
            weighted_signals: List of weighted signal dicts

        Returns:
            List of factor dictionaries
        """
        # Sort by weighted score (descending)
        sorted_signals = sorted(
            weighted_signals,
            key=lambda x: x["weighted_score"],
            reverse=True,
        )

        factors = []
        for ws in sorted_signals:
            signal = ws["signal"]
            factor = {
                "type": f"{signal.indicator_type}_{signal.timeframe}",
                "indicator": signal.indicator_type,
                "timeframe": signal.timeframe,
                "direction": str(signal.direction),
                "strength": round(signal.strength, 3),
                "confidence": round(signal.confidence, 3),
                "weight": round(ws["weight"], 3),
                "weighted_score": round(ws["weighted_score"], 3),
                "raw_value": signal.raw_value,
            }
            factors.append(factor)

        return factors

    def _build_signal_breakdown(
        self,
        weighted_signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build breakdown of signals by type and timeframe.

        Args:
            weighted_signals: List of weighted signal dicts

        Returns:
            Breakdown dictionary
        """
        # By indicator type
        by_indicator: dict[str, dict[str, Any]] = {}
        for ws in weighted_signals:
            ind_type = ws["indicator_type"]
            if ind_type not in by_indicator:
                by_indicator[ind_type] = {
                    "count": 0,
                    "total_weight": 0.0,
                    "directions": [],
                }
            by_indicator[ind_type]["count"] += 1
            by_indicator[ind_type]["total_weight"] += ws["weight"]
            by_indicator[ind_type]["directions"].append(str(ws["direction"]))

        # By timeframe
        by_timeframe: dict[str, dict[str, Any]] = {}
        for ws in weighted_signals:
            tf = ws["timeframe"]
            if tf not in by_timeframe:
                by_timeframe[tf] = {
                    "count": 0,
                    "total_weight": 0.0,
                    "directions": [],
                }
            by_timeframe[tf]["count"] += 1
            by_timeframe[tf]["total_weight"] += ws["weight"]
            by_timeframe[tf]["directions"].append(str(ws["direction"]))

        return {
            "by_indicator": by_indicator,
            "by_timeframe": by_timeframe,
            "total_signals": len(weighted_signals),
        }

    def _calculate_confidence(
        self,
        weighted_signals: list[dict[str, Any]],
        direction_confidence: float,
        aggregated_signals: AggregatedSignals,
    ) -> float:
        """Calculate overall confidence score.

        Args:
            weighted_signals: List of weighted signal dicts
            direction_confidence: Confidence in direction determination
            aggregated_signals: Original aggregated signals

        Returns:
            Overall confidence (0.0-1.0)
        """
        if not weighted_signals:
            return 0.0

        # Average signal confidence
        avg_signal_confidence = sum(
            ws["signal"].confidence for ws in weighted_signals
        ) / len(weighted_signals)

        # Number of signals factor (more signals = more confidence, up to a point)
        signal_count_factor = min(1.0, len(weighted_signals) / 5)  # Max at 5+ signals

        # Combine factors
        confidence: float = (
            avg_signal_confidence * 0.4
            + direction_confidence * 0.4
            + signal_count_factor * 0.2
        )

        return float(min(1.0, max(0.0, confidence)))

    def _has_conflicting_signals(
        self,
        weighted_signals: list[dict[str, Any]],
    ) -> bool:
        """Check if signals are significantly conflicting.

        Args:
            weighted_signals: List of weighted signal dicts

        Returns:
            True if strong conflicting signals detected
        """
        from market_analysis.confluence.signal_aggregator import SignalDirection

        if len(weighted_signals) < 2:
            return False

        long_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == SignalDirection.LONG
        )
        short_weight = sum(
            ws["weighted_score"]
            for ws in weighted_signals
            if ws["direction"] == SignalDirection.SHORT
        )

        total_directional = long_weight + short_weight
        if total_directional == 0:
            return False

        # Check if both directions have significant weight
        long_ratio = long_weight / total_directional
        short_ratio = short_weight / total_directional

        # Conflict if both directions have > 35% weight
        result: bool = (
            long_ratio > self.conflict_neutral_threshold
            and short_ratio > self.conflict_neutral_threshold
        )
        return result

    def _calculate_timeframe_multiplier(
        self,
        weighted_signals: list[dict[str, Any]],
    ) -> tuple[float, str]:
        """Calculate confidence multiplier based on timeframe agreement.

        Multiplier increases with more timeframes agreeing on the same direction,
        but is reduced when conflicting signals exist across timeframes or
        indicator types.

        Multiplier scale:
        - 1.0x: Single timeframe or conflicting signals
        - 1.1x: 2 timeframes agreeing
        - 1.2x: 3 timeframes agreeing
        - 1.3x: 4 timeframes agreeing
        - 1.5x: 5+ timeframes agreeing (max)

        Args:
            weighted_signals: List of weighted signal dicts

        Returns:
            Tuple of (multiplier value, rationale string)
        """
        from market_analysis.confluence.signal_aggregator import SignalDirection

        if not weighted_signals:
            return 1.0, "No signals - no multiplier applied"

        # Group signals by timeframe and determine dominant direction per timeframe
        timeframe_directions: dict[str, dict[str, Any]] = {}
        for ws in weighted_signals:
            tf = ws["timeframe"]
            if tf not in timeframe_directions:
                timeframe_directions[tf] = {
                    "long_weight": 0.0,
                    "short_weight": 0.0,
                    "neutral_weight": 0.0,
                    "total_weight": 0.0,
                }

            weight = ws["weighted_score"]
            direction = ws["direction"]

            timeframe_directions[tf]["total_weight"] += weight
            if direction == SignalDirection.LONG:
                timeframe_directions[tf]["long_weight"] += weight
            elif direction == SignalDirection.SHORT:
                timeframe_directions[tf]["short_weight"] += weight
            else:
                timeframe_directions[tf]["neutral_weight"] += weight

        # Determine dominant direction for each timeframe
        agreeing_timeframes = 0
        conflicting_timeframes = 0
        dominant_directions: list[SignalDirection] = []

        for tf_data in timeframe_directions.values():
            total = tf_data["total_weight"]
            if total == 0:
                continue

            long_ratio = tf_data["long_weight"] / total
            short_ratio = tf_data["short_weight"] / total
            neutral_ratio = tf_data["neutral_weight"] / total

            # Determine dominant direction for this timeframe
            if long_ratio > short_ratio and long_ratio > neutral_ratio:
                tf_direction = SignalDirection.LONG
            elif short_ratio > long_ratio and short_ratio > neutral_ratio:
                tf_direction = SignalDirection.SHORT
            else:
                tf_direction = SignalDirection.NEUTRAL

            dominant_directions.append(tf_direction)

        # Count agreeing vs conflicting timeframes
        if dominant_directions:
            # Find overall dominant direction across all timeframes
            long_count = sum(
                1 for d in dominant_directions if d == SignalDirection.LONG
            )
            short_count = sum(
                1 for d in dominant_directions if d == SignalDirection.SHORT
            )
            neutral_count = sum(
                1 for d in dominant_directions if d == SignalDirection.NEUTRAL
            )

            if long_count > short_count and long_count > neutral_count:
                overall_direction = SignalDirection.LONG
            elif short_count > long_count and short_count > neutral_count:
                overall_direction = SignalDirection.SHORT
            else:
                overall_direction = SignalDirection.NEUTRAL

            # Count agreeing and conflicting
            for tf_dir in dominant_directions:
                if tf_dir == overall_direction and tf_dir != SignalDirection.NEUTRAL:
                    agreeing_timeframes += 1
                elif tf_dir != overall_direction and tf_dir != SignalDirection.NEUTRAL:
                    conflicting_timeframes += 1

        # Calculate base multiplier based on agreeing timeframe count
        if agreeing_timeframes >= 5:
            base_multiplier = 1.5
        elif agreeing_timeframes == 4:
            base_multiplier = 1.3
        elif agreeing_timeframes == 3:
            base_multiplier = 1.2
        elif agreeing_timeframes == 2:
            base_multiplier = 1.1
        else:
            base_multiplier = 1.0

        # Reduce multiplier for conflicting timeframes
        if conflicting_timeframes > 0:
            # Each conflicting timeframe reduces multiplier
            conflict_penalty = min(0.3, conflicting_timeframes * 0.15)
            final_multiplier = max(1.0, base_multiplier - conflict_penalty)
            rationale = (
                f"Base multiplier {base_multiplier:.1f}x for {agreeing_timeframes} "
                f"agreeing timeframes, reduced to {final_multiplier:.1f}x due to "
                f"{conflicting_timeframes} conflicting timeframe(s)"
            )
        else:
            final_multiplier = base_multiplier
            if agreeing_timeframes >= 2:
                rationale = (
                    f"Multiplier {final_multiplier:.1f}x for {agreeing_timeframes} "
                    f"agreeing timeframes"
                )
            else:
                rationale = (
                    f"Multiplier {final_multiplier:.1f}x (single timeframe, "
                    f"no agreement boost)"
                )

        return final_multiplier, rationale


# Import at end to avoid circular imports
from market_analysis.confluence.signal_aggregator import (  # noqa: E402
    SignalDirection,
)
