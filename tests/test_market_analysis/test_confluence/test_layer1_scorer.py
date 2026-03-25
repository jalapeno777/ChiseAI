"""Tests for Layer 1 signal scorer."""

from datetime import datetime

from market_analysis.confluence.layer1_signal_scorer import (
    Layer1Score,
    Layer1SignalDirection,
    Layer1SignalScorer,
)
from market_analysis.cvd.cvd_calculator import CVDResult
from market_analysis.fvg.fvg_detector import (
    FVG,
    FVGDetectionResult,
    FVGDirection,
    FVGMitigation,
)
from market_analysis.order_block.ob_detector import (
    OBDetectionResult,
    OBPolaridade,
)
from market_analysis.zones import Zone, ZoneType
from market_analysis.zones.zone_models import PriceRange


class TestLayer1Score:
    """Test suite for Layer1Score dataclass."""

    def test_valid_score_creation(self):
        """Test creating a valid Layer1Score."""
        score = Layer1Score(
            signal_type="cvd",
            direction=Layer1SignalDirection.BULLISH,
            strength=0.8,
            confidence=0.9,
            timeframe="1H",
        )

        assert score.signal_type == "cvd"
        assert score.direction == Layer1SignalDirection.BULLISH
        assert score.strength == 0.8
        assert score.confidence == 0.9
        assert score.timeframe == "1H"
        assert 0.0 <= score.strength <= 1.0
        assert 0.0 <= score.confidence <= 1.0

    def test_score_clamping(self):
        """Test that strength and confidence are clamped."""
        score = Layer1Score(
            signal_type="cvd",
            direction=Layer1SignalDirection.BEARISH,
            strength=1.5,  # Should clamp to 1.0
            confidence=-0.2,  # Should clamp to 0.0
            timeframe="1H",
        )

        assert score.strength == 1.0
        assert score.confidence == 0.0

    def test_weighted_score_bullish(self):
        """Test weighted score calculation for bullish signal."""
        score = Layer1Score(
            signal_type="cvd",
            direction=Layer1SignalDirection.BULLISH,
            strength=0.8,
            confidence=0.9,
            timeframe="1H",
        )

        # weighted_score = strength * confidence * 1.0 (for non-neutral)
        expected = 0.8 * 0.9 * 1.0
        assert score.weighted_score == expected

    def test_weighted_score_neutral(self):
        """Test weighted score calculation for neutral signal."""
        score = Layer1Score(
            signal_type="cvd",
            direction=Layer1SignalDirection.NEUTRAL,
            strength=0.8,
            confidence=0.9,
            timeframe="1H",
        )

        # weighted_score = strength * confidence * 0.5 (for neutral)
        expected = 0.8 * 0.9 * 0.5
        assert score.weighted_score == expected

    def test_to_dict(self):
        """Test Layer1Score serialization."""
        score = Layer1Score(
            signal_type="fvg",
            direction=Layer1SignalDirection.BULLISH,
            strength=0.75,
            confidence=0.85,
            timeframe="4H",
            metadata={"mitigation": "none"},
        )

        data = score.to_dict()

        assert data["signal_type"] == "fvg"
        assert data["direction"] == "bullish"
        assert data["strength"] == 0.75
        assert data["confidence"] == 0.85
        assert data["timeframe"] == "4H"
        assert "weighted_score" in data
        assert data["metadata"] == {"mitigation": "none"}


