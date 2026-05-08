"""Integration tests for ICT confluence scoring (EP-ICT-005).

Tests the two-layer scorer with real signal data:
1. Layer 1: Individual signal scoring (CVD, FVG, Order Block)
2. Layer 2: Confluence aggregation with weights from EP-ICT-004 validation
3. Confluence score calculation with direction consensus

BOS/CHoCH signals are INCLUDED (re-enabled after accuracy fix).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from market_analysis.confluence.layer1_signal_scorer import Layer1SignalScorer
from market_analysis.confluence.layer2_confluence_aggregator import (
    Layer2ConfluenceAggregator,
)
from market_analysis.confluence.signal_weights import (
    ICTSignalType,
    get_all_weights,
    get_signal_weight,
)
from market_analysis.confluence.two_layer_scorer import (
    TwoLayerScore,
    TwoLayerScorer,
)

# =============================================================================
# Test: Signal Weights (EP-ICT-004 Validation)
# =============================================================================


class TestSignalWeights:
    """Test signal weights from EP-ICT-004 validation."""

    def test_cvd_weight_from_validation(self):
        """CVD validated at 100% → weight 1.0."""
        weight = get_signal_weight("cvd")
        assert weight == 1.0, "CVD must have weight 1.0 (100% validated)"

    def test_fvg_weight_from_validation(self):
        """FVG validated at 100% → weight 1.0."""
        weight = get_signal_weight("fvg")
        assert weight == 1.0, "FVG must have weight 1.0 (100% validated)"

    def test_order_block_weight_from_validation(self):
        """Order Block validated at 80.77% → weight 0.85."""
        weight = get_signal_weight("order_block")
        assert weight == 0.85, "Order Block must have weight 0.85 (80.77% validated)"

    def test_all_weights_summary(self):
        """All weights sum to expected total."""
        weights = get_all_weights()
        # CVD=1.0, FVG=1.0, OB=0.85 = 2.85 total
        assert sum(weights.values()) == 2.85


# =============================================================================
# Test: Layer 1 Signal Scoring
# =============================================================================


class TestLayer1Scoring:
    """Test Layer 1 individual signal scoring."""

    def test_cvd_scoring_produces_valid_score(self):
        """CVD scoring produces a valid Layer1Score."""
        scorer = Layer1SignalScorer(min_confidence_threshold=0.3)

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        score = scorer.score_cvd(cvd, "1H")

        assert score is not None
        assert score.signal_type == "cvd"
        assert score.strength >= 0.0
        assert score.confidence >= 0.3

    def test_fvg_scoring_produces_valid_score(self):
        """FVG scoring produces a valid Layer1Score."""
        scorer = Layer1SignalScorer(min_confidence_threshold=0.3)

        # Create FVG mock with proper structure
        fvg_result = MagicMock()
        fvg_result.fvg.direction.value = "bullish"
        fvg_result.fvg.high = 50500.0
        fvg_result.fvg.low = 49500.0
        fvg_result.fvg.mitigation.value = "none"
        fvg_result.fvg.ce50_reached = False
        fvg_result.fvg.regime_at_formation = None

        scores = scorer.score_fvg(fvg_result, timeframe="1H")

        assert scores is not None
        assert scores.signal_type == "fvg"

    def test_order_block_scoring_produces_valid_score(self):
        """Order Block scoring produces a valid Layer1Score."""
        scorer = Layer1SignalScorer(min_confidence_threshold=0.3)

        ob = MagicMock()
        ob.polarity.value = "bullish"
        ob.strength_score = 0.8
        ob.volume_confirmed = True
        ob.anchor_candle_index = 10
        ob.momentum_candle_index = 11
        ob.zone.price_range.high = 50500.0
        ob.zone.price_range.low = 49500.0

        score = scorer.score_order_block(ob, "1H")

        assert score is not None
        assert score.signal_type == "order_block"
        assert score.strength == 0.8


# =============================================================================
# Test: Two-Layer Scoring
# =============================================================================


class TestTwoLayerScoring:
    """Test two-layer scoring with confluence."""

    def test_two_layer_scorer_initialization(self):
        """Two-layer scorer initializes correctly."""
        scorer = TwoLayerScorer()
        assert scorer is not None
        assert scorer.layer1_scorer is not None
        assert scorer.layer2_aggregator is not None

    def test_score_with_cvd_produces_result(self):
        """CVD signal through two-layer scoring produces valid result."""
        scorer = TwoLayerScorer()

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        result = scorer.score(cvd_result=cvd, timeframe="1H")

        assert isinstance(result, TwoLayerScore)
        assert "cvd" in result.signals_included

    def test_score_with_fvg_produces_result(self):
        """FVG signal through two-layer scoring produces valid result."""
        scorer = TwoLayerScorer()

        fvg_result = MagicMock()
        fvg_result.fvg.direction.value = "bullish"
        fvg_result.fvg.high = 50500.0
        fvg_result.fvg.low = 49500.0
        fvg_result.fvg.mitigation.value = "none"
        fvg_result.fvg.ce50_reached = False
        fvg_result.fvg.regime_at_formation = None

        result = scorer.score(fvg_results=[fvg_result], timeframe="1H")

        assert isinstance(result, TwoLayerScore)
        assert "fvg" in result.signals_included

    def test_score_with_order_block_produces_result(self):
        """Order Block signal through two-layer scoring produces valid result."""
        scorer = TwoLayerScorer()

        ob = MagicMock()
        ob.polarity.value = "bullish"
        ob.strength_score = 0.8
        ob.volume_confirmed = True
        ob.anchor_candle_index = 10
        ob.momentum_candle_index = 11
        ob.zone.price_range.high = 50500.0
        ob.zone.price_range.low = 49500.0

        result = scorer.score(order_blocks=[ob], timeframe="1H")

        assert isinstance(result, TwoLayerScore)
        assert "order_block" in result.signals_included

    def test_score_with_multiple_signals(self):
        """Multiple signals produce confluence score."""
        scorer = TwoLayerScorer()

        # CVD
        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        # FVG
        fvg_result = MagicMock()
        fvg_result.fvg.direction.value = "bullish"
        fvg_result.fvg.high = 50500.0
        fvg_result.fvg.low = 49500.0
        fvg_result.fvg.mitigation.value = "none"
        fvg_result.fvg.ce50_reached = False
        fvg_result.fvg.regime_at_formation = None

        result = scorer.score(cvd_result=cvd, fvg_results=[fvg_result], timeframe="1H")

        assert isinstance(result, TwoLayerScore)
        assert len(result.signals_included) == 2
        assert result.confluence_score >= 0.0


# =============================================================================
# Test: Feature Flag Control
# =============================================================================


class TestFeatureFlagControl:
    """Test feature flags control signal inclusion."""

    def test_cvd_disabled_excluded(self):
        """CVD is excluded when disabled via feature flag."""
        scorer = TwoLayerScorer(enable_feature_flags=True)
        scorer.set_signal_enabled("cvd", False)

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        result = scorer.score(cvd_result=cvd, timeframe="1H")

        assert "cvd" not in result.signals_included
        assert "cvd" in result.signals_excluded

    def test_fvg_disabled_excluded(self):
        """FVG is excluded when disabled via feature flag."""
        scorer = TwoLayerScorer(enable_feature_flags=True)
        scorer.set_signal_enabled("fvg", False)

        fvg_result = MagicMock()
        fvg_result.fvg.direction.value = "bullish"
        fvg_result.fvg.high = 50500.0
        fvg_result.fvg.low = 49500.0
        fvg_result.fvg.mitigation.value = "none"
        fvg_result.fvg.ce50_reached = False
        fvg_result.fvg.regime_at_formation = None

        result = scorer.score(fvg_results=[fvg_result], timeframe="1H")

        assert "fvg" not in result.signals_included
        assert "fvg" in result.signals_excluded

    def test_order_block_disabled_excluded(self):
        """Order Block is excluded when disabled via feature flag."""
        scorer = TwoLayerScorer(enable_feature_flags=True)
        scorer.set_signal_enabled("order_block", False)

        ob = MagicMock()
        ob.polarity.value = "bullish"
        ob.strength_score = 0.8
        ob.volume_confirmed = True
        ob.anchor_candle_index = 10
        ob.momentum_candle_index = 11
        ob.zone.price_range.high = 50500.0
        ob.zone.price_range.low = 49500.0

        result = scorer.score(order_blocks=[ob], timeframe="1H")

        assert "order_block" not in result.signals_included
        assert "order_block" in result.signals_excluded


# =============================================================================
# Test: Layer 2 Aggregation
# =============================================================================


class TestLayer2Aggregation:
    """Test Layer 2 confluence aggregation."""

    def test_empty_aggregation_returns_result(self):
        """Empty aggregation still returns a valid result object."""
        aggregator = Layer2ConfluenceAggregator(min_signals=0)

        result = aggregator.aggregate([], timestamp=None)

        # Result should still be valid
        assert result is not None
        assert result.direction.value is not None

    def test_single_signal_aggregation(self):
        """Single signal through Layer 2 produces valid result."""
        aggregator = Layer2ConfluenceAggregator(min_signals=1)

        # Use a proper mock with numeric weighted_score
        layer1_score = MagicMock()
        layer1_score.weighted_score = 0.8
        layer1_score.direction.value = "bullish"
        layer1_score.signal_type = "cvd"
        layer1_score.strength = 0.8
        layer1_score.confidence = 0.7

        result = aggregator.aggregate([layer1_score], timestamp=None)

        # Result should be valid with a score
        assert result is not None
        assert result.direction.value is not None

    def test_confluence_score_is_normalized(self):
        """Confluence score is always normalized 0.0-1.0."""
        scorer = TwoLayerScorer()

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        result = scorer.score(cvd_result=cvd, timeframe="1H")

        assert 0.0 <= result.confluence_score <= 1.0
        assert 0.0 <= result.confidence <= 1.0


# =============================================================================
# Test: Score Result Metadata
# =============================================================================


class TestScoreMetadata:
    """Test scoring result metadata."""

    def test_result_contains_included_signals(self):
        """Score result lists signals that were included."""
        scorer = TwoLayerScorer()

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        result = scorer.score(cvd_result=cvd, timeframe="1H")

        assert "cvd" in result.signals_included

    def test_result_contains_excluded_signals_when_disabled(self):
        """Score result lists signals that were excluded due to feature flags."""
        scorer = TwoLayerScorer(enable_feature_flags=True)
        scorer.set_signal_enabled("fvg", False)

        fvg_result = MagicMock()
        fvg_result.fvg.direction.value = "bullish"
        fvg_result.fvg.high = 50500.0
        fvg_result.fvg.low = 49500.0
        fvg_result.fvg.mitigation.value = "none"
        fvg_result.fvg.ce50_reached = False
        fvg_result.fvg.regime_at_formation = None

        result = scorer.score(fvg_results=[fvg_result], timeframe="1H")

        assert "fvg" in result.signals_excluded

    def test_result_can_be_serialized_to_dict(self):
        """Score result can be serialized to dictionary."""
        scorer = TwoLayerScorer()

        cvd = MagicMock()
        cvd.cvd_values = [100.0, 150.0, 200.0]
        cvd.net_volume = 1000.0
        cvd.trade_count = 50
        cvd.buy_volume = 600.0
        cvd.sell_volume = 400.0

        result = scorer.score(cvd_result=cvd, timeframe="1H")
        result_dict = result.to_dict()

        assert "confluence_score" in result_dict
        assert "signals_included" in result_dict
        assert "signals_excluded" in result_dict


# =============================================================================
# Test: ICTSignalType Enum
# =============================================================================


class TestICTSignalType:
    """Test ICT signal type validation."""

    def test_valid_signals_are_recognized(self):
        """CVD, FVG, Order Block are valid signal types."""
        assert ICTSignalType.is_valid_signal("cvd") is True
        assert ICTSignalType.is_valid_signal("fvg") is True
        assert ICTSignalType.is_valid_signal("order_block") is True

    def test_bos_choch_are_included(self):
        """BOS and CHoCH are now valid (re-enabled)."""
        assert ICTSignalType.is_valid_signal("bos") is True
        assert ICTSignalType.is_valid_signal("choc") is True

    def test_get_supported_signals(self):
        """get_supported_signals returns all signals including BOS/CHOCH."""
        supported = ICTSignalType.get_supported_signals()
        supported_values = [s.value for s in supported]

        assert "cvd" in supported_values
        assert "fvg" in supported_values
        assert "order_block" in supported_values
        # BOS/CHOCH are now included
        assert "bos" in supported_values
        assert "choc" in supported_values
