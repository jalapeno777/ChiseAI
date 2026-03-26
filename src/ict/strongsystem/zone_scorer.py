"""StrongSystem Zone Scoring (ST-ICT-029).

Scores ICT zones (Order Blocks, FVGs, etc.) based on their alignment with
the StrongSystem hypothesis. Zones that align with institutional order flow
receive enhanced scoring.

Zone Scoring Logic:
    - Zone aligned with bullish hypothesis + zone is bullish: +enhancement
    - Zone aligned with bearish hypothesis + zone is bearish: +enhancement
    - Zone contradicts hypothesis: neutral or reduced score
    - Strong hypothesis alignment yields 0.1-0.2 multiplier on zone confidence

Integration:
    - Takes HypothesisScore from hypothesis.py
    - Produces ZoneScoreResult for use by the integrator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ZoneType(str, Enum):
    """Types of ICT zones."""

    ORDER_BLOCK = "order_block"
    FVG = "fvg"  # Fair Value Gap
    LIQUIDITY_POOL = "liquidity_pool"
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    BREAKER_BLOCK = "breaker_block"
    MITIGATION_BLOCK = "mitigation_block"


class ZoneDirection(str, Enum):
    """Direction of a zone."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class ZoneAlignment(str, Enum):
    """Alignment of a zone with the StrongSystem hypothesis."""

    ALIGNED = "aligned"  # Zone direction matches hypothesis direction
    CONTRADICTING = "contradicting"  # Zone opposes hypothesis
    NEUTRAL = "neutral"  # Hypothesis is neutral, no alignment check
    AMBIGUOUS = "ambiguous"  # Partial alignment


# Alignment enhancement multipliers
ALIGNMENT_MULTIPLIERS = {
    ZoneAlignment.ALIGNED: 0.2,  # Max 0.2 for full alignment
    ZoneAlignment.CONTRADICTING: 0.0,  # No enhancement
    ZoneAlignment.NEUTRAL: 0.05,  # Small neutral bonus
    ZoneAlignment.AMBIGUOUS: 0.1,  # Partial enhancement
}


@dataclass
class ICTZone:
    """Represents an ICT zone for scoring.

    Attributes:
        zone_type: The type of ICT zone
        direction: Bullish or bearish zone
        price_level: The price level of the zone
        zone_width: Width of the zone in price units
        is_unmitigated: Whether the zone has been mitigated (tested)
        touch_count: Number of times price has touched the zone
        age_bars: Age of the zone in bars
        base_confidence: Base confidence from zone validation (0.0-1.0)
    """

    zone_type: ZoneType
    direction: ZoneDirection
    price_level: float
    zone_width: float = 0.0
    is_unmitigated: bool = True
    touch_count: int = 0
    age_bars: int = 0
    base_confidence: float = 0.5


@dataclass
class ZoneScoreResult:
    """Result of zone scoring with StrongSystem alignment.

    Attributes:
        zone: The original ICT zone
        alignment: How the zone aligns with the hypothesis
        hypothesis_direction: The hypothesis direction used for scoring
        enhancement: The confidence enhancement (0.0-0.2)
        final_confidence: Zone confidence after enhancement
        is_valid_target: Whether this zone is a valid entry target
        scoring_factors: Factors that influenced the score
    """

    zone: ICTZone
    alignment: ZoneAlignment = ZoneAlignment.NEUTRAL
    hypothesis_direction: str = "neutral"
    enhancement: float = 0.0
    final_confidence: float = 0.0
    is_valid_target: bool = False
    scoring_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "zone_type": self.zone.zone_type.value,
            "zone_direction": self.zone.direction.value,
            "price_level": self.zone.price_level,
            "alignment": self.alignment.value,
            "hypothesis_direction": self.hypothesis_direction,
            "enhancement": round(self.enhancement, 4),
            "final_confidence": round(self.final_confidence, 4),
            "is_valid_target": self.is_valid_target,
            "scoring_factors": self.scoring_factors,
        }


