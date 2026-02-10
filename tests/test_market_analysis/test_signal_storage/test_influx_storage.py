"""Tests for InfluxDB storage implementation."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from market_analysis.signal_storage.influx_storage import InfluxSignalStorage
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)


@pytest.fixture
def mock_influx_client():
    """Create a mock InfluxDB client."""
    client = MagicMock()
    client.write_api.return_value = MagicMock()
    client.query_api.return_value = MagicMock()
    return client


@pytest.fixture
def storage(mock_influx_client):
    """Create InfluxSignalStorage with mock client."""
    return InfluxSignalStorage(client=mock_influx_client, bucket="test-bucket")


class TestInfluxSignalStorageInit:
    """Tests for InfluxSignalStorage initialization."""

    def test_init_with_client(self, mock_influx_client):
        """Test initialization with existing client."""
        storage = InfluxSignalStorage(
            client=mock_influx_client, bucket="test-bucket", org="test-org"
        )
        assert storage._client == mock_influx_client
        assert storage.bucket == "test-bucket"
        assert storage.org == "test-org"
        assert storage._owned_client is False

    def test_init_without_client(self):
        """Test initialization without client (creates owned client)."""
        storage = InfluxSignalStorage(
            url="http://localhost:8086",
            token="test-token",
            bucket="test-bucket",
        )
        assert storage._client is None
        assert storage._owned_client is True


class TestInfluxSignalStorageStoreSignal:
    """Tests for store_signal method."""

    @pytest.mark.asyncio
    async def test_store_signal_success(self, storage, mock_influx_client):
        """Test successful signal storage."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
            indicators_used=["rsi", "macd"],
            timeframes_used=["1h", "4h"],
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await storage.store_signal(signal)

            assert result is True
            mock_influx_client.write_api.return_value.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_signal_failure(self, storage, mock_influx_client):
        """Test signal storage failure."""
        signal = SignalRecord(
            signal_id="test-uuid",
            token="BTC",
            timestamp=1234567890000,
            direction=SignalDirection.LONG,
            confidence=0.75,
            entry_price=50000.0,
            score=75.0,
        )

        mock_influx_client.write_api.return_value.write.side_effect = Exception(
            "Write failed"
        )

        result = await storage.store_signal(signal)
        assert result is False


class TestInfluxSignalStorageStoreOutcome:
    """Tests for store_outcome method."""

    @pytest.mark.asyncio
    async def test_store_outcome_success(self, storage, mock_influx_client):
        """Test successful outcome storage."""
        outcome = OutcomeRecord(
            signal_id="test-uuid",
            exit_timestamp=1234567950000,
            is_win=True,
            pnl=100.0,
            exit_price=50100.0,
            duration_hours=1.5,
            outcome_type=OutcomeType.TP_HIT,
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await storage.store_outcome(outcome)

            assert result is True
            mock_influx_client.write_api.return_value.write.assert_called_once()


class TestInfluxSignalStorageQuerySignals:
    """Tests for query_signals method."""

    @pytest.mark.asyncio
    async def test_query_signals_empty_result(self, storage, mock_influx_client):
        """Test querying with empty result."""
        mock_influx_client.query_api.return_value.query.return_value = []

        results = await storage.query_signals(token="BTC")

        assert results == []

    @pytest.mark.asyncio
    async def test_query_signals_with_filters(self, storage, mock_influx_client):
        """Test querying with filters."""
        mock_influx_client.query_api.return_value.query.return_value = []

        results = await storage.query_signals(
            token="BTC",
            direction="LONG",
            start_time=1234567800000,
            end_time=1234567900000,
            min_confidence=0.5,
            max_confidence=0.9,
            limit=50,
        )

        assert results == []
        mock_influx_client.query_api.return_value.query.assert_called_once()


class TestInfluxSignalStorageGetSignalById:
    """Tests for get_signal_by_id method."""

    @pytest.mark.asyncio
    async def test_get_signal_by_id_not_found(self, storage, mock_influx_client):
        """Test getting non-existent signal."""
        mock_influx_client.query_api.return_value.query.return_value = []

        result = await storage.get_signal_by_id("non-existent")

        assert result is None


class TestInfluxSignalStorageGetOutcomeBySignalId:
    """Tests for get_outcome_by_signal_id method."""

    @pytest.mark.asyncio
    async def test_get_outcome_by_signal_id_not_found(
        self, storage, mock_influx_client
    ):
        """Test getting non-existent outcome."""
        mock_influx_client.query_api.return_value.query.return_value = []

        result = await storage.get_outcome_by_signal_id("non-existent")

        assert result is None


class TestInfluxSignalStorageCalculateAccuracy:
    """Tests for calculate_prediction_accuracy method."""

    @pytest.mark.asyncio
    async def test_calculate_accuracy_empty(self, storage, mock_influx_client):
        """Test accuracy calculation with no data."""
        mock_influx_client.query_api.return_value.query.return_value = []

        result = await storage.calculate_prediction_accuracy()

        assert result["total_signals"] == 0
        assert result["accuracy"] == 0.0


class TestInfluxSignalStorageClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_owned_client(self, mock_influx_client):
        """Test closing owned client."""
        storage = InfluxSignalStorage(
            url="http://localhost:8086",
            token="test-token",
            bucket="test-bucket",
        )

        mock_write_api = MagicMock()
        storage._write_api = mock_write_api
        storage._client = mock_influx_client

        await storage.close()

        mock_write_api.close.assert_called_once()
        mock_influx_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_shared_client(self, storage, mock_influx_client):
        """Test closing shared client (should not close)."""
        mock_write_api = MagicMock()
        storage._write_api = mock_write_api
        storage._client = mock_influx_client
        storage._owned_client = False

        await storage.close()

        mock_write_api.close.assert_called_once()
        mock_influx_client.close.assert_not_called()


class TestInfluxSignalStorageHelpers:
    """Tests for helper methods."""

    def test_ms_to_rfc3339(self, storage):
        """Test timestamp conversion."""
        rfc3339 = storage._ms_to_rfc3339(1234567890000)
        assert "2009-02-13" in rfc3339  # Known date from this timestamp

    def test_record_to_signal_none(self, storage):
        """Test record conversion with invalid data."""
        result = storage._record_to_signal(None)
        assert result is None

    def test_record_to_outcome_none(self, storage):
        """Test outcome conversion with invalid data."""
        result = storage._record_to_outcome(None)
        assert result is None
