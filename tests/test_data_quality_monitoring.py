"""Tests for data quality monitoring.

Tests for ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from operations.data_quality_monitoring import (
    AlertSeverity,
    DataQualityMonitor,
    DataSource,
    DiscordAlertSender,
    FreshnessMetrics,
    GapAlert,
    GrafanaDashboardQueries,
    InfluxDBExporter,
    SourceConfig,
    check_data_freshness,
    detect_data_gaps,
    send_freshness_alert,
)


class MockDataPoint:
    """Mock data point for testing."""

    def __init__(self, timestamp: int):
        self.timestamp = timestamp

    @property
    def datetime_utc(self) -> datetime:
        """Return timestamp as UTC datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000, tz=UTC)


class TestFreshnessMetrics:
    """Tests for FreshnessMetrics dataclass."""

    def test_freshness_metrics_creation(self):
        """Test creating FreshnessMetrics."""
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )

        assert metrics.source == DataSource.BINANCE
        assert metrics.symbol == "BTC/USDT"
        assert metrics.timeframe == "1m"
        assert metrics.last_update_timestamp == 1234567890000
        assert metrics.data_age_seconds == 30.0
        assert metrics.threshold_seconds == 300.0
        assert metrics.is_fresh is True
        assert metrics.is_stale is False
        assert metrics.staleness_seconds == 0.0

    def test_freshness_metrics_stale(self):
        """Test stale data detection."""
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            last_update_timestamp=1234567890000,
            data_age_seconds=600.0,
            threshold_seconds=300.0,
            is_fresh=False,
            checked_at=now,
        )

        assert metrics.is_fresh is False
        assert metrics.is_stale is True
        assert metrics.staleness_seconds == 300.0

    def test_freshness_metrics_no_data(self):
        """Test metrics with no data."""
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BITGET,
            symbol="SOL/USDT",
            timeframe="1h",
            last_update_timestamp=None,
            data_age_seconds=None,
            threshold_seconds=300.0,
            is_fresh=False,
            checked_at=now,
        )

        assert metrics.is_fresh is False
        assert metrics.is_stale is True
        assert metrics.staleness_seconds == 0.0

    def test_freshness_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )

        data = metrics.to_dict()
        assert data["source"] == "binance"
        assert data["symbol"] == "BTC/USDT"
        assert data["timeframe"] == "1m"
        assert data["is_fresh"] is True
        assert data["is_stale"] is False


class TestGapAlert:
    """Tests for GapAlert dataclass."""

    def test_gap_alert_creation(self):
        """Test creating GapAlert."""
        now = datetime.now(UTC)
        gap = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=10,
            detected_at=now,
            severity=AlertSeverity.WARNING,
        )

        assert gap.source == DataSource.BINANCE
        assert gap.symbol == "BTC/USDT"
        assert gap.timeframe == "1m"
        assert gap.gap_start == 1234567890000
        assert gap.gap_end == 1234567950000
        assert gap.expected_candles == 10
        assert gap.duration_seconds == 60.0
        assert gap.severity == AlertSeverity.WARNING

    def test_gap_alert_to_dict(self):
        """Test converting gap alert to dictionary."""
        now = datetime.now(UTC)
        gap = GapAlert(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=2,
            detected_at=now,
            severity=AlertSeverity.CRITICAL,
        )

        data = gap.to_dict()
        assert data["source"] == "bybit"
        assert data["symbol"] == "ETH/USDT"
        assert data["timeframe"] == "5m"
        assert data["expected_candles"] == 2
        assert data["severity"] == "critical"


