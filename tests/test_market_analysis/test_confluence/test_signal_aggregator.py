"""Tests for signal aggregator."""

import numpy as np
import pytest

from market_analysis.confluence.signal_aggregator import (
    AggregatedSignals,
    IndicatorSignal,
    SignalAggregator,
    SignalDirection,
)
from market_analysis.indicators.bollinger_bands import BollingerBandsResult
from market_analysis.indicators.macd import MACDResult, MACDSignal
from market_analysis.indicators.rsi import RSIResult
from market_analysis.markov.state_model import TrendState


class TestSignalDirection:
    """Test suite for SignalDirection enum."""

    def test_direction_values(self):
        """Test signal direction values."""
        assert str(SignalDirection.LONG) == "long"
        assert str(SignalDirection.SHORT) == "short"
        assert str(SignalDirection.NEUTRAL) == "neutral"

    def test_opposite_direction(self):
        """Test opposite direction method."""
        assert SignalDirection.LONG.opposite() == SignalDirection.SHORT
        assert SignalDirection.SHORT.opposite() == SignalDirection.LONG
        assert SignalDirection.NEUTRAL.opposite() == SignalDirection.NEUTRAL


class TestIndicatorSignal:
    """Test suite for IndicatorSignal dataclass."""

    def test_valid_signal_creation(self):
        """Test creating a valid indicator signal."""
        signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
            raw_value=75.0,
            timestamp=1234567890,
            metadata={"overbought": False},
        )

        assert signal.is_valid
        assert signal.indicator_type == "rsi"
        assert signal.timeframe == "1h"
        assert signal.direction == SignalDirection.LONG
        assert signal.strength == 0.8
        assert signal.confidence == 0.9

    def test_signal_validation_clamping(self):
        """Test that strength and confidence are clamped to valid range."""
        signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=1.5,  # Should be clamped to 1.0
            confidence=-0.2,  # Should be clamped to 0.0
        )

        assert signal.strength == 1.0
        assert signal.confidence == 0.0

    def test_invalid_signal(self):
        """Test invalid signal detection."""
        signal = IndicatorSignal(
            indicator_type="",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
        )

        assert not signal.is_valid

    def test_weighted_score(self):
        """Test weighted score calculation."""
        # Long/Short signal
        signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
        )
        # weighted_score = strength * confidence * 1.0 = 0.72
        assert signal.weighted_score == pytest.approx(0.72, abs=0.01)

        # Neutral signal (0.5 multiplier)
        neutral_signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.NEUTRAL,
            strength=0.8,
            confidence=0.9,
        )
        # weighted_score = strength * confidence * 0.5 = 0.36
        assert neutral_signal.weighted_score == pytest.approx(0.36, abs=0.01)

    def test_to_dict(self):
        """Test signal serialization."""
        signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
            raw_value=75.0,
            timestamp=1234567890,
            metadata={"key": "value"},
        )

        data = signal.to_dict()

        assert data["indicator_type"] == "rsi"
        assert data["timeframe"] == "1h"
        assert data["direction"] == "long"
        assert data["strength"] == 0.8
        assert data["metadata"] == {"key": "value"}


class TestAggregatedSignals:
    """Test suite for AggregatedSignals class."""

    def test_empty_aggregation(self):
        """Test aggregation with no signals."""
        agg = AggregatedSignals()

        assert agg.total_signals == 0
        assert agg.total_strength == 0.0
        assert agg.avg_confidence == 0.0
        assert agg.dominant_direction == SignalDirection.NEUTRAL
        assert agg.direction_agreement == 0.0

    def test_add_signal(self):
        """Test adding signals to aggregation."""
        agg = AggregatedSignals()

        signal = IndicatorSignal(
            indicator_type="rsi",
            timeframe="1h",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
        )

        agg.add_signal(signal)

        assert agg.total_signals == 1
        assert agg.long_count == 1
        assert agg.short_count == 0
        assert agg.total_strength == 0.8

    def test_dominant_direction(self):
        """Test dominant direction calculation."""
        agg = AggregatedSignals()

        # Add 2 LONG signals
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
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.7,
                confidence=0.8,
            )
        )

        assert agg.dominant_direction == SignalDirection.LONG

        # Add 3 SHORT signals (now SHORT should dominate)
        for i in range(3):
            agg.add_signal(
                IndicatorSignal(
                    indicator_type=f"ind_{i}",
                    timeframe="1h",
                    direction=SignalDirection.SHORT,
                    strength=0.8,
                    confidence=0.9,
                )
            )

        assert agg.dominant_direction == SignalDirection.SHORT

    def test_direction_agreement(self):
        """Test direction agreement calculation."""
        agg = AggregatedSignals()

        # 3 LONG, 1 SHORT = 75% agreement with LONG
        for i in range(3):
            agg.add_signal(
                IndicatorSignal(
                    indicator_type=f"long_{i}",
                    timeframe="1h",
                    direction=SignalDirection.LONG,
                    strength=0.8,
                    confidence=0.9,
                )
            )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="short",
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.8,
                confidence=0.9,
            )
        )

        assert agg.direction_agreement == pytest.approx(0.75, abs=0.01)

    def test_filter_by_strength(self):
        """Test filtering signals by strength."""
        agg = AggregatedSignals()

        agg.add_signal(
            IndicatorSignal(
                indicator_type="strong",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )
        agg.add_signal(
            IndicatorSignal(
                indicator_type="weak",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.2,
                confidence=0.9,
            )
        )

        filtered = agg.filter_by_strength(0.5)

        assert filtered.total_signals == 1
        assert filtered.signals[0].indicator_type == "strong"

    def test_get_signals_by_direction(self):
        """Test getting signals by direction."""
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
                timeframe="1h",
                direction=SignalDirection.SHORT,
                strength=0.7,
                confidence=0.8,
            )
        )

        long_signals = agg.get_signals_by_direction(SignalDirection.LONG)
        assert len(long_signals) == 1
        assert long_signals[0].indicator_type == "rsi"

    def test_get_signals_by_timeframe(self):
        """Test getting signals by timeframe."""
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

        hourly_signals = agg.get_signals_by_timeframe("1h")
        assert len(hourly_signals) == 1
        assert hourly_signals[0].indicator_type == "rsi"

    def test_to_dict(self):
        """Test aggregation serialization."""
        agg = AggregatedSignals(timestamp=1234567890)
        agg.add_signal(
            IndicatorSignal(
                indicator_type="rsi",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            )
        )

        data = agg.to_dict()

        assert data["timestamp"] == 1234567890
        assert data["long_count"] == 1
        assert data["dominant_direction"] == "long"
        assert len(data["signals"]) == 1


