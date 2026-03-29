"""Tests for PostgresSignalsPersistence.

Tests PostgreSQL persistence for trading signals using mocked asyncpg.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.infrastructure.persistence.postgres_signals import (
    CREATE_SIGNALS_TABLE_SQL,
    PostgresSignalsPersistence,
    get_postgres_signals,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg.Pool."""
    pool = MagicMock()
    pool.acquire = MagicMock()
    return pool


@pytest.fixture
def mock_connection():
    """Create a mock asyncpg.Connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock()
    return conn


@pytest.fixture
def mock_pool_with_connection(mock_pool, mock_connection):
    """Create a mock pool that returns a mock connection."""
    mock_pool.acquire.return_value.__aenter__.return_value = mock_connection
    return mock_pool


@pytest.fixture
def sample_signal_data():
    """Create sample signal data for testing."""
    return {
        "signal_id": str(uuid.uuid4()),
        "token": "BTC/USDT",
        "direction": "long",
        "confidence": 0.85,
        "base_score": 75.5,
        "status": "logged_only",
        "timeframe": "1h",
        "timestamp": datetime.now(UTC),
        "metadata": {"source": "test"},
    }


@pytest.fixture
def sample_signal_row(sample_signal_data):
    """Create sample signal data as returned from asyncpg fetchrow."""
    return {
        "signal_id": sample_signal_data["signal_id"],
        "token": sample_signal_data["token"],
        "direction": sample_signal_data["direction"],
        "confidence": sample_signal_data["confidence"],
        "base_score": sample_signal_data["base_score"],
        "status": sample_signal_data["status"],
        "timeframe": sample_signal_data["timeframe"],
        "timestamp": sample_signal_data["timestamp"],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "metadata": json.dumps(sample_signal_data["metadata"]),
        "processed_at": None,
        "order_id": None,
        "execution_price": None,
        "execution_status": None,
    }


# ---------------------------------------------------------------------------
# Test: Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Test cases for PostgresSignalsPersistence initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values from environment."""
        with patch.dict(os.environ, {}, clear=True):
            persistence = PostgresSignalsPersistence()

        assert persistence.host == "localhost"
        assert persistence.port == 5432
        assert persistence.user == "postgres"
        assert persistence.password == ""
        assert persistence.database == "chiseai_trading"
        assert persistence._pool is None
        assert persistence._initialized is False

    def test_init_with_env_vars(self):
        """Test initialization reads from environment variables."""
        env_vars = {
            "POSTGRES_HOST": "db.example.com",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "testuser",
            "POSTGRES_PASSWORD": "secret123",
            "POSTGRES_DB": "testdb",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            persistence = PostgresSignalsPersistence()

        assert persistence.host == "db.example.com"
        assert persistence.port == 5433
        assert persistence.user == "testuser"
        assert persistence.password == "secret123"
        assert persistence.database == "testdb"

    def test_init_with_explicit_params(self):
        """Test initialization with explicit parameters overrides env vars."""
        persistence = PostgresSignalsPersistence(
            host="custom-host",
            port=5555,
            user="custom-user",
            password="custom-pass",
            database="custom-db",
        )

        assert persistence.host == "custom-host"
        assert persistence.port == 5555
        assert persistence.user == "custom-user"
        assert persistence.password == "custom-pass"
        assert persistence.database == "custom-db"


# ---------------------------------------------------------------------------
# Test: Context Manager
# ---------------------------------------------------------------------------


class TestContextManager:
    """Test cases for get_postgres_signals context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        """Test context manager initializes and yields persistence."""
        mock_pool_instance = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_pool_instance.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool_instance.close = AsyncMock()

        with patch(
            "src.infrastructure.persistence.postgres_signals.asyncpg.create_pool",
            new_callable=AsyncMock,
        ) as mock_create_pool:
            mock_create_pool.return_value = mock_pool_instance

            async with get_postgres_signals() as persistence:
                assert isinstance(persistence, PostgresSignalsPersistence)
                assert persistence._pool is not None

            # Verify cleanup happened
            mock_pool_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_init_raises(self):
        """Test context manager closes pool when initialization fails."""
        with patch(
            "src.infrastructure.persistence.postgres_signals.asyncpg.create_pool",
            new_callable=AsyncMock,
        ) as mock_create_pool:
            mock_create_pool.side_effect = Exception("Connection failed")

            with pytest.raises(Exception, match="Connection failed"):
                async with get_postgres_signals() as persistence:
                    pass


# ---------------------------------------------------------------------------
# Test: _get_pool
# ---------------------------------------------------------------------------


class TestGetPool:
    """Test cases for _get_pool method."""

    @pytest.mark.asyncio
    async def test_get_pool_creates_new_pool(self):
        """Test _get_pool creates a new pool when none exists."""
        mock_pool_instance = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            persistence = PostgresSignalsPersistence()
            with patch(
                "src.infrastructure.persistence.postgres_signals.asyncpg.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool:
                mock_create_pool.return_value = mock_pool_instance

                pool = await persistence._get_pool()

                assert pool is mock_pool_instance
                assert persistence._pool is mock_pool_instance
                mock_create_pool.assert_called_once_with(
                    host="localhost",
                    port=5432,
                    user="postgres",
                    password="",
                    database="chiseai_trading",
                    min_size=2,
                    max_size=10,
                )

    @pytest.mark.asyncio
    async def test_get_pool_reuses_existing_pool(self):
        """Test _get_pool returns existing pool without creating new."""
        persistence = PostgresSignalsPersistence()
        existing_pool = MagicMock()

        with patch(
            "src.infrastructure.persistence.postgres_signals.asyncpg.create_pool",
            new_callable=AsyncMock,
        ) as mock_create_pool:
            persistence._pool = existing_pool
            pool = await persistence._get_pool()

            assert pool is existing_pool
            mock_create_pool.assert_not_called()


# ---------------------------------------------------------------------------
# Test: close
# ---------------------------------------------------------------------------


class TestClose:
    """Test cases for close method."""

    @pytest.mark.asyncio
    async def test_close_with_pool(self, mock_pool):
        """Test close closes the pool and resets _pool."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool
        mock_pool.close = AsyncMock()

        await persistence.close()

        mock_pool.close.assert_called_once()
        assert persistence._pool is None

    @pytest.mark.asyncio
    async def test_close_without_pool(self):
        """Test close works when no pool exists."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = None

        # Should not raise
        await persistence.close()


# ---------------------------------------------------------------------------
# Test: initialize
# ---------------------------------------------------------------------------


class TestInitialize:
    """Test cases for initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_pool_with_connection, mock_connection):
        """Test successful table initialization."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection

        await persistence.initialize()

        assert persistence._initialized is True
        mock_connection.execute.assert_called_once_with(CREATE_SIGNALS_TABLE_SQL)

    @pytest.mark.asyncio
    async def test_initialize_idempotent(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test initialize is idempotent when already initialized."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        persistence._initialized = True

        await persistence.initialize()

        mock_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_failure(self, mock_pool_with_connection, mock_connection):
        """Test initialize raises on connection error."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.execute.side_effect = Exception("Connection error")

        with pytest.raises(Exception, match="Connection error"):
            await persistence.initialize()

        assert persistence._initialized is False


