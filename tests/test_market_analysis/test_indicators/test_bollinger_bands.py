"""Tests for Bollinger Bands indicator module."""

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.bollinger_bands import (
    BollingerBands,
    BollingerBandsResult,
)


class TestBollingerBandsResult:
    """Test cases for BollingerBandsResult dataclass."""

    def test_creation(self):
        """Test creating BollingerBandsResult."""
        middle = np.array([100.0, 101.0, 102.0])
        upper = np.array([104.0, 105.0, 106.0])
        lower = np.array([96.0, 97.0, 98.0])
        width = np.array([8.0, 8.0, 8.0])
        percent_b = np.array([0.5, 0.5, 0.5])
        timestamps = np.array([1000, 2000, 3000])

        result = BollingerBandsResult(
            middle_band=middle,
            upper_band=upper,
            lower_band=lower,
            band_width=width,
            percent_b=percent_b,
            timestamps=timestamps,
        )

        assert len(result.middle_band) == 3
        assert result.current_middle == 102.0
        assert result.current_upper == 106.0
        assert result.current_lower == 98.0
        assert result.current_band_width == 8.0
        assert result.current_percent_b == 0.5

    def test_empty_result(self):
        """Test BollingerBandsResult with empty arrays."""
        result = BollingerBandsResult(
            middle_band=np.array([]),
            upper_band=np.array([]),
            lower_band=np.array([]),
            band_width=np.array([]),
            percent_b=np.array([]),
            timestamps=np.array([]),
        )

        assert result.current_middle is None
        assert result.current_upper is None
        assert result.current_lower is None
        assert result.current_band_width is None
        assert result.current_percent_b is None


