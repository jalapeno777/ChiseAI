"""Tests for execution telemetry exporter.

For ST-EX-001: InfluxDB exporter tests.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from execution.telemetry.exporter import ExecutionTelemetryExporter
from execution.telemetry.metrics import (
    ExecutionMetrics,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PositionEvent,
    PositionSide,
)


@pytest.fixture
def mock_influx_client():
    """Create a mock InfluxDB client."""
    client = MagicMock()
    client.write_api.return_value = MagicMock()
    return client


@pytest.fixture
def exporter(mock_influx_client):
    """Create exporter with mock client."""
    return ExecutionTelemetryExporter(
        influxdb_client=mock_influx_client,
        bucket="test-bucket",
        org="test-org",
    )


class TestExecutionTelemetryExporterInit:
    """Tests for exporter initialization."""

    def test_init_with_client(self, mock_influx_client):
        """Test initialization with existing client."""
        exporter = ExecutionTelemetryExporter(
            influxdb_client=mock_influx_client,
            bucket="my-bucket",
            org="my-org",
        )
        assert exporter._client == mock_influx_client
        assert exporter.bucket == "my-bucket"
        assert exporter.org == "my-org"
        assert exporter._owned_client is False

    def test_init_without_client(self):
        """Test initialization without client."""
        exporter = ExecutionTelemetryExporter(
            url="http://localhost:8086",
            token="test-token",
            bucket="my-bucket",
        )
        assert exporter._client is None
        assert exporter._owned_client is True


class TestExecutionTelemetryExporterStartStop:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, exporter):
        """Test starting the exporter."""
        await exporter.start()
        assert exporter._running is True
        assert exporter._flush_task is not None
        await exporter.stop()

    @pytest.mark.asyncio
    async def test_stop(self, exporter):
        """Test stopping the exporter."""
        await exporter.start()
        await exporter.stop()
        assert exporter._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_flush_task(self, exporter):
        """Test that stop cancels the flush task."""
        await exporter.start()
        task = exporter._flush_task
        await exporter.stop()
        assert task.cancelled() or task.done()


class TestWriteMetrics:
    """Tests for write_metrics method."""

    @pytest.mark.asyncio
    async def test_write_metrics_success(self, exporter, mock_influx_client):
        """Test successful metrics write."""
        metrics = ExecutionMetrics(
            environment="paper",
            total_pnl=1000.0,
            realized_pnl=500.0,
            unrealized_pnl=500.0,
            max_drawdown_pct=5.0,
            win_rate=60.0,
            trade_count=10,
            win_count=6,
            loss_count=4,
            sharpe_ratio=1.5,
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_metrics(metrics)
            assert result is True

    @pytest.mark.asyncio
    async def test_write_metrics_live_environment(self, exporter, mock_influx_client):
        """Test metrics write for live environment."""
        metrics = ExecutionMetrics(
            environment="live",
            total_pnl=2000.0,
            realized_pnl=1500.0,
            unrealized_pnl=500.0,
            max_drawdown_pct=3.0,
            win_rate=65.0,
            trade_count=20,
            win_count=13,
            loss_count=7,
            sharpe_ratio=2.0,
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_metrics(metrics, portfolio_id="portfolio-1")
            assert result is True


class TestWriteOrderEvent:
    """Tests for write_order_event method."""

    @pytest.mark.asyncio
    async def test_write_order_event_filled(self, exporter, mock_influx_client):
        """Test writing filled order event."""
        order = OrderEvent(
            order_id="order-123",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
            quantity=1.0,
            price=50000.0,
            filled_quantity=1.0,
            environment="paper",
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_order_event(order)
            assert result is True

    @pytest.mark.asyncio
    async def test_write_order_event_partial(self, exporter, mock_influx_client):
        """Test writing partial fill order event."""
        order = OrderEvent(
            order_id="order-456",
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            status=OrderStatus.PARTIAL,
            quantity=2.0,
            price=3000.0,
            filled_quantity=1.5,
            environment="live",
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_order_event(order)
            assert result is True

    @pytest.mark.asyncio
    async def test_write_order_event_cancelled(self, exporter, mock_influx_client):
        """Test writing cancelled order event."""
        order = OrderEvent(
            order_id="order-789",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            status=OrderStatus.CANCELLED,
            quantity=1.0,
            price=50000.0,
            filled_quantity=0.0,
            environment="paper",
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_order_event(order)
            assert result is True


class TestWritePositionEvent:
    """Tests for write_position_event method."""

    @pytest.mark.asyncio
    async def test_write_position_event_long(self, exporter, mock_influx_client):
        """Test writing long position event."""
        position = PositionEvent(
            position_id="pos-123",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=50000.0,
            current_price=51000.0,
            quantity=1.0,
            unrealized_pnl=1000.0,
            leverage=1.0,
            environment="paper",
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_position_event(position)
            assert result is True

    @pytest.mark.asyncio
    async def test_write_position_event_short(self, exporter, mock_influx_client):
        """Test writing short position event."""
        position = PositionEvent(
            position_id="pos-456",
            symbol="ETHUSDT",
            side=PositionSide.SHORT,
            entry_price=3000.0,
            current_price=2900.0,
            quantity=2.0,
            unrealized_pnl=200.0,
            leverage=2.0,
            environment="live",
        )

        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_position_event(position)
            assert result is True


class TestFlushBatch:
    """Tests for batch flushing."""

    @pytest.mark.asyncio
    async def test_flush_batch_empty(self, exporter):
        """Test flushing empty batch."""
        result = await exporter._flush_batch()
        assert result is None  # No error, just returns

    @pytest.mark.asyncio
    async def test_flush_batch_with_points(self, exporter, mock_influx_client):
        """Test flushing batch with points."""
        # Add a mock point to buffer
        mock_point = Mock()
        exporter._batch_buffer.append(mock_point)

        await exporter._flush_batch()

        mock_influx_client.write_api.return_value.write.assert_called_once()


class TestWriteTestPoint:
    """Tests for write_test_point method."""

    @pytest.mark.asyncio
    async def test_write_test_point_success(self, exporter, mock_influx_client):
        """Test writing test point successfully."""
        with patch("influxdb_client.Point") as MockPoint:
            mock_point = Mock()
            MockPoint.return_value = mock_point

            result = await exporter.write_test_point()
            assert result is True
            mock_influx_client.write_api.return_value.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_test_point_failure(self, exporter, mock_influx_client):
        """Test test point write failure."""
        mock_influx_client.write_api.return_value.write.side_effect = Exception(
            "Write failed"
        )

        result = await exporter.write_test_point()
        assert result is False


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats(self, exporter):
        """Test getting exporter stats."""
        stats = exporter.get_stats()
        assert stats["running"] is False
        assert stats["bucket"] == "test-bucket"
        assert stats["org"] == "test-org"
        assert stats["batch_size"] == 0
        assert stats["flush_interval"] == 5.0