# ---------------------------------------------------------------------------
# Test: store_signal
# ---------------------------------------------------------------------------


class TestStoreSignal:
    """Test cases for store_signal method."""

    @pytest.mark.asyncio
    async def test_store_signal_success(
        self, mock_pool_with_connection, mock_connection, sample_signal_data
    ):
        """Test successful signal storage."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection

        result = await persistence.store_signal(
            signal_id=sample_signal_data["signal_id"],
            token=sample_signal_data["token"],
            direction=sample_signal_data["direction"],
            confidence=sample_signal_data["confidence"],
            base_score=sample_signal_data["base_score"],
            status=sample_signal_data["status"],
            timeframe=sample_signal_data["timeframe"],
            metadata=sample_signal_data["metadata"],
        )

        assert result is True
        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        # Verify SQL contains INSERT
        assert "INSERT INTO signals" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_store_signal_with_explicit_timestamp(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test signal storage with explicit timestamp."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

        result = await persistence.store_signal(
            signal_id="sig-123",
            token="ETH/USDT",
            direction="short",
            confidence=0.7,
            base_score=60.0,
            timestamp=ts,
        )

        assert result is True
        call_args = mock_connection.execute.call_args
        # Timestamp should be in the call
        assert ts in call_args[0]

    @pytest.mark.asyncio
    async def test_store_signal_failure(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test signal storage failure returns False."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.execute.side_effect = Exception("Insert failed")

        result = await persistence.store_signal(
            signal_id="sig-123",
            token="BTC/USDT",
            direction="long",
            confidence=0.8,
            base_score=70.0,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_store_signal_with_default_metadata(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test signal storage with None metadata defaults to empty dict."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection

        await persistence.store_signal(
            signal_id="sig-456",
            token="BTC/USDT",
            direction="long",
            confidence=0.8,
            base_score=70.0,
            metadata=None,
        )

        call_args = mock_connection.execute.call_args
        # Last arg should be '{}' for empty metadata
        metadata_arg = call_args[0][-1]
        assert metadata_arg == "{}"


# ---------------------------------------------------------------------------
# Test: update_signal_execution
# ---------------------------------------------------------------------------


class TestUpdateSignalExecution:
    """Test cases for update_signal_execution method."""

    @pytest.mark.asyncio
    async def test_update_execution_success(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test successful execution update."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection

        result = await persistence.update_signal_execution(
            signal_id="sig-123",
            execution_status="filled",
            order_id="order-456",
            execution_price=50000.0,
        )

        assert result is True
        mock_connection.execute.assert_called_once()
        call_args = mock_connection.execute.call_args
        assert "UPDATE signals" in call_args[0][0]
        assert "sig-123" in call_args[0]

    @pytest.mark.asyncio
    async def test_update_execution_with_processed_at(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test execution update with explicit processed_at time."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        processed = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)

        result = await persistence.update_signal_execution(
            signal_id="sig-123",
            execution_status="submitted",
            processed_at=processed,
        )

        assert result is True
        call_args = mock_connection.execute.call_args
        assert processed in call_args[0]

    @pytest.mark.asyncio
    async def test_update_execution_failure(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test execution update failure returns False."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.execute.side_effect = Exception("Update failed")

        result = await persistence.update_signal_execution(
            signal_id="sig-123",
            execution_status="rejected",
        )

        assert result is False


# ---------------------------------------------------------------------------
# Test: get_signal
# ---------------------------------------------------------------------------


class TestGetSignal:
    """Test cases for get_signal method."""

    @pytest.mark.asyncio
    async def test_get_signal_found(
        self, mock_pool_with_connection, mock_connection, sample_signal_row
    ):
        """Test retrieving an existing signal."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchrow.return_value = sample_signal_row

        result = await persistence.get_signal("sig-123")

        assert result is not None
        assert result["signal_id"] == sample_signal_row["signal_id"]
        assert result["token"] == sample_signal_row["token"]
        mock_connection.fetchrow.assert_called_once_with(
            "SELECT * FROM signals WHERE signal_id = $1", "sig-123"
        )

    @pytest.mark.asyncio
    async def test_get_signal_not_found(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test retrieving a non-existent signal returns None."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchrow.return_value = None

        result = await persistence.get_signal("nonexistent-sig")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_signal_error(self, mock_pool_with_connection, mock_connection):
        """Test get_signal error returns None."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchrow.side_effect = Exception("Query failed")

        result = await persistence.get_signal("sig-123")

        assert result is None


# ---------------------------------------------------------------------------
# Test: get_signals_by_status
# ---------------------------------------------------------------------------


class TestGetSignalsByStatus:
    """Test cases for get_signals_by_status method."""

    @pytest.mark.asyncio
    async def test_get_signals_by_status_success(
        self, mock_pool_with_connection, mock_connection, sample_signal_row
    ):
        """Test retrieving signals by status."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = [sample_signal_row]

        result = await persistence.get_signals_by_status("logged_only", limit=50)

        assert len(result) == 1
        assert result[0]["signal_id"] == sample_signal_row["signal_id"]
        mock_connection.fetch.assert_called_once()
        call_args = mock_connection.fetch.call_args
        assert "logged_only" in call_args[0]
        assert 50 in call_args[0]

    @pytest.mark.asyncio
    async def test_get_signals_by_status_empty(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test retrieving signals by status returns empty list."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = []

        result = await persistence.get_signals_by_status("nonexistent_status")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_signals_by_status_error(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test get_signals_by_status error returns empty list."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.side_effect = Exception("Query failed")

        result = await persistence.get_signals_by_status("logged_only")

        assert result == []


# ---------------------------------------------------------------------------
# Test: get_signals_by_token
# ---------------------------------------------------------------------------


class TestGetSignalsByToken:
    """Test cases for get_signals_by_token method."""

    @pytest.mark.asyncio
    async def test_get_signals_by_token_no_time_filter(
        self, mock_pool_with_connection, mock_connection, sample_signal_row
    ):
        """Test retrieving signals by token without time filter."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = [sample_signal_row]

        result = await persistence.get_signals_by_token("BTC/USDT", limit=100)

        assert len(result) == 1
        mock_connection.fetch.assert_called_once()
        call_args = mock_connection.fetch.call_args
        assert "BTC/USDT" in call_args[0]

    @pytest.mark.asyncio
    async def test_get_signals_by_token_with_time_filter(
        self, mock_pool_with_connection, mock_connection, sample_signal_row
    ):
        """Test retrieving signals by token with time filter."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = [sample_signal_row]

        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 12, 31, tzinfo=UTC)

        result = await persistence.get_signals_by_token(
            "ETH/USDT", start_time=start, end_time=end, limit=50
        )

        assert len(result) == 1
        call_args = mock_connection.fetch.call_args
        assert "ETH/USDT" in call_args[0]
        assert start in call_args[0]
        assert end in call_args[0]

    @pytest.mark.asyncio
    async def test_get_signals_by_token_error(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test get_signals_by_token error returns empty list."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.side_effect = Exception("Query failed")

        result = await persistence.get_signals_by_token("BTC/USDT")

        assert result == []


# ---------------------------------------------------------------------------
# Test: count_signals_by_status
# ---------------------------------------------------------------------------


class TestCountSignalsByStatus:
    """Test cases for count_signals_by_status method."""

    @pytest.mark.asyncio
    async def test_count_signals_by_status_success(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test counting signals grouped by status."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = [
            {"status": "logged_only", "count": 10},
            {"status": "actionable", "count": 5},
        ]

        result = await persistence.count_signals_by_status()

        assert result == {"logged_only": 10, "actionable": 5}
        mock_connection.fetch.assert_called_once_with(
            "SELECT status, COUNT(*) as count FROM signals GROUP BY status"
        )

    @pytest.mark.asyncio
    async def test_count_signals_by_status_empty(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test counting signals when table is empty."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.return_value = []

        result = await persistence.count_signals_by_status()

        assert result == {}

    @pytest.mark.asyncio
    async def test_count_signals_by_status_error(
        self, mock_pool_with_connection, mock_connection
    ):
        """Test count_signals_by_status error returns empty dict."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetch.side_effect = Exception("Query failed")

        result = await persistence.count_signals_by_status()

        assert result == {}


# ---------------------------------------------------------------------------
# Test: table_exists
# ---------------------------------------------------------------------------


class TestTableExists:
    """Test cases for table_exists method."""

    @pytest.mark.asyncio
    async def test_table_exists_true(self, mock_pool_with_connection, mock_connection):
        """Test table_exists returns True when table exists."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchval.return_value = True

        result = await persistence.table_exists()

        assert result is True
        mock_connection.fetchval.assert_called_once()
        call_args = mock_connection.fetchval.call_args[0][0]
        assert "information_schema.tables" in call_args
        assert "signals" in call_args

    @pytest.mark.asyncio
    async def test_table_exists_false(self, mock_pool_with_connection, mock_connection):
        """Test table_exists returns False when table doesn't exist."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchval.return_value = False

        result = await persistence.table_exists()

        assert result is False

    @pytest.mark.asyncio
    async def test_table_exists_error(self, mock_pool_with_connection, mock_connection):
        """Test table_exists error returns False."""
        persistence = PostgresSignalsPersistence()
        persistence._pool = mock_pool_with_connection
        mock_connection.fetchval.side_effect = Exception("Query failed")

        result = await persistence.table_exists()

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
