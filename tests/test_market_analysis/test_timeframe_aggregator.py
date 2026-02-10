"""Tests for timeframe aggregator module."""

import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe
from market_analysis.timeframe_aggregator import (
    AggregationResult,
    TimeframeAggregator,
)


class TestAggregationResult:
    """Test cases for AggregationResult dataclass."""

    def test_creation(self):
        """Test creating AggregationResult."""
        data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]
        result = AggregationResult(
            timeframe=Timeframe.MINUTE_5,
            data=data,
            is_consistent=True,
            consistency_errors=[],
            aggregated_from=Timeframe.MINUTE_1,
        )
        assert result.timeframe == Timeframe.MINUTE_5
        assert len(result.data) == 1
        assert result.is_consistent is True


class TestTimeframeAggregator:
    """Test cases for TimeframeAggregator class."""

    @pytest.fixture
    def aggregator(self):
        """Create a TimeframeAggregator instance."""
        return TimeframeAggregator()

    @pytest.fixture
    def one_minute_data(self):
        """Create sample 1-minute OHLCV data."""
        base_ts = 1609459200000  # 2021-01-01 00:00:00 UTC
        return [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0 + i,
                high_price=110.0 + i,
                low_price=95.0 + i,
                close_price=105.0 + i,
                volume=1000.0,
            )
            for i in range(10)  # 10 minutes of data
        ]

    def test_aggregate_1m_to_5m(self, aggregator, one_minute_data):
        """Test aggregating 1m data to 5m."""
        result = aggregator.aggregate(
            one_minute_data, Timeframe.MINUTE_1, Timeframe.MINUTE_5
        )

        assert len(result) == 2  # 10 minutes -> 2 five-minute candles

        # Check first aggregated candle
        assert result[0].timestamp == 1609459200000
        assert result[0].open_price == 100.0  # First open
        assert result[0].close_price == 109.0  # Last close (5th candle)
        assert result[0].high_price == 114.0  # Max high
        assert result[0].low_price == 95.0  # Min low
        assert result[0].volume == 5000.0  # Sum of 5 volumes

    def test_aggregate_same_timeframe(self, aggregator, one_minute_data):
        """Test aggregating to same timeframe returns original data."""
        result = aggregator.aggregate(
            one_minute_data, Timeframe.MINUTE_1, Timeframe.MINUTE_1
        )

        assert len(result) == len(one_minute_data)
        assert result[0].timestamp == one_minute_data[0].timestamp

    def test_aggregate_invalid_direction(self, aggregator, one_minute_data):
        """Test that aggregating to smaller timeframe raises error."""
        with pytest.raises(ValueError, match="target must be larger timeframe"):
            aggregator.aggregate(
                one_minute_data, Timeframe.MINUTE_5, Timeframe.MINUTE_1
            )

    def test_aggregate_empty_data(self, aggregator):
        """Test aggregating empty data returns empty list."""
        result = aggregator.aggregate([], Timeframe.MINUTE_1, Timeframe.MINUTE_5)
        assert result == []

    def test_aggregate_1m_to_1h(self, aggregator):
        """Test aggregating 1m data to 1h."""
        # Create 60 minutes of data
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(60)
        ]

        result = aggregator.aggregate(data, Timeframe.MINUTE_1, Timeframe.HOUR_1)

        assert len(result) == 1
        assert result[0].open_price == 100.0
        assert result[0].close_price == 105.0
        assert result[0].high_price == 110.0
        assert result[0].low_price == 95.0
        assert result[0].volume == 60000.0

    def test_aggregate_with_gaps(self, aggregator):
        """Test aggregation handles gaps in data."""
        base_ts = 1609459200000
        # Data with a gap (missing minutes 2-4)
        data = [
            OHLCVData(
                timestamp=base_ts,  # Minute 0
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 60000,  # Minute 1
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 5 * 60000,  # Minute 5
                open_price=110.0,
                high_price=120.0,
                low_price=105.0,
                close_price=115.0,
                volume=1000.0,
            ),
        ]

        result = aggregator.aggregate(data, Timeframe.MINUTE_1, Timeframe.MINUTE_5)

        # Should create separate buckets for the gap
        assert len(result) == 2

    def test_validate_consistency_match(self, aggregator):
        """Test consistency validation with matching data."""
        aggregated = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]
        fetched = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]

        is_consistent, errors = aggregator.validate_consistency(
            aggregated, fetched, Timeframe.MINUTE_5
        )

        assert is_consistent is True
        assert len(errors) == 0

    def test_validate_consistency_mismatch(self, aggregator):
        """Test consistency validation with mismatched data."""
        aggregated = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]
        fetched = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=101.0,  # Different
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]

        is_consistent, errors = aggregator.validate_consistency(
            aggregated, fetched, Timeframe.MINUTE_5
        )

        assert is_consistent is False
        assert len(errors) > 0

    def test_validate_consistency_missing_timestamps(self, aggregator):
        """Test consistency validation with missing timestamps."""
        aggregated = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]
        fetched = [
            OHLCVData(
                timestamp=1609459500000,  # Different timestamp
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]

        is_consistent, errors = aggregator.validate_consistency(
            aggregated, fetched, Timeframe.MINUTE_5
        )

        assert is_consistent is False
        assert any("Timestamps" in e for e in errors)

    def test_validate_consistency_both_empty(self, aggregator):
        """Test consistency validation with both empty lists."""
        is_consistent, errors = aggregator.validate_consistency(
            [], [], Timeframe.MINUTE_5
        )

        assert is_consistent is True
        assert len(errors) == 0

    def test_values_match_within_tolerance(self, aggregator):
        """Test value matching within tolerance."""
        assert aggregator._values_match(100.0, 100.05) is True  # 0.05% diff

    def test_values_match_outside_tolerance(self, aggregator):
        """Test value matching outside tolerance."""
        assert aggregator._values_match(100.0, 101.0) is False  # 1% diff

    def test_values_match_zero(self, aggregator):
        """Test value matching with zeros."""
        assert aggregator._values_match(0.0, 0.0) is True
        assert aggregator._values_match(0.0, 1.0) is False
        assert aggregator._values_match(1.0, 0.0) is False

    def test_aggregate_and_validate(self, aggregator):
        """Test full aggregate and validate workflow."""
        # Create 1m data
        base_ts = 1609459200000
        data_1m = [
            OHLCVData(
                timestamp=base_ts + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        # Create matching 5m data (2 candles)
        data_5m = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 5 * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            ),
        ]

        data_map = {
            Timeframe.MINUTE_1: data_1m,
            Timeframe.MINUTE_5: data_5m,
        }

        results = aggregator.aggregate_and_validate(data_map)

        assert Timeframe.MINUTE_1 in results
        assert Timeframe.MINUTE_5 in results
        assert results[Timeframe.MINUTE_5].is_consistent is True

    def test_get_consistency_summary(self, aggregator):
        """Test consistency summary generation."""
        results = {
            Timeframe.MINUTE_1: AggregationResult(
                timeframe=Timeframe.MINUTE_1,
                data=[],
                is_consistent=True,
                consistency_errors=[],
            ),
            Timeframe.MINUTE_5: AggregationResult(
                timeframe=Timeframe.MINUTE_5,
                data=[],
                is_consistent=False,
                consistency_errors=["Error 1", "Error 2"],
            ),
        }

        summary = aggregator.get_consistency_summary(results)

        assert summary["total_timeframes"] == 2
        assert summary["consistent_timeframes"] == 1
        assert summary["inconsistent_timeframes"] == 1
        assert summary["total_consistency_errors"] == 2
        assert summary["overall_consistent"] is False
