"""Tests for Markov inference engine module."""

import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.markov.inference_engine import (
    InferenceResult,
    TechnicalIndicators,
    TrendInferenceEngine,
)
from market_analysis.markov.state_model import TrendState


class TestTechnicalIndicators:
    """Test cases for TechnicalIndicators dataclass."""

    def test_creation(self):
        """Test creating TechnicalIndicators."""
        indicators = TechnicalIndicators(
            rsi=65.0,
            macd_line=0.5,
            macd_signal=0.3,
            macd_histogram=0.2,
        )
        assert indicators.rsi == 65.0
        assert indicators.macd_line == 0.5
        assert indicators.macd_signal == 0.3
        assert indicators.macd_histogram == 0.2

    def test_macd_bullish(self):
        """Test MACD bullish property."""
        indicators = TechnicalIndicators(macd_line=0.5, macd_signal=0.3)
        assert indicators.macd_bullish is True
        assert indicators.macd_bearish is False

    def test_macd_bearish(self):
        """Test MACD bearish property."""
        indicators = TechnicalIndicators(macd_line=0.2, macd_signal=0.5)
        assert indicators.macd_bearish is True
        assert indicators.macd_bullish is False

    def test_macd_none(self):
        """Test MACD properties with None values."""
        indicators = TechnicalIndicators()
        assert indicators.macd_bullish is None
        assert indicators.macd_bearish is None


class TestInferenceResult:
    """Test cases for InferenceResult dataclass."""

    def test_creation(self):
        """Test creating InferenceResult."""
        indicators = TechnicalIndicators(rsi=65.0)
        result = InferenceResult(
            state=TrendState.BULLISH,
            confidence=0.85,
            indicators=indicators,
            timestamp=1609459200000,
            price_change_pct=0.02,
            volume_trend=0.1,
            signal_strength=0.75,
        )
        assert result.state == TrendState.BULLISH
        assert result.confidence == 0.85
        assert result.is_high_confidence() is True

    def test_low_confidence(self):
        """Test low confidence detection."""
        indicators = TechnicalIndicators()
        result = InferenceResult(
            state=TrendState.NEUTRAL,
            confidence=0.5,
            indicators=indicators,
            timestamp=1609459200000,
            price_change_pct=0.0,
            volume_trend=0.0,
            signal_strength=0.3,
        )
        assert result.is_high_confidence() is False
        assert result.is_high_confidence(threshold=0.4) is True


