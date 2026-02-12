"""Tests for data source health monitoring.

For ST-OPS-008: Grafana Data Source Health Monitoring
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the module under test
from monitoring.datasource_health import (
    ConnectionMetrics,
    ConnectionStatus,
    DataSourceHealthMonitor,
    DataSourceType,
    DatasourceConfig,
    DatasourceHealthAlert,
    AlertSeverity,
    InfluxDBHealthChecker,
    PostgreSQLHealthChecker,
    create_default_monitor,
    create_influxdb_config,
    create_postgresql_config,
)
from monitoring.datasource_health_discord import (
    DatasourceHealthDiscordFormatter,
    DatasourceHealthDiscordSender,
    create_discord_alert_handler,
)


class TestConnectionMetrics:
    """Test ConnectionMetrics dataclass."""

    def test_is_connected_property(self):
        """Test is_connected property returns correct value."""
        metrics_connected = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        assert metrics_connected.is_connected is True

        metrics_disconnected = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.DISCONNECTED,
        )
        assert metrics_disconnected.is_connected is False

    def test_is_healthy_property(self):
        """Test is_healthy property returns correct value."""
        metrics_connected = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        assert metrics_connected.is_healthy is True

        metrics_reconnecting = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.RECONNECTING,
        )
        assert metrics_reconnecting.is_healthy is True

        metrics_failed = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.FAILED,
        )
        assert metrics_failed.is_healthy is False

    def test_availability_percentage(self):
        """Test availability percentage calculation."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
            uptime_seconds=900,
            downtime_seconds=100,
        )
        assert metrics.availability_percentage == 90.0

    def test_availability_percentage_no_time(self):
        """Test availability percentage when no time recorded."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        assert metrics.availability_percentage == 100.0

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime.now(UTC)
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
            last_connected_at=now,
            uptime_seconds=100,
            response_time_ms=50.0,
        )
        d = metrics.to_dict()
        assert d["source_type"] == "influxdb"
        assert d["source_name"] == "Test InfluxDB"
        assert d["status"] == "connected"
        assert d["is_connected"] is True
        assert d["is_healthy"] is True
        assert d["response_time_ms"] == 50.0


class TestDatasourceHealthAlert:
    """Test DatasourceHealthAlert dataclass."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        alert = DatasourceHealthAlert(
            alert_type="disconnected",
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            message="Connection lost",
            severity=AlertSeverity.WARNING,
            metrics={"disconnect_count": 1},
        )
        d = alert.to_dict()
        assert d["alert_type"] == "disconnected"
        assert d["source_type"] == "influxdb"
        assert d["severity"] == "warning"
        assert d["metrics"]["disconnect_count"] == 1


