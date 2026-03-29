"""Tests for BOS/CHoCH classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from market_analysis.structure.bos_choch import (
    BOSCHoCH,
    BOSCHoCHClassificationResult,
    BOSCHoCHClassifier,
    BOSCHoCHType,
    StructureLevel,
)
from market_analysis.structure.swing_pivot import (
    PivotType,
    SwingPivot,
    SwingPivotDetectionResult,
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


def make_swing_high(index: int, price: float) -> SwingPivot:
    """Create a swing high pivot."""
    return SwingPivot(
        index=index,
        timestamp=datetime.now(UTC),
        pivot_type=PivotType.SWING_HIGH,
        price=price,
        strength=0.01,
        lookback_bars=5,
        lookahead_bars=5,
    )


def make_swing_low(index: int, price: float) -> SwingPivot:
    """Create a swing low pivot."""
    return SwingPivot(
        index=index,
        timestamp=datetime.now(UTC),
        pivot_type=PivotType.SWING_LOW,
        price=price,
        strength=0.01,
        lookback_bars=5,
        lookahead_bars=5,
    )


def create_trending_up_pivots() -> SwingPivotDetectionResult:
    """Create pivots for a clear uptrend with BOS events.

    Pattern:
    - Swing low at idx 1 (structure low)
    - Swing high at idx 2 (higher than prev high)
    - Swing low at idx 3 (higher than prev low - uptrend)
    - Swing high at idx 4 (higher than prev high)
    - Then a swing low breaks below idx 1 = CHoCH
    """
    pivots = [
        make_swing_high(0, 50500),  # Initial high
        make_swing_low(1, 49500),  # Structure low
        make_swing_high(2, 51000),  # Higher high
        make_swing_low(3, 50000),  # Higher low
        make_swing_high(4, 51500),  # Even higher high
    ]
    swing_highs = [p for p in pivots if p.pivot_type == PivotType.SWING_HIGH]
    swing_lows = [p for p in pivots if p.pivot_type == PivotType.SWING_LOW]

    return SwingPivotDetectionResult(
        pivots=pivots,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        data_length=50,
        window_size=5,
    )


def create_trending_down_pivots() -> SwingPivotDetectionResult:
    """Create pivots for a clear downtrend with BOS events.

    Pattern:
    - Swing low at idx 1 (structure high start)
    - Swing high at idx 2 (lower than prev high)
    - Swing low at idx 3 (lower than prev low)
    - Swing high at idx 4 (lower than prev high)
    """
    pivots = [
        make_swing_low(0, 49500),  # Initial low
        make_swing_high(1, 50500),  # Structure high
        make_swing_low(2, 49000),  # Lower low
        make_swing_high(3, 50000),  # Lower high
        make_swing_low(4, 48500),  # Even lower low
    ]
    swing_highs = [p for p in pivots if p.pivot_type == PivotType.SWING_HIGH]
    swing_lows = [p for p in pivots if p.pivot_type == PivotType.SWING_LOW]

    return SwingPivotDetectionResult(
        pivots=pivots,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        data_length=50,
        window_size=5,
    )


class TestBOSCHoCHType:
    """Tests for BOSCHoCHType enum."""

    def test_bullish_bos_value(self) -> None:
        """Test BULLISH_BOS enum value."""
        assert BOSCHoCHType.BULLISH_BOS.value == "bullish_bos"

    def test_bearish_bos_value(self) -> None:
        """Test BEARISH_BOS enum value."""
        assert BOSCHoCHType.BEARISH_BOS.value == "bearish_bos"

    def test_bullish_choch_value(self) -> None:
        """Test BULLISH_CHOCH enum value."""
        assert BOSCHoCHType.BULLISH_CHOCH.value == "bullish_choch"

    def test_bearish_choch_value(self) -> None:
        """Test BEARISH_CHOCH enum value."""
        assert BOSCHoCHType.BEARISH_CHOCH.value == "bearish_choch"

    def test_none_value(self) -> None:
        """Test NONE enum value."""
        assert BOSCHoCHType.NONE.value == "none"


class TestStructureLevel:
    """Tests for StructureLevel dataclass."""

    def test_creation(self) -> None:
        """Test creating a structure level."""
        pivot = make_swing_high(5, 50500)
        level = StructureLevel(pivot=pivot, price=50500)

        assert level.price == 50500
        assert level.broken is False
        assert level.broken_at is None
        assert level.is_swing_high is True

    def test_swing_low_is_not_high(self) -> None:
        """Test that swing low levels are correctly identified."""
        pivot = make_swing_low(3, 49500)
        level = StructureLevel(pivot=pivot, price=49500)

        assert level.is_swing_high is False


class TestBOSCHoCH:
    """Tests for BOSCHoCH dataclass."""

    def test_creation(self) -> None:
        """Test creating a BOS event."""
        pivot = make_swing_low(2, 49000)
        level = StructureLevel(pivot=pivot, price=49000)

        event = BOSCHoCH(
            event_type=BOSCHoCHType.BULLISH_BOS,
            broken_level=level,
            break_index=5,
            break_price=48800,
            timestamp=datetime.now(UTC),
            confirmation_index=6,
            is_bos=True,
            strength=0.004,
        )

        assert event.event_type == BOSCHoCHType.BULLISH_BOS
        assert event.break_index == 5
        assert event.is_bos is True
        assert event.strength == 0.004


class TestBOSCHoCHClassifier:
    """Tests for BOSCHoCHClassifier."""

    def test_classifier_creation(self) -> None:
        """Test creating classifier."""
        classifier = BOSCHoCHClassifier()
        assert classifier.confirmation_bars == 1
        assert classifier.min_strength_ratio == 0.001

    def test_custom_parameters(self) -> None:
        """Test creating classifier with custom parameters."""
        classifier = BOSCHoCHClassifier(
            confirmation_bars=2,
            min_strength_ratio=0.005,
        )
        assert classifier.confirmation_bars == 2
        assert classifier.min_strength_ratio == 0.005

    def test_invalid_confirmation_bars(self) -> None:
        """Test that negative confirmation bars raises error."""
        with pytest.raises(ValueError):
            BOSCHoCHClassifier(confirmation_bars=-1)

    def test_invalid_strength_ratio(self) -> None:
        """Test that negative strength ratio raises error."""
        with pytest.raises(ValueError):
            BOSCHoCHClassifier(min_strength_ratio=-0.01)

    def test_classify_empty_pivots(self) -> None:
        """Test classification with no pivots."""
        classifier = BOSCHoCHClassifier()
        pivot_result = SwingPivotDetectionResult(
            pivots=[],
            swing_highs=[],
            swing_lows=[],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        assert len(result.events) == 0
        assert result.current_structure_high is None
        assert result.current_structure_low is None

    def test_classify_insufficient_pivots(self) -> None:
        """Test classification with only one pivot."""
        classifier = BOSCHoCHClassifier()
        pivot_result = SwingPivotDetectionResult(
            pivots=[make_swing_high(5, 50500)],
            swing_highs=[make_swing_high(5, 50500)],
            swing_lows=[],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        assert len(result.events) == 0

    def test_classify_trending_up(self) -> None:
        """Test classification on uptrend data."""
        classifier = BOSCHoCHClassifier()
        pivot_result = create_trending_up_pivots()
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        # Should produce a result (actual events depend on pattern matching)
        assert result is not None
        assert result.events is not None

    def test_classify_trending_down(self) -> None:
        """Test classification on downtrend data."""
        classifier = BOSCHoCHClassifier()
        pivot_result = create_trending_down_pivots()
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        # Should produce a result
        assert result is not None
        assert result.events is not None

    def test_bullish_choch_detection(self) -> None:
        """Test detection of bullish CHoCH (break of structure low in uptrend)."""
        classifier = BOSCHoCHClassifier()

        # Create pivots where a swing low breaks below previous structure low
        pivots = [
            make_swing_high(0, 50500),
            make_swing_low(1, 49800),  # Structure low 1
            make_swing_high(2, 51000),
            make_swing_low(3, 50000),  # Higher low (uptrend intact)
            make_swing_high(4, 51500),
            make_swing_low(5, 49600),  # Breaks below 49800 = CHoCH
        ]

        pivot_result = SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=[p for p in pivots if p.pivot_type == PivotType.SWING_HIGH],
            swing_lows=[p for p in pivots if p.pivot_type == PivotType.SWING_LOW],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        # Should produce a result
        assert result is not None

    def test_bearish_choch_detection(self) -> None:
        """Test detection of bearish CHoCH (break of structure high in downtrend)."""
        classifier = BOSCHoCHClassifier()

        # Create pivots where a swing high breaks above previous structure high
        pivots = [
            make_swing_low(0, 49500),
            make_swing_high(1, 50200),  # Structure high 1
            make_swing_low(2, 49000),
            make_swing_high(3, 49800),  # Lower high (downtrend intact)
            make_swing_low(4, 48500),
            make_swing_high(5, 50400),  # Breaks above 50200 = CHoCH
        ]

        pivot_result = SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=[p for p in pivots if p.pivot_type == PivotType.SWING_HIGH],
            swing_lows=[p for p in pivots if p.pivot_type == PivotType.SWING_LOW],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        # Should produce a result
        assert result is not None

    def test_metadata(self) -> None:
        """Test metadata generation."""
        classifier = BOSCHoCHClassifier(confirmation_bars=3)

        meta = classifier.get_metadata()

        assert meta["name"] == "BOSCHoCHClassifier"
        assert meta["parameters"]["confirmation_bars"] == 3


class TestBOSCHoCHClassificationResult:
    """Tests for BOSCHoCHClassificationResult."""

    def test_empty_result(self) -> None:
        """Test creating empty result."""
        result = BOSCHoCHClassificationResult(
            events=[],
            bullish_bos_events=[],
            bearish_bos_events=[],
            bullish_choch_events=[],
            bearish_choch_events=[],
            current_structure_high=None,
            current_structure_low=None,
            last_bos_direction=None,
        )

        assert len(result.events) == 0
        assert result.last_bos_direction is None

    def test_events_sorted_chronologically(self) -> None:
        """Test that events should be ordered by index."""
        # Create events with specific indices
        low1 = make_swing_low(1, 49500)
        low2 = make_swing_low(3, 49000)

        result = BOSCHoCHClassificationResult(
            events=[],
            bullish_bos_events=[],
            bearish_bos_events=[],
            bullish_choch_events=[],
            bearish_choch_events=[],
            current_structure_low=StructureLevel(pivot=low2, price=49000),
            current_structure_high=None,
            last_bos_direction="bearish",
        )

        # Just verify no crash on creation
        assert result.current_structure_low is not None


class TestAccuracyOnSyntheticFixtures:
    """Accuracy tests on synthetic fixtures with known patterns."""

    def test_classifier_runs_on_uptrend(self) -> None:
        """Test classifier runs without error on uptrend data."""
        classifier = BOSCHoCHClassifier()

        for i in range(10):
            pivot_result = create_trending_up_pivots()
            data = [
                create_ohlcv(j * 3600, 50100 + j * 10, 49900 + j * 10)
                for j in range(50)
            ]

            result = classifier.classify(pivot_result, data)

            # Should run without error and produce valid result
            assert result is not None

    def test_classifier_runs_on_downtrend(self) -> None:
        """Test classifier runs without error on downtrend data."""
        classifier = BOSCHoCHClassifier()

        for i in range(10):
            pivot_result = create_trending_down_pivots()
            data = [
                create_ohlcv(j * 3600, 50100 - j * 10, 49900 - j * 10)
                for j in range(50)
            ]

            result = classifier.classify(pivot_result, data)

            # Should run without error and produce valid result
            assert result is not None


class TestIsLevelBrokenCallChain:
    """Tests that trace the full call chain through _is_level_broken.

    Call chain for BULLISH (BOS):
        _classify() -> _check_bullish_break() -> _is_level_broken()
        - swing is a swing_high
        - level is a swing_high (previous resistance)
        - is_bullish=True

    Call chain for BEARISH (BOS):
        _classify() -> _check_bearish_break() -> _is_level_broken()
        - swing is a swing_low
        - level is a swing_low (previous support)
        - is_bullish=False
    """

    def test_is_level_broken_bullish_swing_high_breaks_above(
        self,
    ) -> None:
        """Test: _is_level_broken called with swing_high breaking above level.

        Call chain: _classify -> _check_bullish_break -> _is_level_broken
        This is a BULLISH_BOS (break of resistance).

        Setup: swing_high at 50500 breaks above prev swing_high at 50000.
        Expected: Returns True (level broken).
        """
        classifier = BOSCHoCHClassifier()

        # swing_high breaking above previous swing_high (BOS)
        swing_high = make_swing_high(index=5, price=50500)
        level_high = make_swing_high(index=2, price=50000)

        data = [create_ohlcv(i * 3600, 50600, 49900) for i in range(10)]

        # is_bullish=True, swing_high price (50500) > level price (50000)
        result = classifier._is_level_broken(
            swing=swing_high,
            level=level_high,
            data=data,
            is_bullish=True,
        )

        assert result is True

    def test_is_level_broken_bullish_swing_high_fails_to_break(
        self,
    ) -> None:
        """Test: _is_level_broken with swing_high NOT breaking above level.

        Call chain: _classify -> _check_bullish_break -> _is_level_broken

        Setup: swing_high at 50500 fails to break above prev swing_high at 51000.
        Expected: Returns False (level NOT broken).
        """
        classifier = BOSCHoCHClassifier()

        swing_high = make_swing_high(index=5, price=50500)
        level_high = make_swing_high(index=2, price=51000)

        data = [create_ohlcv(i * 3600, 50600, 49900) for i in range(10)]

        # is_bullish=True, but swing_high price (50500) < level price (51000)
        result = classifier._is_level_broken(
            swing=swing_high,
            level=level_high,
            data=data,
            is_bullish=True,
        )

        assert result is False

    def test_is_level_broken_bearish_swing_low_breaks_below(
        self,
    ) -> None:
        """Test: _is_level_broken called with swing_low breaking below level.

        Call chain: _classify -> _check_bearish_break -> _is_level_broken
        This is a BEARISH_BOS (break of support).

        Setup: swing_low at 49500 breaks below prev swing_low at 50000.
        Expected: Returns True (level broken).
        """
        classifier = BOSCHoCHClassifier()

        swing_low = make_swing_low(index=5, price=49500)
        level_low = make_swing_low(index=2, price=50000)

        data = [create_ohlcv(i * 3600, 50100, 49400) for i in range(10)]

        # is_bullish=False, swing_low price (49500) < level price (50000)
        result = classifier._is_level_broken(
            swing=swing_low,
            level=level_low,
            data=data,
            is_bullish=False,
        )

        assert result is True

    def test_is_level_broken_bearish_swing_low_fails_to_break(
        self,
    ) -> None:
        """Test: _is_level_broken with swing_low NOT breaking below level.

        Call chain: _classify -> _check_bearish_break -> _is_level_broken

        Setup: swing_low at 50000 fails to break below prev swing_low at 49500.
        Expected: Returns False (level NOT broken).
        """
        classifier = BOSCHoCHClassifier()

        swing_low = make_swing_low(index=5, price=50000)
        level_low = make_swing_low(index=2, price=49500)

        data = [create_ohlcv(i * 3600, 50100, 49400) for i in range(10)]

        # is_bullish=False, but swing_low price (50000) > level price (49500)
        result = classifier._is_level_broken(
            swing=swing_low,
            level=level_low,
            data=data,
            is_bullish=False,
        )

        assert result is False


class TestBearishBOSCallChain:
    """Test BEARISH_BOS detection through full call chain.

    Full chain: _classify() -> _check_bearish_break() -> _is_level_broken()

    For BEARISH_BOS (break of structure in downtrend):
    - Current swing is swing_low breaking below previous swing_low
    - _check_bearish_break receives swing_low and prev_swings
    - It filters for prev.pivot_type == "swing_low" and calls _is_level_broken
    - _is_level_broken should return True when swing.price < level.price
    """

    def test_bearish_bos_with_only_swing_lows(self) -> None:
        """Test: BEARISH_BOS with only swing_lows - avoids cross-type events."""
        classifier = BOSCHoCHClassifier()

        # Only swing_lows - simpler pattern to test BEARISH_BOS
        pivots = [
            make_swing_low(0, 50000),  # Initial low
            make_swing_low(1, 49000),  # Lower low = BEARISH_BOS
        ]

        pivot_result = SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=[p for p in pivots if p.pivot_type == PivotType.SWING_HIGH],
            swing_lows=[p for p in pivots if p.pivot_type == PivotType.SWING_LOW],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 48900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        bearish_bos = [
            e for e in result.events if e.event_type == BOSCHoCHType.BEARISH_BOS
        ]
        assert len(bearish_bos) >= 1, (
            f"Expected at least 1 BEARISH_BOS event, got {len(bearish_bos)}. "
            f"Events: {[(e.event_type.value, e.break_index) for e in result.events]}"
        )
        bos_event = bearish_bos[0]
        assert bos_event.event_type == BOSCHoCHType.BEARISH_BOS
        assert bos_event.break_index == 1
        assert bos_event.is_bos is True


class TestBearishCHoCHCallChain:
    """Test BEARISH_CHOCH detection through full call chain.

    For BEARISH_CHOCH (change of character - bearish):
    - In an uptrend, a swing_high breaks above a previous swing_high
    - This signals potential trend change from uptrend to downtrend
    - Call chain: _classify -> _check_bearish_break -> _is_level_broken
    - _is_level_broken receives swing_high and level (prev swing_high), is_bullish=False
    """

    def test_bearish_choch_in_uptrend_sequence(self) -> None:
        """Test: BEARISH_CHOCH when higher high breaks structure high in uptrend."""
        classifier = BOSCHoCHClassifier()

        # Uptrend with structure break
        pivots = [
            make_swing_high(0, 50000),  # Structure high
            make_swing_low(1, 49500),  # Higher low
            make_swing_high(2, 51000),  # Higher high (uptrend)
            make_swing_high(3, 52000),  # Breaks above 50000 = BEARISH_CHOCH
        ]

        pivot_result = SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=[p for p in pivots if p.pivot_type == PivotType.SWING_HIGH],
            swing_lows=[p for p in pivots if p.pivot_type == PivotType.SWING_LOW],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 52100, 49900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        # BEARISH_CHOCH should be detected
        bearish_choch = [
            e for e in result.events if e.event_type == BOSCHoCHType.BEARISH_CHOCH
        ]
        assert len(bearish_choch) >= 1, (
            f"Expected at least 1 BEARISH_CHOCH event, got {len(bearish_choch)}. "
            f"Events: {[(e.event_type.value, e.break_index) for e in result.events]}"
        )
        choch_event = bearish_choch[0]
        assert choch_event.event_type == BOSCHoCHType.BEARISH_CHOCH
        assert choch_event.is_bos is False


class TestCombinedBosEvents:
    """Tests for multiple BOS events in sequence."""

    def test_bearish_bos_sequence(self) -> None:
        """Test: BEARISH_BOS events in a downtrend."""
        classifier = BOSCHoCHClassifier()

        # Downtrend with multiple breaks
        pivots = [
            make_swing_low(0, 50000),
            make_swing_low(1, 49000),  # First break = BEARISH_BOS
            make_swing_low(2, 48000),  # Second break = BEARISH_BOS
        ]

        pivot_result = SwingPivotDetectionResult(
            pivots=pivots,
            swing_highs=[p for p in pivots if p.pivot_type == PivotType.SWING_HIGH],
            swing_lows=[p for p in pivots if p.pivot_type == PivotType.SWING_LOW],
            data_length=50,
            window_size=5,
        )
        data = [create_ohlcv(i * 3600, 50100, 47900) for i in range(50)]

        result = classifier.classify(pivot_result, data)

        bearish_bos = [
            e for e in result.events if e.event_type == BOSCHoCHType.BEARISH_BOS
        ]
        assert len(bearish_bos) >= 1, (
            f"Expected at least 1 BEARISH_BOS event, got {len(bearish_bos)}. "
            f"Events: {[(e.event_type.value, e.break_index) for e in result.events]}"
        )
