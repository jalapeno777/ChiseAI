"""Tests for paper trading Grafana exporter.

Validates metrics export to InfluxDB and dashboard integration.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

# Skip tests if influxdb_client not available
try:
    from influxdb_client import Point

    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False

# Import the module under test
from execution.paper.grafana_exporter import (
    PaperTradeResult,
    PaperTradingGrafanaExporter,
    PaperTradingMetrics,
)


# Mock PaperPosition for testing
class MockPaperPosition:
    """Mock PaperPosition for testing."""

    def __init__(self, **kwargs):
        self.position_id = kwargs.get("position_id", "test-pos-1")
        self.symbol = kwargs.get("symbol", "BTC/USDT")
        self.side = kwargs.get("side", "long")
        self.entry_price = kwargs.get("entry_price", 50000.0)
        self.quantity = kwargs.get("quantity", 1.0)
        self.current_price = kwargs.get("current_price", 51000.0)
        self.unrealized_pnl = kwargs.get("unrealized_pnl", 1000.0)
        self.realized_pnl = kwargs.get("realized_pnl", 0.0)
        self.leverage = kwargs.get("leverage", 1.0)
        self.is_open = kwargs.get("is_open", True)

    @property
    def unrealized_pnl_pct(self):
        return 2.0

    @property
    def notional_value(self):
        return self.current_price * self.quantity

    @property
    def market_value(self):
        return self.notional_value + self.unrealized_pnl


@pytest.fixture
def mock_influxdb_client():
    """Create a mock InfluxDB client."""
    client = MagicMock()
    write_api = MagicMock()
    client.write_api.return_value = write_api
    return client


@pytest.fixture
def exporter(mock_influxdb_client):
    """Create a PaperTradingGrafanaExporter instance."""
    return PaperTradingGrafanaExporter(
        influxdb_client=mock_influxdb_client,
        measurement_prefix="paper_test",
        bucket="test_bucket",
        org="test_org",
    )


@pytest.fixture
def sample_position():
    """Create a sample paper position."""
    return MockPaperPosition(
        position_id="pos-001",
        symbol="BTC/USDT",
        side="long",
        entry_price=50000.0,
        quantity=0.5,
        current_price=51000.0,
        unrealized_pnl=500.0,
    )


@pytest.fixture
def sample_trade():
    """Create a sample trade result."""
    return PaperTradeResult(
        trade_id="trade-001",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.5,
        price=50000.0,
        timestamp=datetime.now(UTC),
        pnl=500.0,
        signal_confidence=0.85,
    )


class TestPaperTradingGrafanaExporter:
    """Test suite for PaperTradingGrafanaExporter."""

    def test_init(self, mock_influxdb_client):
        """Test exporter initialization."""
        exporter = PaperTradingGrafanaExporter(
            influxdb_client=mock_influxdb_client,
            measurement_prefix="test_prefix",
            bucket="my_bucket",
            org="my_org",
            interval=10.0,
        )

        assert exporter._client == mock_influxdb_client
        assert exporter.prefix == "test_prefix"
        assert exporter._bucket == "my_bucket"
        assert exporter._org == "my_org"
        assert exporter._interval == 10.0
        assert exporter._export_count == 0

    @pytest.mark.asyncio
    async def test_export_position(
        self, exporter, sample_position, mock_influxdb_client
    ):
        """Test exporting a position."""
        result = await exporter.export_position(sample_position)

        assert result is True
        assert exporter._export_count == 1
        mock_influxdb_client.write_api.return_value.write.assert_called_once()

        # Verify write was called with correct bucket and org
        call_args = mock_influxdb_client.write_api.return_value.write.call_args
        assert call_args.kwargs["bucket"] == "test_bucket"
        assert call_args.kwargs["org"] == "test_org"

    @pytest.mark.asyncio
    async def test_export_position_without_client(self, sample_position):
        """Test exporting a position without InfluxDB client."""
        exporter = PaperTradingGrafanaExporter(influxdb_client=None)
        result = await exporter.export_position(sample_position)

        # Should return True (fallback mode) but not write
        assert result is True
        assert exporter._export_count == 1

    @pytest.mark.asyncio
    async def test_export_portfolio_summary(self, exporter, mock_influxdb_client):
        """Test exporting portfolio summary."""
        result = await exporter.export_portfolio_summary(
            portfolio_value=100000.0,
            open_positions=3,
            total_pnl=5000.0,
            drawdown_pct=2.5,
            unrealized_pnl=1000.0,
        )

        assert result is True
        assert exporter._export_count == 1
        mock_influxdb_client.write_api.return_value.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_trade(self, exporter, sample_trade, mock_influxdb_client):
        """Test exporting a trade."""
        result = await exporter.export_trade(sample_trade)

        assert result is True
        assert exporter._export_count == 1
        assert exporter._total_trades == 1
        assert exporter._win_count == 1
        assert exporter._loss_count == 0
        mock_influxdb_client.write_api.return_value.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_trade_loss(self, exporter, mock_influxdb_client):
        """Test exporting a losing trade."""
        losing_trade = PaperTradeResult(
            trade_id="trade-002",
            symbol="ETH/USDT",
            side="sell",
            quantity=1.0,
            price=3000.0,
            timestamp=datetime.now(UTC),
            pnl=-200.0,
            signal_confidence=0.65,
        )

        result = await exporter.export_trade(losing_trade)

        assert result is True
        assert exporter._total_trades == 1
        assert exporter._win_count == 0
        assert exporter._loss_count == 1

    @pytest.mark.asyncio
    async def test_export_signal_confidence_distribution(
        self, exporter, mock_influxdb_client
    ):
        """Test exporting signal confidence distribution."""
        # Add some signal confidences
        exporter._signal_confidences = [0.1, 0.3, 0.5, 0.7, 0.9, 0.95]

        result = await exporter.export_signal_confidence_distribution()

        assert result is True
        mock_influxdb_client.write_api.return_value.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_signal_confidence_empty(self, exporter):
        """Test exporting signal confidence with no data."""
        result = await exporter.export_signal_confidence_distribution()

        # Should return True without writing
        assert result is True

    @pytest.mark.asyncio
    async def test_export_all_positions(self, exporter, mock_influxdb_client):
        """Test batch exporting positions."""
        positions = [
            MockPaperPosition(position_id="pos-1", symbol="BTC/USDT"),
            MockPaperPosition(position_id="pos-2", symbol="ETH/USDT"),
            MockPaperPosition(position_id="pos-3", symbol="SOL/USDT"),
        ]

        result = await exporter.export_all_positions(positions)

        assert result is True
        assert exporter._export_count == 3
        assert mock_influxdb_client.write_api.return_value.write.call_count == 3

    def test_get_stats(self, exporter):
        """Test getting exporter statistics."""
        # Add some data
        exporter._export_count = 10
        exporter._failed_exports = 2
        exporter._win_count = 7
        exporter._loss_count = 3
        exporter._total_trades = 10
        exporter._signal_confidences = [0.5, 0.6, 0.7]

        stats = exporter.get_stats()

        assert stats["export_count"] == 10
        assert stats["failed_exports"] == 2
        assert stats["win_count"] == 7
        assert stats["loss_count"] == 3
        assert stats["total_trades"] == 10
        assert stats["win_rate"] == 70.0
        assert stats["signal_confidence_count"] == 3
        assert stats["measurement_prefix"] == "paper_test"

    def test_get_metrics(self, exporter):
        """Test getting current metrics snapshot."""
        exporter._win_count = 5
        exporter._loss_count = 3
        exporter._total_trades = 8

        metrics = exporter.get_metrics()

        assert isinstance(metrics, PaperTradingMetrics)
        assert metrics.win_count == 5
        assert metrics.loss_count == 3
        assert metrics.total_trades == 8
        assert metrics.win_rate == 62.5


class TestPaperTradeResult:
    """Test suite for PaperTradeResult dataclass."""

    def test_trade_result_creation(self):
        """Test creating a trade result."""
        now = datetime.now(UTC)
        trade = PaperTradeResult(
            trade_id="trade-001",
            symbol="BTC/USDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
            timestamp=now,
            pnl=1000.0,
            signal_confidence=0.9,
        )

        assert trade.trade_id == "trade-001"
        assert trade.symbol == "BTC/USDT"
        assert trade.side == "buy"
        assert trade.quantity == 1.0
        assert trade.price == 50000.0
        assert trade.timestamp == now
        assert trade.pnl == 1000.0
        assert trade.signal_confidence == 0.9

    def test_trade_result_to_dict(self):
        """Test converting trade result to dictionary."""
        now = datetime.now(UTC)
        trade = PaperTradeResult(
            trade_id="trade-001",
            symbol="BTC/USDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
            timestamp=now,
            pnl=1000.0,
            signal_confidence=0.9,
            signal_metadata={"strategy": "test"},
        )

        data = trade.to_dict()

        assert data["trade_id"] == "trade-001"
        assert data["symbol"] == "BTC/USDT"
        assert data["pnl"] == 1000.0
        assert data["signal_confidence"] == 0.9
        assert data["signal_metadata"] == {"strategy": "test"}


class TestPaperTradingMetrics:
    """Test suite for PaperTradingMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        now = datetime.now(UTC)
        metrics = PaperTradingMetrics(
            timestamp=now,
            portfolio_value=100000.0,
            open_positions=5,
            total_pnl=5000.0,
            unrealized_pnl=2000.0,
            drawdown_pct=3.0,
            win_count=10,
            loss_count=5,
            total_trades=15,
        )

        assert metrics.timestamp == now
        assert metrics.portfolio_value == 100000.0
        assert metrics.open_positions == 5
        assert metrics.total_pnl == 5000.0

    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        metrics = PaperTradingMetrics(
            timestamp=datetime.now(UTC),
            portfolio_value=100000.0,
            open_positions=0,
            total_pnl=0.0,
            unrealized_pnl=0.0,
            drawdown_pct=0.0,
            win_count=7,
            loss_count=3,
            total_trades=10,
        )

        assert metrics.win_rate == 70.0

    def test_win_rate_zero_trades(self):
        """Test win rate with zero trades."""
        metrics = PaperTradingMetrics(
            timestamp=datetime.now(UTC),
            portfolio_value=100000.0,
            open_positions=0,
            total_pnl=0.0,
            unrealized_pnl=0.0,
            drawdown_pct=0.0,
            win_count=0,
            loss_count=0,
            total_trades=0,
        )

        assert metrics.win_rate == 0.0

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        now = datetime.now(UTC)
        metrics = PaperTradingMetrics(
            timestamp=now,
            portfolio_value=100000.0,
            open_positions=5,
            total_pnl=5000.0,
            unrealized_pnl=2000.0,
            drawdown_pct=3.0,
            win_count=10,
            loss_count=5,
            total_trades=15,
        )

        data = metrics.to_dict()

        assert data["portfolio_value"] == 100000.0
        assert data["win_count"] == 10
        assert data["win_rate"] == pytest.approx(66.67, rel=0.01)