class TestBollingerBands:
    """Test cases for Bollinger Bands calculator."""

    @pytest.fixture
    def bb(self):
        """Create a Bollinger Bands calculator with default parameters."""
        return BollingerBands(period=20, num_std_dev=2.0)

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for Bollinger Bands testing."""
        base_ts = 1609459200000
        data = []

        # Generate 40 data points with varying volatility
        np.random.seed(42)  # For reproducibility
        price = 100.0

        for i in range(40):
            # Add some random walk
            change = np.random.normal(0, 1.0)
            price += change

            # Ensure price stays positive
            price = max(price, 10.0)

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
        """Test Bollinger Bands calculator initialization."""
        bb = BollingerBands(period=20, num_std_dev=2.0)

        assert bb.period == 20
        assert bb.num_std_dev == 2.0

    def test_initialization_invalid_parameters(self):
        """Test Bollinger Bands initialization with invalid parameters."""
        with pytest.raises(ValueError, match="Period must be at least 2"):
            BollingerBands(period=1)

        with pytest.raises(
            ValueError, match="Number of standard deviations must be positive"
        ):
            BollingerBands(period=20, num_std_dev=0.0)

        with pytest.raises(
            ValueError, match="Number of standard deviations must be positive"
        ):
            BollingerBands(period=20, num_std_dev=-1.0)

    def test_calculate_insufficient_data(self, bb):
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
            for i in range(10)
        ]

        with pytest.raises(
            ValueError, match="Bollinger Bands require at least 20 data points"
        ):
            bb.calculate(data)

    def test_calculate_with_sufficient_data(self, bb, sample_data):
        """Test Bollinger Bands calculation with sufficient data."""
        result = bb.calculate(sample_data)

        assert isinstance(result, BollingerBandsResult)
        assert len(result.middle_band) == len(sample_data)
        assert len(result.upper_band) == len(sample_data)
        assert len(result.lower_band) == len(sample_data)
        assert len(result.band_width) == len(sample_data)
        assert len(result.percent_b) == len(sample_data)

    def test_band_relationships(self, bb, sample_data):
        """Test that bands maintain correct relationships."""
        result = bb.calculate(sample_data)

        # Upper band should always be >= middle band
        valid_idx = ~np.isnan(result.upper_band) & ~np.isnan(result.middle_band)
        assert np.all(result.upper_band[valid_idx] >= result.middle_band[valid_idx])

        # Middle band should always be >= lower band
        assert np.all(result.middle_band[valid_idx] >= result.lower_band[valid_idx])

        # Band width should equal upper - lower
        expected_width = result.upper_band - result.lower_band
        np.testing.assert_array_almost_equal(
            result.band_width[valid_idx],
            expected_width[valid_idx],
            decimal=10,
        )

    def test_middle_band_is_sma(self, bb, sample_data):
        """Test that middle band equals SMA of close prices."""
        result = bb.calculate(sample_data)

        # Calculate SMA manually
        closes = np.array([d.close_price for d in sample_data])
        sma = bb._calculate_sma(closes, bb.period)

        # Compare (allowing for NaN values at start)
        valid_idx = ~np.isnan(result.middle_band) & ~np.isnan(sma)
        np.testing.assert_array_almost_equal(
            result.middle_band[valid_idx],
            sma[valid_idx],
            decimal=10,
        )

    def test_upper_lower_band_calculation(self, bb, sample_data):
        """Test upper and lower band calculations."""
        result = bb.calculate(sample_data)

        # Calculate expected bands manually
        closes = np.array([d.close_price for d in sample_data])
        sma = bb._calculate_sma(closes, bb.period)
        std = bb._calculate_rolling_std(closes, bb.period)

        expected_upper = sma + (bb.num_std_dev * std)
        expected_lower = sma - (bb.num_std_dev * std)

        valid_idx = ~np.isnan(result.upper_band)
        np.testing.assert_array_almost_equal(
            result.upper_band[valid_idx],
            expected_upper[valid_idx],
            decimal=10,
        )
        np.testing.assert_array_almost_equal(
            result.lower_band[valid_idx],
            expected_lower[valid_idx],
            decimal=10,
        )

    def test_percent_b_calculation(self, bb, sample_data):
        """Test %B calculation."""
        result = bb.calculate(sample_data)

        # %B = (close - lower) / (upper - lower)
        closes = np.array([d.close_price for d in sample_data])
        expected_percent_b = (closes - result.lower_band) / (
            result.upper_band - result.lower_band
        )

        valid_idx = ~np.isnan(result.percent_b)
        np.testing.assert_array_almost_equal(
            result.percent_b[valid_idx],
            expected_percent_b[valid_idx],
            decimal=10,
        )

    def test_percent_b_ranges(self, bb, sample_data):
        """Test that %B can be outside [0, 1] when price breaks bands."""
        # Create data where price breaks above/below bands
        base_ts = 1609459200000
        data = []

        # First 20 candles with consistent range
        for i in range(20):
            data.append(
                OHLCVData(
                    timestamp=base_ts + i * 60000,
                    open_price=100.0,
                    high_price=102.0,
                    low_price=98.0,
                    close_price=100.0,
                    volume=1000.0,
                )
            )

        # Next candle breaks above upper band
        data.append(
            OHLCVData(
                timestamp=base_ts + 20 * 60000,
                open_price=110.0,
                high_price=112.0,
                low_price=108.0,
                close_price=110.0,
                volume=1000.0,
            )
        )

        # Next candle breaks below lower band
        data.append(
            OHLCVData(
                timestamp=base_ts + 21 * 60000,
                open_price=90.0,
                high_price=92.0,
                low_price=88.0,
                close_price=90.0,
                volume=1000.0,
            )
        )

        result = bb.calculate(data)

        # %B should be > 1 when price is above upper band
        assert result.percent_b[-2] > 1.0

        # %B should be < 0 when price is below lower band
        assert result.percent_b[-1] < 0.0

    def test_price_near_upper_band(self, bb):
        """Test is_price_near_upper method."""
        assert bb.is_price_near_upper(0.95, threshold=0.95) is True
        assert bb.is_price_near_upper(0.96, threshold=0.95) is True
        assert bb.is_price_near_upper(0.94, threshold=0.95) is False

    def test_price_near_lower_band(self, bb):
        """Test is_price_near_lower method."""
        assert bb.is_price_near_lower(0.05, threshold=0.05) is True
        assert bb.is_price_near_lower(0.04, threshold=0.05) is True
        assert bb.is_price_near_lower(0.06, threshold=0.05) is False

    def test_calculate_from_prices(self, bb):
        """Test Bollinger Bands calculation directly from price array."""
        np.random.seed(42)
        prices = np.array([100.0 + np.random.normal(0, 2.0) for _ in range(40)])

        middle, upper, lower, width = bb.calculate_from_prices(prices)

        assert len(middle) == len(prices)
        assert len(upper) == len(prices)
        assert len(lower) == len(prices)
        assert len(width) == len(prices)

    def test_calculate_from_prices_insufficient_data(self, bb):
        """Test calculate_from_prices with insufficient data."""
        prices = np.array([100.0] * 10)

        with pytest.raises(
            ValueError, match="Bollinger Bands require at least 20 prices"
        ):
            bb.calculate_from_prices(prices)

    def test_sma_calculation(self, bb):
        """Test SMA calculation."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        sma = bb._calculate_sma(data, period=3)

        # First 2 values should be NaN
        assert np.isnan(sma[0])
        assert np.isnan(sma[1])

        # SMA[2] = (1+2+3)/3 = 2.0
        assert sma[2] == 2.0

        # SMA[3] = (2+3+4)/3 = 3.0
        assert sma[3] == 3.0

        # SMA[4] = (3+4+5)/3 = 4.0
        assert sma[4] == 4.0

    def test_rolling_std_calculation(self, bb):
        """Test rolling standard deviation calculation."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        std = bb._calculate_rolling_std(data, period=3)

        # First 2 values should be NaN
        assert np.isnan(std[0])
        assert np.isnan(std[1])

        # Calculate expected std for index 2
        # Window: [1, 2, 3], mean = 2
        # Variance = ((1-2)^2 + (2-2)^2 + (3-2)^2) / (3-1) = (1+0+1)/2 = 1
        # Std = sqrt(1) = 1
        expected_std_2 = np.std([1.0, 2.0, 3.0], ddof=1)
        assert abs(std[2] - expected_std_2) < 0.0001

    def test_flat_prices(self, bb):
        """Test Bollinger Bands with flat prices (zero volatility)."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0,
                high_price=100.0,
                low_price=100.0,
                close_price=100.0,
                volume=1000.0,
            )
            for i in range(25)
        ]

        result = bb.calculate(data)

        # With flat prices, bands should collapse to middle
        valid_idx = ~np.isnan(result.middle_band)
        assert np.all(result.upper_band[valid_idx] == result.middle_band[valid_idx])
        assert np.all(result.lower_band[valid_idx] == result.middle_band[valid_idx])
        assert np.all(result.band_width[valid_idx] == 0.0)

        # %B should be 0.5 when bands are flat
        assert np.all(result.percent_b[valid_idx] == 0.5)

    def test_different_std_dev_multipliers(self, sample_data):
        """Test Bollinger Bands with different std dev multipliers."""
        bb_1std = BollingerBands(period=20, num_std_dev=1.0)
        bb_2std = BollingerBands(period=20, num_std_dev=2.0)
        bb_3std = BollingerBands(period=20, num_std_dev=3.0)

        result_1std = bb_1std.calculate(sample_data)
        result_2std = bb_2std.calculate(sample_data)
        result_3std = bb_3std.calculate(sample_data)

        # Higher std dev should produce wider bands
        valid_idx = ~np.isnan(result_1std.band_width)
        assert np.all(
            result_1std.band_width[valid_idx] < result_2std.band_width[valid_idx]
        )
        assert np.all(
            result_2std.band_width[valid_idx] < result_3std.band_width[valid_idx]
        )
