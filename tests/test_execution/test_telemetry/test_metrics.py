"""Tests for execution telemetry metrics dataclasses.

For ST-EX-001: Metrics dataclass tests.
"""

from datetime import UTC, datetime, timedelta

import pytest

from execution.telemetry.metrics import (
    ExecutionMetrics,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PositionEvent,
    PositionSide,
    Trade,
)


class TestExecutionMetrics:
    """Tests for ExecutionMetrics dataclass."""

    def test_create_metrics(self):
        """Test creating execution metrics."""
        now = datetime.now(UTC)
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
            timestamp=now,
        )

        assert metrics.environment == "paper"
        assert metrics.total_pnl == 1000.0
        assert metrics.win_rate == 60.0
        assert metrics.timestamp == now

    def test_default_timestamp(self):
        """Test default timestamp is set."""
        before = datetime.now(UTC)
        metrics = ExecutionMetrics(
            environment="live",
            total_pnl=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            max_drawdown_pct=0.0,
            win_rate=0.0,
            trade_count=0,
            win_count=0,
            loss_count=0,
            sharpe_ratio=0.0,
        )
        after = datetime.now(UTC)

        assert before <= metrics.timestamp <= after

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime.now(UTC)
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
            timestamp=now,
        )

        data = metrics.to_dict()

        assert data["environment"] == "paper"
        assert data["total_pnl"] == 1000.0
        assert data["win_rate"] == 60.0
        assert "timestamp" in data


class TestOrderEvent:
    """Tests for OrderEvent dataclass."""

    def test_create_order_event(self):
        """Test creating order event."""
        now = datetime.now(UTC)
        order = OrderEvent(
            order_id="order-123",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
            quantity=1.0,
            price=50000.0,
            filled_quantity=1.0,
            timestamp=now,
            environment="paper",
        )

        assert order.order_id == "order-123"
        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.FILLED

    def test_order_status_values(self):
        """Test order status enum values."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.PARTIAL.value == "partial"
        assert OrderStatus.CANCELLED.value == "cancelled"

    def test_order_side_values(self):
        """Test order side enum values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime.now(UTC)
        order = OrderEvent(
            order_id="order-123",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
            quantity=1.0,
            price=50000.0,
            timestamp=now,
            environment="live",
        )

        data = order.to_dict()

        assert data["order_id"] == "order-123"
        assert data["side"] == "buy"
        assert data["status"] == "filled"
        assert data["environment"] == "live"


class TestPositionEvent:
    """Tests for PositionEvent dataclass."""

    def test_create_position_event(self):
        """Test creating position event."""
        now = datetime.now(UTC)
        position = PositionEvent(
            position_id="pos-123",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=50000.0,
            current_price=51000.0,
            quantity=1.0,
            unrealized_pnl=1000.0,
            leverage=1.0,
            timestamp=now,
            environment="paper",
        )

        assert position.position_id == "pos-123"
        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.unrealized_pnl == 1000.0

    def test_position_side_values(self):
        """Test position side enum values."""
        assert PositionSide.LONG.value == "long"
        assert PositionSide.SHORT.value == "short"

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime.now(UTC)
        position = PositionEvent(
            position_id="pos-123",
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            entry_price=50000.0,
            current_price=49000.0,
            quantity=1.0,
            unrealized_pnl=1000.0,
            leverage=2.0,
            timestamp=now,
            environment="live",
        )

        data = position.to_dict()

        assert data["position_id"] == "pos-123"
        assert data["side"] == "short"
        assert data["leverage"] == 2.0


class TestTrade:
    """Tests for Trade dataclass."""

    def test_create_trade(self):
        """Test creating trade."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000.0,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
            environment="paper",
        )

        assert trade.trade_id == "t1"
        assert trade.symbol == "BTCUSDT"
        assert trade.pnl == 1000.0

    def test_is_win_profit(self):
        """Test is_win with profit."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000.0,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )

        assert trade.is_win is True

    def test_is_win_loss(self):
        """Test is_win with loss."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=49000.0,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=-1000.0,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
        )

        assert trade.is_win is False

    def test_duration_seconds(self):
        """Test duration calculation."""
        now = datetime.now(UTC)
        entry = now - timedelta(hours=2)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000.0,
            entry_time=entry,
            exit_time=now,
        )

        assert trade.duration_seconds == pytest.approx(7200.0, rel=1.0)

    def test_to_dict(self):
        """Test serialization to dict."""
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=1.0,
            side=PositionSide.LONG,
            pnl=1000.0,
            entry_time=now - timedelta(hours=1),
            exit_time=now,
            environment="live",
        )

        data = trade.to_dict()

        assert data["trade_id"] == "t1"
        assert data["pnl"] == 1000.0
        assert data["is_win"] is True
        assert data["environment"] == "live"