class TestDashboardJSON:
    """Test suite for Grafana dashboard JSON."""

    def test_dashboard_json_valid(self):
        """Test that dashboard JSON is valid."""
        dashboard_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "infrastructure",
            "grafana",
            "dashboards",
            "paper_trading.json",
        )

        if not os.path.exists(dashboard_path):
            pytest.skip("Dashboard file not found")

        with open(dashboard_path) as f:
            dashboard = json.load(f)

        # Validate required fields
        assert "title" in dashboard
        assert "uid" in dashboard
        assert "panels" in dashboard
        assert dashboard["title"] == "ChiseAI - Paper Trading"
        assert dashboard["uid"] == "chiseai-paper-trading"

    def test_dashboard_panels_exist(self):
        """Test that all required panels exist."""
        dashboard_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "infrastructure",
            "grafana",
            "dashboards",
            "paper_trading.json",
        )

        if not os.path.exists(dashboard_path):
            pytest.skip("Dashboard file not found")

        with open(dashboard_path) as f:
            dashboard = json.load(f)

        # Get panel titles
        panel_titles = [
            panel.get("title", "")
            for panel in dashboard.get("panels", [])
            if panel.get("type") != "row"
        ]

        # Check required panels
        required_panels = [
            "Portfolio Value",
            "Open Positions",
            "PnL by Symbol",
            "Win/Loss Ratio",
            "Current Drawdown %",
            "Recent Trades",
            "Signal Confidence Distribution",
        ]

        for panel in required_panels:
            assert any(
                panel in title for title in panel_titles
            ), f"Missing panel: {panel}"

    def test_dashboard_datasource_config(self):
        """Test dashboard datasource configuration."""
        dashboard_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "infrastructure",
            "grafana",
            "dashboards",
            "paper_trading.json",
        )

        if not os.path.exists(dashboard_path):
            pytest.skip("Dashboard file not found")

        with open(dashboard_path) as f:
            dashboard = json.load(f)

        # Check templating
        templating = dashboard.get("templating", {}).get("list", [])
        assert len(templating) >= 1

        # Check for InfluxDB datasource variable
        ds_vars = [v for v in templating if v.get("name") == "influxdb_datasource"]
        assert len(ds_vars) > 0

    def test_dashboard_refresh_rate(self):
        """Test dashboard refresh rate is appropriate."""
        dashboard_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "infrastructure",
            "grafana",
            "dashboards",
            "paper_trading.json",
        )

        if not os.path.exists(dashboard_path):
            pytest.skip("Dashboard file not found")

        with open(dashboard_path) as f:
            dashboard = json.load(f)

        # Check refresh rate (should be 5s for real-time)
        assert dashboard.get("refresh") == "5s"


