"""Tests for StrongSystem Zone Scoring (ST-ICT-029).

Tests the ICT zone scoring against hypothesis alignment:
- Zone alignment classification
- Touch penalty calculation
- Age decay calculation
- Enhancement clamping (0.0-0.2)
- Valid target determination
- Multi-zone scoring and sorting
"""

import pytest

from ict.strongsystem.hypothesis import (
    HypothesisDirection,
    HypothesisScore,
    HypothesisStrength,
)
from ict.strongsystem.zone_scorer import (
    ALIGNMENT_MULTIPLIERS,
    ICTZone,
    ZoneAlignment,
    ZoneDirection,
    ZoneScorer,
    ZoneScoreResult,
    ZoneType,
    get_zone_scorer,
)


# --- Helpers ---


def _bullish_hypothesis(
    strength: str = "strong",
    score: float = 0.8,
) -> HypothesisScore:
    """Create a bullish hypothesis score."""
    return HypothesisScore(
        direction=HypothesisDirection.BULLISH,
        strength=HypothesisStrength(strength),
        raw_score=score,
        is_aligned_with_structure=True,
        confidence_contribution=0.15,
    )


def _bearish_hypothesis(
    strength: str = "strong",
    score: float = -0.8,
) -> HypothesisScore:
    """Create a bearish hypothesis score."""
    return HypothesisScore(
        direction=HypothesisDirection.BEARISH,
        strength=HypothesisStrength(strength),
        raw_score=score,
        is_aligned_with_structure=True,
        confidence_contribution=0.15,
    )


def _neutral_hypothesis() -> HypothesisScore:
    """Create a neutral hypothesis score."""
    return HypothesisScore(
        direction=HypothesisDirection.NEUTRAL,
        strength=HypothesisStrength.NONE,
        raw_score=0.0,
    )


def _bullish_ob() -> ICTZone:
    """Create a bullish order block."""
    return ICTZone(
        zone_type=ZoneType.ORDER_BLOCK,
        direction=ZoneDirection.BULLISH,
        price_level=100.0,
        zone_width=2.0,
        is_unmitigated=True,
        touch_count=0,
        age_bars=10,
        base_confidence=0.7,
    )


def _bearish_ob() -> ICTZone:
    """Create a bearish order block."""
    return ICTZone(
        zone_type=ZoneType.ORDER_BLOCK,
        direction=ZoneDirection.BEARISH,
        price_level=105.0,
        zone_width=2.0,
        is_unmitigated=True,
        touch_count=0,
        age_bars=10,
        base_confidence=0.7,
    )


def _bullish_fvg() -> ICTZone:
    """Create a bullish FVG."""
    return ICTZone(
        zone_type=ZoneType.FVG,
        direction=ZoneDirection.BULLISH,
        price_level=98.0,
        zone_width=1.5,
        is_unmitigated=True,
        touch_count=1,
        age_bars=30,
        base_confidence=0.6,
    )


# --- Tests ---


class TestZoneEnums:
    """Test zone-related enums."""

    def test_zone_type_values(self):
        assert ZoneType.ORDER_BLOCK.value == "order_block"
        assert ZoneType.FVG.value == "fvg"
        assert ZoneType.LIQUIDITY_POOL.value == "liquidity_pool"

    def test_zone_direction_values(self):
        assert ZoneDirection.BULLISH.value == "bullish"
        assert ZoneDirection.BEARISH.value == "bearish"

    def test_zone_alignment_values(self):
        assert ZoneAlignment.ALIGNED.value == "aligned"
        assert ZoneAlignment.CONTRADICTING.value == "contradicting"
        assert ZoneAlignment.NEUTRAL.value == "neutral"
        assert ZoneAlignment.AMBIGUOUS.value == "ambiguous"