class TestSourceConfig:
    """Tests for SourceConfig dataclass."""

    def test_source_config_defaults(self):
        """Test default source configuration."""
        config = SourceConfig(source=DataSource.BINANCE)

        assert config.source == DataSource.BINANCE
        assert config.symbols == []
        assert config.timeframes == ["1m", "5m", "15m", "1h"]
        assert config.freshness_threshold_seconds == 300.0
        assert config.gap_detection_enabled is True
        assert config.enabled is True

    def test_source_config_custom(self):
        """Test custom source configuration."""
        config = SourceConfig(
            source=DataSource.BYBIT,
            symbols=["BTC/USDT", "ETH/USDT"],
            timeframes=["1m", "1h"],
            freshness_threshold_seconds=600.0,
            gap_detection_enabled=False,
            enabled=True,
        )

        assert config.source == DataSource.BYBIT
        assert config.symbols == ["BTC/USDT", "ETH/USDT"]
        assert config.timeframes == ["1m", "1h"]
        assert config.freshness_threshold_seconds == 600.0
        assert config.gap_detection_enabled is False

    def test_source_config_to_dict(self):
        """Test converting config to dictionary."""
        config = SourceConfig(
            source=DataSource.BITGET,
            symbols=["SOL/USDT"],
            timeframes=["1m"],
        )

        data = config.to_dict()
        assert data["source"] == "bitget"
        assert data["symbols"] == ["SOL/USDT"]
        assert data["timeframes"] == ["1m"]


