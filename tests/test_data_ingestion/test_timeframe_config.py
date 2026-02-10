"""Tests for timeframe configuration module."""

import pytest

from data_ingestion.timeframe_config import (
    TIMEFRAME_CONFIG,
    Timeframe,
    TimeframeConfig,
    get_all_timeframes,
    get_freshness_threshold,
    timeframe_from_string,
)


class TestTimeframeConfig:
    """Test cases for TimeframeConfig dataclass."""

    def test_timeframe_config_creation(self):
        """Test creating a TimeframeConfig instance."""
        config = TimeframeConfig(
            interval_seconds=60,
            freshness_multiplier=2.0,
            ccxt_code="1m",
            aggregation_factor=1,
        )
        assert config.interval_seconds == 60
        assert config.freshness_multiplier == 2.0
        assert config.ccxt_code == "1m"
        assert config.aggregation_factor == 1


class TestTimeframeEnum:
    """Test cases for Timeframe enum."""

    def test_all_timeframes_exist(self):
        """Test that all 6 required timeframes are defined."""
        expected = ["1m", "5m", "15m", "1h", "4h", "1d"]
        actual = [tf.value for tf in Timeframe]
        assert sorted(actual) == sorted(expected)

    def test_timeframe_values(self):
        """Test timeframe value strings."""
        assert Timeframe.MINUTE_1.value == "1m"
        assert Timeframe.MINUTE_5.value == "5m"
        assert Timeframe.MINUTE_15.value == "15m"
        assert Timeframe.HOUR_1.value == "1h"
        assert Timeframe.HOUR_4.value == "4h"
        assert Timeframe.DAY_1.value == "1d"


class TestTimeframeConfigMapping:
    """Test cases for TIMEFRAME_CONFIG mapping."""

    def test_all_timeframes_have_config(self):
        """Test that all timeframes have configuration."""
        for tf in Timeframe:
            assert tf in TIMEFRAME_CONFIG

    def test_interval_seconds_correct(self):
        """Test that interval seconds are correct for each timeframe."""
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_1].interval_seconds == 60
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_5].interval_seconds == 300
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_15].interval_seconds == 900
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_1].interval_seconds == 3600
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_4].interval_seconds == 14400
        assert TIMEFRAME_CONFIG[Timeframe.DAY_1].interval_seconds == 86400

    def test_ccxt_codes_correct(self):
        """Test that CCXT codes are correct."""
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_1].ccxt_code == "1m"
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_5].ccxt_code == "5m"
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_15].ccxt_code == "15m"
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_1].ccxt_code == "1h"
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_4].ccxt_code == "4h"
        assert TIMEFRAME_CONFIG[Timeframe.DAY_1].ccxt_code == "1d"

    def test_aggregation_factors(self):
        """Test aggregation factors are correct."""
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_1].aggregation_factor == 1
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_5].aggregation_factor == 5
        assert TIMEFRAME_CONFIG[Timeframe.MINUTE_15].aggregation_factor == 15
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_1].aggregation_factor == 60
        assert TIMEFRAME_CONFIG[Timeframe.HOUR_4].aggregation_factor == 240
        assert TIMEFRAME_CONFIG[Timeframe.DAY_1].aggregation_factor == 1440

    def test_freshness_multiplier_default(self):
        """Test default freshness multiplier is 2.0 for all timeframes."""
        for tf in Timeframe:
            assert TIMEFRAME_CONFIG[tf].freshness_multiplier == 2.0


class TestGetFreshnessThreshold:
    """Test cases for get_freshness_threshold function."""

    def test_freshness_threshold_calculation(self):
        """Test freshness threshold calculation."""
        # For 1m: 60 * 2.0 = 120 seconds
        assert get_freshness_threshold(Timeframe.MINUTE_1) == 120.0

        # For 5m: 300 * 2.0 = 600 seconds
        assert get_freshness_threshold(Timeframe.MINUTE_5) == 600.0

        # For 1h: 3600 * 2.0 = 7200 seconds
        assert get_freshness_threshold(Timeframe.HOUR_1) == 7200.0

    def test_all_timeframes_have_threshold(self):
        """Test that all timeframes have calculable thresholds."""
        for tf in Timeframe:
            threshold = get_freshness_threshold(tf)
            assert threshold > 0
            assert isinstance(threshold, float)


class TestGetAllTimeframes:
    """Test cases for get_all_timeframes function."""

    def test_returns_all_timeframes(self):
        """Test that function returns all 6 timeframes."""
        timeframes = get_all_timeframes()
        assert len(timeframes) == 6

    def test_returns_correct_order(self):
        """Test that timeframes are returned in ascending order."""
        timeframes = get_all_timeframes()
        intervals = [TIMEFRAME_CONFIG[tf].interval_seconds for tf in timeframes]
        assert intervals == sorted(intervals)

    def test_first_is_1m(self):
        """Test that first timeframe is 1m."""
        timeframes = get_all_timeframes()
        assert timeframes[0] == Timeframe.MINUTE_1

    def test_last_is_1d(self):
        """Test that last timeframe is 1d."""
        timeframes = get_all_timeframes()
        assert timeframes[-1] == Timeframe.DAY_1


class TestTimeframeFromString:
    """Test cases for timeframe_from_string function."""

    def test_valid_timeframes(self):
        """Test parsing valid timeframe strings."""
        assert timeframe_from_string("1m") == Timeframe.MINUTE_1
        assert timeframe_from_string("5m") == Timeframe.MINUTE_5
        assert timeframe_from_string("15m") == Timeframe.MINUTE_15
        assert timeframe_from_string("1h") == Timeframe.HOUR_1
        assert timeframe_from_string("4h") == Timeframe.HOUR_4
        assert timeframe_from_string("1d") == Timeframe.DAY_1

    def test_invalid_timeframe_raises_error(self):
        """Test that invalid timeframe strings raise ValueError."""
        with pytest.raises(ValueError, match="Unknown timeframe"):
            timeframe_from_string("30m")

        with pytest.raises(ValueError, match="Unknown timeframe"):
            timeframe_from_string("invalid")

        with pytest.raises(ValueError, match="Unknown timeframe"):
            timeframe_from_string("")

    def test_case_sensitivity(self):
        """Test that timeframe strings are case sensitive."""
        with pytest.raises(ValueError):
            timeframe_from_string("1M")

        with pytest.raises(ValueError):
            timeframe_from_string("1H")