@pytest.mark.asyncio
class TestPeriodicExport:
    """Test suite for periodic export functionality."""

    async def test_start_periodic_export(self, exporter):
        """Test starting periodic export."""
        # Mock functions
        portfolio_fn = MagicMock(return_value=100000.0)
        positions_fn = MagicMock(return_value=5)
        pnl_fn = MagicMock(return_value=5000.0)
        drawdown_fn = MagicMock(return_value=2.0)

        # Start periodic export
        await exporter.start_periodic_export(
            portfolio_value_fn=portfolio_fn,
            open_positions_fn=positions_fn,
            total_pnl_fn=pnl_fn,
            drawdown_fn=drawdown_fn,
        )

        # Should be running
        assert hasattr(exporter, "_running")
        assert exporter._running is True

        # Stop immediately
        await exporter.stop_periodic_export()

    async def test_stop_periodic_export(self, exporter):
        """Test stopping periodic export."""
        # Start first
        await exporter.start_periodic_export(
            portfolio_value_fn=lambda: 100000.0,
            open_positions_fn=lambda: 5,
            total_pnl_fn=lambda: 5000.0,
            drawdown_fn=lambda: 2.0,
        )

        # Stop
        await exporter.stop_periodic_export()

        assert exporter._running is False


class TestErrorHandling:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_export_position_error(self, exporter, sample_position):
        """Test handling export errors."""
        # Make write raise an exception
        exporter._client.write_api.return_value.write.side_effect = Exception(
            "Write failed"
        )

        result = await exporter.export_position(sample_position)

        assert result is False
        assert exporter._failed_exports == 1

    @pytest.mark.asyncio
    async def test_export_trade_error(self, exporter, sample_trade):
        """Test handling trade export errors."""
        exporter._client.write_api.return_value.write.side_effect = Exception(
            "Write failed"
        )

        result = await exporter.export_trade(sample_trade)

        assert result is False
        assert exporter._failed_exports == 1

    @pytest.mark.asyncio
    async def test_export_portfolio_error(self, exporter):
        """Test handling portfolio export errors."""
        exporter._client.write_api.return_value.write.side_effect = Exception(
            "Write failed"
        )

        result = await exporter.export_portfolio_summary(
            portfolio_value=100000.0,
            open_positions=3,
            total_pnl=5000.0,
            drawdown_pct=2.5,
        )

        assert result is False
        assert exporter._failed_exports == 1
