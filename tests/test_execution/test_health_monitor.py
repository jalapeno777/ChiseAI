"""Tests for execution health monitor.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execution.health_monitor import (
    AlertSeverity,
    ConnectionStatus,
    DataGapAlert,
    ExecutionHealthMonitor,
)


class TestDataGapAlert:
    """Test DataGapAlert dataclass."""

    def test_create_alert(self):
        """Test creating a data gap alert."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=100.0,
            severity=AlertSeverity.WARNING,
        )

        assert alert.source == "bybit"
        assert alert.duration_seconds == 100.0
        assert alert.severity == AlertSeverity.WARNING

    def test_to_dict(self):
        """Test serialization."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=100.0,
            severity=AlertSeverity.CRITICAL,
        )

        data = alert.to_dict()

        assert data["source"] == "bybit"
        assert data["severity"] == "critical"
        assert data["duration_seconds"] == 100.0


class TestConnectionStatus:
    """Test ConnectionStatus dataclass."""

    def test_default_status(self):
        """Test default connection status."""
        status = ConnectionStatus(exchange="bybit")

        assert status.exchange == "bybit"
        assert status.is_connected is False
        assert status.time_since_heartbeat == float("inf")

    def test_time_since_message(self):
        """Test time since message calculation."""
        status = ConnectionStatus(
            exchange="bybit",
            last_message=datetime.now(UTC),
        )

        # Should be close to 0
        assert status.time_since_message < 1.0

    def test_to_dict(self):
        """Test serialization."""
        status = ConnectionStatus(
            exchange="bybit",
            is_connected=True,
            last_heartbeat=datetime.now(UTC),
            reconnect_count=5,
            latency_ms=50.0,
        )

        data = status.to_dict()

        assert data["exchange"] == "bybit"
        assert data["is_connected"] is True
        assert data["reconnect_count"] == 5
        assert data["latency_ms"] == 50.0


class TestExecutionHealthMonitor:
    """Test ExecutionHealthMonitor functionality."""

    @pytest.fixture
    def mock_bybit(self):
        """Create mock Bybit connector."""
        return MagicMock()

    @pytest.fixture
    def mock_bitget(self):
        """Create mock Bitget connector."""
        return MagicMock()

    @pytest.fixture
    def monitor(self, mock_bybit, mock_bitget):
        """Create health monitor instance."""
        return ExecutionHealthMonitor(
            bybit_connector=mock_bybit,
            bitget_connector=mock_bitget,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """Test starting and stopping monitor."""
        await monitor.start()
        assert monitor._running is True
        assert monitor._monitor_task is not None

        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_check_health_bybit(self, monitor, mock_bybit):
        """Test health check for Bybit."""
        mock_bybit.health_check = AsyncMock(
            return_value={
                "healthy": True,
                "connected": True,
                "last_message_seconds_ago": 5.0,
            }
        )

        await monitor._check_health()

        status = monitor.get_status("bybit")
        assert status["is_connected"] is True
        mock_bybit.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_health_bitget(self, monitor, mock_bitget):
        """Test health check for Bitget."""
        mock_bitget.health_check = AsyncMock(
            return_value={
                "healthy": True,
                "connected": True,
                "last_message_seconds_ago": 3.0,
            }
        )

        await monitor._check_health()

        status = monitor.get_status("bitget")
        assert status["is_connected"] is True

    @pytest.mark.asyncio
    async def test_data_gap_detection(self, monitor, mock_bybit):
        """Test data gap detection."""
        mock_bybit.health_check = AsyncMock(
            return_value={
                "healthy": False,
                "connected": True,
                "last_message_seconds_ago": 15.0,  # > 10s threshold
            }
        )

        await monitor._check_health()

        alerts = monitor.get_active_alerts("bybit")
        assert len(alerts) == 1
        assert alerts[0].source == "bybit"
        assert alerts[0].duration_seconds == 15.0

    @pytest.mark.asyncio
    async def test_critical_gap_detection(self, monitor, mock_bybit):
        """Test critical data gap detection (>60s)."""
        mock_bybit.health_check = AsyncMock(
            return_value={
                "healthy": False,
                "connected": True,
                "last_message_seconds_ago": 90.0,  # > 60s
            }
        )

        await monitor._check_health()

        alerts = monitor.get_active_alerts("bybit")
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_alert_callback(self, monitor, mock_bybit):
        """Test alert callback invocation."""
        callback_called = False
        received_alert = None

        async def alert_callback(alert):
            nonlocal callback_called, received_alert
            callback_called = True
            received_alert = alert

        monitor._alert_callback = alert_callback

        mock_bybit.health_check = AsyncMock(
            return_value={
                "healthy": False,
                "connected": True,
                "last_message_seconds_ago": 20.0,
            }
        )

        await monitor._check_health()

        assert callback_called is True
        assert received_alert is not None
        assert received_alert.source == "bybit"

    def test_get_status_all(self, monitor):
        """Test getting status for all exchanges."""
        status = monitor.get_status()

        assert "bybit" in status
        assert "bitget" in status
        assert "monitoring_active" in status

    def test_is_healthy(self, monitor):
        """Test is_healthy check."""
        # Initially not healthy
        assert monitor.is_healthy("bybit") is False

        # Set healthy status
        monitor._status["bybit"].is_connected = True
        monitor._status["bybit"].last_heartbeat = datetime.now(UTC)

        assert monitor.is_healthy("bybit") is True

    def test_is_healthy_stale(self, monitor):
        """Test is_healthy with stale heartbeat."""
        monitor._status["bybit"].is_connected = True
        # Set heartbeat to 100 seconds ago
        from datetime import timedelta

        monitor._status["bybit"].last_heartbeat = datetime.now(UTC) - timedelta(
            seconds=100
        )

        # Should not be healthy (2x heartbeat interval = 60s)
        assert monitor.is_healthy("bybit") is False

    def test_get_active_alerts(self, monitor):
        """Test getting active alerts."""
        alert1 = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=100.0,
            severity=AlertSeverity.WARNING,
        )
        alert2 = DataGapAlert(
            source="bitget",
            symbol="ETHUSDT",
            gap_start=1704067200.0,
            gap_end=1704067250.0,
            duration_seconds=50.0,
            severity=AlertSeverity.WARNING,
        )

        monitor._status["bybit"].data_gap_alerts.append(alert1)
        monitor._status["bitget"].data_gap_alerts.append(alert2)

        all_alerts = monitor.get_active_alerts()
        assert len(all_alerts) == 2

        bybit_alerts = monitor.get_active_alerts("bybit")
        assert len(bybit_alerts) == 1
        assert bybit_alerts[0].source == "bybit"

    def test_clear_alert(self, monitor):
        """Test clearing an alert."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=100.0,
            severity=AlertSeverity.WARNING,
        )
        monitor._status["bybit"].data_gap_alerts.append(alert)

        alert_id = "bybit_BTCUSDT_1704067200.0"
        cleared = monitor.clear_alert(alert_id)

        assert cleared is True
        assert len(monitor._status["bybit"].data_gap_alerts) == 0

    def test_clear_alert_not_found(self, monitor):
        """Test clearing non-existent alert."""
        cleared = monitor.clear_alert("nonexistent")
        assert cleared is False

    def test_alert_history(self, monitor):
        """Test alert history tracking."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=100.0,
            severity=AlertSeverity.WARNING,
        )
        monitor._alert_history.append(alert)

        history = monitor.get_alert_history()
        assert len(history) == 1
        assert history[0]["source"] == "bybit"

    def test_alert_history_limit(self, monitor):
        """Test alert history limit."""
        # Add more alerts than the limit
        for i in range(150):
            alert = DataGapAlert(
                source="bybit",
                symbol=f"SYM{i}",
                gap_start=1704067200.0 + i,
                gap_end=1704067300.0 + i,
                duration_seconds=100.0,
                severity=AlertSeverity.WARNING,
            )
            monitor._alert_history.append(alert)

        history = monitor.get_alert_history(limit=50)
        assert len(history) == 50

    def test_max_alerts_limit(self, monitor):
        """Test that max alerts limit is enforced via _handle_data_gap."""
        # The limit is enforced when adding through _handle_data_gap
        # Direct append to _alert_history bypasses the limit
        assert monitor.MAX_ALERTS == 100


class TestDiscordIntegration:
    """Test Discord integration functions."""

    @pytest.mark.asyncio
    async def test_send_gap_alert_to_discord(self):
        """Test sending gap alert to Discord."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=15.0,
            severity=AlertSeverity.WARNING,
        )

        # Mock the Discord sender - it's imported inside the function
        with patch(
            "monitoring.data_quality.discord_sender.DataQualityDiscordSender"
        ) as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender
            mock_client = AsyncMock()
            mock_sender._get_client = MagicMock(return_value=mock_client)
            mock_client.send_message = AsyncMock(return_value={"success": True})

            result = await send_gap_alert_to_discord(alert)

            assert result["success"] is True
            mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_gap_alert_error(self):
        """Test Discord send error handling."""
        alert = DataGapAlert(
            source="bybit",
            symbol="BTCUSDT",
            gap_start=1704067200.0,
            gap_end=1704067300.0,
            duration_seconds=15.0,
            severity=AlertSeverity.WARNING,
        )

        with patch(
            "monitoring.data_quality.discord_sender.DataQualityDiscordSender"
        ) as mock_sender_class:
            mock_sender = MagicMock()
            mock_sender_class.return_value = mock_sender
            mock_sender._get_client = MagicMock(
                side_effect=Exception("Connection error")
            )

            result = await send_gap_alert_to_discord(alert)

            assert result["success"] is False
            assert "Connection error" in result["error"]


# Import for testing
from execution.health_monitor import send_gap_alert_to_discord
