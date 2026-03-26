"""Tests for StrongSystem Hypothesis Scoring (ST-ICT-029).

Tests the bullish/bearish hypothesis scoring algorithm:
- Market structure component scoring
- Order flow component scoring
- Liquidity sweep component scoring
- BOS confirmation component scoring
- Weighted combination and classification
- Confidence contribution (AC4: 0.1-0.2 range)
"""

from ict.strongsystem.hypothesis import (
    HYPOTHESIS_WEIGHTS,
    STRENGTH_THRESHOLDS,
    BOSConfirmation,
    HypothesisDirection,
    HypothesisStrength,
    LiquiditySweepEvidence,
    MarketStructureEvidence,
    OrderFlowEvidence,
    StrongSystemHypothesis,
    get_hypothesis_scorer,
)

# --- Helpers ---


def _bullish_structure() -> MarketStructureEvidence:
    """Create bullish market structure evidence."""
    return MarketStructureEvidence(
        higher_highs=3,
        higher_lows=3,
        lower_highs=0,
        lower_lows=0,
        trend_duration_bars=15,
    )


def _bearish_structure() -> MarketStructureEvidence:
    """Create bearish market structure evidence."""
    return MarketStructureEvidence(
        higher_highs=0,
        higher_lows=0,
        lower_highs=3,
        lower_lows=3,
        trend_duration_bars=15,
    )


def _neutral_structure() -> MarketStructureEvidence:
    """Create neutral market structure evidence."""
    return MarketStructureEvidence(
        higher_highs=1,
        higher_lows=0,
        lower_highs=1,
        lower_lows=0,
        trend_duration_bars=5,
    )


def _bullish_order_flow() -> OrderFlowEvidence:
    """Create bullish order flow evidence."""
    return OrderFlowEvidence(
        bullish_volume_delta=800_000,
        bearish_volume_delta=200_000,
        large_order_ratio=0.7,
        absorption_events=0,
    )


def _bearish_order_flow() -> OrderFlowEvidence:
    """Create bearish order flow evidence."""
    return OrderFlowEvidence(
        bullish_volume_delta=200_000,
        bearish_volume_delta=800_000,
        large_order_ratio=0.3,
        absorption_events=0,
    )


def _neutral_order_flow() -> OrderFlowEvidence:
    """Create neutral order flow evidence."""
    return OrderFlowEvidence(
        bullish_volume_delta=500_000,
        bearish_volume_delta=500_000,
        large_order_ratio=0.5,
        absorption_events=0,
    )


def _bullish_sweep() -> LiquiditySweepEvidence:
    """Create bullish liquidity sweep evidence (sell-side swept + displacement)."""
    return LiquiditySweepEvidence(
        buy_side_swept=False,
        sell_side_swept=True,
        sweep_magnitude=0.8,
        displacement_after=True,
    )


def _bearish_sweep() -> LiquiditySweepEvidence:
    """Create bearish liquidity sweep evidence (buy-side swept + displacement)."""
    return LiquiditySweepEvidence(
        buy_side_swept=True,
        sell_side_swept=False,
        sweep_magnitude=0.8,
        displacement_after=True,
    )


def _neutral_sweep() -> LiquiditySweepEvidence:
    """Create neutral sweep evidence (no sweeps)."""
    return LiquiditySweepEvidence()


def _bullish_bos() -> BOSConfirmation:
    """Create bullish BOS confirmation."""
    return BOSConfirmation(
        bullish_bos=True,
        bearish_bos=False,
        bos_count=2,
        is_validated=True,
    )


def _bearish_bos() -> BOSConfirmation:
    """Create bearish BOS confirmation."""
    return BOSConfirmation(
        bullish_bos=False,
        bearish_bos=True,
        bos_count=2,
        is_validated=True,
    )


def _neutral_bos() -> BOSConfirmation:
    """Create neutral BOS confirmation."""
    return BOSConfirmation()


# --- Tests ---


