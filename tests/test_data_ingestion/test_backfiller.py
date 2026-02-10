"""Tests for backfiller module."""

from unittest.mock import AsyncMock, Mock

import pytest

from data_ingestion.backfiller import Backfiller, BackfillResult
from data_ingestion.gap_detector import DataGap
from data_ingestion.ohlcv_fetcher import OHLCVData, OHLCVFetcher
from data_ingestion.timeframe_config import Timeframe


class TestBackfillResult:
    """Test cases for BackfillResult dataclass."""

    def test_creation_success(self):
        """Test creating successful BackfillResult."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )
        result = BackfillResult(
            gap=gap,
            fetched_candles=10,
            success=True,
            error_message=None,
        )
        assert result.success is True
        assert result.fetched_candles == 10
        assert result.error_message is None

    def test_creation_failure(self):
        """Test creating failed BackfillResult."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )
        result = BackfillResult(
            gap=gap,
            fetched_candles=0,
            success=False,
            error_message="Network error",
        )
        assert result.success is False
        assert result.fetched_candles == 0
        assert result.error_message == "Network error"


class TestBackfiller:
    """Test cases for Backfiller class."""

    @pytest.fixture
    def mock_fetcher(self):
        """Create a mock OHLCVFetcher."""
        fetcher = Mock(spec=OHLCVFetcher)
        fetcher.fetch = AsyncMock()
        return fetcher

    @pytest.fixture
    def backfiller(self, mock_fetcher):
        """Create a Backfiller instance."""
        return Backfiller(fetcher=mock_fetcher)

    @pytest.fixture
    def sample_gap(self):
        """Create a sample data gap."""
        return DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )

    @pytest.mark.asyncio
    async def test_backfill_gap_success(self, backfiller, mock_fetcher, sample_gap):
        """Test successful gap backfill."""
        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0 + i,
                high_price=110.0 + i,
                low_price=95.0 + i,
                close_price=105.0 + i,
                volume=1000.0,
            )
            for i in range(10)
        ]
        mock_fetcher.fetch.return_value = mock_data

        result = await backfiller.backfill_gap("BTC/USDT", sample_gap)

        assert result.success is True
        assert result.fetched_candles == 10
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_backfill_gap_no_data(self, backfiller, mock_fetcher, sample_gap):
        """Test backfill when no data is returned."""
        mock_fetcher.fetch.return_value = []

        result = await backfiller.backfill_gap("BTC/USDT", sample_gap)

        assert result.success is False
        assert result.fetched_candles == 0
        assert "No data returned" in result.error_message

    @pytest.mark.asyncio
    async def test_backfill_gap_fetch_error(self, backfiller, mock_fetcher, sample_gap):
        """Test backfill when fetch raises exception."""
        mock_fetcher.fetch.side_effect = Exception("API Error")

        result = await backfiller.backfill_gap("BTC/USDT", sample_gap)

        assert result.success is False
        assert result.fetched_candles == 0
        assert "API Error" in result.error_message

    @pytest.mark.asyncio
    async def test_backfill_gap_partial(self, backfiller, mock_fetcher, sample_gap):
        """Test backfill with partial data."""
        # Return only 3 candles when 10 expected
        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(3)
        ]
        mock_fetcher.fetch.return_value = mock_data

        result = await backfiller.backfill_gap("BTC/USDT", sample_gap)

        assert result.success is True
        assert result.fetched_candles == 3

    @pytest.mark.asyncio
    async def test_backfill_gap_max_limit(self, backfiller, mock_fetcher, sample_gap):
        """Test that max_backfill_candles is respected."""
        backfiller.max_backfill_candles = 5

        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(5)
        ]
        mock_fetcher.fetch.return_value = mock_data

        await backfiller.backfill_gap("BTC/USDT", sample_gap)

        # Verify fetch was called with limit=5
        call_args = mock_fetcher.fetch.call_args
        assert call_args.kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_backfill_gaps_multiple(self, backfiller, mock_fetcher):
        """Test backfilling multiple gaps."""
        gaps = [
            DataGap(
                start_timestamp=1609459200000,
                end_timestamp=1609459800000,
                expected_candles=10,
                timeframe=Timeframe.MINUTE_1,
            ),
            DataGap(
                start_timestamp=1609462800000,
                end_timestamp=1609463400000,
                expected_candles=10,
                timeframe=Timeframe.MINUTE_1,
            ),
        ]

        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(10)
        ]
        mock_fetcher.fetch.return_value = mock_data

        results = await backfiller.backfill_gaps("BTC/USDT", gaps)

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_backfill_gaps_empty_list(self, backfiller):
        """Test backfilling with empty gap list."""
        results = await backfiller.backfill_gaps("BTC/USDT", [])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_detect_and_backfill(self, backfiller, mock_fetcher):
        """Test detect and backfill combined operation."""
        # Data with a gap
        data = [
            OHLCVData(
                timestamp=1609459200000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            ),
            OHLCVData(
                timestamp=1609459800000,  # 10 min gap
                open_price=105.0,
                high_price=115.0,
                low_price=100.0,
                close_price=110.0,
                volume=1500.0,
            ),
        ]

        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(10)
        ]
        mock_fetcher.fetch.return_value = mock_data

        gaps, results = await backfiller.detect_and_backfill(
            "BTC/USDT", data, Timeframe.MINUTE_1
        )

        assert len(gaps) == 1
        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_detect_and_backfill_no_gaps(self, backfiller, mock_fetcher):
        """Test detect and backfill with no gaps."""
        # Continuous data
        data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(10)
        ]

        gaps, results = await backfiller.detect_and_backfill(
            "BTC/USDT", data, Timeframe.MINUTE_1
        )

        assert len(gaps) == 0
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_detect_and_backfill_batch(self, backfiller, mock_fetcher):
        """Test batch detect and backfill across multiple timeframes."""
        data_map = {
            Timeframe.MINUTE_1: [
                OHLCVData(
                    timestamp=1609459200000,
                    open_price=100.0,
                    high_price=110.0,
                    low_price=95.0,
                    close_price=105.0,
                    volume=1000.0,
                ),
                OHLCVData(
                    timestamp=1609459800000,  # Gap
                    open_price=105.0,
                    high_price=115.0,
                    low_price=100.0,
                    close_price=110.0,
                    volume=1500.0,
                ),
            ],
            Timeframe.MINUTE_5: [
                OHLCVData(
                    timestamp=1609459200000,
                    open_price=100.0,
                    high_price=110.0,
                    low_price=95.0,
                    close_price=105.0,
                    volume=5000.0,
                )
            ],
        }

        mock_data = [
            OHLCVData(
                timestamp=1609459200000 + i * 60000,
                open_price=100.0,
                high_price=110.0,
                low_price=95.0,
                close_price=105.0,
                volume=1000.0,
            )
            for i in range(10)
        ]
        mock_fetcher.fetch.return_value = mock_data

        results = await backfiller.detect_and_backfill_batch("BTC/USDT", data_map)

        assert len(results) == 2
        assert Timeframe.MINUTE_1 in results
        assert Timeframe.MINUTE_5 in results

    def test_get_backfill_summary(self, backfiller):
        """Test backfill summary generation."""
        gap = DataGap(
            start_timestamp=1609459200000,
            end_timestamp=1609459800000,
            expected_candles=10,
            timeframe=Timeframe.MINUTE_1,
        )

        results = [
            BackfillResult(
                gap=gap, fetched_candles=10, success=True, error_message=None
            ),
            BackfillResult(
                gap=gap, fetched_candles=0, success=False, error_message="Error"
            ),
        ]

        summary = backfiller.get_backfill_summary(results)

        assert summary["total_gaps"] == 2
        assert summary["successful_gaps"] == 1
        assert summary["failed_gaps"] == 1
        assert summary["total_candles_fetched"] == 10
