"""Tests for Two-Layer Scorer."""

from datetime import datetime

from market_analysis.confluence.signal_aggregator import SignalDirection
from market_analysis.confluence.signal_weights import ICTSignalType
from market_analysis.confluence.two_layer_scorer import TwoLayerScore, TwoLayerScorer
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


class TestTwoLayerScore:
    """Test suite for TwoLayerScore dataclass."""

    def test_valid_score_creation(self):
        """Test creating a valid TwoLayerScore."""
        score = TwoLayerScore(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.85,
        )

        assert score.confluence_score == 0.75
        assert score.direction == SignalDirection.LONG
        assert score.confidence == 0.85

    def test_score_clamping(self):
        """Test that scores are clamped to valid range."""
        score = TwoLayerScore(
            confluence_score=1.5,  # Should clamp to 1.0
            direction=SignalDirection.SHORT,
            confidence=-0.2,  # Should clamp to 0.0
        )

        assert score.confluence_score == 1.0
        assert score.confidence == 0.0

    def test_is_strong_signal(self):
        """Test strong signal detection."""
        strong = TwoLayerScore(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert strong.is_strong_signal

        weak_score = TwoLayerScore(
            confluence_score=0.6,
            direction=SignalDirection.LONG,
            confidence=0.6,
        )
        assert not weak_score.is_strong_signal

        low_conf = TwoLayerScore(
            confluence_score=0.8,
            direction=SignalDirection.LONG,
            confidence=0.4,
        )
        assert not low_conf.is_strong_signal

    def test_to_dict(self):
        """Test TwoLayerScore serialization."""
        score = TwoLayerScore(
            confluence_score=0.75,
            direction=SignalDirection.LONG,
            confidence=0.85,
            signals_included=["cvd", "fvg"],
            signals_excluded=[],
        )

        data = score.to_dict()

        assert data["confluence_score"] == 0.75
        assert data["direction"] == "long"
        assert data["confidence"] == 0.85
        assert data["is_strong_signal"] is True
        assert data["signals_included"] == ["cvd", "fvg"]
        assert data["signals_excluded"] == []


class TestTwoLayerScorer:
    """Test suite for TwoLayerScorer."""

    def test_initialization(self):
        """Test scorer initialization."""
        scorer = TwoLayerScorer(
            min_confidence_threshold=0.4,
            min_signals=2,
        )

        assert scorer.layer1_scorer.min_confidence_threshold == 0.4
        assert scorer.layer2_aggregator.min_signals == 2

    def test_is_signal_supported(self):
        """Test signal type support check."""
        scorer = TwoLayerScorer()

        assert scorer.is_signal_supported("cvd") is True
        assert scorer.is_signal_supported("fvg") is True
        assert scorer.is_signal_supported("order_block") is True
        assert scorer.is_signal_supported("bos") is False
        assert scorer.is_signal_supported("choc") is False

    def test_get_supported_signals(self):
        """Test getting supported signal types."""
        scorer = TwoLayerScorer()

        supported = scorer.get_supported_signals()

        assert "cvd" in supported
        assert "fvg" in supported
        assert "order_block" in supported
        assert "bos" not in supported
        assert "choc" not in supported

    def test_get_signal_weights(self):
        """Test getting signal weights."""
        scorer = TwoLayerScorer()

        weights = scorer.get_signal_weights()

        assert weights["cvd"] == 1.0
        assert weights["fvg"] == 1.0
        assert weights["order_block"] == 0.85

    def test_set_signal_enabled(self):
        """Test enabling/disabling signals."""
        scorer = TwoLayerScorer()

        scorer.set_signal_enabled("cvd", False)
        assert scorer.layer2_aggregator.is_signal_enabled("cvd") is False

        scorer.set_signal_enabled("cvd", True)
        assert scorer.layer2_aggregator.is_signal_enabled("cvd") is True

    def test_score_with_cvd_only(self):
        """Test scoring with only CVD signal."""
        scorer = TwoLayerScorer()

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        result = scorer.score(cvd_result=cvd_result, timeframe="1H")

        assert result is not None
        assert result.direction == SignalDirection.LONG
        assert result.signals_included == ["cvd"]
        assert "cvd" in result.layer1_scores[0].signal_type

    def test_score_with_fvg_only(self):
        """Test scoring with only FVG signals."""
        scorer = TwoLayerScorer()

        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )
        fvg_result = FVGDetectionResult(fvg=fvg, detection_index=1)

        result = scorer.score(fvg_results=[fvg_result], timeframe="1H")

        assert result is not None
        assert result.direction == SignalDirection.LONG
        assert "fvg" in result.signals_included

    def test_score_with_order_block_only(self):
        """Test scoring with only Order Block signals."""
        scorer = TwoLayerScorer()

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

        result = scorer.score(order_blocks=[ob_result], timeframe="1H")

        assert result is not None
        assert result.direction == SignalDirection.LONG
        assert "order_block" in result.signals_included

    def test_score_with_all_signal_types(self):
        """Test scoring with all ICT signal types."""
        scorer = TwoLayerScorer()

        # CVD
        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        # FVG
        fvg = FVG(
            direction=FVGDirection.BULLISH,
            timestamp=1234567890,
            high=105.0,
            low=100.0,
            mitigation=FVGMitigation.NONE,
        )
        fvg_result = FVGDetectionResult(fvg=fvg, detection_index=1)

        # Order Block
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

        result = scorer.score(
            cvd_result=cvd_result,
            fvg_results=[fvg_result],
            order_blocks=[ob_result],
            timeframe="1H",
        )

        assert result is not None
        assert result.direction == SignalDirection.LONG
        assert len(result.signals_included) == 3
        assert "cvd" in result.signals_included
        assert "fvg" in result.signals_included
        assert "order_block" in result.signals_included
        assert len(result.layer1_scores) == 3

    def test_score_no_signals(self):
        """Test scoring with no signals provided."""
        scorer = TwoLayerScorer()

        result = scorer.score(timeframe="1H")

        assert result is not None
        assert result.direction == SignalDirection.NEUTRAL
        assert len(result.signals_included) == 0

    def test_score_with_disabled_signal(self):
        """Test scoring with a disabled signal type."""
        scorer = TwoLayerScorer()
        scorer.set_signal_enabled("cvd", False)

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        result = scorer.score(cvd_result=cvd_result, timeframe="1H")

        # CVD should be excluded
        assert "cvd" in result.signals_excluded or len(result.signals_included) == 0

    def test_score_single_signal(self):
        """Test scoring a single signal type."""
        scorer = TwoLayerScorer()

        cvd_result = CVDResult(
            timestamps=[datetime.now()],
            cvd_values=[100.0, 150.0],
            trade_count=50,
            buy_volume=800.0,
            sell_volume=650.0,
            net_volume=150.0,
        )

        result = scorer.score_single_signal("cvd", cvd_result, "1H")

        assert result is not None
        assert result.signals_included == ["cvd"]

    def test_score_single_signal_unsupported(self):
        """Test scoring unsupported signal type."""
        scorer = TwoLayerScorer()

        result = scorer.score_single_signal("bos", None, "1H")

        assert result is None


class TestICTSignalType:
    """Test suite for ICTSignalType enum."""

    def test_is_valid_signal(self):
        """Test signal validation."""
        assert ICTSignalType.is_valid_signal("cvd") is True
        assert ICTSignalType.is_valid_signal("fvg") is True
        assert ICTSignalType.is_valid_signal("order_block") is True
        assert ICTSignalType.is_valid_signal("bos") is True
        assert ICTSignalType.is_valid_signal("choc") is True
        assert ICTSignalType.is_valid_signal("unknown") is False

    def test_get_supported_signals(self):
        """Test getting supported signals."""
        supported = ICTSignalType.get_supported_signals()

        supported_values = [s.value for s in supported]
        assert "cvd" in supported_values
        assert "fvg" in supported_values
        assert "order_block" in supported_values
        assert "bos" in supported_values
        assert "choc" in supported_values

    def test_bos_included_value(self):
        """Test BOS enum value exists and is included."""
        assert ICTSignalType.BOS.value == "bos"
        assert ICTSignalType.is_valid_signal("bos") is True

    def test_choc_included_value(self):
        """Test CHoCH enum value exists and is included."""
        assert ICTSignalType.CHOC.value == "choc"
        assert ICTSignalType.is_valid_signal("choc") is True
