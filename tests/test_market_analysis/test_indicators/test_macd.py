"""Tests for MACD indicator module."""

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.macd import MACD, MACDResult, MACDSignal


class TestMACDResult:
    """Test cases for MACDResult dataclass."""

    def test_creation(self):
        """Test creating MACDResult."""
        macd_line = np.array([0.0, 0.5, 1.0])
        signal_line = np.array([0.0, 0.3, 0.6])
        histogram = np.array([0.0, 0.2, 0.4])
        crossovers = np.array(
            [MACDSignal.NONE, MACDSignal.NONE, MACDSignal.BULLISH_CROSSOVER]
        )
        timestamps = np.array([1000, 2000, 3000])

        result = MACDResult(
            macd_line=macd_line,
            signal_line=signal_line,
            histogram=histogram,
            crossovers=crossovers,
            timestamps=timestamps,
        )

        assert len(result.macd_line) == 3
        assert result.current_macd == 1.0
        assert result.current_signal == 0.6
        assert result.current_histogram == 0.4
        assert result.latest_crossover == MACDSignal.BULLISH_CROSSOVER

    def test_empty_result(self):
        """Test MACDResult with empty arrays."""
        result = MACDResult(
            macd_line=np.array([]),
            signal_line=np.array([]),
            histogram=np.array([]),
            crossovers=np.array([]),
            timestamps=np.array([]),
        )

        assert result.current_macd is None
        assert result.current_signal is None
        assert result.current_histogram is None
        assert result.latest_crossover == MACDSignal.NONE

    def test_no_crossover(self):
        """Test latest_crossover when no crossovers exist."""
        result = MACDResult(
            macd_line=np.array([0.0, 0.1, 0.2]),
            signal_line=np.array([0.0, 0.1, 0.2]),
            histogram=np.array([0.0, 0.0, 0.0]),
            crossovers=np.array([MACDSignal.NONE, MACDSignal.NONE, MACDSignal.NONE]),
            timestamps=np.array([1000, 2000, 3000]),
        )

        assert result.latest_crossover == MACDSignal.NONE


