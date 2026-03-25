"""Tests for confluence scorer."""

from market_analysis.confluence.indicator_weights import IndicatorWeights
from market_analysis.confluence.scorer import ConfluenceScore, ConfluenceScorer
from market_analysis.confluence.signal_aggregator import (
    AggregatedSignals,
    IndicatorSignal,
    SignalAggregator,
    SignalDirection,
)


class TestConfluenceScore:
    """Test suite for ConfluenceScore dataclass."""

    def test_valid_score_creation(self):
        """Test creating a valid confluence score."""
        score = ConfluenceScore(
            score=75.0,
            direction=SignalDirection.LONG,
            confidence=0.85,
            contributing_factors=[],
            signal_breakdown={},
            timestamp=1234567890,
            calculation_time_ms=5.2,
            metadata={},
        )

        assert score.is_valid
        assert score.score == 75.0
        assert score.direction == SignalDirection.LONG
        assert score.confidence == 0.85

    def test_score_clamping(self):
        """Test that score and confidence are clamped."""
        score = ConfluenceScore(
            score=150.0,  # Should clamp to 100
            direction=SignalDirection.LONG,
            confidence=-0.5,  # Should clamp to 0
            contributing_factors=[],
            signal_breakdown={},
        )

        assert score.score == 100.0
        assert score.confidence == 0.0

    def test_is_strong_signal(self):
        """Test strong signal detection."""
        # Strong signal
        strong = ConfluenceScore(
            score=75.0,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert strong.is_strong_signal

        # Weak score
        weak_score = ConfluenceScore(
            score=60.0,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert not weak_score.is_strong_signal

        # Low confidence
        low_conf = ConfluenceScore(
            score=80.0,
            direction=SignalDirection.LONG,
            confidence=0.4,
        )
        assert not low_conf.is_strong_signal

    def test_direction_str(self):
        """Test direction string conversion."""
        score = ConfluenceScore(
            score=75.0,
            direction=SignalDirection.SHORT,
            confidence=0.8,
        )
        assert score.direction_str == "short"

    def test_to_dict(self):
        """Test score serialization."""
        score = ConfluenceScore(
            score=75.0,
            direction=SignalDirection.LONG,
            confidence=0.85,
            contributing_factors=[{"type": "rsi", "weight": 1.0}],
            signal_breakdown={"by_indicator": {}},
            timestamp=1234567890,
            calculation_time_ms=5.2,
            metadata={"key": "value"},
        )

        data = score.to_dict()

        assert data["score"] == 75.0
        assert data["direction"] == "long"
        assert data["confidence"] == 0.85
        assert data["is_strong_signal"] is True
        assert data["metadata"] == {"key": "value"}


class TestConfluenceScorerInitialization:
    """Test suite for ConfluenceScorer initialization."""

    def test_default_initialization(self):
        """Test default scorer initialization."""
        scorer = ConfluenceScorer()

        assert scorer.weights is not None
        assert scorer.min_score_threshold == 50.0
        assert scorer.conflict_neutral_threshold == 0.4

    def test_custom_initialization(self):
        """Test custom scorer initialization."""
        weights = IndicatorWeights(min_signal_threshold=0.4)
        scorer = ConfluenceScorer(
            weights=weights,
            min_score_threshold=60.0,
            conflict_neutral_threshold=0.35,
        )

        assert scorer.weights == weights
        assert scorer.min_score_threshold == 60.0
        assert scorer.conflict_neutral_threshold == 0.35


class TestConfluenceScorerCalculateScore:
    """Test suite for score calculation."""

    def test_empty_signals(self):
        """Test scoring with no signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        result = scorer.calculate_score(agg)

        assert result.score == 50.0  # Neutral
        assert result.direction == SignalDirection.NEUTRAL
        assert result.confidence == 0.0
        assert result.metadata.get("reason") == "no_signals"
        assert result.calculation_time_ms >= 0

    def test_single_long_signal(self):
        """Test scoring with single LONG signal."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        assert result.score > 50.0  # Above neutral
        assert result.confidence > 0
        assert len(result.contributing_factors) == 1

    def test_single_short_signal(self):
        """Test scoring with single SHORT signal."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.8,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.SHORT
        # Score represents strength (0-100), direction is separate
        assert result.score > 50.0  # Strong signal

    def test_multiple_agreeing_signals(self):
        """Test scoring with multiple agreeing signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add multiple LONG signals
        for ind_type in ["rsi", "macd", "bb"]:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type=ind_type,
                    timeframe="1h",
                    direction=SignalDirection.LONG,
                    strength=0.8,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        assert result.score > 60.0  # Higher score with agreement
        assert result.confidence > 0.6
        assert len(result.contributing_factors) == 3

    def test_conflicting_signals(self):
        """Test scoring with conflicting signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add conflicting signals with similar weights
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.9,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="macd",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.9,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        # Should detect conflict and reduce confidence
        assert result.metadata.get("warning") == "conflicting_signals_detected"
        assert 40.0 <= result.score <= 60.0  # Neutral zone
        assert result.confidence < 0.7  # Reduced confidence

    def test_neutral_signals(self):
        """Test scoring with neutral signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.NEUTRAL,
                strength=0.5,
                confidence=0.6,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.NEUTRAL
        assert 40.0 <= result.score <= 60.0

    def test_signal_breakdown(self):
        """Test that signal breakdown is populated."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="macd",
                timeframe="4h",
                direction=SignalDirection.LONG,
                strength=0.7,
                confidence=0.8,
            )
        )

        result = scorer.calculate_score(agg)

        assert "by_indicator" in result.signal_breakdown
        assert "by_timeframe" in result.signal_breakdown
        assert result.signal_breakdown["total_signals"] == 2
        assert "rsi" in result.signal_breakdown["by_indicator"]
        assert "1h" in result.signal_breakdown["by_timeframe"]

    def test_contributing_factors_sorted(self):
        """Test that contributing factors are sorted by weighted score."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add signals with different strengths
        agg.add_signal(
            IndicatorSignal(
                indicator_type="weak",
                timeframe="1m",  # Lower timeframe weight
                direction=SignalDirection.LONG,
                strength=0.5,
                confidence=0.5,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="strong",
                timeframe="1d",  # Higher timeframe weight
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        # Factors should be sorted by weighted score (descending)
        factors = result.contributing_factors
        assert len(factors) == 2
        # The 1d signal should have higher weighted score
        assert factors[0]["timeframe"] == "1d"

    def test_diversity_bonus(self):
        """Test that timeframe diversity increases score."""
        scorer = ConfluenceScorer()

        # Single timeframe
        agg_single = AggregatedSignals()
        for i in range(3):
            agg_single.add_signal(
                IndicatorSignal(
                    indicator_type=f"ind_{i}",
                    timeframe="1h",
                    direction=SignalDirection.LONG,
                    strength=0.8,
                    confidence=0.9,
                )
            )

        # Multiple timeframes
        agg_multi = AggregatedSignals()
        for i, tf in enumerate(["1h", "4h", "1d"]):
            agg_multi.add_signal(
                IndicatorSignal(
                    indicator_type=f"ind_{i}",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.8,
                    confidence=0.9,
                )
            )

        result_single = scorer.calculate_score(agg_single)
        result_multi = scorer.calculate_score(agg_multi)

        # Multi-timeframe should have higher score due to diversity bonus
        assert result_multi.score > result_single.score

    def test_calculation_time(self):
        """Test that calculation time is recorded."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.calculation_time_ms >= 0
        # Should be very fast (< 100ms as per requirements)
        assert result.calculation_time_ms < 100


class TestConfluenceScorerEdgeCases:
    """Test suite for edge cases."""

    def test_all_neutral_signals(self):
        """Test scoring when all signals are neutral."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        for i in range(3):
            agg.add_signal(
                IndicatorSignal(
                    indicator_type=f"ind_{i}",
                    timeframe="1h",
                    direction=SignalDirection.NEUTRAL,
                    strength=0.5,
                    confidence=0.6,
                )
            )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.NEUTRAL
        assert 40.0 <= result.score <= 60.0

    def test_very_weak_signals(self):
        """Test scoring with very weak signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.1,  # Very weak
                confidence=0.3,
            )
        )

        result = scorer.calculate_score(agg)

        # Score should be low due to weak signals
        assert result.score < 50.0 or result.confidence < 0.5

    def test_high_confidence_scenario(self):
        """Test scoring with high confidence signals."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add multiple strong agreeing signals from different timeframes
        signals = [
            ("rsi", "1h", 0.9, 0.95),
            ("macd", "4h", 0.85, 0.9),
            ("bb", "1d", 0.88, 0.92),
            ("markov", "1d", 0.9, 0.95),
        ]

        for ind_type, tf, strength, conf in signals:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type=ind_type,
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    confidence=conf,
                )
            )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        assert result.score > 70.0
        assert result.confidence > 0.7
        assert result.is_strong_signal

    def test_timestamp_passed_through(self):
        """Test that timestamp is passed through to result."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()
        test_timestamp = 1234567890

        result = scorer.calculate_score(agg, timestamp=test_timestamp)

        assert result.timestamp == test_timestamp


class TestConfluenceScorerIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow_long_signal(self):
        """Test full workflow for LONG signal scenario."""
        scorer = ConfluenceScorer()
        aggregator = SignalAggregator()

        # Simulate signals from multiple indicators
        signals = [
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.85,  # Oversold bounce
                confidence=0.9,
                raw_value=28.0,
            ),
            IndicatorSignal(
                indicator_type="macd",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,  # Bullish crossover
                confidence=0.85,
                raw_value=0.5,
            ),
            IndicatorSignal(
                indicator_type="bb",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.75,  # Near lower band
                confidence=0.8,
                raw_value=0.1,
            ),
            IndicatorSignal(
                indicator_type="markov",
                timeframe="4h",
                direction=SignalDirection.LONG,
                strength=0.9,  # Bullish state
                confidence=0.88,
                raw_value=1.0,
            ),
        ]

        agg = aggregator.aggregate(signals)
        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        assert result.score > 60.0
        assert result.confidence > 0.6
        assert len(result.contributing_factors) == 4
        assert result.is_strong_signal

    def test_full_workflow_short_signal(self):
        """Test full workflow for SHORT signal scenario."""
        scorer = ConfluenceScorer()
        aggregator = SignalAggregator()

        # Simulate signals from multiple indicators
        signals = [
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.85,  # Overbought
                confidence=0.9,
                raw_value=78.0,
            ),
            IndicatorSignal(
                indicator_type="macd",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.8,  # Bearish crossover
                confidence=0.85,
                raw_value=-0.4,
            ),
            IndicatorSignal(
                indicator_type="bb",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.9,  # Near upper band
                confidence=0.88,
                raw_value=0.95,
            ),
        ]

        agg = aggregator.aggregate(signals)
        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.SHORT
        # Score represents strength (0-100), direction is separate
        assert result.score > 50.0  # Strong signal
        assert result.confidence > 0.5

    def test_full_workflow_conflicting_scenario(self):
        """Test full workflow with conflicting signals."""
        scorer = ConfluenceScorer()
        aggregator = SignalAggregator()

        # Mix of LONG and SHORT signals
        signals = [
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.9,
            ),
            IndicatorSignal(
                indicator_type="macd",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.85,
                confidence=0.88,
            ),
            IndicatorSignal(
                indicator_type="bb",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.85,
            ),
            IndicatorSignal(
                indicator_type="markov",
                timeframe="4h",
                direction=SignalDirection.SHORT,
                strength=0.82,
                confidence=0.87,
            ),
        ]

        agg = aggregator.aggregate(signals)
        result = scorer.calculate_score(agg)

        # Should detect conflict and produce neutral-ish result
        assert result.metadata.get("warning") == "conflicting_signals_detected"
        assert 40.0 <= result.score <= 60.0
        assert result.confidence < 0.7


class TestConfidenceMultiplier:
    """Test suite for confidence multiplier functionality (ST-NS-005)."""

    def test_multiplier_1x_single_timeframe(self):
        """Test 1.0x multiplier for single timeframe (no agreement boost)."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add single signal with high confidence to pass threshold
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.95,
            )
        )

        result = scorer.calculate_score(agg)

        # Should have 1.0x multiplier (single timeframe)
        assert result.multiplier_applied == 1.0
        assert (
            "single timeframe" in result.multiplier_rationale.lower()
            or "1.0x" in result.multiplier_rationale
        )
        assert result.metadata["multiplier_applied"] == 1.0

    def test_multiplier_1_5x_four_agreeing(self):
        """Test 1.5x multiplier for 4+ agreeing timeframes."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add signals from 5 different timeframes all agreeing LONG
        timeframes = ["15m", "1h", "4h", "1d", "1w"]
        for tf in timeframes:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.85,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        # Should have 1.5x multiplier (5+ agreeing timeframes)
        assert result.multiplier_applied == 1.5
        assert (
            "1.5" in result.multiplier_rationale
            or "agreeing" in result.multiplier_rationale.lower()
        )
        assert result.metadata["multiplier_applied"] == 1.5

    def test_multiplier_1_3x_four_timeframes(self):
        """Test 1.3x multiplier for exactly 4 agreeing timeframes."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add signals from 4 different timeframes all agreeing LONG
        timeframes = ["1h", "4h", "1d", "1w"]
        for tf in timeframes:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.85,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        # Should have 1.3x multiplier (4 agreeing timeframes)
        assert result.multiplier_applied == 1.3
        assert result.metadata["multiplier_applied"] == 1.3

    def test_multiplier_conflict_reduction(self):
        """Test multiplier reduction when conflicting timeframe signals exist."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add agreeing signals from multiple timeframes
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.9,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="macd",
                timeframe="4h",
                direction=SignalDirection.LONG,
                strength=0.85,
                confidence=0.88,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="bb",
                timeframe="1d",
                direction=SignalDirection.LONG,
                strength=0.87,
                confidence=0.9,
            )
        )
        # Add conflicting signal
        agg.add_signal(
            IndicatorSignal(
                indicator_type="markov",
                timeframe="1w",
                direction=SignalDirection.SHORT,
                strength=0.85,
                confidence=0.88,
            )
        )

        result = scorer.calculate_score(agg)

        # Should have reduced multiplier due to conflict
        # Base would be 1.2x for 3 agreeing, but reduced due to 1 conflicting
        assert result.multiplier_applied < 1.2
        assert (
            "conflict" in result.multiplier_rationale.lower()
            or "reduced" in result.multiplier_rationale.lower()
        )

    def test_multiplier_capped_at_100_confidence(self):
        """Test that final confidence is capped at 1.0 even with high multiplier."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add many agreeing signals with very high confidence
        timeframes = ["15m", "1h", "4h", "1d", "1w"]
        for tf in timeframes:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.95,
                    confidence=0.98,
                )
            )

        result = scorer.calculate_score(agg)

        # Confidence should be capped at 1.0
        assert result.confidence <= 1.0
        assert result.confidence == 1.0  # Should hit the cap

    def test_multiplier_not_applied_below_threshold(self):
        """Test multiplier is not applied when base confidence < 70%."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add weak signals that result in low base confidence
        # Using single weak signal to keep confidence low
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.4,  # Weak signal
                confidence=0.5,  # Low confidence
            )
        )

        result = scorer.calculate_score(agg)

        # Multiplier should not be applied
        assert result.multiplier_applied == 1.0
        assert (
            "not applied" in result.multiplier_rationale.lower()
            or "< threshold" in result.multiplier_rationale
        )

    def test_multiplier_rationale_logged(self):
        """Test that multiplier rationale is properly logged in metadata."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add multiple agreeing signals
        timeframes = ["1h", "4h", "1d"]
        for tf in timeframes:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.85,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        # Rationale should be present and non-empty
        assert result.multiplier_rationale
        assert len(result.multiplier_rationale) > 0
        assert result.metadata["multiplier_rationale"] == result.multiplier_rationale

    def test_multiplier_1_1x_two_timeframes(self):
        """Test 1.1x multiplier for 2 agreeing timeframes."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add signals from 2 timeframes
        for tf in ["1h", "4h"]:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.85,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        # Should have 1.1x multiplier
        assert result.multiplier_applied == 1.1

    def test_multiplier_1_2x_three_timeframes(self):
        """Test 1.2x multiplier for 3 agreeing timeframes."""
        scorer = ConfluenceScorer()
        agg = AggregatedSignals()

        # Add signals from 3 timeframes
        for tf in ["1h", "4h", "1d"]:
            agg.add_signal(
                IndicatorSignal(
                    indicator_type="rsi",
                    timeframe=tf,
                    direction=SignalDirection.LONG,
                    strength=0.85,
                    confidence=0.9,
                )
            )

        result = scorer.calculate_score(agg)

        # Should have 1.2x multiplier
        assert result.multiplier_applied == 1.2

    def test_custom_confidence_threshold(self):
        """Test custom min_base_confidence_for_multiplier threshold."""
        # Create scorer with higher threshold
        scorer = ConfluenceScorer(min_base_confidence_for_multiplier=0.85)
        agg = AggregatedSignals()

        # Add signal that would normally qualify but may not meet higher threshold
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.75,
                confidence=0.8,
            )
        )

        result = scorer.calculate_score(agg)

        # Check that the custom threshold was used
        assert scorer.min_base_confidence_for_multiplier == 0.85
        # Multiplier should not be applied if base confidence < 0.85
        if result.metadata.get("base_confidence_before_multiplier", 1.0) < 0.85:
            assert result.multiplier_applied == 1.0
            assert "not applied" in result.multiplier_rationale.lower()


class TestOrderFlowWeightWiring:
    """Test order_flow weight integration with scorer (ST-ICT-003)."""

    def test_order_flow_weight_used_in_conservative_preset(self):
        """Test scorer uses order_flow weight from conservative preset."""
        from market_analysis.confluence.indicator_weights import WeightPreset

        weights = WeightPreset.conservative()
        scorer = ConfluenceScorer(weights=weights)
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="order_flow",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        # order_flow weight is 1.0 in conservative, timeframe 1h is 1.0
        # So combined weight should be 1.0 * 1.0 = 1.0
        assert len(result.contributing_factors) == 1
        assert result.contributing_factors[0]["indicator"] == "order_flow"
        assert result.contributing_factors[0]["weight"] == 1.0

    def test_order_flow_weight_used_in_aggressive_preset(self):
        """Test scorer uses order_flow weight from aggressive preset."""
        from market_analysis.confluence.indicator_weights import WeightPreset

        weights = WeightPreset.aggressive()
        scorer = ConfluenceScorer(weights=weights)
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="order_flow",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.8,
                confidence=0.9,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.SHORT
        # order_flow weight is 1.2 in aggressive, timeframe 1h is 1.1
        # So combined weight should be 1.2 * 1.1 = 1.32
        assert len(result.contributing_factors) == 1
        assert result.contributing_factors[0]["indicator"] == "order_flow"
        assert result.contributing_factors[0]["weight"] == 1.32

    def test_order_flow_combined_with_other_indicators(self):
        """Test order_flow signals contribute alongside other indicators."""
        from market_analysis.confluence.indicator_weights import WeightPreset

        weights = WeightPreset.conservative()
        scorer = ConfluenceScorer(weights=weights)
        agg = AggregatedSignals()

        # Add order_flow signal
        agg.add_signal(
            IndicatorSignal(
                indicator_type="order_flow",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.85,
                confidence=0.9,
            )
        )
        # Add traditional indicator
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.85,
            )
        )

        result = scorer.calculate_score(agg)

        assert result.direction == SignalDirection.LONG
        assert len(result.contributing_factors) == 2
        indicator_types = {f["indicator"] for f in result.contributing_factors}
        assert "order_flow" in indicator_types
        assert "rsi" in indicator_types

    def test_order_flow_appears_in_signal_breakdown(self):
        """Test order_flow signals appear in signal breakdown."""
        from market_analysis.confluence.indicator_weights import WeightPreset

        weights = WeightPreset.aggressive()
        scorer = ConfluenceScorer(weights=weights)
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="order_flow",
                timeframe="4h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.88,
            )
        )

        result = scorer.calculate_score(agg)

        assert "order_flow" in result.signal_breakdown["by_indicator"]
        assert result.signal_breakdown["by_indicator"]["order_flow"]["count"] == 1
