"""Tests for drawdown monitor.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from execution.kill_switch.drawdown_monitor import (
    DrawdownMetrics,
    DrawdownMonitor,
    PortfolioValuePoint,
)


class TestPortfolioValuePoint:
    """Test PortfolioValuePoint dataclass."""

    def test_creation(self):
        """Test basic creation."""
        ts = datetime.now(UTC)
        point = PortfolioValuePoint(
            timestamp=ts,
            value=100000.0,
            source="bybit",
        )

        assert point.timestamp == ts
        assert point.value == 100000.0
        assert point.source == "bybit"

    def test_default_source(self):
        """Test default source is 'calculated'."""
        point = PortfolioValuePoint(
            timestamp=datetime.now(UTC),
            value=50000.0,
        )

        assert point.source == "calculated"


class TestDrawdownMetrics:
    """Test DrawdownMetrics dataclass."""

    def test_defaults(self):
        """Test default values."""
        metrics = DrawdownMetrics()

        assert metrics.current_drawdown_pct == 0.0
        assert metrics.peak_value == 0.0
        assert metrics.trough_value == 0.0
        assert metrics.peak_timestamp is None
        assert metrics.trough_timestamp is None
        assert metrics.window_start is None
        assert metrics.window_end is None
        assert metrics.data_points == 0

    def test_to_dict(self):
        """Test serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        metrics = DrawdownMetrics(
            current_drawdown_pct=15.5,
            peak_value=100000.0,
            trough_value=85000.0,
            peak_timestamp=ts,
            trough_timestamp=ts - timedelta(hours=2),
            window_start=ts - timedelta(hours=24),
            window_end=ts,
            data_points=100,
        )

        d = metrics.to_dict()
        assert d["current_drawdown_pct"] == 15.5
        assert d["peak_value"] == 100000.0
        assert d["trough_value"] == 85000.0
        assert d["peak_timestamp"] == "2024-01-15T12:00:00+00:00"
        assert d["data_points"] == 100