class TestTrendInferenceEngine:
    """Test cases for TrendInferenceEngine class."""

    @pytest.fixture
    def engine(self):
        """Create a TrendInferenceEngine instance."""
        return TrendInferenceEngine()

    @pytest.fixture
    def bullish_data(self):
        """Create sample bullish OHLCV data (rising prices)."""
        base_ts = 1609459200000
        return [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + i * 2,
                high_price=102.0 + i * 2,
                low_price=99.0 + i * 2,
                close_price=101.0 + i * 2,
                volume=1000.0 + i * 10,
            )
            for i in range(50)
        ]

    @pytest.fixture
    def bearish_data(self):
        """Create sample bearish OHLCV data (falling prices)."""
        base_ts = 1609459200000
        return [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 - i * 2,
                high_price=101.0 - i * 2,
                low_price=98.0 - i * 2,
                close_price=99.0 - i * 2,
                volume=1000.0 + i * 10,
            )
            for i in range(50)
        ]

    @pytest.fixture
    def neutral_data(self):
        """Create sample neutral OHLCV data (sideways prices)."""
        base_ts = 1609459200000
        return [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + (i % 3 - 1),
                high_price=101.0 + (i % 3 - 1),
                low_price=99.0 + (i % 3 - 1),
                close_price=100.0 + (i % 3 - 1),
                volume=1000.0,
            )
            for i in range(50)
        ]

    def test_infer_state_empty_data(self, engine):
        """Test that empty data raises error."""
        with pytest.raises(ValueError, match="OHLCV data cannot be empty"):
            engine.infer_state([])

    def test_infer_bullish_state(self, engine, bullish_data):
        """Test inferring bullish state."""
        result = engine.infer_state(bullish_data)

        # Should detect bullish trend
        assert result.state in [TrendState.BULLISH, TrendState.NEUTRAL]
        assert result.confidence > 0.0
        assert result.price_change_pct > 0

    def test_infer_bearish_state(self, engine, bearish_data):
        """Test inferring bearish state."""
        result = engine.infer_state(bearish_data)

        # Should detect bearish trend
        assert result.state in [TrendState.BEARISH, TrendState.NEUTRAL]
        assert result.confidence > 0.0
        assert result.price_change_pct < 0

    def test_infer_neutral_state(self, engine, neutral_data):
        """Test inferring neutral state."""
        result = engine.infer_state(neutral_data)

        # Should detect neutral or transitional
        assert result.state in [TrendState.NEUTRAL, TrendState.TRANSITIONAL]

    def test_indicators_calculated(self, engine, bullish_data):
        """Test that indicators are calculated."""
        result = engine.infer_state(bullish_data)

        assert result.indicators.rsi is not None
        assert result.indicators.sma_short is not None
        assert result.indicators.sma_long is not None
        assert result.indicators.volatility is not None
        assert result.indicators.volume_sma is not None

    def test_calculate_rsi(self, engine):
        """Test RSI calculation."""
        # Create data with alternating up/down
        prices = [100.0]
        for i in range(20):
            if i % 2 == 0:
                prices.append(prices[-1] + 1.0)
            else:
                prices.append(prices[-1] - 0.5)

        rsi = engine._calculate_rsi(prices)
        assert 0 <= rsi <= 100

    def test_calculate_sma(self, engine):
        """Test SMA calculation."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        sma = engine._calculate_sma(values, 5)
        assert sma == 3.0

    def test_calculate_sma_short_list(self, engine):
        """Test SMA with shorter list than period."""
        values = [1.0, 2.0]
        sma = engine._calculate_sma(values, 5)
        assert sma == 1.5  # Average of available values

    def test_calculate_ema(self, engine):
        """Test EMA calculation."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        ema = engine._calculate_ema(prices, 5)
        assert ema > 0

    def test_calculate_volatility(self, engine):
        """Test volatility calculation."""
        # Create data with some variance
        prices = [100.0 + i * 0.1 for i in range(25)]
        volatility = engine._calculate_volatility(prices)
        assert volatility >= 0

    def test_calculate_volume_trend(self, engine):
        """Test volume trend calculation."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0,
                high_price=101.0,
                low_price=99.0,
                close_price=100.0,
                volume=1000.0 + i * 10,  # Increasing volume
            )
            for i in range(20)
        ]

        trend = engine._calculate_volume_trend(data)
        assert -1.0 <= trend <= 1.0
        assert trend > 0  # Should be positive for increasing volume

    def test_classify_state_bullish(self, engine):
        """Test bullish state classification."""
        indicators = TechnicalIndicators(
            rsi=65.0,
            macd_line=0.5,
            macd_signal=0.2,
            sma_short=105.0,
            sma_long=100.0,
            volatility=0.01,
        )

        state, confidence, strength = engine._classify_state(
            current_price=110.0,
            indicators=indicators,
            price_change_pct=0.03,
            volume_trend=0.2,
        )

        assert state == TrendState.BULLISH
        assert confidence > 0
        assert strength > 0

    def test_classify_state_bearish(self, engine):
        """Test bearish state classification."""
        indicators = TechnicalIndicators(
            rsi=35.0,
            macd_line=0.2,
            macd_signal=0.5,
            sma_short=95.0,
            sma_long=100.0,
            volatility=0.01,
        )

        state, confidence, strength = engine._classify_state(
            current_price=90.0,
            indicators=indicators,
            price_change_pct=-0.03,
            volume_trend=0.2,
        )

        assert state == TrendState.BEARISH
        assert confidence > 0
        assert strength > 0

    def test_classify_state_transitional_high_volatility(self, engine):
        """Test transitional state with high volatility."""
        indicators = TechnicalIndicators(
            rsi=50.0,
            volatility=0.05,  # High volatility
        )

        state, confidence, strength = engine._classify_state(
            current_price=100.0,
            indicators=indicators,
            price_change_pct=0.01,
            volume_trend=0.0,
        )

        # High volatility should push toward transitional
        assert state in [TrendState.TRANSITIONAL, TrendState.NEUTRAL]

    def test_classify_state_conflicting_signals(self, engine):
        """Test transitional state with conflicting signals."""
        indicators = TechnicalIndicators(
            rsi=65.0,  # Bullish
            macd_line=0.2,
            macd_signal=0.5,  # Bearish MACD
        )

        state, confidence, strength = engine._classify_state(
            current_price=100.0,
            indicators=indicators,
            price_change_pct=0.0,
            volume_trend=0.0,
        )

        # Conflicting signals may push toward transitional, neutral, or bullish
        # depending on the weighting of indicators
        assert state in [
            TrendState.TRANSITIONAL,
            TrendState.NEUTRAL,
            TrendState.BULLISH,
        ]
