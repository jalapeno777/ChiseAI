"""Tests for execution telemetry collector.

For ST-EX-001: Collection and push logic tests.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.telemetry.calculator import KPICalculator
from execution.telemetry.collector import ExecutionCollector
from execution.telemetry.metrics import PositionSide, Trade


@pytest.fixture
def mock_exporter():
    """Create a mock exporter."""
    exporter = MagicMock()
    exporter.write_metrics = AsyncMock(return_value=True)
    return exporter


@pytest.fixture
def collector(mock_exporter):
    """Create collector with mock exporter."""
    return ExecutionCollector(
        exporter=mock_exporter,
        environment="paper",
        portfolio_id="test-portfolio",
    )


class TestExecutionCollectorInit:
    """Tests for collector initialization."""

    def test_init(self, mock_exporter):
        """Test initialization."""
        collector = ExecutionCollector(
            exporter=mock_exporter,
            environment="live",
            portfolio_id="portfolio-1",
        )
        assert collector.exporter == mock_exporter
        assert collector.environment == "live"
        assert collector.portfolio_id == "portfolio-1"
        assert collector._running is False

    def test_init_with_calculator(self, mock_exporter):
        """Test initialization with custom calculator."""
        calculator = KPICalculator()
        collector = ExecutionCollector(
            exporter=mock_exporter,
            calculator=calculator,
        )
        assert collector.calculator == calculator


class TestExecutionCollectorStartStop:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, collector):
        """Test starting the collector."""
        await collector.start()
        assert collector._running is True
        assert collector._collection_task is not None
        await collector.stop()

    @pytest.mark.asyncio
    async def test_stop(self, collector):
        """Test stopping the collector."""
        await collector.start()
        await collector.stop()
        assert collector._running is False

    @pytest.mark.asyncio
    async def test_stop_pushes_final_kpis(self, collector, mock_exporter):
        """Test that stop pushes final KPIs."""
        await collector.start()
        await collector.stop()
        # Should have called write_metrics at least once during stop
        mock_exporter.write_metrics.assert_called()


class TestAddTrade:
    """Tests for add_trade method."""

    @pytest.mark.asyncio
    async def test_add_trade(self, collector):
        """Test adding a trade."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000,
            exit_price=51000,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )

        await collector.add_trade(trade)

        trades = await collector.get_trades()
        assert len(trades) == 1
        assert trades[0].trade_id == "t1"

    @pytest.mark.asyncio
    async def test_add_trade_updates_equity(self, collector):
        """Test that adding trade updates equity."""
        now = datetime.now(UTC)
        initial_equity = collector._current_equity

        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000,
            exit_price=51000,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )

        await collector.add_trade(trade)

        assert collector._current_equity == initial_equity + 1000


class TestUpdatePosition:
    """Tests for update_position method."""

    @pytest.mark.asyncio
    async def test_update_position_add(self, collector):
        """Test adding/updating a position."""
        await collector.update_position(
            symbol="BTCUSDT",
            unrealized_pnl=500.0,
            quantity=1.0,
            side="long",
        )

        assert "BTCUSDT" in collector._open_positions
        assert collector._open_positions["BTCUSDT"]["unrealized_pnl"] == 500.0

    @pytest.mark.asyncio
    async def test_update_position_remove(self, collector):
        """Test removing a position (quantity=0)."""
        # First add a position
        await collector.update_position(
            symbol="BTCUSDT",
            unrealized_pnl=500.0,
            quantity=1.0,
            side="long",
        )

        # Then remove it
        await collector.update_position(
            symbol="BTCUSDT",
            unrealized_pnl=0.0,
            quantity=0.0,
            side="long",
        )

        assert "BTCUSDT" not in collector._open_positions


class TestSetEquity:
    """Tests for set_equity method."""

    @pytest.mark.asyncio
    async def test_set_equity(self, collector):
        """Test setting equity."""
        await collector.set_equity(15000.0)
        assert collector._current_equity == 15000.0
        assert len(collector._equity_history) == 1

    @pytest.mark.asyncio
    async def test_set_equity_multiple(self, collector):
        """Test setting equity multiple times."""
        await collector.set_equity(11000.0)
        await collector.set_equity(12000.0)
        await collector.set_equity(11500.0)

        assert collector._current_equity == 11500.0
        assert len(collector._equity_history) == 3


class TestSetInitialEquity:
    """Tests for set_initial_equity method."""

    @pytest.mark.asyncio
    async def test_set_initial_equity(self, collector):
        """Test setting initial equity."""
        await collector.set_initial_equity(20000.0)
        assert collector._initial_equity == 20000.0


class TestCalculateMetrics:
    """Tests for _calculate_metrics method."""

    @pytest.mark.asyncio
    async def test_calculate_metrics_empty(self, collector):
        """Test calculating metrics with no data."""
        metrics = await collector._calculate_metrics()

        assert metrics.environment == "paper"
        assert metrics.trade_count == 0
        assert metrics.win_rate == 0.0
        assert metrics.total_pnl == 0.0

    @pytest.mark.asyncio
    async def test_calculate_metrics_with_trades(self, collector):
        """Test calculating metrics with trades."""
        now = datetime.now(UTC)

        # Add some trades
        trades = [
            Trade(
                trade_id="t1",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=51000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=1000,
                entry_time=now - timedelta(hours=2),
                exit_time=now - timedelta(hours=1),
            ),
            Trade(
                trade_id="t2",
                symbol="BTCUSDT",
                entry_price=50000,
                exit_price=49000,
                quantity=1.0,
                side=PositionSide.LONG,
                pnl=-1000,
                entry_time=now - timedelta(hours=1),
                exit_time=now,
            ),
        ]

        for trade in trades:
            await collector.add_trade(trade)

        metrics = await collector._calculate_metrics()

        assert metrics.trade_count == 2
        assert metrics.win_count == 1
        assert metrics.loss_count == 1
        assert metrics.win_rate == 50.0


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_empty(self, collector):
        """Test getting stats with no data."""
        stats = collector.get_stats()

        assert stats["running"] is False
        assert stats["environment"] == "paper"
        assert stats["portfolio_id"] == "test-portfolio"
        assert stats["trade_count"] == 0
        assert stats["open_positions"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self, collector):
        """Test getting stats with data."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000,
            exit_price=51000,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )
        await collector.add_trade(trade)

        stats = collector.get_stats()

        assert stats["trade_count"] == 1
        assert stats["total_pnl"] == 1000.0


class TestClearTrades:
    """Tests for clear_trades method."""

    @pytest.mark.asyncio
    async def test_clear_trades(self, collector):
        """Test clearing all trades."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000,
            exit_price=51000,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )
        await collector.add_trade(trade)
        assert len(await collector.get_trades()) == 1

        await collector.clear_trades()

        assert len(await collector.get_trades()) == 0
        assert collector._current_equity == collector._initial_equity