class TestLayer1SignalScorer:
    """Test suite for Layer1SignalScorer."""

    def test_initialization(self):
        """Test scorer initialization."""
        scorer = Layer1SignalScorer(min_confidence_threshold=0.4)

        assert scorer.min_confidence_threshold == 0.4

    def test_score_cvd_bullish(self):
        """Test CVD scoring with bullish signal."""
        scorer = Layer1SignalScorer()

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],  # CVD increasing
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        score = scorer.score_cvd(cvd_result, "1H")

        assert score is not None
        assert score.signal_type == "cvd"
        assert score.direction == Layer1SignalDirection.BULLISH
        assert score.strength >= 0.0
        assert score.confidence >= 0.0
        assert score.timeframe == "1H"
        assert "cvd_change" in score.metadata

    def test_score_cvd_bearish(self):
        """Test CVD scoring with bearish signal."""
        scorer = Layer1SignalScorer()

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[150.0, 100.0],  # CVD decreasing
            trade_count=50,
            buy_volume=650.0,
            sell_volume=800.0,
            net_volume=-150.0,
        )

        score = scorer.score_cvd(cvd_result, "1H")

        assert score is not None
        assert score.direction == Layer1SignalDirection.BEARISH

    def test_score_cvd_no_data(self):
        """Test CVD scoring with no data."""
        scorer = Layer1SignalScorer()

        cvd_result = CVDResult(
            timestamps=[],
            cvd_values=[],
            trade_count=0,
            buy_volume=0.0,
            sell_volume=0.0,
            net_volume=0.0,
        )

        score = scorer.score_cvd(cvd_result, "1H")

        assert score is None

    def test_score_cvd_divergence(self):
        """Test CVD scoring with price divergence detection."""
        scorer = Layer1SignalScorer()

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],  # CVD up
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        price_data = [110.0, 105.0]  # Price down - bearish divergence

        score = scorer.score_cvd(cvd_result, "1H", price_data)

        assert score is not None
        assert score.metadata["divergence_detected"] is True

    def test_score_fvg_bullish(self):
        """Test FVG scoring with bullish FVG."""
        scorer = Layer1SignalScorer()

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )

        fvg_result = FVGDetectionResult(fvg=fvg, detection_index=1)

        score = scorer.score_fvg(fvg_result, timeframe="1H")

        assert score is not None
        assert score.signal_type == "fvg"
        assert score.direction == Layer1SignalDirection.BULLISH
        assert "mitigation" in score.metadata

    def test_score_fvg_bearish(self):
        """Test FVG scoring with bearish FVG."""
        scorer = Layer1SignalScorer()

        fvg = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )

        fvg_result = FVGDetectionResult(fvg=fvg, detection_index=1)

        score = scorer.score_fvg(fvg_result, timeframe="1H")

        assert score is not None
        assert score.direction == Layer1SignalDirection.BEARISH

    def test_score_fvg_no_fvg(self):
        """Test FVG scoring with no FVG detected."""
        scorer = Layer1SignalScorer()

        fvg_result = FVGDetectionResult(fvg=None, detection_index=-1)

        score = scorer.score_fvg(fvg_result, timeframe="1H")

        assert score is None

    def test_score_fvg_mitigation_reduces_strength(self):
        """Test that FVG mitigation status affects strength."""
        scorer = Layer1SignalScorer()

        # Unmitigated FVG
        fvg_none = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )
        score_none = scorer.score_fvg(
            FVGDetectionResult(fvg=fvg_none, detection_index=1), "1H"
        )

        # Fully mitigated FVG
        fvg_full = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.FULL,
        )
        score_full = scorer.score_fvg(
            FVGDetectionResult(fvg=fvg_full, detection_index=1), "1H"
        )

        assert score_none is not None
        assert score_full is not None
        assert score_none.strength > score_full.strength

    def test_score_order_block_bullish(self):
        """Test Order Block scoring with bullish OB."""
        scorer = Layer1SignalScorer()

        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )

        ob_result = OBDetectionResult(
            polarity=OBPolaridade.BULLISH,
            zone=zone,
            anchor_candle_index=1,
            momentum_candle_index=2,
            strength_score=0.8,
            volume_confirmed=True,
        )

        score = scorer.score_order_block(ob_result, "1H")

        assert score is not None
        assert score.signal_type == "order_block"
        assert score.direction == Layer1SignalDirection.BULLISH
        assert score.strength == 0.8
        assert score.metadata["volume_confirmed"] is True

    def test_score_order_block_bearish(self):
        """Test Order Block scoring with bearish OB."""
        scorer = Layer1SignalScorer()

        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )

        ob_result = OBDetectionResult(
            polarity=OBPolaridade.BEARISH,
            zone=zone,
            anchor_candle_index=1,
            momentum_candle_index=2,
            strength_score=0.75,
            volume_confirmed=False,
        )

        score = scorer.score_order_block(ob_result, "1H")

        assert score is not None
        assert score.direction == Layer1SignalDirection.BEARISH

    def test_score_order_block_low_confidence(self):
        """Test Order Block scoring with low confidence signal."""
        scorer = Layer1SignalScorer(min_confidence_threshold=0.8)

        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )

        ob_result = OBDetectionResult(
            polarity=OBPolaridade.BULLISH,
            zone=zone,
            anchor_candle_index=1,
            momentum_candle_index=2,
            strength_score=0.3,  # Low strength
            volume_confirmed=False,
        )

        score = scorer.score_order_block(ob_result, "1H")

        assert score is None

    def test_score_multiple_fvgs(self):
        """Test scoring multiple FVG signals."""
        scorer = Layer1SignalScorer()

        fvg1 = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )
        fvg2 = FVG(
            direction=FVGDirection.BEARISH,
            timestamp=1234567891,
            high=110.0,
            low=105.0,
            mitigation=FVGMitigation.NONE,
        )

        results = [
            FVGDetectionResult(fvg=fvg1, detection_index=1),
            FVGDetectionResult(fvg=fvg2, detection_index=2),
        ]

        scores = scorer.score_multiple_fvgs(results, "1H")

        assert len(scores) == 2
        assert any(s.direction == Layer1SignalDirection.BULLISH for s in scores)
        assert any(s.direction == Layer1SignalDirection.BEARISH for s in scores)

    def test_score_multiple_order_blocks(self):
        """Test scoring multiple Order Block signals."""
        scorer = Layer1SignalScorer()

        zone1 = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=105.0, low=100.0),
        )
        zone2 = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=110.0, low=105.0),
        )

        results = [
            OBDetectionResult(
                polarity=OBPolaridade.BULLISH,
                zone=zone1,
                anchor_candle_index=1,
                momentum_candle_index=2,
                strength_score=0.8,
                volume_confirmed=True,
            ),
            OBDetectionResult(
                polarity=OBPolaridade.BEARISH,
                zone=zone2,
                anchor_candle_index=3,
                momentum_candle_index=4,
                strength_score=0.75,
                volume_confirmed=False,
            ),
        ]

        scores = scorer.score_multiple_order_blocks(results, "1H")

        assert len(scores) == 2


class TestLayer1SignalDirection:
    """Test suite for Layer1SignalDirection enum."""

    def test_to_confluence_direction(self):
        """Test direction conversion to SignalDirection."""
        from market_analysis.confluence.signal_aggregator import SignalDirection

        assert (
            Layer1SignalDirection.BULLISH.to_confluence_direction()
            == SignalDirection.LONG
        )
        assert (
            Layer1SignalDirection.BEARISH.to_confluence_direction()
            == SignalDirection.SHORT
        )
        assert (
            Layer1SignalDirection.NEUTRAL.to_confluence_direction()
            == SignalDirection.NEUTRAL
        )