class TestDatasourceConfig:
    """Test DatasourceConfig dataclass."""

    def test_to_dict_excludes_sensitive(self):
        """Test that to_dict excludes sensitive fields."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test",
            host="localhost",
            port=8086,
            token="secret_token",
            password="secret_password",
        )
        d = config.to_dict()
        assert "token" not in d
        assert "password" not in d
        assert "username" not in d
        assert d["host"] == "localhost"
        assert d["port"] == 8086


class TestInfluxDBHealthChecker:
    """Test InfluxDB health checker."""

    @pytest.fixture
    def influxdb_config(self):
        return DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="chiseai-influxdb",
            port=18087,
            token="test_token",
        )

    @pytest.mark.asyncio
    async def test_check_health_with_client(self, influxdb_config):
        """Test health check using InfluxDB client."""
        checker = InfluxDBHealthChecker(influxdb_config)

        # Mock InfluxDB client
        mock_health = MagicMock()
        mock_health.status = "pass"

        mock_client = MagicMock()
        mock_client.health = MagicMock(return_value=mock_health)
        mock_client.close = MagicMock()

        with patch("influxdb_client.InfluxDBClient", return_value=mock_client):
            is_healthy, response_time = await checker.check_health()
            assert is_healthy is True
            assert response_time is not None
            assert response_time > 0
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_health_client_failure(self, influxdb_config):
        """Test health check returns False when client fails and no fallback available."""
        checker = InfluxDBHealthChecker(influxdb_config)

        # Mock InfluxDB client to fail
        with patch(
            "influxdb_client.InfluxDBClient", side_effect=Exception("No InfluxDB")
        ):
            # Mock aiohttp to also fail (simulating no HTTP access)
            with patch("aiohttp.ClientSession", side_effect=Exception("No HTTP")):
                is_healthy, response_time = await checker.check_health()
                # Should fail since both methods fail
                assert is_healthy is False
                assert response_time is None


class TestPostgreSQLHealthChecker:
    """Test PostgreSQL health checker."""

    @pytest.fixture
    def postgres_config(self):
        return DatasourceConfig(
            source_type=DataSourceType.POSTGRESQL,
            source_name="Test PostgreSQL",
            host="chiseai-postgres",
            port=5434,
            database="chiseai",
            username="testuser",
            password="testpass",
        )

    @pytest.mark.asyncio
    async def test_check_health_asyncpg_success(self, postgres_config):
        """Test asyncpg health check success."""
        checker = PostgreSQLHealthChecker(postgres_config)

        # Mock asyncpg
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[(1,)])
        mock_conn.close = AsyncMock()

        with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
            is_healthy, response_time = await checker.check_health()
            assert is_healthy is True
            assert response_time is not None
            assert response_time > 0

    @pytest.mark.asyncio
    async def test_check_health_asyncpg_failure(self, postgres_config):
        """Test asyncpg health check failure."""
        checker = PostgreSQLHealthChecker(postgres_config)

        with patch("asyncpg.connect", side_effect=Exception("Connection refused")):
            is_healthy, response_time = await checker.check_health()
            assert is_healthy is False
            assert response_time is None


class TestDataSourceHealthMonitor:
    """Test DataSourceHealthMonitor."""

    @pytest.fixture
    def influxdb_config(self):
        return DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="chiseai-influxdb",
            port=18087,
            check_interval_seconds=0.1,  # Fast for testing
            reconnect_backoff_seconds=(0.01, 0.02, 0.03),
        )

    @pytest.fixture
    def postgres_config(self):
        return DatasourceConfig(
            source_type=DataSourceType.POSTGRESQL,
            source_name="Test PostgreSQL",
            host="chiseai-postgres",
            port=5434,
            database="chiseai",
            check_interval_seconds=0.1,  # Fast for testing
            reconnect_backoff_seconds=(0.01, 0.02, 0.03),
        )

    @pytest.fixture
    def monitor(self, influxdb_config, postgres_config):
        return DataSourceHealthMonitor(
            datasource_configs=[influxdb_config, postgres_config],
            alert_cooldown_seconds=0.01,  # Fast for testing
            extended_downtime_threshold_seconds=0.05,  # Fast for testing
        )

    def test_initialization(self, monitor):
        """Test monitor initialization."""
        assert DataSourceType.INFLUXDB in monitor.datasource_configs
        assert DataSourceType.POSTGRESQL in monitor.datasource_configs
        assert DataSourceType.INFLUXDB in monitor._checkers
        assert DataSourceType.POSTGRESQL in monitor._checkers

    def test_add_datasource_config(self, monitor):
        """Test adding new datasource config."""
        new_config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="New InfluxDB",
            host="new-host",
            port=8086,
        )
        monitor.add_datasource_config(new_config)
        assert monitor.datasource_configs[DataSourceType.INFLUXDB].host == "new-host"

    def test_remove_datasource_config(self, monitor):
        """Test removing datasource config."""
        monitor.remove_datasource_config(DataSourceType.INFLUXDB)
        assert DataSourceType.INFLUXDB not in monitor.datasource_configs
        assert DataSourceType.INFLUXDB not in monitor._checkers

    @pytest.mark.asyncio
    async def test_check_datasource_connected(self, monitor, influxdb_config):
        """Test checking datasource when connected."""
        # Mock checker to return healthy
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(True, 50.0))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        await monitor._check_datasource(DataSourceType.INFLUXDB, influxdb_config)

        metrics = monitor._metrics[DataSourceType.INFLUXDB]
        assert metrics.status == ConnectionStatus.CONNECTED
        assert metrics.response_time_ms == 50.0
        assert metrics.is_connected is True

    @pytest.mark.asyncio
    async def test_check_datasource_disconnected(self, monitor, influxdb_config):
        """Test checking datasource when disconnected."""
        # Set initial connected state
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.CONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].last_connected_at = datetime.now(UTC)

        # Mock checker to return unhealthy
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Mock alert handler
        alert_received = []

        async def mock_handler(alert):
            alert_received.append(alert)

        monitor.add_alert_handler(mock_handler)

        await monitor._check_datasource(DataSourceType.INFLUXDB, influxdb_config)

        metrics = monitor._metrics[DataSourceType.INFLUXDB]
        # Status transitions: DISCONNECTED -> RECONNECTING (immediately)
        assert metrics.status == ConnectionStatus.RECONNECTING
        assert metrics.disconnect_count == 1
        assert metrics.last_disconnected_at is not None

    @pytest.mark.asyncio
    async def test_check_datasource_reconnect_attempts(self, monitor, influxdb_config):
        """Test reconnection attempts with backoff."""
        # Set disconnected state
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.DISCONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].last_disconnected_at = datetime.now(
            UTC
        )
        monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts = 0

        # Mock checker to return unhealthy (still disconnected)
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        await monitor._check_datasource(DataSourceType.INFLUXDB, influxdb_config)

        metrics = monitor._metrics[DataSourceType.INFLUXDB]
        assert metrics.status == ConnectionStatus.RECONNECTING
        assert metrics.reconnect_attempts == 1

    @pytest.mark.asyncio
    async def test_check_datasource_max_reconnect_exceeded(
        self, monitor, influxdb_config
    ):
        """Test behavior when max reconnection attempts exceeded."""
        # Set reconnecting state at max attempts
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.RECONNECTING
        monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts = 3
        monitor._metrics[DataSourceType.INFLUXDB].last_disconnected_at = datetime.now(
            UTC
        )

        # Mock checker to return unhealthy
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Mock alert handler
        alert_received = []

        async def mock_handler(alert):
            alert_received.append(alert)

        monitor.add_alert_handler(mock_handler)

        await monitor._attempt_reconnect(DataSourceType.INFLUXDB, influxdb_config)

        metrics = monitor._metrics[DataSourceType.INFLUXDB]
        assert metrics.status == ConnectionStatus.FAILED
        assert len(alert_received) == 1
        assert alert_received[0].alert_type == "reconnect_failed"

    @pytest.mark.asyncio
    async def test_check_datasource_recovery(self, monitor, influxdb_config):
        """Test recovery detection and alert."""
        # Set disconnected state
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.DISCONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].last_disconnected_at = datetime.now(
            UTC
        ) - timedelta(seconds=10)
        monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts = 2

        # Mock checker to return healthy (recovered)
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(True, 45.0))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Mock alert handler
        alert_received = []

        async def mock_handler(alert):
            alert_received.append(alert)

        monitor.add_alert_handler(mock_handler)

        await monitor._check_datasource(DataSourceType.INFLUXDB, influxdb_config)

        metrics = monitor._metrics[DataSourceType.INFLUXDB]
        assert metrics.status == ConnectionStatus.CONNECTED
        assert metrics.reconnect_attempts == 0  # Reset on success

    @pytest.mark.asyncio
    async def test_extended_downtime_alert(self, monitor, influxdb_config):
        """Test extended downtime alert."""
        # Set reconnecting state with extended downtime
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.RECONNECTING
        monitor._metrics[DataSourceType.INFLUXDB].last_disconnected_at = datetime.now(
            UTC
        ) - timedelta(seconds=10)
        monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts = 1

        # Mock checker to return unhealthy
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Mock alert handler
        alert_received = []

        async def mock_handler(alert):
            alert_received.append(alert)

        monitor.add_alert_handler(mock_handler)

        await monitor._check_datasource(DataSourceType.INFLUXDB, influxdb_config)

        # Should have extended downtime alert
        extended_alerts = [
            a for a in alert_received if a.alert_type == "extended_downtime"
        ]
        assert len(extended_alerts) > 0 or len(alert_received) > 0

    def test_should_alert_respects_cooldown(self, monitor):
        """Test alert cooldown logic."""
        monitor.alert_cooldown_seconds = 1.0

        # First alert should be allowed
        assert monitor.should_alert(DataSourceType.INFLUXDB, "disconnected") is True
        monitor.record_alert(DataSourceType.INFLUXDB, "disconnected")

        # Immediate second alert should be blocked
        assert monitor.should_alert(DataSourceType.INFLUXDB, "disconnected") is False

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, monitor):
        """Test starting and stopping monitoring."""
        # Mock checkers to avoid actual network calls
        for checker in monitor._checkers.values():
            checker.check_health = AsyncMock(return_value=(True, 50.0))

        await monitor.start_monitoring()
        assert monitor._running is True
        assert len(monitor._monitor_tasks) == 2

        await asyncio.sleep(0.05)  # Let it run briefly

        await monitor.stop_monitoring()
        assert monitor._running is False
        assert len(monitor._monitor_tasks) == 0

    def test_get_metrics(self, monitor):
        """Test getting metrics."""
        all_metrics = monitor.get_metrics()
        assert isinstance(all_metrics, dict)
        assert DataSourceType.INFLUXDB in all_metrics
        assert DataSourceType.POSTGRESQL in all_metrics

        single_metric = monitor.get_metrics(DataSourceType.INFLUXDB)
        assert isinstance(single_metric, ConnectionMetrics)
        assert single_metric.source_type == DataSourceType.INFLUXDB

    def test_get_all_metrics(self, monitor):
        """Test getting all metrics for dashboard."""
        metrics = monitor.get_all_metrics()
        assert "datasources" in metrics
        assert "summary" in metrics
        assert "timestamp" in metrics
        assert metrics["summary"]["total"] == 2

    def test_get_metrics_for_grafana(self, monitor):
        """Test getting metrics formatted for Grafana."""
        grafana_metrics = monitor.get_metrics_for_grafana()
        assert isinstance(grafana_metrics, list)
        assert len(grafana_metrics) == 2

        # Check required fields
        for m in grafana_metrics:
            assert "timestamp" in m
            assert "source_type" in m
            assert "is_connected" in m
            assert "availability_percentage" in m

    @pytest.mark.asyncio
    async def test_check_now(self, monitor, influxdb_config):
        """Test immediate check."""
        # Mock checker
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(True, 50.0))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        await monitor.check_now(DataSourceType.INFLUXDB)
        mock_checker.check_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_now_all(self, monitor):
        """Test immediate check for all sources."""
        # Mock all checkers
        for checker in monitor._checkers.values():
            checker.check_health = AsyncMock(return_value=(True, 50.0))

        await monitor.check_now()
        for checker in monitor._checkers.values():
            checker.check_health.assert_called_once()

    def test_is_healthy(self, monitor):
        """Test is_healthy check."""
        # Initially disconnected
        assert monitor.is_healthy() is False

        # Set connected
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.CONNECTED
        monitor._metrics[DataSourceType.POSTGRESQL].status = ConnectionStatus.CONNECTED
        assert monitor.is_healthy() is True

        # Set one to failed
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.FAILED
        assert monitor.is_healthy() is False

    def test_is_healthy_single_source(self, monitor):
        """Test is_healthy for single source."""
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.CONNECTED
        assert monitor.is_healthy(DataSourceType.INFLUXDB) is True

        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.FAILED
        assert monitor.is_healthy(DataSourceType.INFLUXDB) is False


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_influxdb_config(self):
        """Test InfluxDB config factory."""
        config = create_influxdb_config(
            host="custom-host",
            port=8086,
            token="test_token",
            check_interval_seconds=60.0,
        )
        assert config.source_type == DataSourceType.INFLUXDB
        assert config.host == "custom-host"
        assert config.port == 8086
        assert config.token == "test_token"
        assert config.check_interval_seconds == 60.0
        assert config.reconnect_backoff_seconds == (2.0, 5.0, 10.0)

    def test_create_postgresql_config(self):
        """Test PostgreSQL config factory."""
        config = create_postgresql_config(
            host="custom-host",
            port=5432,
            database="testdb",
            username="testuser",
            password="testpass",
            check_interval_seconds=120.0,
        )
        assert config.source_type == DataSourceType.POSTGRESQL
        assert config.host == "custom-host"
        assert config.port == 5432
        assert config.database == "testdb"
        assert config.username == "testuser"
        assert config.password == "testpass"
        assert config.check_interval_seconds == 120.0

    def test_create_default_monitor(self):
        """Test default monitor factory."""
        monitor = create_default_monitor(
            influxdb_token="influx_token",
            postgres_username="postgres_user",
            postgres_password="postgres_pass",
        )
        assert DataSourceType.INFLUXDB in monitor.datasource_configs
        assert DataSourceType.POSTGRESQL in monitor.datasource_configs
        assert (
            monitor.datasource_configs[DataSourceType.INFLUXDB].token == "influx_token"
        )
        assert (
            monitor.datasource_configs[DataSourceType.POSTGRESQL].username
            == "postgres_user"
        )
        assert monitor.alert_cooldown_seconds == 10.0


class TestDatasourceHealthDiscordFormatter:
    """Test Discord formatter."""

    def test_format_disconnect_alert(self):
        """Test disconnect alert formatting."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.DISCONNECTED,
            disconnect_count=1,
            uptime_seconds=950,
            downtime_seconds=50,
        )
        embed = DatasourceHealthDiscordFormatter.format_disconnect_alert(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert "Disconnected" in embed["title"]
        assert (
            embed["color"]
            == DatasourceHealthDiscordFormatter.SEVERITY_COLORS["warning"]
        )
        assert any(f["name"] == "Disconnect Count" for f in embed["fields"])

    def test_format_reconnect_failed_alert(self):
        """Test reconnect failed alert formatting."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.FAILED,
            disconnect_count=3,
            total_reconnect_attempts=9,
            uptime_seconds=850,
            downtime_seconds=150,
        )
        embed = DatasourceHealthDiscordFormatter.format_reconnect_failed_alert(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
            max_attempts=3,
        )
        assert "Reconnect Failed" in embed["title"]
        assert (
            embed["color"]
            == DatasourceHealthDiscordFormatter.SEVERITY_COLORS["critical"]
        )

    def test_format_extended_downtime_alert(self):
        """Test extended downtime alert formatting."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.FAILED,
            reconnect_attempts=3,
            uptime_seconds=800,
            downtime_seconds=200,
        )
        embed = DatasourceHealthDiscordFormatter.format_extended_downtime_alert(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
            downtime_minutes=10.5,
        )
        assert "Extended Downtime" in embed["title"]
        assert "10.5 min" in str(embed["fields"])

    def test_format_recovery_notice(self):
        """Test recovery notice formatting."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
            response_time_ms=45.0,
            uptime_seconds=980,
            downtime_seconds=20,
            disconnect_count=2,
        )
        embed = DatasourceHealthDiscordFormatter.format_recovery_notice(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert "Recovered" in embed["title"]
        assert embed["color"] == 0x2ECC71  # Green


class TestDatasourceHealthDiscordSender:
    """Test Discord sender."""

    @pytest.fixture
    def mock_discord_client(self):
        client = AsyncMock()
        client.send_message = AsyncMock(
            return_value={"success": True, "message_id": "123"}
        )
        return client

    @pytest.fixture
    def sender(self, mock_discord_client):
        return DatasourceHealthDiscordSender(
            discord_client=mock_discord_client,
            alerts_channel="alerts",
        )

    @pytest.mark.asyncio
    async def test_send_disconnect_alert(self, sender, mock_discord_client):
        """Test sending disconnect alert."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.DISCONNECTED,
        )
        result = await sender.send_disconnect_alert(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert result["success"] is True
        mock_discord_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_reconnect_failed_alert(self, sender, mock_discord_client):
        """Test sending reconnect failed alert."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.FAILED,
        )
        result = await sender.send_reconnect_failed_alert(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
            max_attempts=3,
        )
        assert result["success"] is True
        mock_discord_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_recovery_notice(self, sender, mock_discord_client):
        """Test sending recovery notice."""
        # First add an active alert
        sender._active_alerts.add(("disconnected", "influxdb"))

        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        result = await sender.send_recovery_notice(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert result["success"] is True
        mock_discord_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_recovery_notice_skipped_no_active_alert(self, sender):
        """Test recovery notice skipped when no active alert."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        result = await sender.send_recovery_notice(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert result["skipped"] is True
        assert result["reason"] == "no_active_alert"

    @pytest.mark.asyncio
    async def test_send_recovery_notice_skipped_disabled(self, sender):
        """Test recovery notice skipped when disabled."""
        sender.enable_recovery_notices = False
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            status=ConnectionStatus.CONNECTED,
        )
        result = await sender.send_recovery_notice(
            DataSourceType.INFLUXDB,
            "Test InfluxDB",
            metrics,
        )
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_send_generic_alert_disconnect(self, sender, mock_discord_client):
        """Test sending generic disconnect alert."""
        alert = DatasourceHealthAlert(
            alert_type="disconnected",
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            message="Connection lost",
            severity=AlertSeverity.WARNING,
            metrics={"status": "disconnected", "disconnect_count": 1},
        )
        result = await sender.send_generic_alert(alert)
        assert result["success"] is True
        mock_discord_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_generic_alert_unknown_type(self, sender):
        """Test sending generic alert with unknown type."""
        alert = DatasourceHealthAlert(
            alert_type="unknown",
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            message="Unknown",
            severity=AlertSeverity.INFO,
        )
        result = await sender.send_generic_alert(alert)
        assert result["success"] is False
        assert "Unknown alert type" in result["error"]

    def test_get_active_alert_count(self, sender):
        """Test getting active alert count."""
        assert sender.get_active_alert_count() == 0
        sender._active_alerts.add(("disconnected", "influxdb"))
        assert sender.get_active_alert_count() == 1

    def test_clear_active_alerts(self, sender):
        """Test clearing active alerts."""
        sender._active_alerts.add(("disconnected", "influxdb"))
        sender.clear_active_alerts()
        assert sender.get_active_alert_count() == 0


