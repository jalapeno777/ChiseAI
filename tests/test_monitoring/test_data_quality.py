"""Tests for data quality monitoring.

Tests for freshness monitoring, gap detection, and alerting.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitoring.data_quality import (
    AlertSeverity,
    DataFreshnessMonitor,
    DataQualityAlert,
    DataQualityMonitor,
    DataSource,
    FreshnessMetrics,
    GapAlert,
    GapDetector,
    SourceConfig,
)
from data_ingestion.gap_detector import DataGap


class TestFreshnessMetrics:
    """Tests for FreshnessMetrics dataclass."""

    def test_is_stale_property(self):
        """Test is_stale property returns correct value."""
        fresh = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        assert not fresh.is_stale

        stale = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=400.0,
            threshold_seconds=300.0,
            is_fresh=False,
        )
        assert stale.is_stale

    def test_staleness_seconds_property(self):
        """Test staleness_seconds property calculation."""
        fresh = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        assert fresh.staleness_seconds == 0.0

        stale = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=400.0,
            threshold_seconds=300.0,
            is_fresh=False,
        )
        assert stale.staleness_seconds == 100.0

    def test_to_dict(self):
        """Test to_dict serialization."""
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        d = metrics.to_dict()
        assert d["source"] == "binance"
        assert d["symbol"] == "BTC/USDT"
        assert d["timeframe"] == "1m"
        assert d["is_fresh"] is True
        assert d["is_stale"] is False


class TestGapAlert:
    """Tests for GapAlert dataclass."""

    def test_duration_seconds_property(self):
        """Test duration_seconds calculation."""
        gap = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1000000,
            gap_end=1060000,  # 60 seconds later
            expected_candles=1,
        )
        assert gap.duration_seconds == 60.0

    def test_to_dict(self):
        """Test to_dict serialization."""
        gap = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1000000,
            gap_end=1060000,
            expected_candles=1,
            severity=AlertSeverity.WARNING,
        )
        d = gap.to_dict()
        assert d["source"] == "binance"
        assert d["symbol"] == "BTC/USDT"
        assert d["expected_candles"] == 1
        assert d["severity"] == "warning"


class TestDataFreshnessMonitor:
    """Tests for DataFreshnessMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create a freshness monitor for testing."""
        config = SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT"],
            timeframes=["1m"],
            freshness_threshold_seconds=300.0,
        )
        return DataFreshnessMonitor(source_configs=[config])

    @pytest.fixture
    def mock_ohlcv_data(self):
        """Create mock OHLCV data."""
        mock_data = MagicMock()
        mock_data.timestamp = int(
            (datetime.now(UTC) - timedelta(seconds=30)).timestamp() * 1000
        )
        mock_data.datetime_utc = datetime.now(UTC) - timedelta(seconds=30)
        return [mock_data]

    @pytest.mark.asyncio
    async def test_check_freshness_fresh_data(self, monitor, mock_ohlcv_data):
        """Test freshness check with fresh data."""
        metrics = await monitor.check_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=mock_ohlcv_data,
        )

        assert metrics.is_fresh is True
        assert metrics.is_stale is False
        assert metrics.source == DataSource.BINANCE
        assert metrics.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_check_freshness_stale_data(self, monitor):
        """Test freshness check with stale data."""
        # Create old data
        old_data = MagicMock()
        old_data.timestamp = int(
            (datetime.now(UTC) - timedelta(seconds=400)).timestamp() * 1000
        )
        old_data.datetime_utc = datetime.now(UTC) - timedelta(seconds=400)

        metrics = await monitor.check_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=[old_data],
        )

        assert metrics.is_fresh is False
        assert metrics.is_stale is True

    @pytest.mark.asyncio
    async def test_check_freshness_empty_data(self, monitor):
        """Test freshness check with empty data."""
        metrics = await monitor.check_freshness(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=[],
        )

        assert metrics.is_fresh is False
        assert metrics.data_age_seconds is None

    def test_should_alert_respects_cooldown(self, monitor):
        """Test that should_alert respects cooldown."""
        source = DataSource.BINANCE
        symbol = "BTC/USDT"
        timeframe = "1m"

        # First call should allow alert
        assert monitor.should_alert(source, symbol, timeframe) is True

        # Record an alert
        monitor.record_alert(source, symbol, timeframe)

        # Immediate second call should not allow alert
        assert monitor.should_alert(source, symbol, timeframe) is False

    def test_get_latest_metrics_filtering(self, monitor):
        """Test get_latest_metrics with filters."""
        # Add some metrics
        metrics1 = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        metrics2 = FreshnessMetrics(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )

        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = metrics1
        monitor._latest_metrics[(DataSource.BYBIT, "ETH/USDT", "5m")] = metrics2

        # Test filtering by source
        binance_metrics = monitor.get_latest_metrics(source=DataSource.BINANCE)
        assert len(binance_metrics) == 1
        assert binance_metrics[0].source == DataSource.BINANCE

        # Test filtering by symbol
        btc_metrics = monitor.get_latest_metrics(symbol="BTC/USDT")
        assert len(btc_metrics) == 1
        assert btc_metrics[0].symbol == "BTC/USDT"

    def test_get_stale_sources(self, monitor):
        """Test get_stale_sources returns only stale metrics."""
        fresh = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        stale = FreshnessMetrics(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=400.0,
            threshold_seconds=300.0,
            is_fresh=False,
        )

        monitor._latest_metrics[(DataSource.BINANCE, "BTC/USDT", "1m")] = fresh
        monitor._latest_metrics[(DataSource.BYBIT, "ETH/USDT", "1m")] = stale

        stale_sources = monitor.get_stale_sources()
        assert len(stale_sources) == 1
        assert stale_sources[0].source == DataSource.BYBIT


class TestGapDetector:
    """Tests for GapDetector."""

    @pytest.fixture
    def detector(self):
        """Create a gap detector for testing."""
        return GapDetector(detection_window_seconds=60.0)

    def create_mock_candle(self, timestamp_ms: int):
        """Create a mock OHLCV candle."""
        mock = MagicMock()
        mock.timestamp = timestamp_ms
        return mock

    def test_detect_no_gap(self, detector):
        """Test gap detection with continuous data."""
        # Create data with 1-minute intervals
        base_time = 1000000
        data = [self.create_mock_candle(base_time + i * 60000) for i in range(5)]

        gaps = detector.update_and_detect(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        assert len(gaps) == 0

    def test_detect_gap(self, detector):
        """Test gap detection with missing data."""
        # Create data with a 3-minute gap between candles
        base_time = 1000000
        data = [
            self.create_mock_candle(base_time),
            self.create_mock_candle(base_time + 60000),
            # Gap here - missing 2 candles (120 seconds / 60 = 2)
            self.create_mock_candle(base_time + 240000),
            self.create_mock_candle(base_time + 300000),
        ]

        gaps = detector.update_and_detect(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=data,
            expected_interval_ms=60000,
        )

        # Gap detector finds internal gaps within the data
        # Gap from 1060000 to 1240000 = 180 seconds = 3 expected candles
        assert len(gaps) == 1
        assert gaps[0].expected_candles == 3

        # Now add data with a gap from the last seen
        new_data = [
            self.create_mock_candle(base_time + 480000),  # 3 min gap from last (300000)
        ]

        gaps = detector.update_and_detect(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=new_data,
            expected_interval_ms=60000,
        )

        # Gap from 3060000 to 4800000 = 1740000 ms = 29 candles
        assert len(gaps) == 1
        assert gaps[0].expected_candles >= 1

    def test_get_active_gaps_filtering(self, detector):
        """Test get_active_gaps with filtering."""
        gap1 = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1000000,
            gap_end=1060000,
            expected_candles=1,
        )
        gap2 = GapAlert(
            source=DataSource.BYBIT,
            symbol="ETH/USDT",
            timeframe="5m",
            gap_start=2000000,
            gap_end=2120000,
            expected_candles=1,
        )

        detector._active_gaps[(DataSource.BINANCE, "BTC/USDT", "1m")] = gap1
        detector._active_gaps[(DataSource.BYBIT, "ETH/USDT", "5m")] = gap2

        # Test filtering by source
        binance_gaps = detector.get_active_gaps(source=DataSource.BINANCE)
        assert len(binance_gaps) == 1
        assert binance_gaps[0].source == DataSource.BINANCE

    def test_clear_gap(self, detector):
        """Test clearing a gap."""
        gap = GapAlert(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            gap_start=1000000,
            gap_end=1060000,
            expected_candles=1,
        )

        detector._active_gaps[(DataSource.BINANCE, "BTC/USDT", "1m")] = gap
        assert len(detector.get_active_gaps()) == 1

        detector.clear_gap(DataSource.BINANCE, "BTC/USDT", "1m")
        assert len(detector.get_active_gaps()) == 0


class TestDataQualityMonitor:
    """Tests for DataQualityMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create a data quality monitor for testing."""
        return DataQualityMonitor(
            freshness_cooldown_seconds=60.0,
            gap_detection_window_seconds=60.0,
        )

    @pytest.fixture
    def mock_handler(self):
        """Create a mock alert handler."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_add_alert_handler(self, monitor, mock_handler):
        """Test adding an alert handler."""
        monitor.add_alert_handler(mock_handler)
        assert len(monitor._alert_handlers) == 1
        assert mock_handler in monitor._alert_handlers

    @pytest.mark.asyncio
    async def test_dispatch_alert(self, monitor, mock_handler):
        """Test dispatching alerts to handlers."""
        monitor.add_alert_handler(mock_handler)

        alert = DataQualityAlert(
            alert_type="test",
            source=DataSource.BINANCE,
            message="Test alert",
            severity=AlertSeverity.INFO,
        )

        await monitor._dispatch_alert(alert)

        mock_handler.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_dispatch_alert_handler_error(self, monitor):
        """Test that handler errors don't break other handlers."""
        failing_handler = AsyncMock(side_effect=Exception("Handler error"))
        success_handler = AsyncMock()

        monitor.add_alert_handler(failing_handler)
        monitor.add_alert_handler(success_handler)

        alert = DataQualityAlert(
            alert_type="test",
            source=DataSource.BINANCE,
            message="Test alert",
            severity=AlertSeverity.INFO,
        )

        await monitor._dispatch_alert(alert)

        # Both handlers should be called despite the error
        failing_handler.assert_called_once()
        success_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_data_quality_freshness_alert(self, monitor, mock_handler):
        """Test that freshness alerts are dispatched when data is stale."""
        monitor.add_alert_handler(mock_handler)

        # Create stale data
        old_data = MagicMock()
        old_data.timestamp = int(
            (datetime.now(UTC) - timedelta(seconds=400)).timestamp() * 1000
        )
        old_data.datetime_utc = datetime.now(UTC) - timedelta(seconds=400)

        freshness, gaps = await monitor.check_data_quality(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            data=[old_data],
            expected_interval_ms=60000,
        )

        assert freshness.is_stale is True
        # Alert should be dispatched
        mock_handler.assert_called()

    def test_get_all_metrics(self, monitor):
        """Test get_all_metrics returns expected structure."""
        metrics = monitor.get_all_metrics()

        assert "freshness" in metrics
        assert "gaps" in metrics
        assert "timestamp" in metrics
        assert metrics["freshness"]["total_monitored"] == 0

    def test_get_freshness_for_grafana(self, monitor):
        """Test get_freshness_for_grafana formatting."""
        # Add a metric
        metrics = FreshnessMetrics(
            source=DataSource.BINANCE,
            symbol="BTC/USDT",
            timeframe="1m",
            last_update_timestamp=1234567890000,
            data_age_seconds=30.0,
            threshold_seconds=300.0,
            is_fresh=True,
        )
        monitor.freshness_monitor._latest_metrics[
            (DataSource.BINANCE, "BTC/USDT", "1m")
        ] = metrics

        grafana_data = monitor.get_freshness_for_grafana()

        assert len(grafana_data) == 1
        assert grafana_data[0]["source"] == "binance"
        assert grafana_data[0]["is_fresh"] == 1


