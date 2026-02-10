"""Tests for unified indicator calculator module."""

import numpy as np
import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe
from market_analysis.indicators.calculator import (
    IndicatorCache,
    IndicatorCalculator,
    IndicatorSet,
)


class TestIndicatorSet:
    """Test cases for IndicatorSet dataclass."""

    def test_creation(self):
        """Test creating IndicatorSet."""
        indicator_set = IndicatorSet(timeframe=Timeframe.MINUTE_5)

        assert indicator_set.timeframe == Timeframe.MINUTE_5
        assert indicator_set.rsi is None
        assert indicator_set.macd is None
        assert indicator_set.bollinger_bands is None

    def test_creation_with_indicators(self):
        """Test creating IndicatorSet with calculated indicators."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + i,
                high_price=101.0 + i,
                low_price=99.0 + i,
                close_price=100.0 + i,
                volume=1000.0,
            )
            for i in range(50)
        ]

        calculator = IndicatorCalculator(use_cache=False)
        indicator_set = calculator.calculate_all(data, Timeframe.MINUTE_5)

        assert indicator_set.timeframe == Timeframe.MINUTE_5
        assert indicator_set.rsi is not None
        assert indicator_set.macd is not None
        assert indicator_set.bollinger_bands is not None


class TestIndicatorCache:
    """Test cases for IndicatorCache dataclass."""

    def test_creation(self):
        """Test creating IndicatorCache."""
        indicator_set = IndicatorSet(timeframe=Timeframe.MINUTE_5)
        cache = IndicatorCache(
            data_hash="test_hash_123",
            indicators=indicator_set,
        )

        assert cache.data_hash == "test_hash_123"
        assert cache.indicators == indicator_set


class TestIndicatorCalculator:
    """Test cases for IndicatorCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create an IndicatorCalculator instance."""
        return IndicatorCalculator(use_cache=True)

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing."""
        base_ts = 1609459200000
        data = []

        # Generate 50 data points with a trend
        price = 100.0
        for i in range(50):
            price += np.sin(i * 0.3) * 2.0 + 0.5
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
        """Test IndicatorCalculator initialization."""
        calc_with_cache = IndicatorCalculator(use_cache=True)
        calc_without_cache = IndicatorCalculator(use_cache=False)

        assert calc_with_cache.use_cache is True
        assert calc_without_cache.use_cache is False
        assert len(calc_with_cache._cache) == 0

    def test_calculate_rsi(self, calculator, sample_data):
        """Test RSI calculation through calculator."""
        result = calculator.calculate_rsi(sample_data)

        assert result is not None
        assert len(result.values) == len(sample_data)
        assert result.current is not None
        assert 0.0 <= result.current <= 100.0

    def test_calculate_macd(self, calculator, sample_data):
        """Test MACD calculation through calculator."""
        result = calculator.calculate_macd(sample_data)

        assert result is not None
        assert len(result.macd_line) == len(sample_data)
        assert len(result.signal_line) == len(sample_data)
        assert len(result.histogram) == len(sample_data)

    def test_calculate_bollinger_bands(self, calculator, sample_data):
        """Test Bollinger Bands calculation through calculator."""
        result = calculator.calculate_bollinger_bands(sample_data)

        assert result is not None
        assert len(result.middle_band) == len(sample_data)
        assert len(result.upper_band) == len(sample_data)
        assert len(result.lower_band) == len(sample_data)

    def test_calculate_all(self, calculator, sample_data):
        """Test calculating all indicators at once."""
        result = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)

        assert isinstance(result, IndicatorSet)
        assert result.timeframe == Timeframe.MINUTE_5
        assert result.rsi is not None
        assert result.macd is not None
        assert result.bollinger_bands is not None

    def test_calculate_all_empty_data(self, calculator):
        """Test calculate_all with empty data."""
        result = calculator.calculate_all([], Timeframe.MINUTE_5)

        assert isinstance(result, IndicatorSet)
        assert result.timeframe == Timeframe.MINUTE_5
        assert result.rsi is None
        assert result.macd is None
        assert result.bollinger_bands is None

    def test_calculate_all_insufficient_data(self, calculator):
        """Test calculate_all with insufficient data for some indicators."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0,
                high_price=101.0,
                low_price=99.0,
                close_price=100.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        result = calculator.calculate_all(data, Timeframe.MINUTE_5)

        # All indicators should be None due to insufficient data
        assert result.rsi is None
        assert result.macd is None
        assert result.bollinger_bands is None

    def test_calculate_multiple_timeframes(self, calculator, sample_data):
        """Test calculating indicators for multiple timeframes."""
        data_map = {
            Timeframe.MINUTE_1: sample_data,
            Timeframe.MINUTE_5: sample_data[:40],
            Timeframe.HOUR_1: sample_data[:30],
        }

        results = calculator.calculate_multiple_timeframes(data_map)

        assert len(results) == 3
        assert Timeframe.MINUTE_1 in results
        assert Timeframe.MINUTE_5 in results
        assert Timeframe.HOUR_1 in results

        # All should have indicators calculated
        for timeframe, indicator_set in results.items():
            assert indicator_set.timeframe == timeframe

    def test_get_latest_values(self, calculator, sample_data):
        """Test getting latest values from indicator set."""
        indicators = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)
        latest = calculator.get_latest_values(indicators)

        assert "rsi" in latest
        assert "rsi_overbought" in latest
        assert "rsi_oversold" in latest
        assert "macd" in latest
        assert "macd_signal" in latest
        assert "macd_histogram" in latest
        assert "bb_middle" in latest
        assert "bb_upper" in latest
        assert "bb_lower" in latest
        assert "bb_width" in latest
        assert "bb_percent_b" in latest

        # All values should be floats or None
        for _key, value in latest.items():
            assert value is None or isinstance(value, (float, bool))

    def test_get_latest_values_empty_indicators(self, calculator):
        """Test get_latest_values with empty indicator set."""
        indicators = IndicatorSet(timeframe=Timeframe.MINUTE_5)
        latest = calculator.get_latest_values(indicators)

        # All values should be None
        for _key, value in latest.items():
            assert value is None

    def test_caching(self, calculator, sample_data):
        """Test that caching works correctly."""
        # First calculation should store in cache
        result1 = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)

        # Second calculation with same data should use cache
        result2 = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)

        # Results should be identical (same object from cache)
        assert result1 is result2

    def test_cache_invalidation(self, calculator, sample_data):
        """Test that cache is invalidated when data changes."""
        # First calculation
        result1 = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)

        # Modify data slightly
        modified_data = sample_data.copy()
        modified_data[-1] = OHLCVData(
            timestamp=modified_data[-1].timestamp,
            open_price=modified_data[-1].open_price + 1.0,
            high_price=modified_data[-1].high_price + 1.0,
            low_price=modified_data[-1].low_price + 1.0,
            close_price=modified_data[-1].close_price + 1.0,
            volume=modified_data[-1].volume,
        )

        # Second calculation with modified data should not use cache
        result2 = calculator.calculate_all(modified_data, Timeframe.MINUTE_5)

        # Results should be different objects
        assert result1 is not result2

    def test_clear_cache(self, calculator, sample_data):
        """Test clearing the cache."""
        # Calculate and store in cache
        calculator.calculate_all(sample_data, Timeframe.MINUTE_5)
        assert len(calculator._cache) > 0

        # Clear cache
        calculator.clear_cache()
        assert len(calculator._cache) == 0

    def test_cache_disabled(self, sample_data):
        """Test calculator with caching disabled."""
        calculator = IndicatorCalculator(use_cache=False)

        # Multiple calculations should create new objects
        result1 = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)
        result2 = calculator.calculate_all(sample_data, Timeframe.MINUTE_5)

        # Results should be different objects
        assert result1 is not result2

    def test_generate_cache_key(self, calculator, sample_data):
        """Test cache key generation."""
        key1 = calculator._generate_cache_key(sample_data, Timeframe.MINUTE_5)
        key2 = calculator._generate_cache_key(sample_data, Timeframe.MINUTE_5)
        key3 = calculator._generate_cache_key(sample_data, Timeframe.HOUR_1)

        # Same data and timeframe should produce same key
        assert key1 == key2

        # Different timeframe should produce different key
        assert key1 != key3

    def test_generate_cache_key_empty_data(self, calculator):
        """Test cache key generation with empty data."""
        key = calculator._generate_cache_key([], Timeframe.MINUTE_5)

        assert "empty" in key
        assert Timeframe.MINUTE_5.value in key

    def test_hash_data(self, calculator, sample_data):
        """Test data hashing for cache validation."""
        hash1 = calculator._hash_data(sample_data)
        hash2 = calculator._hash_data(sample_data)

        # Same data should produce same hash
        assert hash1 == hash2

        # Modify data
        modified_data = sample_data.copy()
        modified_data[0] = OHLCVData(
            timestamp=modified_data[0].timestamp,
            open_price=modified_data[0].open_price + 1.0,
            high_price=modified_data[0].high_price + 1.0,
            low_price=modified_data[0].low_price + 1.0,
            close_price=modified_data[0].close_price + 1.0,
            volume=modified_data[0].volume,
        )

        hash3 = calculator._hash_data(modified_data)

        # Modified data should produce different hash
        assert hash1 != hash3

    def test_hash_data_empty(self, calculator):
        """Test data hashing with empty list."""
        hash_val = calculator._hash_data([])

        assert hash_val == "empty"

    def test_partial_indicator_calculation(self, calculator):
        """Test calculation when only some indicators have sufficient data."""
        base_ts = 1609459200000

        # Create data sufficient for RSI (needs 15) but not MACD (needs 35)
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + i * 0.5,
                high_price=101.0 + i * 0.5,
                low_price=99.0 + i * 0.5,
                close_price=100.0 + i * 0.5,
                volume=1000.0,
            )
            for i in range(20)
        ]

        result = calculator.calculate_all(data, Timeframe.MINUTE_5)

        # RSI should be calculated (needs 15 data points)
        assert result.rsi is not None

        # MACD should not be calculated (needs 35 data points)
        assert result.macd is None

        # Bollinger Bands should be calculated (needs 20 data points)
        assert result.bollinger_bands is not None