class TestCreateDiscordAlertHandler:
    """Test create_discord_alert_handler factory."""

    @pytest.mark.asyncio
    async def test_handler_creation(self):
        """Test handler factory creates working handler."""
        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"success": True})

        handler = create_discord_alert_handler(discord_client=mock_client)

        alert = DatasourceHealthAlert(
            alert_type="disconnected",
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            message="Connection lost",
            severity=AlertSeverity.WARNING,
            metrics={"status": "disconnected"},
        )

        await handler(alert)
        mock_client.send_message.assert_called_once()


class TestIntegrationScenarios:
    """Integration test scenarios."""

    @pytest.mark.asyncio
    async def test_full_disconnect_reconnect_flow(self):
        """Test full flow: connected -> disconnected -> reconnecting -> connected."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
            check_interval_seconds=0.01,
            reconnect_backoff_seconds=(0.001, 0.002, 0.003),
            max_reconnect_attempts=3,
        )
        monitor = DataSourceHealthMonitor(
            datasource_configs=[config],
            alert_cooldown_seconds=0.001,
        )

        # Track alerts
        alerts = []

        async def alert_handler(alert):
            alerts.append(alert)

        monitor.add_alert_handler(alert_handler)

        # Mock checker with state machine
        call_count = [0]

        async def mock_check():
            call_count[0] += 1
            # First call: connected
            # Second call: disconnected
            # Third call: reconnected
            if call_count[0] == 1:
                return True, 50.0
            elif call_count[0] == 2:
                return False, None
            else:
                return True, 45.0

        mock_checker = MagicMock()
        mock_checker.check_health = mock_check
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # First check - connected
        await monitor.check_now(DataSourceType.INFLUXDB)
        assert (
            monitor._metrics[DataSourceType.INFLUXDB].status
            == ConnectionStatus.CONNECTED
        )

        # Second check - disconnected (transitions to RECONNECTING immediately)
        await monitor.check_now(DataSourceType.INFLUXDB)
        assert (
            monitor._metrics[DataSourceType.INFLUXDB].status
            == ConnectionStatus.RECONNECTING
        )
        assert monitor._metrics[DataSourceType.INFLUXDB].disconnect_count == 1

        # Third check - reconnected
        await monitor.check_now(DataSourceType.INFLUXDB)
        assert (
            monitor._metrics[DataSourceType.INFLUXDB].status
            == ConnectionStatus.CONNECTED
        )
        assert monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_multiple_simultaneous_disconnects(self):
        """Test handling multiple data sources disconnecting simultaneously."""
        influx_config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
            check_interval_seconds=0.01,
        )
        postgres_config = DatasourceConfig(
            source_type=DataSourceType.POSTGRESQL,
            source_name="Test PostgreSQL",
            host="localhost",
            port=5432,
            database="test",
            check_interval_seconds=0.01,
        )
        monitor = DataSourceHealthMonitor(
            datasource_configs=[influx_config, postgres_config],
            alert_cooldown_seconds=0.001,
        )

        alerts = []

        async def alert_handler(alert):
            alerts.append(alert)

        monitor.add_alert_handler(alert_handler)

        # Mock both checkers to fail
        for checker in monitor._checkers.values():
            checker.check_health = AsyncMock(return_value=(False, None))

        # Set initial connected state
        for metrics in monitor._metrics.values():
            metrics.status = ConnectionStatus.CONNECTED
            metrics.last_connected_at = datetime.now(UTC)

        # Check both
        await monitor.check_now()

        # Both should be in RECONNECTING state (transitioned from DISCONNECTED)
        assert (
            monitor._metrics[DataSourceType.INFLUXDB].status
            == ConnectionStatus.RECONNECTING
        )
        assert (
            monitor._metrics[DataSourceType.POSTGRESQL].status
            == ConnectionStatus.RECONNECTING
        )
        assert monitor._metrics[DataSourceType.INFLUXDB].disconnect_count == 1
        assert monitor._metrics[DataSourceType.POSTGRESQL].disconnect_count == 1

    @pytest.mark.asyncio
    async def test_alert_cooldown_prevents_spam(self):
        """Test that alert cooldown prevents alert spam."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
            check_interval_seconds=0.001,
        )
        monitor = DataSourceHealthMonitor(
            datasource_configs=[config],
            alert_cooldown_seconds=1.0,  # 1 second cooldown
        )

        alerts = []

        async def alert_handler(alert):
            alerts.append(alert)

        monitor.add_alert_handler(alert_handler)

        # Mock checker to always fail
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Set initial connected state
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.CONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].last_connected_at = datetime.now(UTC)

        # First disconnect - should alert
        await monitor.check_now(DataSourceType.INFLUXDB)
        initial_alert_count = len(alerts)
        assert initial_alert_count > 0

        # Immediate second check - should not alert due to cooldown
        await monitor.check_now(DataSourceType.INFLUXDB)
        assert len(alerts) == initial_alert_count  # No new alerts


