"""StrongSystem Hypothesis Scoring (ST-ICT-029).

Implements bullish/bearish hypothesis scoring based on institutional order flow
alignment. The StrongSystem evaluates market structure to determine whether
price action supports a bullish or bearish thesis.

Hypothesis Components:
    - Market structure bias (higher highs/lows vs lower highs/lows)
    - Institutional order flow alignment (smart money activity)
    - Liquidity sweep analysis
    - Break of structure confirmation

Scoring:
    - Hypothesis score ranges from -1.0 (strong bearish) to +1.0 (strong bullish)
    - Score near 0 indicates neutral/no clear hypothesis
    - |score| >= 0.6 is considered a "strong" hypothesis

Integration:
    - Combined with existing ICT signals via StrongSystemIntegrator
    - Aligned hypotheses add 0.1-0.2 confidence multiplier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HypothesisDirection(str, Enum):
    """Direction of the StrongSystem hypothesis."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class HypothesisStrength(str, Enum):
    """Strength tier for hypothesis scoring."""

    STRONG = "strong"  # |score| >= 0.6
    MODERATE = "moderate"  # 0.3 <= |score| < 0.6
    WEAK = "weak"  # 0.1 <= |score| < 0.3
    NONE = "none"  # |score| < 0.1


# Score thresholds for strength tiers
STRENGTH_THRESHOLDS = {
    HypothesisStrength.STRONG: 0.6,
    HypothesisStrength.MODERATE: 0.3,
    HypothesisStrength.WEAK: 0.1,
}

# Weighting for hypothesis components
HYPOTHESIS_WEIGHTS = {
    "market_structure": 0.30,
    "order_flow": 0.35,
    "liquidity_sweep": 0.20,
    "bos_confirmation": 0.15,
}


@dataclass
class MarketStructureEvidence:
    """Evidence from market structure analysis.

    Attributes:
        higher_highs: Count of recent higher highs (bullish indicator)
        higher_lows: Count of recent higher lows (bullish indicator)
        lower_highs: Count of recent lower highs (bearish indicator)
        lower_lows: Count of recent lower lows (bearish indicator)
        trend_duration_bars: Duration of current structural trend in bars
    """

    higher_highs: int = 0
    higher_lows: int = 0
    lower_highs: int = 0
    lower_lows: int = 0
    trend_duration_bars: int = 0


@dataclass
class OrderFlowEvidence:
    """Evidence from institutional order flow analysis.

    Attributes:
        bullish_volume_delta: Net buying pressure (positive = bullish)
        bearish_volume_delta: Net selling pressure (positive = bearish)
        large_order_ratio: Ratio of institutional-sized orders
        absorption_events: Count of absorption events (rejection of price)
    """

    bullish_volume_delta: float = 0.0
    bearish_volume_delta: float = 0.0
    large_order_ratio: float = 0.0
    absorption_events: int = 0


@dataclass
class LiquiditySweepEvidence:
    """Evidence from liquidity sweep analysis.

    Attributes:
        buy_side_swept: Whether buy-side liquidity was recently swept
        sell_side_swept: Whether sell-side liquidity was recently swept
        sweep_magnitude: Size of the sweep relative to ATR
        displacement_after: Whether displacement followed the sweep
    """

    buy_side_swept: bool = False
    sell_side_swept: bool = False
    sweep_magnitude: float = 0.0
    displacement_after: bool = False


@dataclass
class BOSConfirmation:
    """Break of Structure confirmation evidence.

    Attributes:
        bullish_bos: Whether a bullish BOS occurred
        bearish_bos: Whether a bearish BOS occurred
        bos_count: Number of BOS events in current trend
        is_validated: Whether the BOS is validated by displacement
    """

    bullish_bos: bool = False
    bearish_bos: bool = False
    bos_count: int = 0
    is_validated: bool = False


@dataclass
class HypothesisScore:
    """Scored hypothesis result.

    Attributes:
        direction: The hypothesized direction (bullish/bearish/neutral)
        strength: The strength tier of the hypothesis
        raw_score: Raw hypothesis score (-1.0 to +1.0)
        component_scores: Individual component scores
        component_weights: Weights used for each component
        is_aligned_with_structure: Whether hypothesis aligns with visible structure
        confidence_contribution: Contribution to overall signal confidence (0.0-0.2)
    """

    direction: HypothesisDirection = HypothesisDirection.NEUTRAL
    strength: HypothesisStrength = HypothesisStrength.NONE
    raw_score: float = 0.0
    component_scores: dict[str, float] = field(default_factory=dict)
    component_weights: dict[str, float] = field(default_factory=dict)
    is_aligned_with_structure: bool = False
    confidence_contribution: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "direction": self.direction.value,
            "strength": self.strength.value,
            "raw_score": round(self.raw_score, 4),
            "component_scores": {
                k: round(v, 4) for k, v in self.component_scores.items()
            },
            "is_aligned_with_structure": self.is_aligned_with_structure,
            "confidence_contribution": round(self.confidence_contribution, 4),
        }


