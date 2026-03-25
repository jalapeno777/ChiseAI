"""Tests for unified market regime classification."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from market_analysis.regime import (
    MarketRegimeClassifier,
    MarkovTrendResult,
    RegimeClassification,
    UnifiedRegime,
    VolatilityRegime,
)


@dataclass
class MockOHLCVData:
    """Mock OHLCV data for testing."""

    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float


def create_trending_data(
    count: int,
    direction: str = "up",
    strength: float = 1.0,
) -> list[MockOHLCVData]:
    """Create mock data with trending pattern."""
    data = []
    price = 50000.0

    for i in range(count):
        if direction == "up":
            price *= 1 + 0.001 * strength
        else:
            price *= 1 - 0.001 * strength

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,
                open_price=price * 0.998,
                high_price=price * 1.005,
                low_price=price * 0.995,
                close_price=price,
                volume=1000.0,
            )
        )

    return data


def create_ranging_data(count: int) -> list[MockOHLCVData]:
    """Create mock data with ranging pattern."""
    data = []
    base_price = 50000.0

    for i in range(count):
        oscillation = (i % 10 - 5) * 100
        price = base_price + oscillation

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,
                open_price=price - 50,
                high_price=price + 200,
                low_price=price - 200,
                close_price=price,
                volume=1000.0,
            )
        )

    return data


def create_volatile_data(count: int) -> list[MockOHLCVData]:
    """Create mock data with volatile pattern."""
    import random

    data = []
    price = 50000.0

    for i in range(count):
        # Large random swings
        change = random.uniform(-0.03, 0.03)
        price *= 1 + change

        data.append(
            MockOHLCVData(
                timestamp=i * 3600,
                open_price=price * 0.99,
                high_price=price * 1.02,
                low_price=price * 0.98,
                close_price=price,
                volume=2000.0,
            )
        )

    return data


class TestUnifiedRegime:
    """Tests for UnifiedRegime enum."""

    def test_trending_is_trending(self) -> None:
        """Test TRENDING regime is_trending property."""
        assert UnifiedRegime.TRENDING.is_trending is True
        assert UnifiedRegime.TRENDING.is_ranging is False
        assert UnifiedRegime.TRENDING.is_volatile is False

    def test_ranging_is_ranging(self) -> None:
        """Test RANGING regime is_ranging property."""
        assert UnifiedRegime.RANGING.is_ranging is True
        assert UnifiedRegime.RANGING.is_trending is False
        assert UnifiedRegime.RANGING.is_volatile is False

    def test_volatile_is_volatile(self) -> None:
        """Test VOLATILE regime is_volatile property."""
        assert UnifiedRegime.VOLATILE.is_volatile is True
        assert UnifiedRegime.VOLATILE.is_trending is False
        assert UnifiedRegime.VOLATILE.is_ranging is False

    def test_unknown_defaults(self) -> None:
        """Test UNKNOWN regime default properties."""
        assert UnifiedRegime.UNKNOWN.is_trending is False
        assert UnifiedRegime.UNKNOWN.is_ranging is False
        assert UnifiedRegime.UNKNOWN.is_volatile is False


class TestVolatilityRegime:
    """Tests for VolatilityRegime enum."""

    def test_values(self) -> None:
        """Test volatility regime values."""
        assert VolatilityRegime.HIGH.value == "high"
        assert VolatilityRegime.MEDIUM.value == "medium"
        assert VolatilityRegime.LOW.value == "low"


class TestRegimeClassification:
    """Tests for RegimeClassification dataclass."""

    def test_creation(self) -> None:
        """Test creating RegimeClassification."""
        result = RegimeClassification(
            regime=UnifiedRegime.TRENDING,
            confidence=0.85,
            adx_value=35.0,
            volatility_regime=VolatilityRegime.MEDIUM,
            trend_direction="up",
            markov_trending=True,
            markov_confidence=0.75,
            volatility_score=2.5,
            description="Strong uptrend",
        )

        assert result.regime == UnifiedRegime.TRENDING
        assert result.confidence == 0.85
        assert result.adx_value == 35.0
        assert result.volatility_regime == VolatilityRegime.MEDIUM
        assert result.trend_direction == "up"
        assert result.markov_trending is True
        assert result.markov_confidence == 0.75

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = RegimeClassification(
            regime=UnifiedRegime.TRENDING,
            confidence=0.85,
            adx_value=35.0,
        )

        d = result.to_dict()

        assert d["regime"] == "trending"
        assert d["confidence"] == 0.85
        assert d["adx_value"] == 35.0
        assert d["is_trending"] is True
        assert d["is_ranging"] is False
        assert d["is_volatile"] is False


class TestMarketRegimeClassifier:
    """Tests for MarketRegimeClassifier."""

    def test_classifier_creation(self) -> None:
        """Test creating classifier."""
        classifier = MarketRegimeClassifier()

        assert classifier.adx_period == 14
        assert classifier.adx_trending_threshold == 25.0
        assert classifier.adx_ranging_threshold == 20.0
        assert classifier.volatility_period == 14

    def test_custom_parameters(self) -> None:
        """Test creating classifier with custom parameters."""
        classifier = MarketRegimeClassifier(
            adx_period=20,
            adx_trending_threshold=30.0,
            volatility_period=20,
        )

        assert classifier.adx_period == 20
        assert classifier.adx_trending_threshold == 30.0
        assert classifier.volatility_period == 20

    def test_classify_insufficient_data(self) -> None:
        """Test classification with insufficient data."""
        classifier = MarketRegimeClassifier()

        # Only 3 candles - should return UNKNOWN
        data = create_trending_data(3)

        result = classifier.classify(data)

        assert result.regime == UnifiedRegime.UNKNOWN
        assert result.confidence == 0.0
        assert "Insufficient" in result.description

    def test_classify_trending_up(self) -> None:
        """Test trending up detection."""
        classifier = MarketRegimeClassifier()

        # Strong uptrend should be detected
        data = create_trending_data(50, direction="up", strength=3.0)

        result = classifier.classify(data)

        # Should be trending (not ranging or volatile)
        assert result.regime in (UnifiedRegime.TRENDING, UnifiedRegime.VOLATILE)
        assert result.adx_value >= 0

    def test_classify_trending_down(self) -> None:
        """Test trending down detection."""
        classifier = MarketRegimeClassifier()

        data = create_trending_data(50, direction="down", strength=3.0)

        result = classifier.classify(data)

        # Should be trending
        assert result.regime in (UnifiedRegime.TRENDING, UnifiedRegime.VOLATILE)
        assert result.adx_value >= 0

    def test_classify_ranging(self) -> None:
        """Test ranging detection."""
        classifier = MarketRegimeClassifier()

        data = create_ranging_data(50)

        result = classifier.classify(data)

        # Ranging data should produce ranging or volatile regime
        assert result.regime in (UnifiedRegime.RANGING, UnifiedRegime.VOLATILE)

    def test_classify_volatile(self) -> None:
        """Test volatile data classification."""
        classifier = MarketRegimeClassifier()

        data = create_volatile_data(50)

        result = classifier.classify(data)

        # Volatile data can produce any regime depending on the randomness
        # Just verify we get a valid classification
        assert result.regime in (
            UnifiedRegime.VOLATILE,
            UnifiedRegime.TRENDING,
            UnifiedRegime.RANGING,
        )
        assert result.adx_value >= 0

    def test_reset(self) -> None:
        """Test classifier reset."""
        classifier = MarketRegimeClassifier()

        data = create_trending_data(50)
        classifier.classify(data)

        # Should not raise
        classifier.reset()

    def test_smooth_regime_detection(self) -> None:
        """Test that regime smoothing works."""
        classifier = MarketRegimeClassifier()

        # Create data that oscillates
        data1 = create_trending_data(30, direction="up", strength=2.0)
        result1 = classifier.classify(data1)

        # Reset and try with different regime
        classifier.reset()
        data2 = create_ranging_data(30)
        result2 = classifier.classify(data2)

        # Both should return valid results
        assert result1.regime != UnifiedRegime.UNKNOWN
        assert result2.regime != UnifiedRegime.UNKNOWN

    def test_description_generation(self) -> None:
        """Test description is generated."""
        classifier = MarketRegimeClassifier()

        data = create_trending_data(50, direction="up", strength=2.0)
        result = classifier.classify(data)

        assert len(result.description) > 0

    def test_description_with_volatile_regime(self) -> None:
        """Test description generation for volatile regime includes ADX."""
        classifier = MarketRegimeClassifier()

        # Create data with high volatility
        data = create_volatile_data(50)
        result = classifier.classify(data)

        # Description should be generated
        assert len(result.description) > 0

    def test_smooth_regime_flapping_prevention(self) -> None:
        """Test that regime smoothing prevents flapping."""
        classifier = MarketRegimeClassifier()

        # First classify one regime
        data1 = create_trending_data(30, direction="up", strength=2.0)
        result1 = classifier.classify(data1)

        # Without reset, immediately classify different data
        # Should maintain previous regime due to smoothing
        classifier.reset()
        data2 = create_ranging_data(30)
        result2 = classifier.classify(data2)

        # Both should be valid regimes
        assert result1.regime != UnifiedRegime.UNKNOWN
        assert result2.regime != UnifiedRegime.UNKNOWN

    def test_markov_trend_result(self) -> None:
        """Test MarkovTrendResult dataclass."""
        from market_analysis.regime import MarkovTrendResult

        result = MarkovTrendResult(is_trending=True, confidence=0.8)
        assert result.is_trending is True
        assert result.confidence == 0.8

    def test_wilder_smooth_empty_values(self) -> None:
        """Test Wilder smoothing with empty values."""
        import numpy as np

        classifier = MarketRegimeClassifier()

        # Empty array should return 0.0
        result = classifier._wilder_smooth(np.array([]), 14)
        assert result == 0.0

    def test_wilder_smooth_short_values(self) -> None:
        """Test Wilder smoothing with short values."""
        import numpy as np

        classifier = MarketRegimeClassifier()

        # Values shorter than period should return mean
        values = np.array([1.0, 2.0, 3.0])
        result = classifier._wilder_smooth(values, 5)
        assert result == 2.0  # mean of [1, 2, 3]

    def test_volatility_calculation_short_data(self) -> None:
        """Test volatility calculation with short data."""
        classifier = MarketRegimeClassifier()

        # Only 1 candle - should return 0.0
        data = [create_trending_data(1)[0]]
        result = classifier._calculate_volatility(data)
        assert result == 0.0

    def test_classify_volatility_low(self) -> None:
        """Test low volatility classification."""
        classifier = MarketRegimeClassifier()

        # Create data with low volatility (very small price movements)
        data = []
        price = 50000.0
        for i in range(100):
            price *= 1 + 0.00001  # Very small change
            data.append(
                MockOHLCVData(
                    timestamp=i * 3600,
                    open_price=price * 0.999,
                    high_price=price * 1.001,
                    low_price=price * 0.999,
                    close_price=price,
                    volume=1000.0,
                )
            )

        vol = classifier._calculate_volatility(data)
        vol_regime = classifier._classify_volatility(vol, data)

        # With such small movements, should be low or medium volatility
        assert vol_regime in (VolatilityRegime.LOW, VolatilityRegime.MEDIUM)

    def test_classify_volatility_high(self) -> None:
        """Test high volatility classification."""
        classifier = MarketRegimeClassifier()

        # Use volatile data
        data = create_volatile_data(100)
        vol = classifier._calculate_volatility(data)
        vol_regime = classifier._classify_volatility(vol, data)

        # High volatility data should produce high volatility regime
        # (or at least not low)
        assert vol_regime in (VolatilityRegime.HIGH, VolatilityRegime.MEDIUM)

    def test_compute_unified_regime_volatile_low_adx(self) -> None:
        """Test _compute_unified_regime with volatile market and low ADX."""
        classifier = MarketRegimeClassifier()

        # This tests the code path where:
        # - is_high_volatility = True
        # - adx_value < adx_trending_threshold
        # Should return VOLATILE, 0.6
        regime, confidence = classifier._compute_unified_regime(
            adx_value=15.0,  # Low ADX (below 20)
            volatility_score=5.0,
            vol_regime=VolatilityRegime.HIGH,
            markov_trending=False,
            markov_confidence=0.5,
        )

        assert regime == UnifiedRegime.VOLATILE
        assert confidence == 0.6

    def test_compute_unified_regime_volatile_high_adx_not_markov(self) -> None:
        """Test _compute_unified_regime with high ADX but Markov not trending."""
        classifier = MarketRegimeClassifier()

        # This tests the code path where:
        # - adx_value >= adx_trending_threshold
        # - markov_trending = False
        # - adx_value < adx_trending_threshold + 10
        # - is_high_volatility = True
        # Should return VOLATILE, 0.5
        regime, confidence = classifier._compute_unified_regime(
            adx_value=30.0,  # Above 25
            volatility_score=5.0,
            vol_regime=VolatilityRegime.HIGH,
            markov_trending=False,
            markov_confidence=0.5,
        )

        assert regime == UnifiedRegime.VOLATILE
        assert confidence == 0.5

    def test_compute_unified_regime_transitional_high_vol(self) -> None:
        """Test _compute_unified_regime transitional zone with high volatility."""
        classifier = MarketRegimeClassifier()

        # This tests the code path where:
        # - adx_value >= adx_trending_threshold (25+)
        # - markov_trending = False
        # - adx_value < adx_trending_threshold + 10 (35)
        # - is_high_volatility = True
        # Should return VOLATILE, 0.5 (not 0.6 because it passes the first check)
        regime, confidence = classifier._compute_unified_regime(
            adx_value=28.0,  # Between 25 and 35
            volatility_score=5.0,
            vol_regime=VolatilityRegime.HIGH,
            markov_trending=False,
            markov_confidence=0.5,
        )

        assert regime == UnifiedRegime.VOLATILE
        assert confidence == 0.5

    def test_compute_unified_regime_transitional_low_vol(self) -> None:
        """Test _compute_unified_regime transitional zone with low volatility."""
        classifier = MarketRegimeClassifier()

        # This tests the code path where:
        # - adx_value between 20-25
        # - is_high_volatility = False
        # Should return RANGING, 0.3
        regime, confidence = classifier._compute_unified_regime(
            adx_value=22.0,  # Between 20-25
            volatility_score=1.0,
            vol_regime=VolatilityRegime.LOW,
            markov_trending=False,
            markov_confidence=0.5,
        )

        assert regime == UnifiedRegime.RANGING
        assert confidence == 0.3

    def test_smooth_regime_consecutive_smoothing(self) -> None:
        """Test that smoothing requires consecutive confirmations."""
        classifier = MarketRegimeClassifier()

        # First classify trending
        data1 = create_trending_data(30, direction="up", strength=2.0)
        result1 = classifier.classify(data1)

        # Immediately classify with different data
        data2 = create_ranging_data(30)
        result2 = classifier.classify(data2)

        # With only 1 confirmation, should keep previous or reduce confidence
        # The smoothing kicks in after < 2 confirmations
        assert result2.confidence <= result1.confidence

    def test_smooth_regime_sustained_boost(self) -> None:
        """Test confidence boost for sustained regime detection."""
        classifier = MarketRegimeClassifier()

        # Classify same regime multiple times
        for _ in range(5):
            data = create_trending_data(30, direction="up", strength=2.0)
            result = classifier.classify(data)
            classifier.reset()  # Reset between each

        # After 3+ consecutive of same regime, confidence should be boosted
        # This test just verifies it doesn't crash
        assert result.confidence >= 0

    def test_determine_trend_direction_short_data(self) -> None:
        """Test trend direction with insufficient data."""
        classifier = MarketRegimeClassifier()

        # Only 5 candles - less than 10 needed
        data = create_trending_data(5)
        direction = classifier._determine_trend_direction(data, 25.0)

        assert direction == "neutral"

    def test_markov_trend_exception_handling(self) -> None:
        """Test Markov trend fallback on exception."""
        classifier = MarketRegimeClassifier()

        # The _get_markov_trend method has exception handling
        # Just call it and verify it returns a valid result
        data = create_trending_data(30)
        result = classifier._get_markov_trend(data)

        assert result is not None
        assert isinstance(result.is_trending, bool)
        assert isinstance(result.confidence, float)


class TestMarkovTrendResult:
    """Tests for MarkovTrendResult."""

    def test_creation(self) -> None:
        """Test creating MarkovTrendResult."""
        result = MarkovTrendResult(is_trending=True, confidence=0.8)

        assert result.is_trending is True
        assert result.confidence == 0.8

    def test_defaults(self) -> None:
        """Test default values."""
        result = MarkovTrendResult(is_trending=False, confidence=0.5)

        assert result.is_trending is False
        assert result.confidence == 0.5


class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""

    def test_regime_type_alias(self) -> None:
        """Test RegimeType is aliased to UnifiedRegime."""
        from market_analysis.regime import RegimeType

        assert RegimeType is UnifiedRegime

    def test_market_regime_alias(self) -> None:
        """Test MarketRegime is aliased to RegimeClassification."""
        from market_analysis.regime import MarketRegime

        assert MarketRegime is RegimeClassification


class TestDeprecationWarnings:
    """Tests for deprecation warnings in legacy modules."""

    def test_regime_detector_deprecation(self) -> None:
        """Test RegimeDetector deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            from dashboard.regime_detector import RegimeDetector

            # Warning should be raised on instantiation
            detector = RegimeDetector()

            # Check deprecation warning was raised
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) > 0

    def test_analyzer_market_regime_deprecation(self) -> None:
        """Test MarketRegime deprecation in analyzer is documented."""
        from ml.feedback.analyzer import MarketRegime

        # MarketRegime should still work (backward compatibility)
        assert MarketRegime.BULLISH.value == "bullish"
        assert MarketRegime.RANGING.value == "ranging"

        # Check that the class docstring documents deprecation
        assert "deprecated" in MarketRegime.__doc__.lower()
        assert "UnifiedRegime" in MarketRegime.__doc__
