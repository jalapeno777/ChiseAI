"""Tests for paper trading models.

Tests for OrderState, PaperOrder, and PaperFill dataclasses.
"""

import pytest
from src.execution.paper.models import (
    OrderSide,
    OrderState,
    OrderType,
    PaperFill,
    PaperOrder,
)


class TestOrderState:
    """Test OrderState enum."""

    def test_order_state_values(self):
        """Test that all order states have correct values."""
        assert OrderState.PENDING.value == "pending"
        assert OrderState.PARTIAL.value == "partial"
        assert OrderState.FILLED.value == "filled"
        assert OrderState.REJECTED.value == "rejected"
        assert OrderState.CANCELLED.value == "cancelled"
        assert OrderState.EXPIRED.value == "expired"


class TestOrderType:
    """Test OrderType enum."""

    def test_order_type_values(self):
        """Test that all order types have correct values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"


class TestOrderSide:
    """Test OrderSide enum."""

    def test_order_side_values(self):
        """Test that all order sides have correct values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"


class TestPaperOrder:
    """Test PaperOrder dataclass."""

    def test_create_market_order(self):
        """Test creating a market order."""
        order = PaperOrder(
            order_id="test_123",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        assert order.order_id == "test_123"
        assert order.symbol == "BTCUSDT"
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.quantity == 1.0
        assert order.price is None
        assert order.state == OrderState.PENDING
        assert order.filled_quantity == 0.0
        assert order.remaining_quantity == 1.0
        assert order.created_at.tzinfo is not None  # timezone-aware

    def test_create_limit_order(self):
        """Test creating a limit order."""
        order = PaperOrder(
            order_id="test_456",
            symbol="ETHUSDT",
            side="sell",
            order_type="limit",
            quantity=2.0,
            price=3000.0,
        )

        assert order.order_type == "limit"
        assert order.price == 3000.0
        assert order.remaining_quantity == 2.0

    def test_side_normalization(self):
        """Test that side is normalized to lowercase."""
        order = PaperOrder(
            order_id="test_789",
            symbol="BTCUSDT",
            side="BUY",
            order_type="market",
            quantity=1.0,
        )
        assert order.side == "buy"

        order2 = PaperOrder(
            order_id="test_790",
            symbol="BTCUSDT",
            side="Sell",
            order_type="market",
            quantity=1.0,
        )
        assert order2.side == "sell"

    def test_order_type_normalization(self):
        """Test that order_type is normalized to lowercase."""
        order = PaperOrder(
            order_id="test_791",
            symbol="BTCUSDT",
            side="buy",
            order_type="MARKET",
            quantity=1.0,
        )
        assert order.order_type == "market"

    def test_invalid_side_raises(self):
        """Test that invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            PaperOrder(
                order_id="test_792",
                symbol="BTCUSDT",
                side="invalid",
                order_type="market",
                quantity=1.0,
            )

    def test_invalid_order_type_raises(self):
        """Test that invalid order_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid order_type"):
            PaperOrder(
                order_id="test_793",
                symbol="BTCUSDT",
                side="buy",
                order_type="stop_loss",
                quantity=1.0,
            )

    def test_negative_quantity_raises(self):
        """Test that negative quantity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid quantity"):
            PaperOrder(
                order_id="test_794",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=-1.0,
            )

    def test_zero_quantity_raises(self):
        """Test that zero quantity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid quantity"):
            PaperOrder(
                order_id="test_795",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=0.0,
            )

    def test_limit_order_requires_price(self):
        """Test that limit orders require a price."""
        with pytest.raises(ValueError, match="Limit orders require positive price"):
            PaperOrder(
                order_id="test_796",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1.0,
                price=None,
            )

    def test_limit_order_requires_positive_price(self):
        """Test that limit orders require positive price."""
        with pytest.raises(ValueError, match="Limit orders require positive price"):
            PaperOrder(
                order_id="test_797",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1.0,
                price=-100.0,
            )

    def test_is_active(self):
        """Test is_active method."""
        order = PaperOrder(
            order_id="test_798",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        assert order.is_active()

        order.state = OrderState.PARTIAL
        assert order.is_active()

        order.state = OrderState.FILLED
        assert not order.is_active()

        order.state = OrderState.REJECTED
        assert not order.is_active()

        order.state = OrderState.CANCELLED
        assert not order.is_active()

    def test_is_filled(self):
        """Test is_filled method."""
        order = PaperOrder(
            order_id="test_799",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )
        assert not order.is_filled()

        order.state = OrderState.FILLED
        assert order.is_filled()

    def test_add_fill(self):
        """Test adding a fill to an order."""
        order = PaperOrder(
            order_id="test_800",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        fill = PaperFill(
            fill_id="fill_001",
            order_id="test_800",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            price=50000.0,
        )

        order.add_fill(fill)

        assert len(order.fills) == 1
        assert order.filled_quantity == 0.5
        assert order.remaining_quantity == 0.5
        assert order.state == OrderState.PARTIAL
        assert order.updated_at > order.created_at

    def test_add_complete_fill(self):
        """Test adding a fill that completes the order."""
        order = PaperOrder(
            order_id="test_801",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        fill = PaperFill(
            fill_id="fill_002",
            order_id="test_801",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
        )

        order.add_fill(fill)

        assert order.filled_quantity == 1.0
        assert order.remaining_quantity == 0.0
        assert order.state == OrderState.FILLED
        assert order.is_filled()

    def test_reject(self):
        """Test rejecting an order."""
        order = PaperOrder(
            order_id="test_802",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        order.reject("Insufficient funds")

        assert order.state == OrderState.REJECTED
        assert order.reject_reason == "Insufficient funds"
        assert order.is_rejected()

    def test_cancel(self):
        """Test cancelling an order."""
        order = PaperOrder(
            order_id="test_803",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        result = order.cancel()

        assert result is True
        assert order.state == OrderState.CANCELLED
        assert order.is_cancelled()

    def test_cancel_filled_order_fails(self):
        """Test that cancelling a filled order fails."""
        order = PaperOrder(
            order_id="test_804",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
            state=OrderState.FILLED,
        )

        result = order.cancel()

        assert result is False
        assert order.state == OrderState.FILLED

    def test_avg_fill_price(self):
        """Test calculating average fill price."""
        order = PaperOrder(
            order_id="test_805",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=2.0,
        )

        # No fills yet
        assert order.avg_fill_price is None

        # Add first fill
        fill1 = PaperFill(
            fill_id="fill_003",
            order_id="test_805",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
        )
        order.add_fill(fill1)

        assert order.avg_fill_price == 50000.0

        # Add second fill at different price
        fill2 = PaperFill(
            fill_id="fill_004",
            order_id="test_805",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=51000.0,
        )
        order.add_fill(fill2)

        # Average: (50000*1 + 51000*1) / 2 = 50500
        assert order.avg_fill_price == 50500.0

    def test_to_dict(self):
        """Test converting order to dictionary."""
        order = PaperOrder(
            order_id="test_806",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1.0,
        )

        data = order.to_dict()

        assert data["order_id"] == "test_806"
        assert data["symbol"] == "BTCUSDT"
        assert data["side"] == "buy"
        assert data["order_type"] == "market"
        assert data["quantity"] == 1.0
        assert data["state"] == "pending"
        assert "created_at" in data
        assert "fills" in data

    def test_from_dict(self):
        """Test creating order from dictionary."""
        data = {
            "order_id": "test_807",
            "symbol": "ETHUSDT",
            "side": "sell",
            "order_type": "limit",
            "quantity": 2.0,
            "price": 3000.0,
            "state": "pending",
            "filled_quantity": 0.0,
            "remaining_quantity": 2.0,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "fills": [],
            "metadata": {"test": True},
        }

        order = PaperOrder.from_dict(data)

        assert order.order_id == "test_807"
        assert order.symbol == "ETHUSDT"
        assert order.side == "sell"
        assert order.price == 3000.0


class TestPaperFill:
    """Test PaperFill dataclass."""

    def test_create_fill(self):
        """Test creating a fill."""
        fill = PaperFill(
            fill_id="fill_100",
            order_id="order_100",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            price=50000.0,
        )

        assert fill.fill_id == "fill_100"
        assert fill.order_id == "order_100"
        assert fill.symbol == "BTCUSDT"
        assert fill.side == "buy"
        assert fill.quantity == 0.5
        assert fill.price == 50000.0
        assert fill.timestamp.tzinfo is not None

    def test_side_normalization(self):
        """Test that side is normalized."""
        fill = PaperFill(
            fill_id="fill_101",
            order_id="order_101",
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            price=50000.0,
        )
        assert fill.side == "sell"

    def test_invalid_side_raises(self):
        """Test that invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Invalid side"):
            PaperFill(
                fill_id="fill_102",
                order_id="order_102",
                symbol="BTCUSDT",
                side="invalid",
                quantity=0.5,
                price=50000.0,
            )

    def test_invalid_quantity_raises(self):
        """Test that invalid quantity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid quantity"):
            PaperFill(
                fill_id="fill_103",
                order_id="order_103",
                symbol="BTCUSDT",
                side="buy",
                quantity=-0.5,
                price=50000.0,
            )

    def test_invalid_price_raises(self):
        """Test that invalid price raises ValueError."""
        with pytest.raises(ValueError, match="Invalid price"):
            PaperFill(
                fill_id="fill_104",
                order_id="order_104",
                symbol="BTCUSDT",
                side="buy",
                quantity=0.5,
                price=-50000.0,
            )

    def test_notional_value(self):
        """Test calculating notional value."""
        fill = PaperFill(
            fill_id="fill_105",
            order_id="order_105",
            symbol="BTCUSDT",
            side="buy",
            quantity=2.0,
            price=50000.0,
        )

        assert fill.notional_value == 100000.0

    def test_to_dict(self):
        """Test converting fill to dictionary."""
        fill = PaperFill(
            fill_id="fill_106",
            order_id="order_106",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.5,
            price=50000.0,
        )

        data = fill.to_dict()

        assert data["fill_id"] == "fill_106"
        assert data["quantity"] == 0.5
        assert data["price"] == 50000.0
        assert data["notional_value"] == 25000.0

    def test_from_dict(self):
        """Test creating fill from dictionary."""
        data = {
            "fill_id": "fill_107",
            "order_id": "order_107",
            "symbol": "ETHUSDT",
            "side": "sell",
            "quantity": 1.5,
            "price": 3000.0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "metadata": {},
        }

        fill = PaperFill.from_dict(data)

        assert fill.fill_id == "fill_107"
        assert fill.quantity == 1.5
        assert fill.price == 3000.0