class TestDrawdownMonitor:
    """Test DrawdownMonitor class."""

    def test_initialization(self):
        """Test monitor initialization."""
        monitor = DrawdownMonitor()

        assert monitor.rolling_window_hours == 24
        assert monitor.max_data_points == 10000
        assert monitor.influxdb_client is None
        assert monitor.measurement_name == "drawdown_metrics"

    def test_custom_initialization(self):
        """Test monitor with custom config."""
        mock_client = MagicMock()
        monitor = DrawdownMonitor(
            rolling_window_hours=12,
            max_data_points=5000,
            influxdb_client=mock_client,
            measurement_name="custom_metrics",
        )

        assert monitor.rolling_window_hours == 12
        assert monitor.max_data_points == 5000
        assert monitor.influxdb_client == mock_client
        assert monitor.measurement_name == "custom_metrics"

    def test_record_value(self):
        """Test recording portfolio values."""
        monitor = DrawdownMonitor()

        ts = datetime.now(UTC)
        monitor.record_value(100000.0, ts, "bybit")

        assert len(monitor._value_history) == 1
        assert monitor._value_history[0].value == 100000.0
        assert monitor._value_history[0].source == "bybit"

    def test_record_value_default_timestamp(self):
        """Test recording with default timestamp."""
        monitor = DrawdownMonitor()

        monitor.record_value(50000.0)

        assert len(monitor._value_history) == 1
        # Should have a timestamp close to now
        assert (
            datetime.now(UTC) - monitor._value_history[0].timestamp
        ).total_seconds() < 1

    def test_trim_to_window(self):
        """Test old data is trimmed from window."""
        monitor = DrawdownMonitor(rolling_window_hours=1)

        # Add old data (outside window)
        old_ts = datetime.now(UTC) - timedelta(hours=2)
        monitor.record_value(100000.0, old_ts)

        # Add recent data
        recent_ts = datetime.now(UTC)
        monitor.record_value(95000.0, recent_ts)

        # Trim should remove old data
        monitor._trim_to_window()

        assert len(monitor._value_history) == 1
        assert monitor._value_history[0].value == 95000.0

    def test_max_data_points_limit(self):
        """Test max data points limit is enforced."""
        monitor = DrawdownMonitor(max_data_points=5)

        # Add more than max points
        for i in range(10):
            monitor.record_value(float(i * 1000))

        # Should only keep last 5
        assert len(monitor._value_history) == 5

    def test_calculate_rolling_drawdown_insufficient_data(self):
        """Test drawdown calculation with insufficient data."""
        monitor = DrawdownMonitor()

        # Less than 2 data points
        monitor.record_value(100000.0)

        metrics = monitor.calculate_rolling_drawdown()

        assert metrics.current_drawdown_pct == 0.0
        assert metrics.data_points == 1

    def test_calculate_rolling_drawdown_no_decline(self):
        """Test drawdown when value stays flat."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(minutes=10))
        monitor.record_value(100000.0, datetime.now(UTC))

        metrics = monitor.calculate_rolling_drawdown()

        assert metrics.current_drawdown_pct == 0.0
        assert metrics.peak_value == 100000.0
        assert metrics.trough_value == 100000.0

    def test_calculate_rolling_drawdown_with_decline(self):
        """Test drawdown calculation with value decline."""
        monitor = DrawdownMonitor()

        # Peak value
        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=2))
        # Current value (15% decline)
        monitor.record_value(85000.0, datetime.now(UTC))

        metrics = monitor.calculate_rolling_drawdown()

        assert metrics.current_drawdown_pct == 15.0
        assert metrics.peak_value == 100000.0
        assert metrics.trough_value == 85000.0
        assert metrics.data_points == 2

    def test_calculate_rolling_drawdown_recovery(self):
        """Test drawdown after recovery."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=3))
        monitor.record_value(85000.0, datetime.now(UTC) - timedelta(hours=2))
        monitor.record_value(100000.0, datetime.now(UTC))  # Back to peak

        metrics = monitor.calculate_rolling_drawdown()

        # Drawdown should be 0 after recovery
        assert metrics.current_drawdown_pct == 0.0
        assert metrics.peak_value == 100000.0

    def test_check_drawdown_threshold_exceeded(self):
        """Test threshold check when exceeded."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=1))
        monitor.record_value(84000.0, datetime.now(UTC))  # 16% decline

        exceeded = monitor.check_drawdown_threshold(15.0)

        assert exceeded is True

    def test_check_drawdown_threshold_not_exceeded(self):
        """Test threshold check when not exceeded."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=1))
        monitor.record_value(95000.0, datetime.now(UTC))  # 5% decline

        exceeded = monitor.check_drawdown_threshold(15.0)

        assert exceeded is False

    def test_get_current_value(self):
        """Test getting current value."""
        monitor = DrawdownMonitor()

        assert monitor.get_current_value() is None

        monitor.record_value(100000.0)
        assert monitor.get_current_value() == 100000.0

        monitor.record_value(95000.0)
        assert monitor.get_current_value() == 95000.0

    def test_get_peak_value(self):
        """Test getting peak value."""
        monitor = DrawdownMonitor()

        assert monitor.get_peak_value() is None

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=2))
        monitor.record_value(85000.0, datetime.now(UTC) - timedelta(hours=1))
        monitor.record_value(90000.0, datetime.now(UTC))

        assert monitor.get_peak_value() == 100000.0

    def test_get_value_history(self):
        """Test getting value history copy."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0)
        monitor.record_value(95000.0)

        history = monitor.get_value_history()

        assert len(history) == 2
        # Should be a copy
        assert history is not monitor._value_history

    def test_reset(self):
        """Test reset clears history."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0)
        monitor.record_value(95000.0)

        monitor.reset()

        assert len(monitor._value_history) == 0
        assert monitor._last_metrics is None

    def test_get_summary(self):
        """Test getting summary."""
        monitor = DrawdownMonitor()

        monitor.record_value(100000.0, datetime.now(UTC) - timedelta(hours=1))
        monitor.record_value(85000.0, datetime.now(UTC))

        summary = monitor.get_summary()

        assert summary["current_drawdown_pct"] == 15.0
        assert summary["current_value"] == 85000.0
        assert summary["peak_value"] == 100000.0
        assert summary["trough_value"] == 85000.0
        assert summary["window_hours"] == 24
        assert summary["data_points"] == 2

    @pytest.mark.asyncio
    async def test_write_metrics_to_influxdb_no_client(self):
        """Test write without InfluxDB client."""
        monitor = DrawdownMonitor(influxdb_client=None)

        result = await monitor.write_metrics_to_influxdb()

        assert result is False

    @pytest.mark.asyncio
    async def test_write_metrics_to_influxdb_success(self):
        """Test successful write to InfluxDB."""
        mock_client = AsyncMock()
        monitor = DrawdownMonitor(influxdb_client=mock_client)

        monitor.record_value(100000.0)
        monitor.record_value(85000.0)

        result = await monitor.write_metrics_to_influxdb()

        assert result is True
        mock_client.write_point.assert_called_once()

        # Check the point structure
        call_args = mock_client.write_point.call_args[0][0]
        assert call_args["measurement"] == "drawdown_metrics"
        assert call_args["fields"]["drawdown_pct"] == 15.0

    @pytest.mark.asyncio
    async def test_write_metrics_to_influxdb_failure(self):
        """Test failed write to InfluxDB."""
        mock_client = AsyncMock()
        mock_client.write_point.side_effect = Exception("Connection failed")

        monitor = DrawdownMonitor(influxdb_client=mock_client)
        monitor.record_value(100000.0)

        result = await monitor.write_metrics_to_influxdb()

        assert result is False
