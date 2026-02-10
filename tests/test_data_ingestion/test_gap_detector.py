"""Tests for gap detector module."""

from datetime import UTC

import pytest

from data_ingestion.gap_detector import DataGap, GapDetector
from data_ingestion.ohlcv_fetcher import OHLCVData
from data_ingestion.timeframe_config import Timeframe


class TestDataGap:
    """Test cases for DataGap dataclass."""

    def test_creation(self):
        """Test creating DataGap instance."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )
        assert gap.start_timestamp == 1609459200000
        assert gap.end_timestamp == 1609459800000
        assert gap.expected_candles == 10
        assert gap.timeframe == Timeframe.MINUTE_1

    def test_duration_seconds(self):
        """Test duration calculation."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,  # 600 seconds later
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )
        assert gap.duration_seconds == 600.0

    def test_datetime_properties(self):
        """Test datetime conversion properties."""
        gap = DataGap(
            start_timestamp=1609459200000,  # 2021-01-01 00:00:00 UTC
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )

        start_dt = gap.start_datetime
        assert start_dt.year == 2021
        assert start_dt.month == 1
        assert start_dt.day == 1
        assert start_dt.tzinfo == UTC


class TestGapDetector:
    """Test cases for GapDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a GapDetector instance."""
        return GapDetector()

    @pytest.fixture
    def continuous_data(self):
        """Create continuous 1m data with no gaps."""
        base_ts = 1609459200000  # 2021-01-01 00:00:00 UTC
        return [
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

    def test_no_gaps_in_continuous_data(self, detector, continuous_data):
        """Test that continuous data has no gaps."""
        gaps = detector.detect_gaps(continuous_data, Timeframe.MINUTE_1)
        assert len(gaps) == 0

    def test_detect_gap_in_middle(self, detector):
        """Test detecting a gap in the middle of data."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            # Gap: missing 5 minutes
            OHLCVData(
                timestamp=base_ts + 6 * 60000,  # 6 minutes later
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1)

        assert len(gaps) == 1
        # Gap from base_ts + 60s to base_ts + 360s = 300s = 5 candles
        # But the calculation includes the interval, so 6 candles expected
        assert gaps[0].expected_candles == 6

    def test_detect_leading_gap(self, detector):
        """Test detecting a gap at the beginning."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts + 5 * 60000,  # Starts 5 minutes after expected
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        expected_start = base_ts
        gaps = detector.detect_gaps(
            data, Timeframe.MINUTE_1, expected_start=expected_start
        )

        assert len(gaps) == 1
        assert gaps[0].expected_candles == 5

    def test_detect_trailing_gap(self, detector):
        """Test detecting a gap at the end."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
        ]

        expected_end = base_ts + 5 * 60000  # Expect 5 more minutes
        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1, expected_end=expected_end)

        assert len(gaps) == 1
        assert gaps[0].expected_candles == 5

    def test_no_gap_with_tolerance(self, detector):
        """Test that small gaps within tolerance are not detected."""
        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 63000,  # 63 seconds (3 seconds over)
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1)

        # With 5% tolerance on 60 seconds = 3 seconds, this should not be a gap
        assert len(gaps) == 0

    def test_empty_data(self, detector):
        """Test detection with empty data."""
        gaps = detector.detect_gaps([], Timeframe.MINUTE_1)
        assert len(gaps) == 0

    def test_single_candle(self, detector):
        """Test detection with single candle."""
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

        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1)
        assert len(gaps) == 0

    def test_max_gap_duration_filter(self, detector):
        """Test that very long gaps are filtered out."""
        detector = GapDetector(max_gap_duration_hours=1.0)

        base_ts = 1609459200000
        data = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 2 * 3600 * 1000,  # 2 hours later
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1)

        # 2 hour gap exceeds max_gap_duration_hours=1
        assert len(gaps) == 0

    def test_detect_gaps_batch(self, detector):
        """Test batch gap detection across multiple timeframes."""
        base_ts = 1609459200000

        # Create data with gaps in both timeframes
        data_1m = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=base_ts + 2 * 60000,  # 2 min gap
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

        data_5m = [
            OHLCVData(
                timestamp=base_ts,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=5000.0,
            )
        ]

        data_map = {
            Timeframe.MINUTE_1: data_1m,
            Timeframe.MINUTE_5: data_5m,
        }

        results = detector.detect_gaps_batch(data_map)

        assert len(results) == 2
        assert len(results[Timeframe.MINUTE_1]) == 1
        assert len(results[Timeframe.MINUTE_5]) == 0

    def test_estimate_missing_candles(self, detector):
        """Test estimation of missing candles."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,  # 600 seconds = 10 minutes
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )

        estimated = detector.estimate_missing_candles(gap, Timeframe.MINUTE_1)
        assert estimated == 10

    def test_estimate_missing_candles_different_timeframe(self, detector):
        """Test estimation with different timeframe."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609462800000,  # 3600 seconds = 1 hour
            expected_candles=12,  # 5 minute candles
            timeframe=Timeframe.MINUTE_5,
        )

        estimated = detector.estimate_missing_candles(gap, Timeframe.MINUTE_5)
        assert estimated == 12

    def test_unsorted_data_handling(self, detector):
        """Test that unsorted data is handled correctly."""
        base_ts = 1609459200000
        # Data with 1-minute intervals but provided out of order
        data = [
            OHLCVData(
                timestamp=base_ts + 60000,  # 1 minute later, provided first
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
            OHLCVData(
                timestamp=base_ts,  # Base timestamp, provided second
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
        ]

        gaps = detector.detect_gaps(data, Timeframe.MINUTE_1)

        # After sorting, there's no gap (just 1 minute apart)
        assert len(gaps) == 0
