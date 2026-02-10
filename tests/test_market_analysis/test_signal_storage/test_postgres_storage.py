"""Tests for PostgreSQL storage implementation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
)
from market_analysis.signal_storage.postgres_storage import PostgresSignalStorage


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def storage(mock_pool):
    """Create PostgresSignalStorage with mock pool."""
    storage = PostgresSignalStorage(dsn="postgresql://test")
    storage._pool = mock_pool
    storage._owned_pool = False
    return storage


class TestPostgresSignalStorageInit:
    """Tests for PostgresSignalStorage initialization."""

    def test_init_with_pool(self, mock_pool):
        """Test initialization with existing pool."""
        storage = PostgresSignalStorage(pool=mock_pool)
        assert storage._pool == mock_pool
        assert storage._owned_pool is False

    def test_init_with_dsn(self):
        """Test initialization with DSN."""
        storage = PostgresSignalStorage(dsn="postgresql://user:pass@localhost/db")
        assert storage._pool is None
        assert storage._dsn == "postgresql://user:pass@localhost/db"
        assert storage._owned_pool is True

    def test_init_with_params(self):
        """Test initialization with connection parameters."""
        storage = PostgresSignalStorage(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        assert storage._host == "localhost"
        assert storage._port == 5432


class TestPostgresSignalStorageInitializeSchema:
    """Tests for initialize_schema method."""

    @pytest.mark.asyncio
    async def test_initialize_schema(self, storage, mock_pool):
        """Test schema initialization."""
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        await storage.initialize_schema()

        # Should execute multiple CREATE TABLE/INDEX statements
        assert mock_conn.execute.call_count >= 6


class TestPostgresSignalStorageStoreSignal:
    """Tests for store_signal method."""

    @pytest.mark.asyncio
    async def test_store_signal_success(self, storage, mock_pool):
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

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.store_signal(signal)

        assert result is True
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_signal_failure(self, storage, mock_pool):
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

        mock_pool.acquire.side_effect = Exception("Connection failed")

        result = await storage.store_signal(signal)
        assert result is False


class TestPostgresSignalStorageStoreOutcome:
    """Tests for store_outcome method."""

    @pytest.mark.asyncio
    async def test_store_outcome_success(self, storage, mock_pool):
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

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.store_outcome(outcome)

        assert result is True
        mock_conn.execute.assert_called_once()


class TestPostgresSignalStorageQuerySignals:
    """Tests for query_signals method."""

    @pytest.mark.asyncio
    async def test_query_signals_empty(self, storage, mock_pool):
        """Test querying with empty result."""
        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await storage.query_signals(token="BTC")

        assert results == []

    @pytest.mark.asyncio
    async def test_query_signals_with_results(self, storage, mock_pool):
        """Test querying with results."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "signal_id": "test-uuid",
            "token": "BTC",
            "timestamp": 1234567890000,
            "direction": "LONG",
            "confidence": 0.75,
            "entry_price": 50000.0,
            "score": 75.0,
            "multiplier_applied": None,
            "indicators_used": ["rsi"],
            "timeframes_used": ["1h"],
            "metadata": {},
        }.get(key)

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_record])
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await storage.query_signals(token="BTC")

        assert len(results) == 1
        assert results[0].token == "BTC"


class TestPostgresSignalStorageGetSignalById:
    """Tests for get_signal_by_id method."""

    @pytest.mark.asyncio
    async def test_get_signal_by_id_found(self, storage, mock_pool):
        """Test getting existing signal."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "signal_id": "test-uuid",
            "token": "BTC",
            "timestamp": 1234567890000,
            "direction": "LONG",
            "confidence": 0.75,
            "entry_price": 50000.0,
            "score": 75.0,
            "multiplier_applied": None,
            "indicators_used": ["rsi"],
            "timeframes_used": ["1h"],
            "metadata": {},
        }.get(key)

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_record)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.get_signal_by_id("test-uuid")

        assert result is not None
        assert result.signal_id == "test-uuid"

    @pytest.mark.asyncio
    async def test_get_signal_by_id_not_found(self, storage, mock_pool):
        """Test getting non-existent signal."""
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.get_signal_by_id("non-existent")

        assert result is None


class TestPostgresSignalStorageCalculateAccuracy:
    """Tests for calculate_prediction_accuracy method."""

    @pytest.mark.asyncio
    async def test_calculate_accuracy_with_data(self, storage, mock_pool):
        """Test accuracy calculation with data."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "total_signals": 10,
            "wins": 7,
            "losses": 3,
            "avg_pnl": 50.0,
            "total_pnl": 500.0,
            "avg_duration_hours": 2.5,
        }.get(key)

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_record)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.calculate_prediction_accuracy()

        assert result["total_signals"] == 10
        assert result["wins"] == 7
        assert result["accuracy"] == 0.7

    @pytest.mark.asyncio
    async def test_calculate_accuracy_empty(self, storage, mock_pool):
        """Test accuracy calculation with no data."""
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await storage.calculate_prediction_accuracy()

        assert result["total_signals"] == 0
        assert result["accuracy"] == 0.0


class TestPostgresSignalStorageClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_owned_pool(self):
        """Test closing owned pool."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        storage = PostgresSignalStorage(pool=mock_pool)
        storage._owned_pool = True

        await storage.close()

        mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_shared_pool(self, mock_pool):
        """Test closing shared pool (should not close)."""
        storage = PostgresSignalStorage(pool=mock_pool)
        storage._owned_pool = False

        await storage.close()

        mock_pool.close.assert_not_called()


class TestPostgresSignalStorageRowConversion:
    """Tests for row conversion methods."""

    def test_row_to_signal(self, storage):
        """Test converting row to SignalRecord."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "signal_id": "test-uuid",
            "token": "BTC",
            "timestamp": 1234567890000,
            "direction": "LONG",
            "confidence": 0.75,
            "entry_price": 50000.0,
            "score": 75.0,
            "multiplier_applied": 1.2,
            "indicators_used": ["rsi", "macd"],
            "timeframes_used": ["1h", "4h"],
            "metadata": {"source": "test"},
        }.get(key)

        signal = storage._row_to_signal(mock_row)

        assert signal.signal_id == "test-uuid"
        assert signal.token == "BTC"
        assert signal.direction == SignalDirection.LONG

    def test_row_to_outcome(self, storage):
        """Test converting row to OutcomeRecord."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "signal_id": "test-uuid",
            "exit_timestamp": 1234567950000,
            "is_win": True,
            "pnl": 100.0,
            "exit_price": 50100.0,
            "duration_hours": 1.5,
            "outcome_type": "tp_hit",
            "note": "Test note",
        }.get(key)

        outcome = storage._row_to_outcome(mock_row)

        assert outcome is not None
        assert outcome.signal_id == "test-uuid"
        assert outcome.is_win is True
        assert outcome.outcome_type == OutcomeType.TP_HIT

    def test_row_to_outcome_none_timestamp(self, storage):
        """Test converting row with None timestamp."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: (
            None if key == "exit_timestamp" else "value"
        )

        outcome = storage._row_to_outcome(mock_row)

        assert outcome is None
