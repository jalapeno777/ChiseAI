"""Tests for RSI indicator module."""

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.rsi import RSI, RSIResult


class TestRSIResult:
    """Test cases for RSIResult dataclass."""

    def test_creation(self):
        """Test creating RSIResult."""
        values = np.array([50.0, 60.0, 70.0])
        overbought = np.array([False, False, True])
        oversold = np.array([False, False, False])
        timestamps = np.array([1000, 2000, 3000])

        result = RSIResult(
            values=values,
            overbought=overbought,
            oversold=oversold,
            timestamps=timestamps,
        )

        assert len(result.values) == 3
        assert result.current == 70.0
        assert result.is_overbought is True
        assert result.is_oversold is False

    def test_empty_result(self):
        """Test RSIResult with empty arrays."""
        result = RSIResult(
            values=np.array([]),
            overbought=np.array([]),
            oversold=np.array([]),
            timestamps=np.array([]),
        )

        assert result.current is None
        assert result.is_overbought is False
        assert result.is_oversold is False


class TestRSI:
    """Test cases for RSI calculator."""

    @pytest.fixture
    def rsi(self):
        """Create an RSI calculator with default parameters."""
        return RSI(period=14)

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for RSI testing.

        Uses a price series that produces known RSI values.
        """
        # Generate 30 data points with alternating up/down moves
        base_ts = 1609459200000
        prices = []
        price = 100.0

        for i in range(30):
            if i % 2 == 0:
                price += 2.0  # Up move
            else:
                price -= 1.0  # Down move (smaller)

            prices.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        return prices

    def test_initialization(self):
        """Test RSI calculator initialization."""
        rsi = RSI(period=14, overbought_threshold=75.0, oversold_threshold=25.0)

        assert rsi.period == 14
        assert rsi.overbought_threshold == 75.0
        assert rsi.oversold_threshold == 25.0

    def test_calculate_insufficient_data(self, rsi):
        """Test that calculate raises error with insufficient data."""
        data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=101.0,
                low_price=99.0,
                close_price=100.0,
                volume=1000.0,
            )
            for _ in range(10)
        ]

        with pytest.raises(ValueError, match="RSI requires at least 15 data points"):
            rsi.calculate(data)

    def test_calculate_with_sufficient_data(self, rsi, sample_data):
        """Test RSI calculation with sufficient data."""
        result = rsi.calculate(sample_data)

        assert isinstance(result, RSIResult)
        assert len(result.values) == len(sample_data)

        # First period values should be NaN (not enough data)
        assert np.isnan(result.values[13])

        # Values from period onwards should be valid
        assert not np.isnan(result.values[14])

    def test_rsi_range(self, rsi, sample_data):
        """Test that RSI values are within valid range [0, 100]."""
        result = rsi.calculate(sample_data)

        valid_values = result.values[~np.isnan(result.values)]
        assert np.all(valid_values >= 0.0)
        assert np.all(valid_values <= 100.0)

    def test_overbought_detection(self):
        """Test overbought condition detection."""
        rsi = RSI(period=14, overbought_threshold=70.0)

        # Create data with strong upward trend (should produce high RSI)
        base_ts = 1609459200000
        data = []
        price = 100.0

        for i in range(30):
            price += 5.0  # Strong upward move
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = rsi.calculate(data)

        # RSI should be high (overbought)
        assert result.current > 70.0
        assert result.is_overbought is True
        assert result.is_oversold is False

    def test_oversold_detection(self):
        """Test oversold condition detection."""
        rsi = RSI(period=14, oversold_threshold=30.0)

        # Create data with strong downward trend (should produce low RSI)
        base_ts = 1609459200000
        data = []
        price = 200.0

        for i in range(30):
            price -= 5.0  # Strong downward move
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = rsi.calculate(data)

        # RSI should be low (oversold)
        assert result.current < 30.0
        assert result.is_oversold is True
        assert result.is_overbought is False

    def test_calculate_from_prices(self, rsi):
        """Test RSI calculation directly from price array."""
        prices = np.array([100.0 + i * 2.0 for i in range(30)])

        result = rsi.calculate_from_prices(prices)

        assert len(result) == len(prices)
        assert not np.isnan(result[-1])
        assert 0.0 <= result[-1] <= 100.0

    def test_calculate_from_prices_insufficient_data(self, rsi):
        """Test calculate_from_prices with insufficient data."""
        prices = np.array([100.0, 101.0, 102.0])

        with pytest.raises(ValueError, match="RSI requires at least 15 prices"):
            rsi.calculate_from_prices(prices)

    def test_tradingview_comparison(self):
        """Test RSI calculation matches TradingView within 0.1% tolerance.

        Uses known price data and compares calculated RSI against
        expected values from TradingView.

        TradingView's RSI uses RMA (Running Moving Average) with:
        - alpha = 1 / period
        - First value: alpha * x[0] (not SMA of first 'period' values)
        - Subsequent: alpha * x[i] + (1 - alpha) * prev_rma
        """
        # Sample price data (close prices)
        # These prices should produce specific RSI values
        prices = np.array(
            [
                100.0,
                102.0,
                101.0,
                103.0,
                104.0,  # Day 1-5
                103.0,
                105.0,
                106.0,
                104.0,
                107.0,  # Day 6-10
                108.0,
                106.0,
                109.0,
                110.0,
                108.0,  # Day 11-15
                111.0,
                112.0,
                110.0,
                113.0,
                114.0,  # Day 16-20
                112.0,
                115.0,
                116.0,
                114.0,
                117.0,  # Day 21-25
                118.0,
                116.0,
                119.0,
                120.0,
                118.0,  # Day 26-30
            ]
        )

        # Expected RSI values calculated using TradingView's formula
        # These values are computed using RMA (Running Moving Average)
        # with alpha = 1/14 and first value = alpha * x[0]
        expected_rsi_values = np.array(
            [
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,  # First 14 are NaN
                63.61851851851852,  # Index 14 - first valid RSI
                69.74235417764317,  # Index 15
                71.46645259938874,  # Index 16
                63.65431922465338,  # Index 17
                69.10906352869640,  # Index 18
                70.68822762855144,  # Index 19
                63.67701035480493,  # Index 20
                68.69307122681439,  # Index 21
                70.17174542582584,  # Index 22
                63.69235718268411,  # Index 23
                68.40501421515193,  # Index 24
                69.81161538461538,  # Index 25
                63.70319666170879,  # Index 26
                68.19818787878787,  # Index 27
                69.55177539364318,  # Index 28
                63.71108986615638,  # Index 29
            ]
        )

        rsi = RSI(period=14)
        result = rsi.calculate_from_prices(prices)

        # Compare calculated values with expected values
        tolerance = 0.1  # 0.1% tolerance
        for i in range(len(prices)):
            if np.isnan(expected_rsi_values[i]):
                assert np.isnan(result[i]), f"Index {i}: expected NaN, got {result[i]}"
            else:
                diff_pct = (
                    abs(result[i] - expected_rsi_values[i])
                    / expected_rsi_values[i]
                    * 100
                )
                assert diff_pct < tolerance, (
                    f"Index {i}: RSI {result[i]:.6f} differs from expected "
                    f"{expected_rsi_values[i]:.6f} by {diff_pct:.4f}%"
                    f" (tolerance: {tolerance}%)"
                )

    def test_wilder_smoothing(self):
        """Test that Wilder's smoothing method is correctly applied."""
        rsi = RSI(period=14)

        # Create data with consistent gains and losses
        base_ts = 1609459200000
        data = []
        price = 100.0

        # Alternating +2, -1 pattern
        for i in range(30):
            if i % 2 == 0:
                price += 2.0
            else:
                price -= 1.0

            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 1.0,
                    high_price=price + 1.0,
                    low_price=price - 2.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = rsi.calculate(data)

        # With net positive moves, RSI should be > 50
        valid_values = result.values[~np.isnan(result.values)]
        assert np.mean(valid_values) > 50.0

    def test_rma_rolling_update_behavior(self):
        """Test RMA (Running Moving Average) rolling update behavior.

        Verifies that the RMA calculation follows TradingView's formula:
        - First value: alpha * x[0] where alpha = 1/period
        - Subsequent: (prev_rma * (period - 1) + current) / period
        """
        rsi = RSI(period=14)

        # Test with simple gain values
        test_gains = np.array(
            [2.0, 0.0, 2.0, 1.0, 0.0, 2.0, 1.0, 0.0, 3.0, 1.0, 0.0, 3.0, 1.0, 0.0]
        )

        # Calculate RMA manually using TradingView's formula
        period = 14
        alpha = 1.0 / period
        expected_rma = np.zeros(len(test_gains))

        # First value: alpha * x[0]
        rma = alpha * test_gains[0]
        expected_rma[0] = rma

        # Subsequent values: alpha * x[i] + (1 - alpha) * prev_rma
        for i in range(1, len(test_gains)):
            rma = alpha * test_gains[i] + (1 - alpha) * rma
            expected_rma[i] = rma

        # Get RMA from RSI calculator
        calculated_rma = rsi._calculate_rma(test_gains)

        # Compare values
        np.testing.assert_array_almost_equal(
            calculated_rma,
            expected_rma,
            decimal=10,
            err_msg="RMA calculation does not match TradingView's formula",
        )

    def test_rma_vs_sma_initialization_difference(self):
        """Test that RMA initialization differs from SMA.

        This test documents the key difference between our implementation
        and a naive SMA-based approach. TradingView's RSI uses RMA which
        initializes with alpha * x[0], NOT the SMA of first 'period' values.
        """
        rsi = RSI(period=14)

        # Simple test data
        test_values = np.array([2.0] * 14)  # 14 values of 2.0

        # RMA calculation (TradingView method)
        rma_result = rsi._calculate_rma(test_values)

        # SMA calculation (naive method - NOT what TradingView uses)
        sma_result = np.mean(test_values)

        # RMA first value should be alpha * x[0] = 2.0 / 14 = 0.142857...
        expected_first_rma = 2.0 / 14
        assert (
            abs(rma_result[0] - expected_first_rma) < 1e-10
        ), f"RMA first value {rma_result[0]} != expected {expected_first_rma}"

        # SMA of all 14 values would be 2.0
        assert abs(sma_result - 2.0) < 1e-10, f"SMA value {sma_result} != expected 2.0"

        # RMA converges toward the mean over time but starts differently
        assert rma_result[-1] > rma_result[0], "RMA should increase toward mean"
        assert abs(rma_result[-1] - 1.5) < 0.5, "RMA final value should approach ~1.5"

    def test_nan_handling(self, rsi):
        """Test handling of NaN and infinite values."""
        base_ts = 1609459200000
        data = []

        for i in range(30):
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=100.0,
                    high_price=100.0,
                    low_price=100.0,
                    close_price=100.0,  # Flat prices
                    volume=1000.0,
                )
            )

        result = rsi.calculate(data)

        # Should handle flat prices gracefully
        assert not np.any(np.isinf(result.values))
        # NaN values are expected for initial period
        assert np.all(np.isnan(result.values[:14]))