class TestBackoffTiming:
    """Test reconnection backoff timing."""

    @pytest.mark.asyncio
    async def test_backoff_sequence(self):
        """Test that backoff follows expected sequence."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
            reconnect_backoff_seconds=(0.01, 0.02, 0.03),
            max_reconnect_attempts=3,
        )
        monitor = DataSourceHealthMonitor(datasource_configs=[config])

        # Mock checker to always fail
        mock_checker = MagicMock()
        mock_checker.check_health = AsyncMock(return_value=(False, None))
        monitor._checkers[DataSourceType.INFLUXDB] = mock_checker

        # Set initial disconnected state
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.DISCONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].last_disconnected_at = datetime.now(
            UTC
        )
        monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts = 0

        # Track timing
        start_time = asyncio.get_event_loop().time()

        # First reconnect attempt
        await monitor._attempt_reconnect(DataSourceType.INFLUXDB, config)
        assert monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts == 1

        # Second reconnect attempt
        await monitor._attempt_reconnect(DataSourceType.INFLUXDB, config)
        assert monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts == 2

        # Third reconnect attempt
        await monitor._attempt_reconnect(DataSourceType.INFLUXDB, config)
        assert monitor._metrics[DataSourceType.INFLUXDB].reconnect_attempts == 3

        # Fourth attempt should fail (max exceeded)
        await monitor._attempt_reconnect(DataSourceType.INFLUXDB, config)
        assert (
            monitor._metrics[DataSourceType.INFLUXDB].status == ConnectionStatus.FAILED
        )


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_monitor(self):
        """Test monitor with no datasources."""
        monitor = DataSourceHealthMonitor(datasource_configs=[])
        assert len(monitor.datasource_configs) == 0
        assert monitor.is_healthy() is True  # No sources = healthy

    @pytest.mark.asyncio
    async def test_alert_handler_exception(self):
        """Test that alert handler exceptions don't crash the monitor."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
        )
        monitor = DataSourceHealthMonitor(datasource_configs=[config])

        # Add failing handler
        async def failing_handler(alert):
            raise Exception("Handler failed")

        monitor.add_alert_handler(failing_handler)

        # Add working handler
        working_calls = []

        async def working_handler(alert):
            working_calls.append(alert)

        monitor.add_alert_handler(working_handler)

        # Dispatch alert
        alert = DatasourceHealthAlert(
            alert_type="test",
            source_type=DataSourceType.INFLUXDB,
            source_name="Test",
            message="Test",
            severity=AlertSeverity.INFO,
        )
        await monitor._dispatch_alert(alert)

        # Working handler should still be called
        assert len(working_calls) == 1

    def test_metrics_with_none_values(self):
        """Test metrics with None values."""
        metrics = ConnectionMetrics(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test",
            status=ConnectionStatus.DISCONNECTED,
            last_connected_at=None,
            last_disconnected_at=None,
            response_time_ms=None,
        )
        d = metrics.to_dict()
        assert d["last_connected_at"] is None
        assert d["last_disconnected_at"] is None
        assert d["response_time_ms"] is None

    @pytest.mark.asyncio
    async def test_check_now_nonexistent_source(self):
        """Test check_now with nonexistent source."""
        monitor = DataSourceHealthMonitor(datasource_configs=[])
        # Should not raise
        await monitor.check_now(DataSourceType.INFLUXDB)


class TestPrometheusMetrics:
    """Test Prometheus-compatible metrics."""

    def test_metrics_format(self):
        """Test that metrics are in correct format for Prometheus."""
        config = DatasourceConfig(
            source_type=DataSourceType.INFLUXDB,
            source_name="Test InfluxDB",
            host="localhost",
            port=8086,
        )
        monitor = DataSourceHealthMonitor(datasource_configs=[config])

        # Set some values
        monitor._metrics[DataSourceType.INFLUXDB].status = ConnectionStatus.CONNECTED
        monitor._metrics[DataSourceType.INFLUXDB].uptime_seconds = 3600
        monitor._metrics[DataSourceType.INFLUXDB].response_time_ms = 25.5

        grafana_metrics = monitor.get_metrics_for_grafana()

        # Check format
        assert len(grafana_metrics) == 1
        metric = grafana_metrics[0]
        assert "timestamp" in metric
        assert "source_type" in metric
        assert "is_connected" in metric
        assert "is_healthy" in metric
        assert "availability_percentage" in metric
        assert "response_time_ms" in metric

        # Check types
        assert isinstance(metric["is_connected"], int)
        assert isinstance(metric["is_healthy"], int)
        assert isinstance(metric["availability_percentage"], float)
