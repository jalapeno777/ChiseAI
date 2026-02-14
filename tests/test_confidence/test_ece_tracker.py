"""Tests for ECE history tracking module.

Tests cover:
- Recording ECE to InfluxDB
- Retrieving ECE history
- Trend analysis
- Batch operations
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from confidence.ece import ECEBin, ECECalculator, ECEResult, SignalType
from confidence.ece_tracker import ECEHistoryPoint, ECEHistoryTracker, ECETrend

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_influx_client():
    """Create a mock InfluxDB client."""
    with patch("influxdb_client.InfluxDBClient") as mock_client_class:
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_query_api = MagicMock()

        mock_client.write_api.return_value = mock_write_api
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        yield {
            "client": mock_client,
            "write_api": mock_write_api,
            "query_api": mock_query_api,
            "client_class": mock_client_class,
        }


@pytest.fixture
def sample_ece_result():
    """Create a sample ECEResult for testing."""
    bins = [
        ECEBin(
            bin_index=i,
            bin_start=i / 10,
            bin_end=(i + 1) / 10,
            confidence=0.05 + i * 0.1,
            accuracy=0.06 + i * 0.09,
            sample_count=10,
        )
        for i in range(10)
    ]
    return ECEResult(
        ece=0.05,
        n_bins=10,
        total_samples=100,
        bins=bins,
        signal_type=SignalType.ENTRY,
        strategy_id="test_strategy",
    )


class TestECEHistoryTracker:
    """Tests for ECEHistoryTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = ECEHistoryTracker(
            url="http://test:8086",
            token="test_token",
            org="test_org",
            bucket="test_bucket",
        )

        assert tracker._url == "http://test:8086"
        assert tracker._token == "test_token"
        assert tracker.org == "test_org"
        assert tracker.bucket == "test_bucket"
        assert tracker._client is None
        assert tracker._write_api is None

    def test_initialization_with_client(self):
        """Test tracker initialization with existing client."""
        mock_client = MagicMock()
        tracker = ECEHistoryTracker(client=mock_client)

        assert tracker._client is mock_client
        assert not tracker._owned_client

    @pytest.mark.asyncio
    async def test_record_ece(self, mock_influx_client, sample_ece_result):
        """Test recording ECE to InfluxDB."""
        tracker = ECEHistoryTracker()

        result = await tracker.record_ece(sample_ece_result)

        assert result is True
        mock_influx_client["write_api"].write.assert_called_once()

        # Check the call arguments
        call_args = mock_influx_client["write_api"].write.call_args
        assert call_args.kwargs["bucket"] == "signals"
        assert call_args.kwargs["org"] == "chiseai"

    @pytest.mark.asyncio
    async def test_record_ece_with_timestamp(
        self, mock_influx_client, sample_ece_result
    ):
        """Test recording ECE with custom timestamp."""
        tracker = ECEHistoryTracker()
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        result = await tracker.record_ece(sample_ece_result, timestamp=timestamp)

        assert result is True
        mock_influx_client["write_api"].write.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_ece_failure(self, mock_influx_client, sample_ece_result):
        """Test handling of write failure."""
        mock_influx_client["write_api"].write.side_effect = Exception("Write failed")

        tracker = ECEHistoryTracker()
        result = await tracker.record_ece(sample_ece_result)

        assert result is False

    @pytest.mark.asyncio
    async def test_record_ece_batch(self, mock_influx_client):
        """Test batch recording of ECE results."""
        tracker = ECEHistoryTracker()

        results = [
            ECEResult(
                ece=0.05,
                n_bins=10,
                total_samples=100,
                bins=[],
                signal_type=SignalType.ENTRY,
                strategy_id="s1",
            ),
            ECEResult(
                ece=0.08,
                n_bins=10,
                total_samples=100,
                bins=[],
                signal_type=SignalType.EXIT,
                strategy_id="s1",
            ),
            ECEResult(
                ece=0.03,
                n_bins=10,
                total_samples=100,
                bins=[],
                signal_type=SignalType.STOP_LOSS,
                strategy_id="s1",
            ),
        ]

        count = await tracker.record_ece_batch(results)

        assert count == 3
        mock_influx_client["write_api"].write.assert_called_once()

        # Verify multiple points were written
        call_args = mock_influx_client["write_api"].write.call_args
        points = call_args.kwargs["record"]
        assert len(points) == 3

    @pytest.mark.asyncio
    async def test_record_ece_batch_failure(self, mock_influx_client):
        """Test handling of batch write failure."""
        mock_influx_client["write_api"].write.side_effect = Exception("Write failed")

        tracker = ECEHistoryTracker()
        results = [
            ECEResult(ece=0.05, n_bins=10, total_samples=100, bins=[]),
        ]

        count = await tracker.record_ece_batch(results)

        assert count == 0