class StrongSystemHypothesis:
    """Scores bullish/bearish hypotheses based on institutional order flow.

    The hypothesis scorer evaluates four key components:
    1. Market structure (30% weight): Higher highs/lows vs lower highs/lows
    2. Order flow (35% weight): Institutional volume and order analysis
    3. Liquidity sweep (20% weight): Sweep and displacement patterns
    4. BOS confirmation (15% weight): Break of structure validation

    Usage:
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=structure_ev,
            order_flow=flow_ev,
            liquidity_sweep=sweep_ev,
            bos_confirmation=bos_ev,
        )
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        strength_thresholds: dict[HypothesisStrength, float] | None = None,
    ):
        """Initialize hypothesis scorer.

        Args:
            weights: Component weights (default: HYPOTHESIS_WEIGHTS)
            strength_thresholds: Strength tier thresholds (default: STRENGTH_THRESHOLDS)
        """
        self.weights = weights or dict(HYPOTHESIS_WEIGHTS)
        self.strength_thresholds = strength_thresholds or dict(STRENGTH_THRESHOLDS)

    def _score_market_structure(
        self,
        evidence: MarketStructureEvidence,
    ) -> float:
        """Score market structure component (-1.0 to +1.0).

        Bullish evidence: higher highs and higher lows
        Bearish evidence: lower highs and lower lows

        Args:
            evidence: Market structure evidence

        Returns:
            Score from -1.0 (bearish) to +1.0 (bullish)
        """
        bullish_count = evidence.higher_highs + evidence.higher_lows
        bearish_count = evidence.lower_highs + evidence.lower_lows
        total = bullish_count + bearish_count

        if total == 0:
            return 0.0

        raw = (bullish_count - bearish_count) / total

        # Boost for sustained trends
        duration_bonus = min(evidence.trend_duration_bars / 20.0, 0.2)
        boosted = raw + (duration_bonus if raw > 0 else -duration_bonus)

        return max(-1.0, min(1.0, boosted))

    def _score_order_flow(
        self,
        evidence: OrderFlowEvidence,
    ) -> float:
        """Score order flow component (-1.0 to +1.0).

        Bullish evidence: net buying pressure, institutional buying
        Bearish evidence: net selling pressure, institutional selling

        Args:
            evidence: Order flow evidence

        Returns:
            Score from -1.0 (bearish) to +1.0 (bullish)
        """
        total_delta = evidence.bullish_volume_delta - evidence.bearish_volume_delta

        # Normalize delta: assume large delta values saturate at ±1.0
        normalized = max(-1.0, min(1.0, total_delta / 1_000_000))

        # Large order ratio bias
        institutional_bias = (evidence.large_order_ratio - 0.5) * 0.3

        # Absorption events indicate rejection (contrarian signal)
        absorption_impact = evidence.absorption_events * 0.05

        combined = normalized + institutional_bias - absorption_impact
        return max(-1.0, min(1.0, combined))

    def _score_liquidity_sweep(
        self,
        evidence: LiquiditySweepEvidence,
    ) -> float:
        """Score liquidity sweep component (-1.0 to +1.0).

        Buy-side swept + displacement after = bullish (liquidity taken,
        then price moves away from swept level)
        Sell-side swept + displacement after = bearish

        Args:
            evidence: Liquidity sweep evidence

        Returns:
            Score from -1.0 (bearish) to +1.0 (bullish)
        """
        if not (evidence.buy_side_swept or evidence.sell_side_swept):
            return 0.0

        score = 0.0

        if evidence.buy_side_swept and evidence.displacement_after:
            # Swept buy-side liquidity, displaced lower = bearish continuation
            score = -0.5 * evidence.sweep_magnitude
        elif evidence.buy_side_swept and not evidence.displacement_after:
            # Swept buy-side, no displacement = potential bullish reversal
            score = 0.3 * evidence.sweep_magnitude

        if evidence.sell_side_swept and evidence.displacement_after:
            # Swept sell-side liquidity, displaced higher = bullish continuation
            score = 0.5 * evidence.sweep_magnitude
        elif evidence.sell_side_swept and not evidence.displacement_after:
            # Swept sell-side, no displacement = potential bearish reversal
            score = -0.3 * evidence.sweep_magnitude

        return max(-1.0, min(1.0, score))

    def _score_bos_confirmation(
        self,
        evidence: BOSConfirmation,
    ) -> float:
        """Score BOS confirmation component (-1.0 to +1.0).

        Validated bullish BOS = bullish, validated bearish BOS = bearish.
        Multiple BOS in same direction = stronger conviction.

        Args:
            evidence: BOS confirmation evidence

        Returns:
            Score from -1.0 (bearish) to +1.0 (bullish)
        """
        if not (evidence.bullish_bos or evidence.bearish_bos):
            return 0.0

        base = 0.5 if evidence.is_validated else 0.25
        count_multiplier = min(evidence.bos_count, 3) / 3.0

        if evidence.bullish_bos:
            return base * count_multiplier
        elif evidence.bearish_bos:
            return -base * count_multiplier
        return 0.0

    def _classify_strength(self, abs_score: float) -> HypothesisStrength:
        """Classify hypothesis strength from absolute score.

        Args:
            abs_score: Absolute value of the hypothesis score

        Returns:
            HypothesisStrength tier
        """
        if abs_score >= self.strength_thresholds[HypothesisStrength.STRONG]:
            return HypothesisStrength.STRONG
        elif abs_score >= self.strength_thresholds[HypothesisStrength.MODERATE]:
            return HypothesisStrength.MODERATE
        elif abs_score >= self.strength_thresholds[HypothesisStrength.WEAK]:
            return HypothesisStrength.WEAK
        return HypothesisStrength.NONE

    def _classify_direction(self, score: float) -> HypothesisDirection:
        """Classify hypothesis direction from score.

        Args:
            score: The hypothesis score

        Returns:
            HypothesisDirection
        """
        abs_score = abs(score)
        if abs_score < self.strength_thresholds[HypothesisStrength.WEAK]:
            return HypothesisDirection.NEUTRAL
        elif score > 0:
            return HypothesisDirection.BULLISH
        elif score < 0:
            return HypothesisDirection.BEARISH
        return HypothesisDirection.NEUTRAL

    def _calculate_confidence_contribution(
        self,
        score: float,
        strength: HypothesisStrength,
    ) -> float:
        """Calculate confidence contribution (0.0 to 0.2).

        Per AC4: StrongSystem score adds 0.1-0.2 confidence multiplier
        when aligned. The contribution scales with hypothesis strength.

        Args:
            score: Raw hypothesis score
            strength: Hypothesis strength tier

        Returns:
            Confidence contribution (0.0 to 0.2)
        """
        if strength == HypothesisStrength.NONE:
            return 0.0
        if strength == HypothesisStrength.WEAK:
            return 0.05  # Below the 0.1 floor, not counted
        if strength == HypothesisStrength.MODERATE:
            return 0.1
        if strength == HypothesisStrength.STRONG:
            # Scale from 0.1 to 0.2 based on score proximity to ±1.0
            base = 0.1
            bonus = (
                abs(score) - self.strength_thresholds[HypothesisStrength.STRONG]
            ) / (1.0 - self.strength_thresholds[HypothesisStrength.STRONG])
            return base + 0.1 * max(0.0, min(1.0, bonus))
        return 0.0

    def score_hypothesis(
        self,
        market_structure: MarketStructureEvidence,
        order_flow: OrderFlowEvidence,
        liquidity_sweep: LiquiditySweepEvidence,
        bos_confirmation: BOSConfirmation,
    ) -> HypothesisScore:
        """Score the overall bullish/bearish hypothesis.

        Combines all four evidence components using weighted scoring to
        produce a final hypothesis score from -1.0 to +1.0.

        Args:
            market_structure: Market structure evidence
            order_flow: Order flow evidence
            liquidity_sweep: Liquidity sweep evidence
            bos_confirmation: BOS confirmation evidence

        Returns:
            HypothesisScore with direction, strength, and confidence data
        """
        ms_score = self._score_market_structure(market_structure)
        of_score = self._score_order_flow(order_flow)
        ls_score = self._score_liquidity_sweep(liquidity_sweep)
        bos_score = self._score_bos_confirmation(bos_confirmation)

        component_scores = {
            "market_structure": ms_score,
            "order_flow": of_score,
            "liquidity_sweep": ls_score,
            "bos_confirmation": bos_score,
        }

        # Weighted combination
        total_score = sum(
            component_scores[k] * self.weights.get(k, 0.0) for k in self.weights
        )
        total_score = max(-1.0, min(1.0, total_score))

        strength = self._classify_strength(abs(total_score))
        direction = self._classify_direction(total_score)
        confidence_contrib = self._calculate_confidence_contribution(
            total_score, strength
        )

        # Check alignment: majority of components agree with direction
        aligned_count = sum(
            1
            for v in component_scores.values()
            if (total_score > 0 and v > 0) or (total_score < 0 and v < 0)
        )
        is_aligned = aligned_count >= 3  # At least 3 of 4 components agree

        return HypothesisScore(
            direction=direction,
            strength=strength,
            raw_score=total_score,
            component_scores=component_scores,
            component_weights=dict(self.weights),
            is_aligned_with_structure=is_aligned,
            confidence_contribution=confidence_contrib,
        )


# Global scorer instance
_scorer_instance: StrongSystemHypothesis | None = None


def get_hypothesis_scorer() -> StrongSystemHypothesis:
    """Get or create the global StrongSystemHypothesis instance.

    Returns:
        Global StrongSystemHypothesis instance
    """
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = StrongSystemHypothesis()
    return _scorer_instance