class TestAlignmentDetermination:
    """Test zone-hypothesis alignment logic."""

    def test_bullish_zone_aligned_with_bullish_hypothesis(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        alignment = scorer._determine_alignment(
            zone,
            hypo.direction.value,
            hypo.strength.value,
        )
        assert alignment == ZoneAlignment.ALIGNED

    def test_bullish_zone_contradicts_bearish_hypothesis(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bearish_hypothesis()
        alignment = scorer._determine_alignment(
            zone,
            hypo.direction.value,
            hypo.strength.value,
        )
        assert alignment == ZoneAlignment.CONTRADICTING

    def test_bearish_zone_aligned_with_bearish_hypothesis(self):
        scorer = ZoneScorer()
        zone = _bearish_ob()
        hypo = _bearish_hypothesis()
        alignment = scorer._determine_alignment(
            zone,
            hypo.direction.value,
            hypo.strength.value,
        )
        assert alignment == ZoneAlignment.ALIGNED

    def test_neutral_hypothesis_gives_neutral_alignment(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _neutral_hypothesis()
        alignment = scorer._determine_alignment(
            zone,
            hypo.direction.value,
            hypo.strength.value,
        )
        assert alignment == ZoneAlignment.NEUTRAL

    def test_weak_hypothesis_gives_ambiguous_alignment(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis(strength="weak", score=0.2)
        alignment = scorer._determine_alignment(
            zone,
            hypo.direction.value,
            hypo.strength.value,
        )
        assert alignment == ZoneAlignment.AMBIGUOUS


class TestTouchPenalty:
    """Test touch count penalty calculation."""

    def test_no_penalty_within_limit(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            touch_count=3,
        )
        assert scorer._calculate_touch_penalty(zone) == 0.0

    def test_penalty_after_max_touches(self):
        scorer = ZoneScorer(max_touch_count=3, max_touch_penalty=0.15)
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            touch_count=5,
        )
        penalty = scorer._calculate_touch_penalty(zone)
        assert penalty > 0

    def test_penalty_capped(self):
        scorer = ZoneScorer(max_touch_count=3, max_touch_penalty=0.15)
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            touch_count=20,
        )
        penalty = scorer._calculate_touch_penalty(zone)
        assert penalty <= 0.15


class TestAgeDecay:
    """Test age decay calculation."""

    def test_no_decay_for_fresh_zones(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            age_bars=10,
        )
        assert scorer._calculate_age_decay(zone) == 0.0

    def test_moderate_decay_for_old_zones(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            age_bars=150,
        )
        decay = scorer._calculate_age_decay(zone)
        assert decay > 0

    def test_heavy_decay_for_very_old_zones(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            age_bars=300,
        )
        decay = scorer._calculate_age_decay(zone)
        assert decay >= 0.3


class TestZoneScoring:
    """Test single zone scoring."""

    def test_aligned_zone_gets_enhancement(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert result.enhancement > 0
        assert result.final_confidence > zone.base_confidence

    def test_contradicting_zone_no_enhancement(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bearish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert result.alignment == ZoneAlignment.CONTRADICTING
        assert result.enhancement == 0.0

    def test_neutral_hypothesis_small_enhancement(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _neutral_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert result.alignment == ZoneAlignment.NEUTRAL

    def test_enhancement_clamped_to_max(self):
        """AC4: Enhancement should not exceed 0.2."""
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            is_unmitigated=True,
            touch_count=0,
            age_bars=0,
            base_confidence=0.9,
        )
        hypo = _bullish_hypothesis(score=1.0)
        result = scorer.score_zone(zone, hypo)
        assert result.enhancement <= 0.2

    def test_enhancement_non_negative(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert result.enhancement >= 0.0

    def test_final_confidence_does_not_exceed_one(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            base_confidence=0.95,
            is_unmitigated=True,
        )
        hypo = _bullish_hypothesis(score=1.0)
        result = scorer.score_zone(zone, hypo)
        assert result.final_confidence <= 1.0

    def test_mitigated_zone_reduced_target(self):
        scorer = ZoneScorer()
        zone = ICTZone(
            zone_type=ZoneType.ORDER_BLOCK,
            direction=ZoneDirection.BULLISH,
            price_level=100.0,
            is_unmitigated=False,
            base_confidence=0.7,
        )
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        # Mitigated zones should not be valid targets
        assert result.is_valid_target is False

    def test_valid_target_for_aligned_unmitigated(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert result.is_valid_target is True

    def test_scoring_factors_populated(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        assert len(result.scoring_factors) > 0


class TestMultiZoneScoring:
    """Test scoring multiple zones."""

    def test_zones_sorted_by_confidence(self):
        scorer = ZoneScorer()
        zones = [_bullish_ob(), _bullish_fvg(), _bearish_ob()]
        hypo = _bullish_hypothesis()
        results = scorer.score_zones(zones, hypo)
        for i in range(len(results) - 1):
            assert results[i].final_confidence >= results[i + 1].final_confidence

    def test_empty_zones_list(self):
        scorer = ZoneScorer()
        hypo = _bullish_hypothesis()
        results = scorer.score_zones([], hypo)
        assert results == []


class TestZoneScoreResultSerialization:
    """Test ZoneScoreResult serialization."""

    def test_to_dict(self):
        scorer = ZoneScorer()
        zone = _bullish_ob()
        hypo = _bullish_hypothesis()
        result = scorer.score_zone(zone, hypo)
        d = result.to_dict()
        assert "zone_type" in d
        assert "zone_direction" in d
        assert "alignment" in d
        assert "enhancement" in d
        assert "final_confidence" in d
        assert "is_valid_target" in d
        assert "scoring_factors" in d


class TestGlobalInstance:
    """Test global singleton pattern."""

    def test_get_zone_scorer_returns_instance(self):
        scorer = get_zone_scorer()
        assert isinstance(scorer, ZoneScorer)

    def test_get_zone_scorer_returns_same_instance(self):
        s1 = get_zone_scorer()
        s2 = get_zone_scorer()
        assert s1 is s2
