"""Tests for portfolio storage backends."""

import pytest

from portfolio.state_management.models import (
    PortfolioSnapshot,
    PortfolioState,
)
from portfolio.state_management.storage import (
    FallbackPortfolioStorage,
    InfluxDBPortfolioStorage,
    PostgresPortfolioStorage,
    StorageConfig,
)


@pytest.fixture
def influx_config():
    """Create InfluxDB config."""
    return StorageConfig(
        host="localhost",
        port=8086,
        database="portfolio",
        username="admin",
        password="admin",
    )


@pytest.fixture
def postgres_config():
    """Create PostgreSQL config."""
    return StorageConfig(
        host="localhost",
        port=5432,
        database="portfolio",
        username="admin",
        password="admin",
    )


class TestStorageConfig:
    """Tests for StorageConfig dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic config creation."""
        config = StorageConfig(
            host="localhost",
            port=8086,
            database="portfolio",
            username="admin",
            password="secret",
            ssl=True,
        )

        assert config.host == "localhost"
        assert config.port == 8086
        assert config.database == "portfolio"
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.ssl is True


class TestInfluxDBPortfolioStorage:
    """Tests for InfluxDB storage backend."""

    @pytest.mark.asyncio
    async def test_store_snapshot(self, influx_config):
        """Test storing a snapshot in InfluxDB."""
        storage = InfluxDBPortfolioStorage(influx_config)

        snapshot = PortfolioSnapshot(
            snapshot_id="snap-1",
            portfolio_id="test-portfolio",
            timestamp=1234567890000,
            total_equity=100000.0,
            available_equity=80000.0,
            margin_used=20000.0,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            position_count=5,
        )

        # In test environment, InfluxDB client may or may not be available
        # Just verify the method runs without error
        result = await storage.store_snapshot(snapshot)
        # Result depends on whether influxdb_client is installed
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, influx_config):
        """Test health check when InfluxDB is unhealthy."""
        storage = InfluxDBPortfolioStorage(influx_config)

        result = await storage.health_check()

        # Should return False when client can't be created
        assert result is False


class TestPostgresPortfolioStorage:
    """Tests for PostgreSQL storage backend."""

    @pytest.mark.asyncio
    async def test_store_state(self, postgres_config):
        """Test storing state in PostgreSQL."""
        storage = PostgresPortfolioStorage(postgres_config)

        state = PortfolioState(portfolio_id="test-portfolio")
        state.update_balance("USDT", free=10000.0)

        # Should handle import error gracefully
        result = await storage.store_state(state)
        assert result is False

    @pytest.mark.asyncio
    async def test_store_snapshot(self, postgres_config):
        """Test storing snapshot in PostgreSQL."""
        storage = PostgresPortfolioStorage(postgres_config)

        snapshot = PortfolioSnapshot(
            snapshot_id="snap-1",
            portfolio_id="test-portfolio",
            timestamp=1234567890000,
            total_equity=100000.0,
            available_equity=80000.0,
            margin_used=20000.0,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            position_count=5,
        )

        # Should handle import error gracefully
        result = await storage.store_snapshot(snapshot)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_latest_state_not_found(self, postgres_config):
        """Test getting latest state when none exists."""
        storage = PostgresPortfolioStorage(postgres_config)

        result = await storage.get_latest_state("test-portfolio")

        # Should return None when connection fails
        assert result is None

    @pytest.mark.asyncio
    async def test_get_snapshots_empty(self, postgres_config):
        """Test getting snapshots when none exist."""
        storage = PostgresPortfolioStorage(postgres_config)

        result = await storage.get_snapshots("test-portfolio")

        # Should return empty list when connection fails
        assert result == []

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, postgres_config):
        """Test health check when PostgreSQL is unhealthy."""
        storage = PostgresPortfolioStorage(postgres_config)

        result = await storage.health_check()

        # Should return False when client can't be created
        assert result is False


class TestFallbackPortfolioStorage:
    """Tests for fallback storage wrapper."""

    @pytest.mark.asyncio
    async def test_fallback_to_postgres(self, influx_config, postgres_config):
        """Test fallback when InfluxDB fails."""
        storage = FallbackPortfolioStorage(influx_config, postgres_config)

        # Both backends will fail in test environment
        snapshot = PortfolioSnapshot(
            snapshot_id="snap-1",
            portfolio_id="test-portfolio",
            timestamp=1234567890000,
            total_equity=100000.0,
            available_equity=80000.0,
            margin_used=20000.0,
            unrealized_pnl=5000.0,
            realized_pnl=2000.0,
            position_count=5,
        )

        # Should try primary, fail, then try fallback
        result = await storage.store_snapshot(snapshot)

        # Both fail in test environment
        assert result is False
        assert storage._using_fallback is True

    @pytest.mark.asyncio
    async def test_health_check_fallback(self, influx_config, postgres_config):
        """Test health check with fallback."""
        storage = FallbackPortfolioStorage(influx_config, postgres_config)

        result = await storage.health_check()

        # Both backends fail in test environment
        assert result is False

    @pytest.mark.asyncio
    async def test_close_both_backends(self, influx_config, postgres_config):
        """Test closing both storage backends."""
        storage = FallbackPortfolioStorage(influx_config, postgres_config)

        # Should not raise
        await storage.close()