class TestECEHistoryQuery:
    """Tests for querying ECE history."""

    @pytest.mark.asyncio
    async def test_get_history(self, mock_influx_client):
        """Test retrieving ECE history."""
        # Create mock table with records
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_record.values = {
            "ece": 0.05,
            "n_bins": 10,
            "total_samples": 100,
            "signal_type": "entry",
            "strategy_id": "test_strategy",
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        history = await tracker.get_history(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            days=30,
        )

        assert len(history) == 1
        assert history[0].ece == 0.05
        assert history[0].signal_type == SignalType.ENTRY
        assert history[0].strategy_id == "test_strategy"

    @pytest.mark.asyncio
    async def test_get_history_no_filters(self, mock_influx_client):
        """Test retrieving history without filters."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = ECEHistoryTracker()
        history = await tracker.get_history(days=7)

        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_query_failure(self, mock_influx_client):
        """Test handling of query failure."""
        mock_influx_client["query_api"].query.side_effect = Exception("Query failed")

        tracker = ECEHistoryTracker()
        history = await tracker.get_history()

        assert history == []


class TestECETrend:
    """Tests for ECE trend analysis."""

    @pytest.mark.asyncio
    async def test_get_trend(self, mock_influx_client):
        """Test trend analysis."""
        # Create mock records showing improving trend
        records = []
        for i in range(10):
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=UTC
            ) + timedelta(days=i)
            mock_record.values = {
                "ece": 0.2 - i * 0.01,  # Decreasing ECE (improving)
                "n_bins": 10,
                "total_samples": 100,
                "signal_type": "entry",
                "strategy_id": "test_strategy",
            }
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        trend = await tracker.get_trend(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            days=30,
        )

        assert trend is not None
        assert trend.strategy_id == "test_strategy"
        assert trend.signal_type == SignalType.ENTRY
        assert trend.trend_direction == "improving"
        assert trend.trend_slope < 0
        assert len(trend.points) == 10

    @pytest.mark.asyncio
    async def test_get_trend_degrading(self, mock_influx_client):
        """Test trend analysis for degrading calibration."""
        records = []
        for i in range(10):
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=UTC
            ) + timedelta(days=i)
            mock_record.values = {
                "ece": 0.1 + i * 0.01,  # Increasing ECE (degrading)
                "n_bins": 10,
                "total_samples": 100,
                "signal_type": "entry",
                "strategy_id": "test_strategy",
            }
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        trend = await tracker.get_trend(
            strategy_id="test_strategy",
            days=30,
        )

        assert trend is not None
        assert trend.trend_direction == "degrading"
        assert trend.trend_slope > 0

    @pytest.mark.asyncio
    async def test_get_trend_stable(self, mock_influx_client):
        """Test trend analysis for stable calibration."""
        records = []
        for i in range(10):
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=UTC
            ) + timedelta(days=i)
            mock_record.values = {
                "ece": 0.1,  # Constant ECE (stable)
                "n_bins": 10,
                "total_samples": 100,
                "signal_type": "entry",
                "strategy_id": "test_strategy",
            }
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        trend = await tracker.get_trend(
            strategy_id="test_strategy",
            days=30,
        )

        assert trend is not None
        assert trend.trend_direction == "stable"

    @pytest.mark.asyncio
    async def test_get_trend_insufficient_data(self, mock_influx_client):
        """Test trend analysis with insufficient data."""
        # Only 1 record
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime(2024, 1, 1, tzinfo=UTC)
        mock_record.values = {
            "ece": 0.1,
            "n_bins": 10,
            "total_samples": 100,
            "signal_type": "entry",
            "strategy_id": "test_strategy",
        }

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        trend = await tracker.get_trend(
            strategy_id="test_strategy",
            days=30,
        )

        assert trend is None

    @pytest.mark.asyncio
    async def test_get_trend_statistics(self, mock_influx_client):
        """Test trend statistics calculation."""
        records = []
        ece_values = [0.05, 0.08, 0.03, 0.12, 0.06]
        for i, ece in enumerate(ece_values):
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=UTC
            ) + timedelta(days=i)
            mock_record.values = {
                "ece": ece,
                "n_bins": 10,
                "total_samples": 100,
                "signal_type": "entry",
                "strategy_id": "test_strategy",
            }
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        trend = await tracker.get_trend(
            strategy_id="test_strategy",
            days=30,
        )

        assert trend is not None
        assert trend.current_ece == 0.06  # Last value
        assert trend.min_ece == 0.03
        assert trend.max_ece == 0.12
        assert trend.avg_ece == pytest.approx(0.068, abs=0.01)


class TestLatestECE:
    """Tests for getting latest ECE."""

    @pytest.mark.asyncio
    async def test_get_latest_ece(self, mock_influx_client):
        """Test retrieving latest ECE value."""
        records = []
        for i in range(5):
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=UTC
            ) + timedelta(days=i)
            mock_record.values = {
                "ece": 0.05 + i * 0.01,
                "n_bins": 10,
                "total_samples": 100,
                "signal_type": "entry",
                "strategy_id": "test_strategy",
            }
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        latest = await tracker.get_latest_ece(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
        )

        assert latest is not None
        assert latest.ece == 0.09  # Last value

    @pytest.mark.asyncio
    async def test_get_latest_ece_no_data(self, mock_influx_client):
        """Test retrieving latest ECE when no data exists."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = ECEHistoryTracker()
        latest = await tracker.get_latest_ece(strategy_id="test_strategy")

        assert latest is None


class TestGetAllStrategies:
    """Tests for getting all strategies with ECE history."""

    @pytest.mark.asyncio
    async def test_get_all_strategies(self, mock_influx_client):
        """Test retrieving all strategy IDs."""
        records = []
        for strategy_id in ["strategy_a", "strategy_b", "strategy_c"]:
            mock_record = MagicMock()
            mock_record.values = {"strategy_id": strategy_id}
            records.append(mock_record)

        mock_table = MagicMock()
        mock_table.records = records

        mock_influx_client["query_api"].query.return_value = [mock_table]

        tracker = ECEHistoryTracker()
        strategies = await tracker.get_all_strategies()

        assert len(strategies) == 3
        assert "strategy_a" in strategies
        assert "strategy_b" in strategies
        assert "strategy_c" in strategies
        # Should be sorted
        assert strategies == ["strategy_a", "strategy_b", "strategy_c"]

    @pytest.mark.asyncio
    async def test_get_all_strategies_empty(self, mock_influx_client):
        """Test retrieving strategies when none exist."""
        mock_influx_client["query_api"].query.return_value = []

        tracker = ECEHistoryTracker()
        strategies = await tracker.get_all_strategies()

        assert strategies == []

    @pytest.mark.asyncio
    async def test_get_all_strategies_query_failure(self, mock_influx_client):
        """Test handling of query failure."""
        mock_influx_client["query_api"].query.side_effect = Exception("Query failed")

        tracker = ECEHistoryTracker()
        strategies = await tracker.get_all_strategies()

        assert strategies == []


class TestECEHistoryPoint:
    """Tests for ECEHistoryPoint dataclass."""

    def test_history_point_creation(self):
        """Test ECEHistoryPoint creation."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        point = ECEHistoryPoint(
            timestamp=timestamp,
            ece=0.05,
            n_bins=10,
            total_samples=100,
            signal_type=SignalType.ENTRY,
            strategy_id="test_strategy",
        )

        assert point.timestamp == timestamp
        assert point.ece == 0.05
        assert point.n_bins == 10
        assert point.total_samples == 100
        assert point.signal_type == SignalType.ENTRY
        assert point.strategy_id == "test_strategy"

    def test_history_point_without_signal_type(self):
        """Test ECEHistoryPoint without signal type."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        point = ECEHistoryPoint(
            timestamp=timestamp,
            ece=0.05,
            n_bins=10,
            total_samples=100,
            signal_type=None,
            strategy_id="test_strategy",
        )

        assert point.signal_type is None