class TestMACD:
    """Test cases for MACD calculator."""

    @pytest.fixture
    def macd(self):
        """Create a MACD calculator with default parameters."""
        return MACD(fast_period=12, slow_period=26, signal_period=9)

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for MACD testing."""
        base_ts = 1609459200000
        data = []

        # Generate 50 data points with a trend
        price = 100.0
        for i in range(50):
            # Add some trend and noise
            trend = i * 0.1
            noise = np.sin(i * 0.5) * 2.0
            price = 100.0 + trend + noise

            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 1.0,
                    low_price=price - 1.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        return data

    def test_initialization(self):
        """Test MACD calculator initialization."""
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)

        assert macd.fast_period == 12
        assert macd.slow_period == 26
        assert macd.signal_period == 9

    def test_initialization_invalid_periods(self):
        """Test MACD initialization with invalid periods."""
        with pytest.raises(
            ValueError, match="Fast period must be less than slow period"
        ):
            MACD(fast_period=26, slow_period=12)

        with pytest.raises(ValueError, match="Signal period must be positive"):
            MACD(fast_period=12, slow_period=26, signal_period=0)

    def test_calculate_insufficient_data(self, macd):
        """Test that calculate raises error with insufficient data."""
        data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=101.0,
                low_price=99.0,
                close_price=100.0,
                volume=1000.0,
            )
            for i in range(30)
        ]

        with pytest.raises(ValueError, match="MACD requires at least 35 data points"):
            macd.calculate(data)

    def test_calculate_with_sufficient_data(self, macd, sample_data):
        """Test MACD calculation with sufficient data."""
        result = macd.calculate(sample_data)

        assert isinstance(result, MACDResult)
        assert len(result.macd_line) == len(sample_data)
        assert len(result.signal_line) == len(sample_data)
        assert len(result.histogram) == len(sample_data)
        assert len(result.crossovers) == len(sample_data)

    def test_macd_line_calculation(self, macd, sample_data):
        """Test that MACD line equals Fast EMA - Slow EMA."""
        result = macd.calculate(sample_data)

        # Calculate expected MACD line manually for a few points
        closes = np.array([d.close_price for d in sample_data])
        fast_ema = macd._calculate_ema(closes, macd.fast_period)
        slow_ema = macd._calculate_ema(closes, macd.slow_period)
        expected_macd = fast_ema - slow_ema

        # Compare (allowing for NaN values at start)
        valid_idx = ~np.isnan(result.macd_line) & ~np.isnan(expected_macd)
        np.testing.assert_array_almost_equal(
            result.macd_line[valid_idx],
            expected_macd[valid_idx],
            decimal=10,
        )

    def test_histogram_calculation(self, macd, sample_data):
        """Test that histogram equals MACD line - Signal line."""
        result = macd.calculate(sample_data)

        expected_histogram = result.macd_line - result.signal_line

        valid_idx = ~np.isnan(result.histogram) & ~np.isnan(expected_histogram)
        np.testing.assert_array_almost_equal(
            result.histogram[valid_idx],
            expected_histogram[valid_idx],
            decimal=10,
        )

    def test_bullish_crossover_detection(self):
        """Test detection of bullish crossover (MACD crosses above signal)."""
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)

        # Create data that produces a clear bullish crossover
        # Prices start low then rise sharply
        base_ts = 1609459200000
        data = []

        # Initial declining prices (MACD below signal)
        price = 120.0
        for i in range(12):
            price -= 2.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 0.5,
                    low_price=price - 1.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        # Sharp rise (MACD crosses above signal)
        for i in range(12, 24):
            price += 5.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 0.5,
                    low_price=price - 1.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = macd.calculate(data)

        # Should have at least one bullish crossover
        bullish_crosses = np.sum(result.crossovers == MACDSignal.BULLISH_CROSSOVER)
        assert (
            bullish_crosses >= 1
        ), f"Expected at least one bullish crossover, got {bullish_crosses}"

    def test_bearish_crossover_detection(self):
        """Test detection of bearish crossover (MACD crosses below signal)."""
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)

        # Create data that produces a clear bearish crossover
        # Prices start high then fall sharply
        base_ts = 1609459200000
        data = []

        # Initial rising prices (MACD above signal)
        price = 80.0
        for i in range(12):
            price += 2.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 0.5,
                    low_price=price - 1.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        # Sharp drop (MACD crosses below signal)
        for i in range(12, 24):
            price -= 5.0
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 0.5,
                    low_price=price - 1.0,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = macd.calculate(data)

        # Should have at least one bearish crossover
        bearish_crosses = np.sum(result.crossovers == MACDSignal.BEARISH_CROSSOVER)
        assert (
            bearish_crosses >= 1
        ), f"Expected at least one bearish crossover, got {bearish_crosses}"

    def test_crossover_accuracy(self):
        """Test that crossover detection is accurate.

        Verify that crossovers are detected exactly when MACD line
        crosses the signal line.
        """
        macd = MACD(fast_period=3, slow_period=6, signal_period=2)

        # Create data with known crossover points
        base_ts = 1609459200000
        data = []

        # Generate prices that will create a predictable crossover
        prices = [100.0] * 8 + [110.0] * 8 + [100.0] * 8

        for i, price in enumerate(prices):
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=price - 0.5,
                    high_price=price + 0.5,
                    low_price=price - 0.5,
                    close_price=price,
                    volume=1000.0,
                )
            )

        result = macd.calculate(data)

        # Verify crossover detection by checking sign changes in histogram
        for i in range(1, len(result.histogram)):
            if result.crossovers[i] == MACDSignal.BULLISH_CROSSOVER:
                # Histogram should change from negative/zero to positive
                assert result.histogram[i] > 0 or (
                    result.histogram[i - 1] <= 0 and result.histogram[i] > 0
                )
            elif result.crossovers[i] == MACDSignal.BEARISH_CROSSOVER:
                # Histogram should change from positive/zero to negative
                assert result.histogram[i] < 0 or (
                    result.histogram[i - 1] >= 0 and result.histogram[i] < 0
                )

    def test_calculate_from_prices(self, macd):
        """Test MACD calculation directly from price array."""
        prices = np.array([100.0 + i * 0.5 for i in range(50)])

        macd_line, signal_line, histogram = macd.calculate_from_prices(prices)

        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)
        assert len(histogram) == len(prices)

    def test_calculate_from_prices_insufficient_data(self, macd):
        """Test calculate_from_prices with insufficient data."""
        prices = np.array([100.0] * 30)

        with pytest.raises(ValueError, match="MACD requires at least 35 prices"):
            macd.calculate_from_prices(prices)

    def test_ema_calculation(self, macd):
        """Test EMA calculation."""
        data = np.array([100.0, 101.0, 102.0, 101.0, 100.0, 99.0, 100.0])

        ema = macd._calculate_ema(data, period=3)

        # First valid EMA should be at index 2 (period - 1)
        assert np.isnan(ema[0])
        assert np.isnan(ema[1])
        assert not np.isnan(ema[2])

        # EMA should follow the trend
        # With alpha = 2/(3+1) = 0.5
        # EMA[2] = SMA of first 3 = (100+101+102)/3 = 101.0
        expected_ema_2 = np.mean(data[:3])
        assert abs(ema[2] - expected_ema_2) < 0.001

    def test_macd_signal_enum(self):
        """Test MACDSignal enum values."""
        assert MACDSignal.NONE.value == "none"
        assert MACDSignal.BULLISH_CROSSOVER.value == "bullish_crossover"
        assert MACDSignal.BEARISH_CROSSOVER.value == "bearish_crossover"