class TestSignalAggregator:
    """Test suite for SignalAggregator class."""

    def test_initialization(self):
        """Test aggregator initialization."""
        aggregator = SignalAggregator(min_signal_threshold=0.4, max_indicators=8)

        assert aggregator.min_signal_threshold == 0.4
        assert aggregator.max_indicators == 8

    def test_aggregate_empty_signals(self):
        """Test aggregation with no signals."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate([])

        assert result.total_signals == 0

    def test_aggregate_filters_by_strength(self):
        """Test that aggregation filters signals below threshold."""
        aggregator = SignalAggregator(min_signal_threshold=0.5)

        signals = [
            IndicatorSignal(
                indicator_type="strong",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            ),
            IndicatorSignal(
                indicator_type="weak",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.2,
                confidence=0.9,
            ),
        ]

        result = aggregator.aggregate(signals)

        assert result.total_signals == 1
        assert result.signals[0].indicator_type == "strong"

    def test_aggregate_limits_count(self):
        """Test that aggregation limits number of signals."""
        aggregator = SignalAggregator(max_indicators=3)

        # Create 5 signals with varying weighted scores
        signals = [
            IndicatorSignal(
                indicator_type=f"sig_{i}",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.5 + i * 0.1,  # Increasing strength
                confidence=0.9,
            )
            for i in range(5)
        ]

        result = aggregator.aggregate(signals)

        assert result.total_signals == 3  # Limited to max_indicators

    def test_aggregate_sorts_by_score(self):
        """Test that aggregation sorts signals by weighted score."""
        aggregator = SignalAggregator(max_indicators=2)

        signals = [
            IndicatorSignal(
                indicator_type="low_score",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.3,
                confidence=0.5,
            ),
            IndicatorSignal(
                indicator_type="high_score",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.9,
                confidence=0.9,
            ),
            IndicatorSignal(
                indicator_type="medium_score",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.6,
                confidence=0.7,
            ),
        ]

        result = aggregator.aggregate(signals)

        # Should keep highest scoring signals
        assert result.total_signals == 2
        assert result.signals[0].indicator_type == "high_score"
        assert result.signals[1].indicator_type == "medium_score"

    def test_aggregate_filters_invalid_signals(self):
        """Test that aggregation filters out invalid signals."""
        aggregator = SignalAggregator()

        signals = [
            IndicatorSignal(
                indicator_type="valid",
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            ),
            IndicatorSignal(
                indicator_type="",  # Invalid - empty type
                timeframe="1h",
                direction=SignalDirection.LONG,
                strength=0.8,
                confidence=0.9,
            ),
        ]

        result = aggregator.aggregate(signals)

        assert result.total_signals == 1
        assert result.signals[0].indicator_type == "valid"


class TestSignalAggregatorFromIndicators:
    """Test suite for static factory methods."""

    def test_from_rsi_overbought(self):
        """Test RSI signal extraction - overbought."""
        rsi_result = RSIResult(
            values=np.array([75.0]),
            overbought=np.array([True]),
            oversold=np.array([False]),
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_rsi(rsi_result, "1h")

        assert signal is not None
        assert signal.indicator_type == "rsi"
        assert signal.direction == SignalDirection.SHORT
        assert signal.raw_value == 75.0
        assert signal.metadata["overbought"] is True

    def test_from_rsi_oversold(self):
        """Test RSI signal extraction - oversold."""
        rsi_result = RSIResult(
            values=np.array([25.0]),
            overbought=np.array([False]),
            oversold=np.array([True]),
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_rsi(rsi_result, "1h")

        assert signal is not None
        assert signal.direction == SignalDirection.LONG
        assert signal.metadata["oversold"] is True

    def test_from_rsi_neutral(self):
        """Test RSI signal extraction - neutral."""
        rsi_result = RSIResult(
            values=np.array([50.0]),
            overbought=np.array([False]),
            oversold=np.array([False]),
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_rsi(rsi_result, "1h")

        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL

    def test_from_rsi_empty(self):
        """Test RSI signal extraction with empty result."""
        rsi_result = RSIResult(
            values=np.array([]),
            overbought=np.array([]),
            oversold=np.array([]),
            timestamps=np.array([]),
        )

        signal = SignalAggregator.from_rsi(rsi_result, "1h")

        assert signal is None

    def test_from_macd_bullish(self):
        """Test MACD signal extraction - bullish."""
        macd_result = MACDResult(
            macd_line=np.array([0.5]),
            signal_line=np.array([0.3]),
            histogram=np.array([0.2]),
            crossovers=np.array([MACDSignal.NONE]),
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_macd(macd_result, "1h")

        assert signal is not None
        assert signal.indicator_type == "macd"
        assert signal.direction == SignalDirection.LONG
        assert signal.metadata["signal_line"] == 0.3

    def test_from_macd_bearish(self):
        """Test MACD signal extraction - bearish."""
        macd_result = MACDResult(
            macd_line=np.array([-0.5]),
            signal_line=np.array([-0.3]),
            histogram=np.array([-0.2]),
            crossovers=np.array([MACDSignal.NONE]),
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_macd(macd_result, "1h")

        assert signal is not None
        assert signal.direction == SignalDirection.SHORT

    def test_from_macd_empty(self):
        """Test MACD signal extraction with empty result."""
        macd_result = MACDResult(
            macd_line=np.array([]),
            signal_line=np.array([]),
            histogram=np.array([]),
            crossovers=np.array([]),
            timestamps=np.array([]),
        )

        signal = SignalAggregator.from_macd(macd_result, "1h")

        assert signal is None

    def test_from_bollinger_bands_upper(self):
        """Test Bollinger Bands signal extraction - near upper band."""
        bb_result = BollingerBandsResult(
            middle_band=np.array([100.0]),
            upper_band=np.array([110.0]),
            lower_band=np.array([90.0]),
            band_width=np.array([20.0]),
            percent_b=np.array([0.95]),  # Near upper band
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_bollinger_bands(bb_result, 109.0, "1h")

        assert signal is not None
        assert signal.indicator_type == "bb"
        assert signal.direction == SignalDirection.SHORT
        assert signal.raw_value == 0.95

    def test_from_bollinger_bands_lower(self):
        """Test Bollinger Bands signal extraction - near lower band."""
        bb_result = BollingerBandsResult(
            middle_band=np.array([100.0]),
            upper_band=np.array([110.0]),
            lower_band=np.array([90.0]),
            band_width=np.array([20.0]),
            percent_b=np.array([0.05]),  # Near lower band
            timestamps=np.array([1234567890]),
        )

        signal = SignalAggregator.from_bollinger_bands(bb_result, 91.0, "1h")

        assert signal is not None
        assert signal.direction == SignalDirection.LONG

    def test_from_bollinger_bands_empty(self):
        """Test Bollinger Bands signal extraction with empty result."""
        bb_result = BollingerBandsResult(
            middle_band=np.array([]),
            upper_band=np.array([]),
            lower_band=np.array([]),
            band_width=np.array([]),
            percent_b=np.array([]),
            timestamps=np.array([]),
        )

        signal = SignalAggregator.from_bollinger_bands(bb_result, 100.0, "1h")

        assert signal is None

    def test_from_markov_state_bullish(self):
        """Test Markov state signal extraction - bullish."""
        signal = SignalAggregator.from_markov_state(
            TrendState.BULLISH,
            confidence=0.85,
            signal_strength=0.75,
            timeframe="1h",
            timestamp=1234567890,
        )

        assert signal is not None
        assert signal.indicator_type == "markov"
        assert signal.direction == SignalDirection.LONG
        assert signal.confidence == 0.85
        assert signal.strength == 0.75
        assert signal.metadata["state_name"] == "bullish"

    def test_from_markov_state_bearish(self):
        """Test Markov state signal extraction - bearish."""
        signal = SignalAggregator.from_markov_state(
            TrendState.BEARISH,
            confidence=0.80,
            signal_strength=0.70,
            timeframe="1h",
            timestamp=1234567890,
        )

        assert signal is not None
        assert signal.direction == SignalDirection.SHORT

    def test_from_markov_state_neutral(self):
        """Test Markov state signal extraction - neutral."""
        signal = SignalAggregator.from_markov_state(
            TrendState.NEUTRAL,
            confidence=0.60,
            signal_strength=0.50,
            timeframe="1h",
            timestamp=1234567890,
        )

        assert signal is not None
        assert signal.direction == SignalDirection.NEUTRAL