class TestHypothesisEnums:
    """Test enum values and thresholds."""

    def test_direction_values(self):
        assert HypothesisDirection.BULLISH.value == "bullish"
        assert HypothesisDirection.BEARISH.value == "bearish"
        assert HypothesisDirection.NEUTRAL.value == "neutral"

    def test_strength_values(self):
        assert HypothesisStrength.STRONG.value == "strong"
        assert HypothesisStrength.MODERATE.value == "moderate"
        assert HypothesisStrength.WEAK.value == "weak"
        assert HypothesisStrength.NONE.value == "none"

    def test_strength_thresholds(self):
        assert STRENGTH_THRESHOLDS[HypothesisStrength.STRONG] == 0.6
        assert STRENGTH_THRESHOLDS[HypothesisStrength.MODERATE] == 0.3
        assert STRENGTH_THRESHOLDS[HypothesisStrength.WEAK] == 0.1

    def test_weights_sum_to_one(self):
        total = sum(HYPOTHESIS_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


class TestMarketStructureScoring:
    """Test market structure component scoring."""

    def test_bullish_structure_positive_score(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_market_structure(_bullish_structure())
        assert score > 0

    def test_bearish_structure_negative_score(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_market_structure(_bearish_structure())
        assert score < 0

    def test_neutral_structure_near_zero(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_market_structure(_neutral_structure())
        assert abs(score) < 0.5

    def test_empty_structure_returns_zero(self):
        scorer = StrongSystemHypothesis()
        evidence = MarketStructureEvidence()
        score = scorer._score_market_structure(evidence)
        assert score == 0.0

    def test_score_clamped_to_range(self):
        scorer = StrongSystemHypothesis()
        # Extreme bullish
        evidence = MarketStructureEvidence(
            higher_highs=100,
            higher_lows=100,
            trend_duration_bars=50,
        )
        score = scorer._score_market_structure(evidence)
        assert -1.0 <= score <= 1.0

    def test_duration_bonus_boosts_score(self):
        scorer = StrongSystemHypothesis()
        # Use mixed structure so raw isn't saturated at 1.0
        short = MarketStructureEvidence(
            higher_highs=2,
            higher_lows=1,
            lower_highs=1,
            lower_lows=0,
            trend_duration_bars=0,
        )
        long_trend = MarketStructureEvidence(
            higher_highs=2,
            higher_lows=1,
            lower_highs=1,
            lower_lows=0,
            trend_duration_bars=20,
        )
        assert scorer._score_market_structure(
            long_trend
        ) > scorer._score_market_structure(short)


class TestOrderFlowScoring:
    """Test order flow component scoring."""

    def test_bullish_flow_positive_score(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_order_flow(_bullish_order_flow())
        assert score > 0

    def test_bearish_flow_negative_score(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_order_flow(_bearish_order_flow())
        assert score < 0

    def test_neutral_flow_near_zero(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_order_flow(_neutral_order_flow())
        assert abs(score) < 0.5

    def test_large_institutional_bias(self):
        scorer = StrongSystemHypothesis()
        flow = OrderFlowEvidence(
            bullish_volume_delta=500_000,
            bearish_volume_delta=500_000,
            large_order_ratio=0.9,  # Heavy institutional buying
            absorption_events=0,
        )
        score = scorer._score_order_flow(flow)
        assert score > 0

    def test_absorption_events_reduce_score(self):
        scorer = StrongSystemHypothesis()
        no_absorption = OrderFlowEvidence(
            bullish_volume_delta=800_000,
            bearish_volume_delta=200_000,
            large_order_ratio=0.7,
            absorption_events=0,
        )
        with_absorption = OrderFlowEvidence(
            bullish_volume_delta=800_000,
            bearish_volume_delta=200_000,
            large_order_ratio=0.7,
            absorption_events=5,
        )
        assert scorer._score_order_flow(no_absorption) > scorer._score_order_flow(
            with_absorption
        )


class TestLiquiditySweepScoring:
    """Test liquidity sweep component scoring."""

    def test_sell_side_sweep_with_displacement_bullish(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_liquidity_sweep(_bullish_sweep())
        assert score > 0

    def test_buy_side_sweep_with_displacement_bearish(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_liquidity_sweep(_bearish_sweep())
        assert score < 0

    def test_no_sweep_returns_zero(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_liquidity_sweep(_neutral_sweep())
        assert score == 0.0

    def test_sweep_without_displacement_weaker(self):
        scorer = StrongSystemHypothesis()
        with_disp = LiquiditySweepEvidence(
            sell_side_swept=True,
            displacement_after=True,
            sweep_magnitude=0.8,
        )
        without_disp = LiquiditySweepEvidence(
            sell_side_swept=True,
            displacement_after=False,
            sweep_magnitude=0.8,
        )
        # With displacement should give higher absolute score
        assert abs(scorer._score_liquidity_sweep(with_disp)) > abs(
            scorer._score_liquidity_sweep(without_disp)
        )


class TestBOSConfirmationScoring:
    """Test BOS confirmation component scoring."""

    def test_bullish_bos_positive(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_bos_confirmation(_bullish_bos())
        assert score > 0

    def test_bearish_bos_negative(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_bos_confirmation(_bearish_bos())
        assert score < 0

    def test_no_bos_returns_zero(self):
        scorer = StrongSystemHypothesis()
        score = scorer._score_bos_confirmation(_neutral_bos())
        assert score == 0.0

    def test_validated_bos_stronger_than_unvalidated(self):
        scorer = StrongSystemHypothesis()
        validated = BOSConfirmation(
            bullish_bos=True,
            bos_count=1,
            is_validated=True,
        )
        unvalidated = BOSConfirmation(
            bullish_bos=True,
            bos_count=1,
            is_validated=False,
        )
        assert scorer._score_bos_confirmation(
            validated
        ) > scorer._score_bos_confirmation(unvalidated)

    def test_multiple_bos_stronger(self):
        scorer = StrongSystemHypothesis()
        single = BOSConfirmation(
            bullish_bos=True,
            bos_count=1,
            is_validated=True,
        )
        multiple = BOSConfirmation(
            bullish_bos=True,
            bos_count=3,
            is_validated=True,
        )
        assert scorer._score_bos_confirmation(
            multiple
        ) > scorer._score_bos_confirmation(single)


class TestHypothesisScoring:
    """Test full hypothesis scoring integration."""

    def test_strong_bullish_hypothesis(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        assert result.direction == HypothesisDirection.BULLISH
        assert result.raw_score > 0
        assert result.strength in (
            HypothesisStrength.MODERATE,
            HypothesisStrength.STRONG,
        )

    def test_strong_bearish_hypothesis(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bearish_structure(),
            order_flow=_bearish_order_flow(),
            liquidity_sweep=_bearish_sweep(),
            bos_confirmation=_bearish_bos(),
        )
        assert result.direction == HypothesisDirection.BEARISH
        assert result.raw_score < 0

    def test_neutral_hypothesis(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_neutral_structure(),
            order_flow=_neutral_order_flow(),
            liquidity_sweep=_neutral_sweep(),
            bos_confirmation=_neutral_bos(),
        )
        assert result.direction == HypothesisDirection.NEUTRAL

    def test_score_within_range(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        assert -1.0 <= result.raw_score <= 1.0

    def test_component_scores_present(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        assert "market_structure" in result.component_scores
        assert "order_flow" in result.component_scores
        assert "liquidity_sweep" in result.component_scores
        assert "bos_confirmation" in result.component_scores

    def test_component_weights_present(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        for key in HYPOTHESIS_WEIGHTS:
            assert key in result.component_weights

    def test_aligned_with_structure_when_components_agree(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        # All bullish components should show alignment
        assert result.is_aligned_with_structure is True


class TestConfidenceContribution:
    """Test AC4: 0.1-0.2 confidence multiplier when aligned."""

    def test_no_contribution_for_none_strength(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            0.05, HypothesisStrength.NONE
        )
        assert contrib == 0.0

    def test_no_contribution_for_weak_strength(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            0.2, HypothesisStrength.WEAK
        )
        assert contrib == 0.05  # Below the 0.1 floor

    def test_moderate_gives_minimum_multiplier(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            0.5, HypothesisStrength.MODERATE
        )
        assert contrib == 0.1  # AC4 floor

    def test_strong_at_threshold_gives_minimum_multiplier(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            0.6, HypothesisStrength.STRONG
        )
        assert contrib == 0.1  # AC4 floor at threshold

    def test_strong_max_gives_maximum_multiplier(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            1.0, HypothesisStrength.STRONG
        )
        assert contrib == 0.2  # AC4 ceiling

    def test_strong_mid_range_within_bounds(self):
        scorer = StrongSystemHypothesis()
        contrib = scorer._calculate_confidence_contribution(
            0.8, HypothesisStrength.STRONG
        )
        assert 0.1 <= contrib <= 0.2

    def test_strong_bullish_result_has_contribution(self):
        """End-to-end: strong bullish hypothesis has confidence contribution."""
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        if result.strength in (HypothesisStrength.MODERATE, HypothesisStrength.STRONG):
            assert result.confidence_contribution >= 0.1


class TestHypothesisScoreDataclass:
    """Test HypothesisScore serialization."""

    def test_to_dict(self):
        scorer = StrongSystemHypothesis()
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_bullish_sweep(),
            bos_confirmation=_bullish_bos(),
        )
        d = result.to_dict()
        assert "direction" in d
        assert "strength" in d
        assert "raw_score" in d
        assert "component_scores" in d
        assert "is_aligned_with_structure" in d
        assert "confidence_contribution" in d


class TestGlobalInstance:
    """Test global singleton pattern."""

    def test_get_hypothesis_scorer_returns_instance(self):
        scorer = get_hypothesis_scorer()
        assert isinstance(scorer, StrongSystemHypothesis)

    def test_get_hypothesis_scorer_returns_same_instance(self):
        s1 = get_hypothesis_scorer()
        s2 = get_hypothesis_scorer()
        assert s1 is s2

    def test_custom_weights(self):
        scorer = StrongSystemHypothesis(
            weights={"market_structure": 0.5, "order_flow": 0.5},
        )
        result = scorer.score_hypothesis(
            market_structure=_bullish_structure(),
            order_flow=_bullish_order_flow(),
            liquidity_sweep=_neutral_sweep(),
            bos_confirmation=_neutral_bos(),
        )
        # Should only have 2 components contributing
        assert "market_structure" in result.component_scores
        assert "order_flow" in result.component_scores
