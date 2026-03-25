"""Tests for swing pivot detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from market_analysis.structure.swing_pivot import (
    PivotType,
    SwingPivot,
    SwingPivotDetector,
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
    open_price: float | None = None,
    close: float | None = None,
) -> MockOHLCVData:
    """Create mock OHLCV data."""
    return MockOHLCVData(
        timestamp=timestamp,
        open_price=open_price if open_price else (high + low) / 2,
        high_price=high,
        low_price=low,
        close_price=close if close else (high + low) / 2,
        volume=1000.0,
    )


def create_uptrend_data(count: int) -> list[MockOHLCVData]:
    """Create data with clear uptrend and swing highs/lows."""
    data = []
    price = 50000.0

    # Pattern: up, pullback (lower low), up higher
    for i in range(count):
        if i % 5 == 0:
            # Swing high
            price *= 1.02
        elif i % 5 == 1:
            # Pullback low
            price *= 0.98
        else:
            price *= 1.005

        data.append(create_ohlcv(i * 3600, price * 1.01, price * 0.99))

    return data


def create_downtrend_data(count: int) -> list[MockOHLCVData]:
    """Create data with clear downtrend and swing highs/lows."""
    data = []
    price = 50000.0

    for i in range(count):
        if i % 5 == 0:
            # Swing low
            price *= 0.98
        elif i % 5 == 1:
            # Rally high
            price *= 1.02
        else:
            price *= 0.995

        data.append(create_ohlcv(i * 3600, price * 1.01, price * 0.99))

    return data


def create_swing_high_data() -> list[MockOHLCVData]:
    """Create data with a clear swing high at index 5.

    Pattern:
    idx 0-4: rising highs (not a swing high)
    idx 5:   highest high (swing high)
    idx 6-9: lower highs (confirms swing high)
    """
    data = []
    highs = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102]
    lows = [98, 100, 102, 104, 106, 108, 106, 104, 102, 100]
    base_price = 50000.0

    for i in range(10):
        price = base_price + highs[i]
        low = base_price + lows[i]
        data.append(create_ohlcv(i * 3600, price, low))

    return data


def create_swing_low_data() -> list[MockOHLCVData]:
    """Create data with a clear swing low at index 5.

    Pattern:
    idx 0-4: falling lows (not a swing low)
    idx 5:   lowest low (swing low)
    idx 6-9: higher lows (confirms swing low)
    """
    data = []
    highs = [110, 108, 106, 104, 102, 100, 102, 104, 106, 108]
    lows = [108, 106, 104, 102, 100, 98, 100, 102, 104, 106]
    base_price = 50000.0

    for i in range(10):
        price = base_price + highs[i]
        low = base_price + lows[i]
        data.append(create_ohlcv(i * 3600, price, low))

    return data


class TestPivotType:
    """Tests for PivotType enum."""

    def test_swing_high_value(self) -> None:
        """Test SWING_HIGH enum value."""
        assert PivotType.SWING_HIGH.value == "swing_high"

    def test_swing_low_value(self) -> None:
        """Test SWING_LOW enum value."""
        assert PivotType.SWING_LOW.value == "swing_low"

    def test_none_value(self) -> None:
        """Test NONE enum value."""
        assert PivotType.NONE.value == "none"


class TestSwingPivot:
    """Tests for SwingPivot dataclass."""

    def test_creation_swing_high(self) -> None:
        """Test creating a swing high pivot."""
        pivot = SwingPivot(
            index=5,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_HIGH,
            price=51000.0,
            strength=0.02,
            lookback_bars=5,
            lookahead_bars=5,
        )

        assert pivot.index == 5
        assert pivot.pivot_type == PivotType.SWING_HIGH
        assert pivot.price == 51000.0
        assert pivot.strength == 0.02

    def test_creation_swing_low(self) -> None:
        """Test creating a swing low pivot."""
        pivot = SwingPivot(
            index=3,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_LOW,
            price=49000.0,
            strength=0.015,
        )

        assert pivot.index == 3
        assert pivot.pivot_type == PivotType.SWING_LOW
        assert pivot.price == 49000.0

    def test_invalid_pivot_type(self) -> None:
        """Test that invalid pivot type raises error."""
        with pytest.raises(ValueError):
            SwingPivot(
                index=0,
                timestamp=datetime.now(UTC),
                pivot_type=PivotType.NONE,  # Invalid for SwingPivot
                price=50000.0,
            )

    def test_negative_strength_raises(self) -> None:
        """Test that negative strength raises error."""
        with pytest.raises(ValueError):
            SwingPivot(
                index=0,
                timestamp=datetime.now(UTC),
                pivot_type=PivotType.SWING_HIGH,
                price=50000.0,
                strength=-0.01,
            )


class TestSwingPivotDetector:
    """Tests for SwingPivotDetector."""

    def test_detector_creation(self) -> None:
        """Test creating detector."""
        detector = SwingPivotDetector(window_size=5)
        assert detector.window_size == 5

    def test_custom_parameters(self) -> None:
        """Test creating detector with custom parameters."""
        detector = SwingPivotDetector(
            window_size=10,
            min_window_size=3,
            max_window_size=20,
        )
        assert detector.window_size == 10
        assert detector.min_window_size == 3
        assert detector.max_window_size == 20

    def test_invalid_window_size(self) -> None:
        """Test that invalid window size raises error."""
        with pytest.raises(ValueError):
            SwingPivotDetector(window_size=1)  # Below min

        with pytest.raises(ValueError):
            SwingPivotDetector(window_size=100)  # Above max

    def test_detect_insufficient_data(self) -> None:
        """Test detection with insufficient data."""
        detector = SwingPivotDetector(window_size=5)
        # Need at least 2*window_size + 1 = 11 bars
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(5)]

        result = detector.detect(data)

        assert len(result.pivots) == 0
        assert len(result.swing_highs) == 0
        assert len(result.swing_lows) == 0

    def test_detect_swing_high(self) -> None:
        """Test detecting a swing high."""
        detector = SwingPivotDetector(window_size=3)
        data = create_swing_high_data()

        result = detector.detect(data)

        # Index 3 should be a swing high (higher than 0-2 and 4-6)
        swing_highs = [p for p in result.swing_highs]
        assert len(swing_highs) >= 1

    def test_detect_swing_low(self) -> None:
        """Test detecting a swing low."""
        detector = SwingPivotDetector(window_size=3)
        data = create_swing_low_data()

        result = detector.detect(data)

        # Index 5 should be a swing low (lower than 0-4 and 6-9)
        swing_lows = [p for p in result.swing_lows]
        assert len(swing_lows) >= 1

    def test_detect_uptrend(self) -> None:
        """Test detection on uptrend data."""
        detector = SwingPivotDetector(window_size=3)
        data = create_uptrend_data(20)

        result = detector.detect(data)

        # In a pure uptrend, we detect swing highs
        # (swings are defined by relative peaks, not by trend direction)
        assert len(result.swing_highs) >= 1
        # Pivots count should equal highs + lows
        assert len(result.pivots) == len(result.swing_highs) + len(result.swing_lows)

    def test_detect_downtrend(self) -> None:
        """Test detection on downtrend data."""
        detector = SwingPivotDetector(window_size=3)
        data = create_downtrend_data(20)

        result = detector.detect(data)

        # In a pure downtrend, we detect swing lows
        assert len(result.swing_lows) >= 1

    def test_pivots_sorted_by_index(self) -> None:
        """Test that pivots are sorted by index."""
        detector = SwingPivotDetector(window_size=3)
        data = create_uptrend_data(30)

        result = detector.detect(data)

        if len(result.pivots) >= 2:
            for i in range(len(result.pivots) - 1):
                assert result.pivots[i].index < result.pivots[i + 1].index

    def test_get_last_pivot(self) -> None:
        """Test getting the last pivot."""
        detector = SwingPivotDetector(window_size=3)
        data = create_uptrend_data(20)

        last_pivot = detector.get_last_pivot(data)

        if len(detector.detect(data).pivots) > 0:
            assert last_pivot is not None
            result = detector.detect(data)
            assert last_pivot.index == result.pivots[-1].index

    def test_get_last_pivot_empty(self) -> None:
        """Test getting last pivot when none exist."""
        detector = SwingPivotDetector(window_size=5)
        data = [create_ohlcv(i * 3600, 50100, 49900) for i in range(5)]

        last_pivot = detector.get_last_pivot(data)
        assert last_pivot is None

    def test_get_pivots_since(self) -> None:
        """Test getting pivots since a given index."""
        detector = SwingPivotDetector(window_size=3)
        data = create_uptrend_data(30)

        result = detector.detect(data)
        if len(result.pivots) > 0:
            since_index = result.pivots[0].index + 2
            filtered = detector.get_pivots_since(data, since_index)

            for pivot in filtered.pivots:
                assert pivot.index >= since_index

    def test_validate(self) -> None:
        """Test validation of sufficient data."""
        detector = SwingPivotDetector(window_size=5)

        insufficient = [create_ohlcv(i * 3600, 50100, 49900) for i in range(5)]
        assert detector.validate(insufficient) is False

        sufficient = [create_ohlcv(i * 3600, 50100, 49900) for i in range(15)]
        assert detector.validate(sufficient) is True

    def test_metadata(self) -> None:
        """Test metadata generation."""
        detector = SwingPivotDetector(window_size=7)

        meta = detector.get_metadata()

        assert meta["name"] == "SwingPivotDetector"
        assert meta["parameters"]["window_size"] == 7


class TestSwingPivotDetectionResult:
    """Tests for SwingPivotDetectionResult."""

    def test_result_sorted_on_creation(self) -> None:
        """Test that pivots are sorted when result is created."""
        pivot1 = SwingPivot(
            index=5,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_HIGH,
            price=50500.0,
        )
        pivot2 = SwingPivot(
            index=3,
            timestamp=datetime.now(UTC),
            pivot_type=PivotType.SWING_LOW,
            price=49500.0,
        )

        result = SwingPivotDetectionResult(
            pivots=[pivot1, pivot2],  # Unsorted
            swing_highs=[pivot1],
            swing_lows=[pivot2],
            data_length=10,
            window_size=5,
        )

        # Should be sorted by index
        assert result.pivots[0].index == 3
        assert result.pivots[1].index == 5

    def test_data_length_tracked(self) -> None:
        """Test that data length is tracked."""
        result = SwingPivotDetectionResult(
            pivots=[],
            swing_highs=[],
            swing_lows=[],
            data_length=50,
            window_size=5,
        )

        assert result.data_length == 50


class TestAccuracyOnSyntheticData:
    """Accuracy tests on synthetic fixtures with known patterns."""

    def test_swing_high_detection(self) -> None:
        """Test that swing high pattern is detected."""
        detector = SwingPivotDetector(window_size=3)

        # Create swing high pattern - peak at index 5
        data = create_swing_high_data()
        result = detector.detect(data)

        # Should detect at least one swing high in the peak pattern
        assert len(result.swing_highs) >= 1, "Should detect swing high in peak pattern"

    def test_swing_low_detection(self) -> None:
        """Test that swing low pattern is detected."""
        detector = SwingPivotDetector(window_size=3)

        # Create swing low pattern - trough at index 5
        data = create_swing_low_data()
        result = detector.detect(data)

        # Should detect at least one swing low in the trough pattern
        assert len(result.swing_lows) >= 1, "Should detect swing low in trough pattern"

    def test_no_false_pivot_on_flat(self) -> None:
        """Test that flat data doesn't produce many false pivots."""
        detector = SwingPivotDetector(window_size=3)

        # Flat data with small noise
        base = 50000.0
        data = []
        for i in range(30):
            noise = (i % 3 - 1) * 10  # Small noise: -10, 0, +10
            high = base + 50 + noise
            low = base - 50 + noise
            data.append(create_ohlcv(i * 3600, high, low))

        result = detector.detect(data)

        # On truly flat data, pivots should be minimal
        # Allow up to 30% false positive rate
        max_allowed_pivots = len(data) * 0.3
        assert len(result.pivots) <= max_allowed_pivots
