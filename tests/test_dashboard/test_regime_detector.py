"""Tests for regime detector."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from dashboard.regime_detector import (
    MarketRegime,
    RegimeDetector,
    RegimeState,
    RegimeType,
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
            price *= 1 + 0.001 * strength  # Gradual uptrend
        else:
            price *= 1 - 0.001 * strength  # Gradual downtrend

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
        # Oscillate around base price
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


class TestMarketRegime:
    """Tests for MarketRegime dataclass."""

    def test_market_regime_creation(self) -> None:
        """Test creating MarketRegime."""
        regime = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=80.0,
            adx_value=30.0,
            volatility_regime="medium",
            volume_confirmation=True,
            duration_bars=10,
            description="Strong uptrend",
        )

        assert regime.regime == RegimeType.TRENDING_UP
        assert regime.confidence == 80.0
        assert regime.adx_value == 30.0

    def test_market_regime_normalization(self) -> None:
        """Test MarketRegime value normalization."""
        regime = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=150.0,  # Should be clamped to 100
            adx_value=30.0,
            transition_probability=1.5,  # Should be clamped to 1.0
        )

        assert regime.confidence == 100.0
        assert regime.transition_probability == 1.0

    def test_is_trending(self) -> None:
        """Test is_trending property."""
        trending_up = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=80.0,
            adx_value=30.0,
        )
        trending_down = MarketRegime(
            regime=RegimeType.TRENDING_DOWN,
            confidence=80.0,
            adx_value=30.0,
        )
        ranging = MarketRegime(
            regime=RegimeType.RANGING,
            confidence=60.0,
            adx_value=15.0,
        )

        assert trending_up.is_trending is True
        assert trending_down.is_trending is True
        assert ranging.is_trending is False

    def test_is_ranging(self) -> None:
        """Test is_ranging property."""
        ranging = MarketRegime(
            regime=RegimeType.RANGING,
            confidence=60.0,
            adx_value=15.0,
        )
        trending = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=80.0,
            adx_value=30.0,
        )

        assert ranging.is_ranging is True
        assert trending.is_ranging is False

    def test_direction(self) -> None:
        """Test direction property."""
        up = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=80.0,
            adx_value=30.0,
        )
        down = MarketRegime(
            regime=RegimeType.TRENDING_DOWN,
            confidence=80.0,
            adx_value=30.0,
        )
        ranging = MarketRegime(
            regime=RegimeType.RANGING,
            confidence=60.0,
            adx_value=15.0,
        )

        assert up.direction == "up"
        assert down.direction == "down"
        assert ranging.direction == "neutral"

    def test_to_dict(self) -> None:
        """Test MarketRegime serialization."""
        regime = MarketRegime(
            regime=RegimeType.TRENDING_UP,
            confidence=80.0,
            adx_value=30.0,
            volatility_regime="medium",
            volume_confirmation=True,
            duration_bars=10,
            transition_probability=0.2,
            description="Strong uptrend",
        )

        d = regime.to_dict()

        assert d["regime"] == "trending_up"
        assert d["confidence"] == 80.0
        assert d["adx_value"] == 30.0
        assert d["is_trending"] is True
        assert d["direction"] == "up"


class TestRegimeState:
    """Tests for RegimeState."""

    def test_regime_state_update(self) -> None:
        """Test state update."""
        state = RegimeState()

        state.update(RegimeType.TRENDING_UP, 30.0, 2.5)

        assert state.current_regime == RegimeType.TRENDING_UP
        assert len(state.regime_history) == 1
        assert len(state.adx_history) == 1

    def test_regime_state_duration(self) -> None:
        """Test regime duration calculation."""
        state = RegimeState()

        # Add multiple updates with same regime
        for _ in range(5):
            state.update(RegimeType.TRENDING_UP, 30.0, 2.5)

        assert state.regime_duration == 5

    def test_regime_state_duration_after_change(self) -> None:
        """Test duration after regime change."""
        state = RegimeState()

        # Add updates with different regimes
        for _ in range(3):
            state.update(RegimeType.TRENDING_UP, 30.0, 2.5)

        for _ in range(2):
            state.update(RegimeType.RANGING, 15.0, 1.5)

        assert state.regime_duration == 2  # Only counting RANGING


class TestRegimeDetector:
    """Tests for RegimeDetector."""

    def test_detect_insufficient_data(self) -> None:
        """Test detection with insufficient data."""
        detector = RegimeDetector()

        data = create_trending_data(5)  # Too few candles

        regime = detector.detect(data)

        assert regime.regime == RegimeType.UNKNOWN
        assert regime.confidence == 0.0

    def test_detect_trending_up(self) -> None:
        """Test trending up detection."""
        detector = RegimeDetector()

        data = create_trending_data(50, direction="up", strength=2.0)

        regime = detector.detect(data)

        # Should detect some kind of regime (trending or transitional)
        assert regime.regime in (RegimeType.TRENDING_UP, RegimeType.TRANSITIONAL)
        assert regime.adx_value >= 0

    def test_detect_trending_down(self) -> None:
        """Test trending down detection."""
        detector = RegimeDetector()

        data = create_trending_data(50, direction="down", strength=2.0)

        regime = detector.detect(data)

        # Should detect some kind of regime
        assert regime.regime in (RegimeType.TRENDING_DOWN, RegimeType.TRANSITIONAL)
        assert regime.adx_value >= 0

    def test_detect_ranging(self) -> None:
        """Test ranging detection."""
        detector = RegimeDetector()

        data = create_ranging_data(50)

        regime = detector.detect(data)

        # Should detect ranging or transitional
        assert regime.regime in (RegimeType.RANGING, RegimeType.TRANSITIONAL)

    def test_calculate_adx(self) -> None:
        """Test ADX calculation."""
        detector = RegimeDetector()

        data = create_trending_data(30, direction="up", strength=3.0)

        adx = detector._calculate_adx(data)

        # ADX should be a positive value
        assert adx >= 0
        assert adx <= 100

    def test_calculate_volatility(self) -> None:
        """Test volatility calculation."""
        detector = RegimeDetector()

        data = create_ranging_data(30)

        volatility = detector._calculate_volatility(data)

        # Volatility should be non-negative
        assert volatility >= 0

    def test_classify_volatility(self) -> None:
        """Test volatility classification."""
        detector = RegimeDetector()

        data = create_ranging_data(30)

        # Test with different volatility levels
        assert detector._classify_volatility(0.5, data) in ["low", "medium", "high"]
        assert detector._classify_volatility(5.0, data) in ["low", "medium", "high"]

    def test_check_volume_confirmation(self) -> None:
        """Test volume confirmation check."""
        detector = RegimeDetector()

        # High recent volume: recent avg (1500) > overall avg (1000) * 1.1
        # Overall avg = (500*5 + 1500*5) / 10 = 1000
        # Recent avg = 1500 (last 5), threshold = 1100, so 1500 > 1100 = True
        high_volume = [500.0] * 5 + [1500.0] * 5
        result = detector._check_volume_confirmation(high_volume)
        assert bool(result) is True

        # Low recent volume: recent avg (600) < overall avg (1000) * 1.1
        # Overall avg = (1400*5 + 600*5) / 10 = 1000
        # Recent avg = 600 (last 5), threshold = 1100, so 600 > 1100 = False
        low_volume = [1400.0] * 5 + [600.0] * 5
        result = detector._check_volume_confirmation(low_volume)
        assert bool(result) is False

    def test_calculate_confidence_trending(self) -> None:
        """Test confidence calculation for trending."""
        detector = RegimeDetector()

        confidence = detector._calculate_confidence(
            RegimeType.TRENDING_UP,
            30.0,  # High ADX
            2.0,  # Normal volatility
        )

        # High ADX should give high confidence
        assert confidence > 50

    def test_calculate_confidence_ranging(self) -> None:
        """Test confidence calculation for ranging."""
        detector = RegimeDetector()

        confidence = detector._calculate_confidence(
            RegimeType.RANGING,
            15.0,  # Low ADX
            1.0,  # Low volatility
        )

        # Low ADX should give decent confidence for ranging
        assert confidence > 0

    def test_calculate_transition_probability(self) -> None:
        """Test transition probability calculation."""
        detector = RegimeDetector()

        # Add some history
        for i in range(15):
            adx = 30.0 - i  # Decreasing ADX
            detector._state.update(RegimeType.TRENDING_UP, adx, 2.0)

        prob = detector._calculate_transition_probability()

        # Decreasing ADX from trending should suggest transition
        assert prob >= 0

    def test_generate_description(self) -> None:
        """Test description generation."""
        detector = RegimeDetector()

        desc = detector._generate_description(
            RegimeType.TRENDING_UP,
            30.0,
            "medium",
            True,
        )

        assert "Trending Up" in desc
        assert "Volume confirmed" in desc

    def test_reset_state(self) -> None:
        """Test state reset."""
        detector = RegimeDetector()

        # Add some history
        detector._state.update(RegimeType.TRENDING_UP, 30.0, 2.0)

        detector.reset_state()

        assert detector._state.current_regime == RegimeType.UNKNOWN
        assert len(detector._state.regime_history) == 0

    def test_wilder_smooth(self) -> None:
        """Test Wilder's smoothing."""
        detector = RegimeDetector()

        values = [10.0, 11.0, 12.0, 13.0, 14.0]

        smoothed = detector._wilder_smooth(values, 5)

        # Smoothed value should be reasonable
        assert smoothed > 0
