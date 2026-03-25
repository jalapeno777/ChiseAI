"""Tests for main StructureDetector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from market_analysis.regime import (
    RegimeClassification,
    UnifiedRegime,
    VolatilityRegime,
)
from market_analysis.structure.bos_choch import BOSCHoCHType
from market_analysis.structure.structure_detector import (
    StructureDetectionResult,
    StructureDetector,
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


def create_ohlcv(
    timestamp: int,
    high: float,
    low: float,
) -> MockOHLCVData:
    """Create mock OHLCV data."""
    return MockOHLCVData(
        timestamp=timestamp,
        open_price=(high + low) / 2,
        high_price=high,
        low_price=low,
        close_price=(high + low) / 2,
        volume=1000.0,
    )


def create_trending_up_data(count: int) -> list[MockOHLCVData]:
    """Create uptrend data."""
    data = []
    price = 50000.0
    for i in range(count):
        price *= 1.001  # Steady uptrend
        data.append(create_ohlcv(i * 3600, price * 1.01, price * 0.99))
    return data


def create_ranging_data(count: int) -> list[MockOHLCVData]:
    """Create ranging data."""
    data = []
    for i in range(count):
        price = 50000 + (i % 10 - 5) * 100  # Oscillate
        data.append(create_ohlcv(i * 3600, price + 100, price - 100))
    return data


def create_uptrend_with_swings(count: int) -> list[MockOHLCVData]:
    """Create uptrend data with clear swing highs and lows."""
    data = []
    price = 50000.0
    for i in range(count):
        # Create a pattern with ups and downs but overall uptrend
        cycle = i % 10
        if cycle < 5:
            # Up phase
            price *= 1.002
        else:
            # Pullback phase
            price *= 0.998
        data.append(create_ohlcv(i * 3600, price * 1.01, price * 0.99))
    return data


def create_trending_regime() -> RegimeClassification:
    """Create a trending regime classification."""
    return RegimeClassification(
        regime=UnifiedRegime.TRENDING,
        confidence=0.85,
        adx_value=35.0,
        volatility_regime=VolatilityRegime.MEDIUM,
        trend_direction="up",
        markov_trending=True,
        markov_confidence=0.8,
        volatility_score=2.5,
        description="Strong uptrend",
    )


def create_ranging_regime() -> RegimeClassification:
    """Create a ranging regime classification."""
    return RegimeClassification(
        regime=UnifiedRegime.RANGING,
        confidence=0.75,
        adx_value=15.0,
        volatility_regime=VolatilityRegime.MEDIUM,
        trend_direction="neutral",
        markov_trending=False,
        markov_confidence=0.6,
        volatility_score=1.5,
        description="Ranging market",
    )


class TestStructureDetector:
    """Tests for StructureDetector."""

    def test_detector_creation(self) -> None:
        """Test creating detector."""
        detector = StructureDetector()
        assert detector.window_size == 5
        assert detector.require_trending is True

    def test_custom_parameters(self) -> None:
        """Test creating detector with custom parameters."""
        detector = StructureDetector(
            window_size=7,
            confirmation_bars=2,
            min_strength_ratio=0.005,
            require_trending=False,
        )
        assert detector.window_size == 7
        assert detector.confirmation_bars == 2
        assert detector.min_strength_ratio == 0.005
        assert detector.require_trending is False

    def test_detect_structure_basic(self) -> None:
        """Test basic structure detection."""
        detector = StructureDetector()
        # Use data with actual swing patterns - not pure monotonic
        data = create_uptrend_with_swings(30)

        result = detector.detect_structure(data)

        assert result is not None
        assert result.pivots is not None
        assert result.bos_choch is not None
        # is_trending depends on whether regime info is available
        assert result.confirmed is True

    def test_detect_with_trending_regime(self) -> None:
        """Test detection with trending regime."""
        detector = StructureDetector(require_trending=True)
        data = create_trending_up_data(30)
        regime = create_trending_regime()

        result = detector.detect_structure(data, regime=regime)

        assert result.is_trending is True
        assert result.regime is not None
        assert result.regime.regime == UnifiedRegime.TRENDING

    def test_detect_with_ranging_regime(self) -> None:
        """Test detection with ranging regime (should suppress BOS/CHoCH)."""
        detector = StructureDetector(require_trending=True)
        data = create_trending_up_data(30)
        regime = create_ranging_regime()

        result = detector.detect_structure(data, regime=regime)

        # BOS/CHoCH should be empty when not trending
        assert result.is_trending is False
        assert len(result.bos_choch.events) == 0

    def test_detect_without_regime(self) -> None:
        """Test detection without regime (should use require_trending setting)."""
        detector = StructureDetector(require_trending=False)
        data = create_trending_up_data(30)

        result = detector.detect_structure(data)

        # Without regime, should use require_trending setting
        assert result.is_trending is True
        assert result.regime is None

    def test_validate_insufficient_data(self) -> None:
        """Test validation with insufficient data."""
        detector = StructureDetector(window_size=5)
        # Need at least 2*window_size + 1 = 11 bars
        data = create_trending_up_data(5)

        assert detector.validate(data) is False

    def test_validate_sufficient_data(self) -> None:
        """Test validation with sufficient data."""
        detector = StructureDetector(window_size=5)
        data = create_trending_up_data(20)

        assert detector.validate(data) is True

    def test_metadata(self) -> None:
        """Test metadata generation."""
        detector = StructureDetector(window_size=7)

        meta = detector.get_metadata()

        assert meta["name"] == "StructureDetector"
        assert meta["parameters"]["window_size"] == 7
        assert meta["parameters"]["require_trending"] is True

    def test_result_timestamp(self) -> None:
        """Test that result has timestamp."""
        detector = StructureDetector()
        data = create_trending_up_data(20)

        result = detector.detect_structure(data)

        assert result.timestamp is not None

    def test_current_trend_from_regime(self) -> None:
        """Test trend determination from regime."""
        detector = StructureDetector()
        data = create_trending_up_data(20)

        regime_up = create_trending_regime()
        regime_up.trend_direction = "up"
        result = detector.detect_structure(data, regime=regime_up)
        assert result.current_trend == "up"

        regime_down = create_trending_regime()
        regime_down.trend_direction = "down"
        result = detector.detect_structure(data, regime=regime_down)
        assert result.current_trend == "down"

    def test_confirmed_only_true(self) -> None:
        """Test that confirmed flag is always True."""
        detector = StructureDetector()
        data = create_trending_up_data(30)

        result = detector.detect_structure(data)

        assert result.confirmed is True


class TestStructureDetectionResult:
    """Tests for StructureDetectionResult."""

    def test_last_bos_property(self) -> None:
        """Test last_bos property."""
        from market_analysis.structure.bos_choch import (
            BOSCHoCH,
            BOSCHoCHType,
            StructureLevel,
        )
        from market_analysis.structure.swing_pivot import (
            PivotType,
            SwingPivot,
        )

        # Create mock pivots
        low_pivot = SwingPivot(
            index=2,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_LOW,
            price=49000,
        )
        level = StructureLevel(pivot=low_pivot, price=49000)

        bos = BOSCHoCH(
            event_type=BOSCHoCHType.BULLISH_BOS,
            broken_level=level,
            break_index=5,
            break_price=48800,
            timestamp=datetime.now(UTC),
            confirmation_index=6,
            is_bos=True,
            strength=0.004,
        )

        from market_analysis.structure.bos_choch import BOSCHoCHClassificationResult

        result = StructureDetectionResult(
            pivots=None,
            bos_choch=BOSCHoCHClassificationResult(
                events=[bos],
                bullish_bos_events=[bos],
                bearish_bos_events=[],
                bullish_choch_events=[],
                bearish_choch_events=[],
                current_structure_low=level,
                current_structure_high=None,
                last_bos_direction="bullish",
            ),
            regime=None,
            is_trending=True,
            current_trend="up",
            structure_level=level,
            timestamp=datetime.now(UTC),
        )

        assert result.last_bos is not None
        assert result.last_bos.event_type == BOSCHoCHType.BULLISH_BOS

    def test_last_choch_property(self) -> None:
        """Test last_choch property."""
        from market_analysis.structure.bos_choch import (
            BOSCHoCH,
            BOSCHoCHType,
            StructureLevel,
        )
        from market_analysis.structure.swing_pivot import (
            PivotType,
            SwingPivot,
        )

        low_pivot = SwingPivot(
            index=2,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_LOW,
            price=49000,
        )
        level = StructureLevel(pivot=low_pivot, price=49000)

        chch = BOSCHoCH(
            event_type=BOSCHoCHType.BULLISH_CHOCH,
            broken_level=level,
            break_index=5,
            break_price=48600,
            timestamp=datetime.now(UTC),
            confirmation_index=6,
            is_bos=False,
            strength=0.008,
        )

        from market_analysis.structure.bos_choch import BOSCHoCHClassificationResult

        result = StructureDetectionResult(
            pivots=None,
            bos_choch=BOSCHoCHClassificationResult(
                events=[chch],
                bullish_bos_events=[],
                bearish_bos_events=[],
                bullish_choch_events=[chch],
                bearish_choch_events=[],
                current_structure_low=level,
                current_structure_high=None,
                last_bos_direction=None,
            ),
            regime=None,
            is_trending=True,
            current_trend="up",
            structure_level=level,
            timestamp=datetime.now(UTC),
        )

        assert result.last_choch is not None
        assert result.last_choch.event_type == BOSCHoCHType.BULLISH_CHOCH

    def test_last_bos_none_when_no_bos(self) -> None:
        """Test last_bos is None when no BOS events."""
        from market_analysis.structure.bos_choch import BOSCHoCHClassificationResult

        result = StructureDetectionResult(
            pivots=None,
            bos_choch=BOSCHoCHClassificationResult(
                events=[],
                bullish_bos_events=[],
                bearish_bos_events=[],
                bullish_choch_events=[],
                bearish_choch_events=[],
                current_structure_low=None,
                current_structure_high=None,
                last_bos_direction=None,
            ),
            regime=None,
            is_trending=True,
            current_trend="up",
            structure_level=None,
            timestamp=datetime.now(UTC),
        )

        assert result.last_bos is None


class TestRegimeGating:
    """Tests for regime gating functionality."""

    def test_trending_regime_enables_structure(self) -> None:
        """Test that TRENDING regime enables structure detection."""
        detector = StructureDetector(require_trending=True)
        data = create_trending_up_data(30)
        regime = create_trending_regime()

        result = detector.detect_structure(data, regime=regime)

        assert result.is_trending is True

    def test_ranging_regime_disables_structure(self) -> None:
        """Test that RANGING regime disables BOS/CHoCH detection."""
        detector = StructureDetector(require_trending=True)
        data = create_trending_up_data(30)
        regime = create_ranging_regime()

        result = detector.detect_structure(data, regime=regime)

        assert result.is_trending is False
        # BOS/CHoCH should be empty
        assert len(result.bos_choch.events) == 0

    def test_require_trending_false_overrides(self) -> None:
        """Test that require_trending=False overrides regime check."""
        detector = StructureDetector(require_trending=False)
        data = create_ranging_data(30)

        # No regime provided, so is_trending defaults to True
        result = detector.detect_structure(data)

        # Should detect since require_trending=False
        assert result.is_trending is True


class TestAccuracyOnSyntheticData:
    """Accuracy tests on synthetic data."""

    def test_structure_detection_runs(self) -> None:
        """Test that structure detection runs without error on synthetic data."""
        detector = StructureDetector(window_size=3)

        for _ in range(10):
            data = create_uptrend_with_swings(30)
            regime = create_trending_regime()

            result = detector.detect_structure(data, regime=regime)

            # Should run without error
            assert result is not None
            assert result.confirmed is True

    def test_non_repainting_confirmed_bars(self) -> None:
        """Test that only confirmed bars are used (non-repainting)."""
        detector = StructureDetector()
        data = create_uptrend_with_swings(30)
        regime = create_trending_regime()

        result = detector.detect_structure(data, regime=regime)

        # Confirmed should always be True
        assert result.confirmed is True

        # All pivots should have valid indices
        for pivot in result.pivots.pivots:
            assert 0 <= pivot.index < len(data)
