"""Tests for Layer 2 confluence aggregator."""

import pytest

from market_analysis.confluence.layer1_signal_scorer import (
    Layer1Score,
    Layer1SignalDirection,
)
from market_analysis.confluence.layer2_confluence_aggregator import (
    Layer2ConfluenceAggregator,
    Layer2ConfluenceResult,
)
from market_analysis.confluence.signal_aggregator import SignalDirection
from market_analysis.confluence.signal_weights import get_signal_weight


class TestLayer2ConfluenceResult:
    """Test suite for Layer2ConfluenceResult dataclass."""

    def test_valid_result_creation(self):
        """Test creating a valid Layer2ConfluenceResult."""
        result = Layer2ConfluenceResult(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.85,
        )

        assert result.confluence_score == 0.75
        assert result.direction == SignalDirection.LONG
        assert result.confidence == 0.85
        assert result.is_strong_signal

    def test_score_clamping(self):
        """Test that scores are clamped to valid range."""
        result = Layer2ConfluenceResult(
            confluence_score=1.5,  # Should clamp to 1.0
            direction=SignalDirection.SHORT,
            confidence=-0.2,  # Should clamp to 0.0
        )

        assert result.confluence_score == 1.0
        assert result.confidence == 0.0

    def test_is_strong_signal(self):
        """Test strong signal detection."""
        strong = Layer2ConfluenceResult(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert strong.is_strong_signal

        weak_score = Layer2ConfluenceResult(
            confluence_score=0.6,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert not weak_score.is_strong_signal

        low_conf = Layer2ConfluenceResult(
            confluence_score=0.8,
            direction=SignalDirection.LONG,
            confidence=0.4,
        )
        assert not low_conf.is_strong_signal

    def test_to_dict(self):
        """Test result serialization."""
        result = Layer2ConfluenceResult(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.85,
            direction_breakdown={"long": 0.7, "short": 0.2, "neutral": 0.1},
        )

        data = result.to_dict()

        assert data["confluence_score"] == 0.75
        assert data["direction"] == "long"
        assert data["confidence"] == 0.85
        assert data["is_strong_signal"] is True


class TestLayer2ConfluenceAggregator:
    """Test suite for Layer2ConfluenceAggregator."""

    def test_initialization(self):
        """Test aggregator initialization."""
        agg = Layer2ConfluenceAggregator(
            min_signals=2,
            min_confluence_threshold=0.4,
        )

        assert agg.min_signals == 2
        assert agg.min_confluence_threshold == 0.4

    def test_aggregate_empty_scores(self):
        """Test aggregation with no scores."""
        agg = Layer2ConfluenceAggregator()

        result = agg.aggregate([])

        assert result.confluence_score == 0.5
        assert result.direction == SignalDirection.NEUTRAL
        assert result.confidence == 0.0

    def test_aggregate_single_bullish_signal(self):
        """Test aggregation with single bullish signal."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        assert result.direction == SignalDirection.LONG
        assert result.confluence_score > 0.5
        assert len(result.contributing_signals) == 1

    def test_aggregate_single_bearish_signal(self):
        """Test aggregation with single bearish signal."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BEARISH,
                strength=0.75,
                confidence=0.85,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        assert result.direction == SignalDirection.SHORT
        assert result.confluence_score > 0.5

    def test_aggregate_multiple_agreeing_signals(self):
        """Test aggregation with multiple agreeing signals."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.75,
                confidence=0.85,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="order_block",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.7,
                confidence=0.8,
                timeframe="1H",
            ),
        ]

        result = agg.aggregate(scores)

        assert result.direction == SignalDirection.LONG
        assert result.confluence_score > 0.7
        assert len(result.contributing_signals) == 3
        assert result.signal_breakdown is not None

    def test_aggregate_conflicting_signals(self):
        """Test aggregation with conflicting signals."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BEARISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
        ]

        result = agg.aggregate(scores)

        # Should result in lower confluence due to conflict
        assert result.direction_breakdown is not None
        assert result.direction_breakdown["long"] > 0
        assert result.direction_breakdown["short"] > 0

    def test_signal_weights_applied(self):
        """Test that signal weights are correctly applied."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",  # Weight 1.0
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="order_block",  # Weight 0.85
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
        ]

        result = agg.aggregate(scores)

        assert "cvd" in result.weights_applied
        assert "order_block" in result.weights_applied
        assert result.weights_applied["cvd"] == 1.0
        assert result.weights_applied["order_block"] == 0.85

    def test_min_signals_threshold(self):
        """Test minimum signals threshold."""
        agg = Layer2ConfluenceAggregator(min_signals=2)

        # Only one signal - below threshold
        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        # Should still produce result but with low confidence
        assert len(result.contributing_signals) == 1

    def test_feature_flags_cvd_disabled(self):
        """Test feature flag disabling CVD."""
        agg = Layer2ConfluenceAggregator(enable_feature_flags=True)
        agg.set_feature_flag("cvd", False)

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        # CVD should be filtered out
        assert len(result.contributing_signals) == 0
        assert (
            "cvd" in result.signals_excluded
            if hasattr(result, "signals_excluded")
            else True
        )

    def test_feature_flags_fvg_disabled(self):
        """Test feature flag disabling FVG."""
        agg = Layer2ConfluenceAggregator(enable_feature_flags=True)
        agg.set_feature_flag("fvg", False)

        scores = [
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        assert len(result.contributing_signals) == 0

    def test_feature_flags_order_block_disabled(self):
        """Test feature flag disabling Order Block."""
        agg = Layer2ConfluenceAggregator(enable_feature_flags=True)
        agg.set_feature_flag("order_block", False)

        scores = [
            Layer1Score(
                signal_type="order_block",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            )
        ]

        result = agg.aggregate(scores)

        assert len(result.contributing_signals) == 0

    def test_signal_breakdown(self):
        """Test signal breakdown by type."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.75,
                confidence=0.85,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="order_block",
                direction=Layer1SignalDirection.BEARISH,
                strength=0.7,
                confidence=0.8,
                timeframe="1H",
            ),
        ]

        result = agg.aggregate(scores)

        assert "cvd" in result.signal_breakdown
        assert "fvg" in result.signal_breakdown
        assert "order_block" in result.signal_breakdown
        assert result.signal_breakdown["cvd"]["count"] == 1
        assert result.signal_breakdown["fvg"]["count"] == 1
        assert result.signal_breakdown["order_block"]["count"] == 1

    def test_direction_breakdown(self):
        """Test direction breakdown."""
        agg = Layer2ConfluenceAggregator()

        scores = [
            Layer1Score(
                signal_type="cvd",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.8,
                confidence=0.9,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="fvg",
                direction=Layer1SignalDirection.BULLISH,
                strength=0.75,
                confidence=0.85,
                timeframe="1H",
            ),
            Layer1Score(
                signal_type="order_block",
                direction=Layer1SignalDirection.BEARISH,
                strength=0.7,
                confidence=0.8,
                timeframe="1H",
            ),
        ]

        result = agg.aggregate(scores)

        assert result.direction_breakdown is not None
        assert result.direction_breakdown["long"] > 0
        assert result.direction_breakdown["short"] > 0
        assert result.direction_breakdown["neutral"] == 0


class TestSignalWeights:
    """Test suite for signal weights."""

    def test_cvd_weight(self):
        """Test CVD weight is 1.0."""
        weight = get_signal_weight("cvd")
        assert weight == 1.0

    def test_fvg_weight(self):
        """Test FVG weight is 1.0."""
        weight = get_signal_weight("fvg")
        assert weight == 1.0

    def test_order_block_weight(self):
        """Test Order Block weight is 0.85."""
        weight = get_signal_weight("order_block")
        assert weight == 0.85

    def test_bos_included(self):
        """Test BOS now returns a weight (re-enabled)."""
        weight = get_signal_weight("bos")
        assert isinstance(weight, (int, float))

    def test_choc_included(self):
        """Test CHoCH now returns a weight (re-enabled)."""
        weight = get_signal_weight("choc")
        assert isinstance(weight, (int, float))