class TestSourceConfig:
    """Tests for SourceConfig."""

    def test_source_config_creation(self):
        """Test SourceConfig creation."""
        config = SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT", "ETH/USDT"],
            timeframes=["1m", "5m"],
            freshness_threshold_seconds=300.0,
        )

        assert config.source == DataSource.BINANCE
        assert config.symbols == ["BTC/USDT", "ETH/USDT"]
        assert config.timeframes == ["1m", "5m"]
        assert config.freshness_threshold_seconds == 300.0
        assert config.gap_detection_enabled is True
        assert config.enabled is True

    def test_source_config_to_dict(self):
        """Test SourceConfig serialization."""
        config = SourceConfig(
            source=DataSource.BINANCE,
            symbols=["BTC/USDT"],
            timeframes=["1m"],
        )

        d = config.to_dict()
        assert d["source"] == "binance"
        assert d["symbols"] == ["BTC/USDT"]
        assert d["timeframes"] == ["1m"]


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestDataQualityAlert:
    """Tests for DataQualityAlert."""

    def test_alert_creation(self):
        """Test DataQualityAlert creation."""
        alert = DataQualityAlert(
            alert_type="freshness",
            source=DataSource.BINANCE,
            message="Data is stale",
            severity=AlertSeverity.WARNING,
            metrics={"age": 400},
        )

        assert alert.alert_type == "freshness"
        assert alert.source == DataSource.BINANCE
        assert alert.message == "Data is stale"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metrics == {"age": 400}

    def test_alert_to_dict(self):
        """Test DataQualityAlert serialization."""
        alert = DataQualityAlert(
            alert_type="freshness",
            source=DataSource.BINANCE,
            message="Data is stale",
            severity=AlertSeverity.WARNING,
        )

        d = alert.to_dict()
        assert d["alert_type"] == "freshness"
        assert d["source"] == "binance"
        assert d["severity"] == "warning"