class TestECETrendDataclass:
    """Tests for ECETrend dataclass."""

    def test_trend_creation(self):
        """Test ECETrend creation."""
        points = [
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                ece=0.1,
                n_bins=10,
                total_samples=100,
            ),
            ECEHistoryPoint(
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                ece=0.08,
                n_bins=10,
                total_samples=100,
            ),
        ]

        trend = ECETrend(
            strategy_id="test_strategy",
            signal_type=SignalType.ENTRY,
            points=points,
            trend_direction="improving",
            trend_slope=-0.02,
            current_ece=0.08,
            avg_ece=0.09,
            min_ece=0.08,
            max_ece=0.1,
        )

        assert trend.strategy_id == "test_strategy"
        assert trend.signal_type == SignalType.ENTRY
        assert trend.trend_direction == "improving"
        assert trend.trend_slope == -0.02
        assert len(trend.points) == 2


class TestTrackerClose:
    """Tests for closing tracker connections."""

    @pytest.mark.asyncio
    async def test_close_owned_client(self, mock_influx_client):
        """Test closing tracker with owned client."""
        tracker = ECEHistoryTracker()
        await tracker._get_client()  # Initialize client

        await tracker.close()

        mock_influx_client["client"].close.assert_called_once()
        assert tracker._client is None
        assert tracker._write_api is None

    @pytest.mark.asyncio
    async def test_close_external_client(self):
        """Test closing tracker with external client."""
        mock_client = MagicMock()
        tracker = ECEHistoryTracker(client=mock_client)

        await tracker.close()

        # External client should not be closed, but reference should be cleared
        mock_client.close.assert_not_called()
        assert tracker._client is None

    @pytest.mark.asyncio
    async def test_close_without_init(self):
        """Test closing tracker that was never initialized."""
        tracker = ECEHistoryTracker()

        # Should not raise
        await tracker.close()

        assert tracker._client is None
        assert tracker._write_api is None