class ZoneScorer:
    """Scores ICT zones based on StrongSystem hypothesis alignment.

    The zone scorer evaluates how well each ICT zone aligns with the
    current institutional order flow hypothesis to produce enhanced
    zone confidence scores.

    Usage:
        scorer = ZoneScorer()
        result = scorer.score_zone(zone, hypothesis_score)
    """

    def __init__(
        self,
        alignment_multipliers: dict[ZoneAlignment, float] | None = None,
        min_confidence_for_target: float = 0.4,
        unmitigated_bonus: float = 0.1,
        max_touch_penalty: float = 0.15,
        max_touch_count: int = 3,
    ):
        """Initialize zone scorer.

        Args:
            alignment_multipliers: Enhancement multipliers per alignment
            min_confidence_for_target: Min confidence for valid target
            unmitigated_bonus: Bonus for unmitigated zones
            max_touch_penalty: Penalty per touch beyond max_touch_count
            max_touch_count: Touches before penalty applies
        """
        self.alignment_multipliers = alignment_multipliers or dict(
            ALIGNMENT_MULTIPLIERS
        )
        self.min_confidence_for_target = min_confidence_for_target
        self.unmitigated_bonus = unmitigated_bonus
        self.max_touch_penalty = max_touch_penalty
        self.max_touch_count = max_touch_count

    def _determine_alignment(
        self,
        zone: ICTZone,
        hypothesis_direction: str,
        hypothesis_strength: str,
    ) -> ZoneAlignment:
        """Determine how a zone aligns with the hypothesis.

        Args:
            zone: The ICT zone to evaluate
            hypothesis_direction: Direction from HypothesisScore
            hypothesis_strength: Strength from HypothesisScore

        Returns:
            ZoneAlignment classification
        """
        if hypothesis_direction == "neutral" or hypothesis_strength == "none":
            return ZoneAlignment.NEUTRAL

        zone_bullish = zone.direction == ZoneDirection.BULLISH
        hypo_bullish = hypothesis_direction == "bullish"

        if zone_bullish == hypo_bullish:
            if hypothesis_strength in ("strong", "moderate"):
                return ZoneAlignment.ALIGNED
            else:
                return ZoneAlignment.AMBIGUOUS
        else:
            if hypothesis_strength in ("strong", "moderate"):
                return ZoneAlignment.CONTRADICTING
            else:
                return ZoneAlignment.AMBIGUOUS

    def _calculate_touch_penalty(self, zone: ICTZone) -> float:
        """Calculate penalty for multiple touches on a zone.

        Zones that have been tested multiple times are less reliable.

        Args:
            zone: The ICT zone

        Returns:
            Penalty value (0.0 to max_touch_penalty)
        """
        if zone.touch_count <= self.max_touch_count:
            return 0.0
        excess = zone.touch_count - self.max_touch_count
        return min(excess * 0.05, self.max_touch_penalty)

    def _calculate_age_decay(self, zone: ICTZone) -> float:
        """Calculate confidence decay based on zone age.

        Args:
            zone: The ICT zone

        Returns:
            Decay factor (0.0 = no decay, up to 0.3 = heavy decay)
        """
        if zone.age_bars <= 50:
            return 0.0
        if zone.age_bars <= 100:
            return 0.05
        if zone.age_bars <= 200:
            return 0.1
        return 0.3

    def score_zone(
        self,
        zone: ICTZone,
        hypothesis_score: Any,  # HypothesisScore
    ) -> ZoneScoreResult:
        """Score a single ICT zone against the hypothesis.

        Args:
            zone: The ICT zone to score
            hypothesis_score: HypothesisScore from StrongSystemHypothesis

        Returns:
            ZoneScoreResult with alignment and enhanced confidence
        """
        factors: list[str] = []

        # Determine alignment
        alignment = self._determine_alignment(
            zone,
            hypothesis_score.direction.value,
            hypothesis_score.strength.value,
        )
        factors.append(f"alignment={alignment.value}")

        # Base enhancement from alignment
        base_enhancement = self.alignment_multipliers.get(alignment, 0.0)

        # Scale enhancement by hypothesis strength
        if hypothesis_score.strength.value == "strong":
            enhancement_scale = 1.0
        elif hypothesis_score.strength.value == "moderate":
            enhancement_scale = 0.7
        elif hypothesis_score.strength.value == "weak":
            enhancement_scale = 0.3
        else:
            enhancement_scale = 0.0

        enhancement = base_enhancement * enhancement_scale
        factors.append(f"strength_scale={enhancement_scale:.1f}")

        # Apply unmitigated bonus (only for aligned/neutral zones)
        if zone.is_unmitigated and alignment != ZoneAlignment.CONTRADICTING:
            enhancement += self.unmitigated_bonus
            factors.append("unmitigated_bonus")

        # Apply touch penalty
        touch_penalty = self._calculate_touch_penalty(zone)
        if touch_penalty > 0:
            enhancement -= touch_penalty
            factors.append(f"touch_penalty={touch_penalty:.2f}")

        # Apply age decay to enhancement (not to base confidence)
        age_decay = self._calculate_age_decay(zone)
        if age_decay > 0:
            enhancement *= 1.0 - age_decay
            factors.append(f"age_decay={age_decay:.2f}")

        # Clamp enhancement to 0.0-0.2 range
        enhancement = max(0.0, min(0.2, enhancement))

        # Calculate final confidence
        final_confidence = min(1.0, zone.base_confidence + enhancement)

        # Determine if this is a valid target
        is_valid = (
            final_confidence >= self.min_confidence_for_target
            and alignment in (ZoneAlignment.ALIGNED, ZoneAlignment.NEUTRAL)
            and zone.is_unmitigated
        )

        return ZoneScoreResult(
            zone=zone,
            alignment=alignment,
            hypothesis_direction=hypothesis_score.direction.value,
            enhancement=enhancement,
            final_confidence=final_confidence,
            is_valid_target=is_valid,
            scoring_factors=factors,
        )

    def score_zones(
        self,
        zones: list[ICTZone],
        hypothesis_score: Any,  # HypothesisScore
    ) -> list[ZoneScoreResult]:
        """Score multiple ICT zones against the hypothesis.

        Args:
            zones: List of ICT zones to score
            hypothesis_score: HypothesisScore from StrongSystemHypothesis

        Returns:
            List of ZoneScoreResult sorted by final_confidence (descending)
        """
        results = [self.score_zone(z, hypothesis_score) for z in zones]
        results.sort(key=lambda r: r.final_confidence, reverse=True)
        return results


# Global scorer instance
_zone_scorer_instance: ZoneScorer | None = None


def get_zone_scorer() -> ZoneScorer:
    """Get or create the global ZoneScorer instance.

    Returns:
        Global ZoneScorer instance
    """
    global _zone_scorer_instance
    if _zone_scorer_instance is None:
        _zone_scorer_instance = ZoneScorer()
    return _zone_scorer_instance