class TestDataQualityMonitor:
    """Tests for DataQualityMonitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a test monitor."""
        return DataQualityMonitor()

    @pytest.fixture
    def sample_config(self):
        """Create sample source configuration."""
        return SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT"],
            timeframes=["1m"],
            freshness_threshold_seconds=300.0,
        )

    @pytest.mark.asyncio
    async def test_add_remove_source_config(self, monitor, sample_config):
        """Test adding and removing source configurations."""
        monitor.add_source_config(sample_config)
        assert DataSource.BINANCE in monitor.source_configs

        monitor.remove_source_config(DataSource.BINANCE)
        assert DataSource.BINANCE not in monitor.source_configs

    @pytest.mark.asyncio
    async def test_check_data_freshness_fresh(self, monitor, sample_config):
        """Test freshness check with fresh data."""
        monitor.add_source_config(sample_config)

        now = datetime.now(UTC)
        # Data from 30 seconds ago
        mock_timestamp = int((now - timedelta(seconds=30)).timestamp() * 1000)
        data = [MockDataPoint(mock_timestamp)]

        metrics = await monitor.check_data_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
        )

        assert metrics.is_fresh is True
        assert metrics.is_stale is False
        assert metrics.data_age_seconds <= 35.0  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_check_data_freshness_stale(self, monitor, sample_config):
        """Test freshness check with stale data."""
        monitor.add_source_config(sample_config)

        now = datetime.now(UTC)
        # Data from 10 minutes ago
        mock_timestamp = int((now - timedelta(minutes=10)).timestamp() * 1000)
        data = [MockDataPoint(mock_timestamp)]

        metrics = await monitor.check_data_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
        )

        assert metrics.is_fresh is False
        assert metrics.is_stale is True
        assert metrics.data_age_seconds >= 600.0

    @pytest.mark.asyncio
    async def test_check_data_freshness_no_data(self, monitor, sample_config):
        """Test freshness check with no data."""
        monitor.add_source_config(sample_config)

        metrics = await monitor.check_data_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=[],
        )

        assert metrics.is_fresh is False
        assert metrics.is_stale is True
        assert metrics.data_age_seconds is None

    @pytest.mark.asyncio
    async def test_detect_data_gaps_no_gap(self, monitor):
        """Test gap detection with continuous data."""
        now = datetime.now(UTC)
        # Continuous 1-minute data
        data = [
            MockDataPoint(int((now - timedelta(minutes=2)).timestamp() * 1000)),
            MockDataPoint(int((now - timedelta(minutes=1)).timestamp() * 1000)),
            MockDataPoint(int(now.timestamp() * 1000)),
        ]

        gaps = await monitor.detect_data_gaps(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,  # 1 minute
        )

        assert len(gaps) == 0

    @pytest.mark.asyncio
    async def test_detect_data_gaps_with_gap(self, monitor):
        """Test gap detection with missing data."""
        now = datetime.now(UTC)
        # Data with a 5-minute gap
        data = [
            MockDataPoint(int((now - timedelta(minutes=10)).timestamp() * 1000)),
            MockDataPoint(int((now - timedelta(minutes=5)).timestamp() * 1000)),
        ]

        gaps = await monitor.detect_data_gaps(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,  # 1 minute
        )

        assert len(gaps) == 1
        assert gaps[0].expected_candles >= 4  # At least 4 missing candles
        assert gaps[0].source == DataSource.BINANCE

    @pytest.mark.asyncio
    async def test_detect_data_gaps_internal_gap(self, monitor):
        """Test gap detection within data batch."""
        now = datetime.now(UTC)
        # Data with internal gap
        data = [
            MockDataPoint(int((now - timedelta(minutes=5)).timestamp() * 1000)),
            MockDataPoint(int((now - timedelta(minutes=2)).timestamp() * 1000)),
            MockDataPoint(int(now.timestamp() * 1000)),
        ]

        gaps = await monitor.detect_data_gaps(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        # Should detect gap between first and second point
        assert len(gaps) >= 1

    @pytest.mark.asyncio
    async def test_alert_handler(self, monitor):
        """Test alert handler registration and dispatch."""
        handler = AsyncMock()
        monitor.add_alert_handler(handler)

        await monitor._dispatch_alert(
            alert_type="freshness",
            source=DataSource.BINANCE,
            message="Test alert",
            severity=AlertSeverity.WARNING,
            metrics={"test": "data"},
        )

        handler.assert_called_once()
        call_args = handler.call_args[0]
        assert call_args[0] == "freshness"
        assert call_args[1] == DataSource.BINANCE
        assert call_args[2] == "Test alert"

    @pytest.mark.asyncio
    async def test_remove_alert_handler(self, monitor):
        """Test removing alert handler."""
        handler = AsyncMock()
        monitor.add_alert_handler(handler)
        monitor.remove_alert_handler(handler)

        await monitor._dispatch_alert(
            alert_type="freshness",
            source=DataSource.BINANCE,
            message="Test",
            severity=AlertSeverity.INFO,
            metrics={},
        )

        handler.assert_not_called()

    def test_get_latest_metrics(self, monitor, sample_config):
        """Test retrieving latest metrics."""
        monitor.add_source_config(sample_config)

        # Add some mock metrics
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = metrics

        # Get all metrics
        all_metrics = monitor.get_latest_metrics()
        assert len(all_metrics) == 1

        # Filter by source
        binance_metrics = monitor.get_latest_metrics(source=DataSource.BINANCE)
        assert len(binance_metrics) == 1

        # Filter by non-matching source
        bybit_metrics = monitor.get_latest_metrics(source=DataSource.BYBIT)
        assert len(bybit_metrics) == 0

    def test_get_stale_sources(self, monitor):
        """Test retrieving stale sources."""
        now = datetime.now(UTC)

        # Add fresh metric
        fresh_metric = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = fresh_metric

        # Add stale metric
        stale_metric = FreshnessMetrics(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            last_update_timestamp=1234567890000,
            data_age_seconds=600.0,
            threshold_seconds=300.0,
            is_fresh=False,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BYBIT, "ETH/USDT", "5m")] = stale_metric

        stale = monitor.get_stale_sources()
        assert len(stale) == 1
        assert stale[0].source == DataSource.BYBIT

    def test_get_active_gaps(self, monitor):
        """Test retrieving active gaps."""
        now = datetime.now(UTC)

        gap = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=10,
            detected_at=now,
        )
        monitor._active_gaps[(DataSource.BINANCE, "BTC/USDT", "1m")] = gap

        active = monitor.get_active_gaps()
        assert len(active) == 1
        assert active[0].source == DataSource.BINANCE

    def test_get_all_metrics(self, monitor):
        """Test getting all metrics summary."""
        now = datetime.now(UTC)

        # Add a metric
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = metrics

        summary = monitor.get_all_metrics()
        assert "freshness" in summary
        assert "gaps" in summary
        assert summary["freshness"]["total_monitored"] == 1
        assert summary["freshness"]["stale_count"] == 0

    def test_get_freshness_for_grafana(self, monitor):
        """Test Grafana-formatted freshness metrics."""
        now = datetime.now(UTC)

        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = metrics

        grafana_data = monitor.get_freshness_for_grafana()
        assert len(grafana_data) == 1
        assert grafana_data[0]["source"] == "binance"
        assert grafana_data[0]["is_fresh"] == 1
        assert grafana_data[0]["is_stale"] == 0

    def test_clear_metrics(self, monitor):
        """Test clearing all metrics."""
        now = datetime.now(UTC)

        # Add some data
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )
        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = metrics
        monitor._metrics_history.append(metrics)

        monitor.clear_metrics()
        assert len(monitor._latest_metrics) == 0
        assert len(monitor._metrics_history) == 0

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, monitor):
        """Test starting and stopping monitoring."""
        await monitor.start_monitoring(interval_seconds=0.1)
        assert monitor._running is True
        assert monitor._monitor_task is not None

        await asyncio.sleep(0.15)  # Let it run one iteration

        await monitor.stop_monitoring()
        assert monitor._running is False
        assert monitor._monitor_task is None


