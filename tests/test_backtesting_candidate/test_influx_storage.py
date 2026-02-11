"""Tests for InfluxDB storage."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from backtesting.candidate.influx_storage import CandidateResultStorage
from backtesting.candidate.models import (
    BacktestMetrics,
    CandidateResult,
    CandidateStatus,
    RankingCriteria,
    RankingScore,
    WalkForwardWindow,
)


class TestCandidateResultStorage:
    """Tests for CandidateResultStorage."""

    def test_default_initialization(self) -> None:
        """Test default initialization from environment."""
        storage = CandidateResultStorage()

        # Just verify the storage initializes with some defaults
        assert storage.url is not None
        assert storage.token is not None
        assert storage.org is not None
        assert storage.bucket is not None

    def test_custom_initialization(self) -> None:
        """Test custom initialization."""
        storage = CandidateResultStorage(
            url="http://custom:8086",
            token="custom-token",
            org="custom-org",
            bucket="custom-bucket",
        )

        assert storage.url == "http://custom:8086"
        assert storage.token == "custom-token"
        assert storage.org == "custom-org"
        assert storage.bucket == "custom-bucket"

    def create_test_result(self) -> CandidateResult:
        """Create a test candidate result."""
        window = WalkForwardWindow(
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 1, 31),
            test_start=datetime(2024, 1, 31),
            test_end=datetime(2024, 2, 7),
        )

        result = CandidateResult(
            candidate_id="test-001",
            strategy_id="strategy-001",
            version="1.0.0",
            status=CandidateStatus.COMPLETED,
            window=window,
            composite_score=75.0,
            rank_position=1,
            completed_at=datetime(2024, 2, 7, 12, 0, 0),
        )

        result.metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown_pct=15.0,
            win_rate_pct=55.0,
            profit_factor=1.8,
            total_return_pct=25.0,
            volatility_pct=20.0,
            calmar_ratio=1.67,
            sortino_ratio=2.0,
            trade_count=50,
        )

        result.ranking_scores = [
            RankingScore(
                criteria=RankingCriteria.SHARPE_RATIO,
                raw_value=1.5,
                normalized_score=75.0,
                weight=0.3,
                weighted_score=22.5,
            ),
        ]

        return result

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_store_result(self, mock_client_class) -> None:
        """Test storing a single result."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        result = self.create_test_result()

        success = storage.store_result(result)

        assert success is True
        assert mock_write_api.write.called

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_store_results(self, mock_client_class) -> None:
        """Test storing multiple results."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        results = [self.create_test_result() for _ in range(3)]

        stored = storage.store_results(results)

        assert stored == 3
        assert mock_write_api.write.call_count == 3

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_store_result_failure(self, mock_client_class) -> None:
        """Test handling of store failure."""
        mock_client = MagicMock()
        mock_write_api = MagicMock()
        mock_write_api.write.side_effect = Exception("Connection error")
        mock_client.write_api.return_value = mock_write_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        result = self.create_test_result()

        success = storage.store_result(result)

        assert success is False

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_query_results(self, mock_client_class) -> None:
        """Test querying results."""
        # Mock query response
        mock_record = MagicMock()
        mock_record.values = {"candidate_id": "test-001", "sharpe_ratio": 1.5}

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_query_api = MagicMock()
        mock_query_api.query.return_value = [mock_table]

        mock_client = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        results = storage.query_results(strategy_id="strategy-001")

        assert len(results) == 1
        assert results[0]["candidate_id"] == "test-001"

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_query_results_failure(self, mock_client_class) -> None:
        """Test handling of query failure."""
        mock_query_api = MagicMock()
        mock_query_api.query.side_effect = Exception("Query error")

        mock_client = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        results = storage.query_results()

        assert results == []

    @patch("backtesting.candidate.influx_storage.InfluxDBClient")
    def test_get_latest_results(self, mock_client_class) -> None:
        """Test getting latest results."""
        mock_record = MagicMock()
        mock_record.values = {"candidate_id": "test-001", "_time": datetime.now()}

        mock_table = MagicMock()
        mock_table.records = [mock_record]

        mock_query_api = MagicMock()
        mock_query_api.query.return_value = [mock_table]

        mock_client = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        storage = CandidateResultStorage()
        results = storage.get_latest_results(limit=10)

        assert len(results) == 1

    def test_close(self) -> None:
        """Test closing storage connection."""
        storage = CandidateResultStorage()
        storage._client = MagicMock()

        storage.close()

        assert storage._client is None
        assert storage._write_api is None
