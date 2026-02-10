"""Tests for ATR indicator.

Validates ATR calculation using Wilder's smoothing method.
"""

from __future__ import annotations

import numpy as np
import pytest

from portfolio_risk.stop_loss.atr_indicator import ATR, ATRResult


class TestATRResult:
    """Tests for ATRResult dataclass."""

    def test_atr_result_creation(self):
        """Test ATRResult creation."""
        values = np.array([100.0, 110.0, 120.0])
        result = ATRResult(values=values, current=120.0, period=14)

        assert result.current == 120.0
        assert result.period == 14
        np.testing.assert_array_equal(result.values, values)

    def test_atr_result_current_conversion(self):
        """Test that current is converted to float."""
        values = np.array([100.0, 110.0])
        result = ATRResult(values=values, current=np.int64(110), period=14)

        assert isinstance(result.current, float)
        assert result.current == 110.0


class TestATRBasic:
    """Basic tests for ATR calculator."""

    def test_atr_initialization(self):
        """Test ATR calculator initialization."""
        atr = ATR(period=14)
        assert atr.period == 14

    def test_atr_default_period(self):
        """Test ATR default period."""
        atr = ATR()
        assert atr.period == 14


class TestATRCalculation:
    """Tests for ATR calculation."""

    def create_ohlcv_data(
        self,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ):
        """Create mock OHLCV data."""
        from dataclasses import dataclass

        @dataclass
        class MockOHLCV:
            open_price: float
            high_price: float
            low_price: float
            close_price: float
            volume: float = 1000.0
            timestamp: int = 0

        return [MockOHLCV(o, h, l, c) for o, h, l, c in zip(opens, highs, lows, closes)]

    def test_atr_insufficient_data(self):
        """Test ATR raises error with insufficient data."""
        atr = ATR(period=14)

        # Need at least 15 data points (period + 1)
        data = self.create_ohlcv_data(
            opens=[100.0] * 10,
            highs=[110.0] * 10,
            lows=[90.0] * 10,
            closes=[100.0] * 10,
        )

        with pytest.raises(ValueError, match="ATR requires at least 15 data points"):
            atr.calculate(data)

    def test_atr_calculation_basic(self):
        """Test basic ATR calculation."""
        atr = ATR(period=14)

        # Create 20 data points with consistent volatility
        np.random.seed(42)
        base_price = 50000.0

        opens = [base_price + np.random.randn() * 100 for _ in range(20)]
        closes = [o + np.random.randn() * 200 for o in opens]
        highs = [
            max(o, c) + abs(np.random.randn()) * 150 for o, c in zip(opens, closes)
        ]
        lows = [min(o, c) - abs(np.random.randn()) * 150 for o, c in zip(opens, closes)]

        data = self.create_ohlcv_data(opens, highs, lows, closes)

        result = atr.calculate(data)

        assert isinstance(result, ATRResult)
        assert len(result.values) == 20
        assert result.current > 0
        assert result.period == 14

    def test_atr_values_positive(self):
        """Test that all ATR values are positive."""
        atr = ATR(period=5)

        # Create volatile data
        opens = [100.0] * 10
        highs = [110.0, 115.0, 105.0, 120.0, 108.0, 112.0, 118.0, 106.0, 114.0, 110.0]
        lows = [90.0, 85.0, 95.0, 80.0, 92.0, 88.0, 82.0, 94.0, 86.0, 90.0]
        closes = [105.0, 100.0, 110.0, 95.0, 105.0, 100.0, 110.0, 95.0, 105.0, 100.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        result = atr.calculate(data)

        # All values should be positive
        assert all(v > 0 for v in result.values)
        assert result.current > 0

    def test_atr_with_gaps(self):
        """Test ATR calculation with price gaps."""
        atr = ATR(period=5)

        # Create data with gaps
        opens = [100.0, 105.0, 95.0, 110.0, 90.0, 115.0, 85.0, 120.0, 80.0, 125.0]
        highs = [105.0, 110.0, 100.0, 115.0, 95.0, 120.0, 90.0, 125.0, 85.0, 130.0]
        lows = [95.0, 100.0, 90.0, 105.0, 85.0, 110.0, 80.0, 115.0, 75.0, 120.0]
        closes = [105.0, 95.0, 110.0, 90.0, 115.0, 85.0, 120.0, 80.0, 125.0, 85.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        result = atr.calculate(data)

        assert result.current > 0
        # ATR should reflect the volatility from gaps
        assert result.current > 5.0  # Minimum expected volatility

    def test_atr_wilders_smoothing(self):
        """Test that Wilder's smoothing is applied correctly."""
        atr = ATR(period=3)

        # Create simple data with known true ranges
        # TR1 = high - low = 10
        # TR2 = max(10, |110-95|, |90-95|) = 15
        # TR3 = max(10, |105-100|, |95-100|) = 10
        opens = [100.0, 100.0, 100.0, 100.0]
        highs = [110.0, 110.0, 110.0, 110.0]
        lows = [90.0, 90.0, 90.0, 90.0]
        closes = [100.0, 95.0, 105.0, 100.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        result = atr.calculate(data)

        # Values should be smoothed
        assert len(result.values) == 4
        assert result.current > 0

    def test_atr_consistency(self):
        """Test that ATR calculation is consistent."""
        atr = ATR(period=10)

        np.random.seed(42)
        base_price = 50000.0

        opens = [base_price + np.random.randn() * 100 for _ in range(20)]
        closes = [o + np.random.randn() * 200 for o in opens]
        highs = [
            max(o, c) + abs(np.random.randn()) * 150 for o, c in zip(opens, closes)
        ]
        lows = [min(o, c) - abs(np.random.randn()) * 150 for o, c in zip(opens, closes)]

        data = self.create_ohlcv_data(opens, highs, lows, closes)

        # Calculate twice with same data
        result1 = atr.calculate(data)
        result2 = atr.calculate(data)

        np.testing.assert_array_almost_equal(result1.values, result2.values)
        assert result1.current == result2.current


class TestATRTrueRange:
    """Tests for true range calculation."""

    def create_ohlcv_data(
        self,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ):
        """Create mock OHLCV data."""
        from dataclasses import dataclass

        @dataclass
        class MockOHLCV:
            open_price: float
            high_price: float
            low_price: float
            close_price: float
            volume: float = 1000.0
            timestamp: int = 0

        return [MockOHLCV(o, h, l, c) for o, h, l, c in zip(opens, highs, lows, closes)]

    def test_true_range_simple(self):
        """Test true range with simple range."""
        atr = ATR(period=5)

        # Simple case: TR = high - low
        opens = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
        highs = [110.0, 110.0, 110.0, 110.0, 110.0, 110.0]
        lows = [90.0, 90.0, 90.0, 90.0, 90.0, 90.0]
        closes = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        true_ranges = atr._calculate_true_ranges(data)

        # First bar: simple range
        assert true_ranges[0] == 20.0
        # Subsequent bars: same range (no gaps)
        assert all(tr == 20.0 for tr in true_ranges)

    def test_true_range_with_gap_up(self):
        """Test true range with gap up."""
        atr = ATR(period=5)

        # Gap up: previous close = 100, current low = 110
        opens = [100.0, 120.0]
        highs = [110.0, 130.0]
        lows = [90.0, 110.0]
        closes = [100.0, 120.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        true_ranges = atr._calculate_true_ranges(data)

        # First bar: simple range = 20
        assert true_ranges[0] == 20.0
        # Second bar: max(130-110=20, |130-100|=30, |110-100|=10) = 30
        assert true_ranges[1] == 30.0

    def test_true_range_with_gap_down(self):
        """Test true range with gap down."""
        atr = ATR(period=5)

        # Gap down: previous close = 120, current high = 100
        opens = [100.0, 80.0]
        highs = [110.0, 100.0]
        lows = [90.0, 70.0]
        closes = [120.0, 80.0]

        data = self.create_ohlcv_data(opens, highs, lows, closes)
        true_ranges = atr._calculate_true_ranges(data)

        # First bar: simple range = 20
        assert true_ranges[0] == 20.0
        # Second bar: max(100-70=30, |100-120|=20, |70-120|=50) = 50
        assert true_ranges[1] == 50.0