class TestDiscordAlertSender:
    """Tests for DiscordAlertSender class."""

    @pytest.fixture
    def sender(self):
        """Create a test sender."""
        return DiscordAlertSender(
            webhook_url="https://discord.com/api/webhooks/test",
            alerts_channel="alerts",
        )

    @pytest.fixture
    def sender_no_webhook(self):
        """Create a test sender without webhook."""
        return DiscordAlertSender(
            webhook_url=None,
            alerts_channel="alerts",
        )

    @pytest.mark.asyncio
    async def test_send_freshness_alert_success(self, sender):
        """Test sending freshness alert with successful webhook call."""
        # Mock aiohttp ClientSession
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.text = AsyncMock(return_value="")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await sender.send_freshness_alert(
                source=DataSource.BINANCE,
                symbol="BTC/USDT",
                timeframe="1m",
                data_age_seconds=600.0,
                threshold_seconds=300.0,
            )

        assert result["success"] is True
        assert result["channel"] == "alerts"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_send_freshness_alert_rate_limited(self, sender):
        """Test sending freshness alert when rate limited."""
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.headers = {"Retry-After": "10"}
        mock_response.text = AsyncMock(return_value="Rate limited")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await sender.send_freshness_alert(
                source=DataSource.BINANCE,
                symbol="BTC/USDT",
                timeframe="1m",
                data_age_seconds=600.0,
                threshold_seconds=300.0,
            )

        assert result["success"] is False
        assert "Rate limited" in result["error"]
        assert result["retry_after"] == 10.0

    @pytest.mark.asyncio
    async def test_send_freshness_alert_no_webhook(self, sender_no_webhook):
        """Test sending freshness alert without webhook configured."""
        result = await sender_no_webhook.send_freshness_alert(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            data_age_seconds=600.0,
            threshold_seconds=300.0,
        )

        assert result["success"] is False
        assert "Discord webhook not configured" in result["error"]
        assert "embed" in result
        assert "Stale Data Alert" in result["embed"]["title"]

    @pytest.mark.asyncio
    async def test_send_freshness_alert_no_data(self, sender_no_webhook):
        """Test sending freshness alert with no data and no webhook."""
        result = await sender_no_webhook.send_freshness_alert(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            data_age_seconds=None,
            threshold_seconds=300.0,
        )

        assert result["success"] is False
        assert "No Data" in result["embed"]["title"]

    @pytest.mark.asyncio
    async def test_send_gap_alert_success(self, sender):
        """Test sending gap alert with successful webhook call."""
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.text = AsyncMock(return_value="")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        gap = GapAlert(
            source=DataSource.BITGET,
            symbol="SOL/USDT",
            timeframe="1m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=10,
            severity=AlertSeverity.WARNING,
        )

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await sender.send_gap_alert(gap)

        assert result["success"] is True
        assert result["channel"] == "alerts"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_send_gap_alert_no_webhook(self, sender_no_webhook):
        """Test sending gap alert without webhook configured."""
        gap = GapAlert(
            source=DataSource.BITGET,
            symbol="SOL/USDT",
            timeframe="1m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=10,
            severity=AlertSeverity.WARNING,
        )

        result = await sender_no_webhook.send_gap_alert(gap)

        assert result["success"] is False
        assert "Discord webhook not configured" in result["error"]
        assert "embed" in result
        assert "Gap Detected" in result["embed"]["title"]
        assert "10" in result["embed"]["description"]

    @pytest.mark.asyncio
    async def test_send_gap_alert_http_error(self, sender):
        """Test sending gap alert with HTTP error response."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        gap = GapAlert(
            source=DataSource.BITGET,
            symbol="SOL/USDT",
            timeframe="1m",
            gap_start=1234567890000,
            gap_end=1234567950000,
            expected_candles=10,
            severity=AlertSeverity.WARNING,
        )

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await sender.send_gap_alert(gap)

        assert result["success"] is False
        assert "HTTP 400" in result["error"]

    @pytest.mark.asyncio
    async def test_send_freshness_alert_aiohttp_not_installed(self, sender):
        """Test sending freshness alert when aiohttp is not installed."""
        with patch(
            "aiohttp.ClientSession",
            side_effect=ImportError("No module named 'aiohttp'"),
        ):
            result = await sender.send_freshness_alert(
                source=DataSource.BINANCE,
                symbol="BTC/USDT",
                timeframe="1m",
                data_age_seconds=600.0,
                threshold_seconds=300.0,
            )

        assert result["success"] is False
        assert "aiohttp not installed" in result["error"]


class TestGrafanaDashboardQueries:
    """Tests for GrafanaDashboardQueries class."""

    def test_get_freshness_panel_query(self):
        """Test freshness panel query generation."""
        query = GrafanaDashboardQueries.get_freshness_panel_query()
        assert "data_freshness" in query
        assert "data_age_seconds" in query

    def test_get_freshness_panel_query_with_source(self):
        """Test freshness panel query with source filter."""
        query = GrafanaDashboardQueries.get_freshness_panel_query(source="binance")
        assert 'r.source == "binance"' in query

    def test_get_freshness_status_query(self):
        """Test freshness status query generation."""
        query = GrafanaDashboardQueries.get_freshness_status_query()
        assert "is_stale" in query
        assert "last()" in query

    def test_get_gap_count_query(self):
        """Test gap count query generation."""
        query = GrafanaDashboardQueries.get_gap_count_query(hours=24)
        assert "data_gaps" in query
        assert "range(start: -24h)" in query

    def test_get_last_update_query(self):
        """Test last update query generation."""
        query = GrafanaDashboardQueries.get_last_update_query()
        assert "last()" in query

    def test_get_dashboard_json_template(self):
        """Test dashboard template generation."""
        dashboard = GrafanaDashboardQueries.get_dashboard_json_template()
        assert "dashboard" in dashboard
        assert dashboard["dashboard"]["title"] == "Data Quality Monitoring"
        assert len(dashboard["dashboard"]["panels"]) == 4


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_check_data_freshness(self):
        """Test check_data_freshness convenience function."""
        now = datetime.now(UTC)
        mock_timestamp = int((now - timedelta(seconds=30)).timestamp() * 1000)
        data = [MockDataPoint(mock_timestamp)]

        metrics = await check_data_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            threshold_seconds=300.0,
        )

        assert metrics.is_fresh is True
        assert metrics.source == DataSource.BINANCE

    @pytest.mark.asyncio
    async def test_detect_data_gaps(self):
        """Test detect_data_gaps convenience function."""
        now = datetime.now(UTC)
        # Data with gap
        data = [
            MockDataPoint(int((now - timedelta(minutes=5)).timestamp() * 1000)),
            MockDataPoint(int(now.timestamp() * 1000)),
        ]

        gaps = await detect_data_gaps(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        assert isinstance(gaps, list)

    @pytest.mark.asyncio
    async def test_send_freshness_alert(self):
        """Test send_freshness_alert convenience function without webhook."""
        result = await send_freshness_alert(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            data_age_seconds=600.0,
            threshold_seconds=300.0,
        )

        # Without webhook configured, returns success=False with warning
        assert result["success"] is False
        assert "embed" in result
        assert "Discord webhook not configured" in result["error"]


class TestInfluxDBExporter:
    """Tests for InfluxDBExporter class."""

    @pytest.fixture
    def exporter(self):
        """Create a test exporter."""
        return InfluxDBExporter(
            influx_url="http://localhost:8086",
            influx_token="test-token",
            influx_org="chiseai",
            influx_bucket="data_quality",
        )

    def test_exporter_creation(self, exporter):
        """Test creating InfluxDB exporter."""
        assert exporter.influx_url == "http://localhost:8086"
        assert exporter.influx_token == "test-token"
        assert exporter.influx_org == "chiseai"
        assert exporter.influx_bucket == "data_quality"

    def test_exporter_close(self, exporter):
        """Test closing exporter."""
        # Should not raise even if client not initialized
        exporter.close()

    @pytest.mark.skip(reason="Requires influxdb-client to be installed")
    def test_export_freshness_metric(self, exporter):
        """Test exporting freshness metric."""
        now = datetime.now(UTC)
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
            checked_at=now,
        )

        result = exporter.export_freshness_metric(metrics)
        # Will be False if influxdb-client not available
        assert isinstance(result, bool)


class TestIntegration:
    """Integration tests for data quality monitoring."""

    @pytest.mark.asyncio
    async def test_full_data_quality_check(self):
        """Test full data quality check workflow."""
        # Create monitor
        config = SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT"],
            timeframes=["1m"],
            freshness_threshold_seconds=300.0,
        )
        monitor = DataQualityMonitor(source_configs=[config])

        # Create test data with gap
        now = datetime.now(UTC)
        data = [
            MockDataPoint(int((now - timedelta(minutes=5)).timestamp() * 1000)),
            MockDataPoint(int(now.timestamp() * 1000)),
        ]

        # Run full check
        freshness, gaps = await monitor.check_data_quality(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        # Verify results
        assert isinstance(freshness, FreshnessMetrics)
        assert isinstance(gaps, list)

    @pytest.mark.asyncio
    async def test_alert_cooldown(self):
        """Test alert cooldown functionality."""
        config = SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT"],
            timeframes=["1m"],
            freshness_threshold_seconds=300.0,
        )
        monitor = DataQualityMonitor(
            source_configs=[config],
            freshness_cooldown_seconds=60.0,
        )

        # Track alert calls
        alert_calls = []

        async def tracking_handler(
            alert_type: str,
            source: DataSource,
            message: str,
            severity: str,
            metrics: dict,
        ) -> None:
            alert_calls.append((alert_type, source, message))

        monitor.add_alert_handler(tracking_handler)

        # Create stale data
        now = datetime.now(UTC)
        mock_timestamp = int((now - timedelta(minutes=10)).timestamp() * 1000)
        data = [MockDataPoint(mock_timestamp)]

        # First check - should alert
        await monitor.check_data_quality(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        # Should have triggered alert
        assert len(alert_calls) >= 1

        # Second check immediately - should not alert due to cooldown
        initial_count = len(alert_calls)
        await monitor.check_data_quality(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        # Should not have triggered new alert
        assert len(alert_calls) == initial_count
