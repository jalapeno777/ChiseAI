"""Tests for fill data model.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from data.execution.fill_model import Fill, FillBatch


class TestFill:
    """Test Fill dataclass."""

    def test_create_fill(self):
        """Test creating a valid fill."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        assert fill.order_id == "order_123"
        assert fill.fill_id == "fill_456"
        assert fill.symbol == "BTCUSDT"
        assert fill.side == "buy"
        assert fill.price == Decimal("65000.00")
        assert fill.quantity == Decimal("0.1")
        assert fill.exchange == "bybit"

    def test_invalid_side(self):
        """Test validation of invalid side."""
        with pytest.raises(ValueError, match="Invalid side"):
            Fill(
                order_id="order_123",
                fill_id="fill_456",
                symbol="BTCUSDT",
                side="invalid",
                price=Decimal("65000.00"),
                quantity=Decimal("0.1"),
                timestamp=datetime.now(timezone.utc),
                fee=Decimal("6.50"),
                fee_currency="USDT",
                exchange="bybit",
            )

    def test_invalid_exchange(self):
        """Test validation of invalid exchange."""
        with pytest.raises(ValueError, match="Invalid exchange"):
            Fill(
                order_id="order_123",
                fill_id="fill_456",
                symbol="BTCUSDT",
                side="buy",
                price=Decimal("65000.00"),
                quantity=Decimal("0.1"),
                timestamp=datetime.now(timezone.utc),
                fee=Decimal("6.50"),
                fee_currency="USDT",
                exchange="invalid_exchange",
            )

    def test_notional_value(self):
        """Test notional value calculation."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        assert fill.notional_value == Decimal("6500.00")

    def test_net_quantity_buy(self):
        """Test net quantity for buy order."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("0.0001"),  # Fee in BTC
            fee_currency="BTC",
            exchange="bybit",
        )

        # Fee in base currency reduces net quantity
        assert fill.net_quantity == Decimal("0.0999")

    def test_net_quantity_buy_usdt_fee(self):
        """Test net quantity for buy order with USDT fee."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        # Fee in quote currency doesn't affect quantity
        assert fill.net_quantity == Decimal("0.1")

    def test_net_value_sell(self):
        """Test net value for sell order."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="sell",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        # Fee deducted from proceeds
        assert fill.net_value == Decimal("6493.50")

    def test_to_dict(self):
        """Test serialization to dictionary."""
        fill = Fill(
            order_id="order_123",
            fill_id="fill_456",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        data = fill.to_dict()

        assert data["order_id"] == "order_123"
        assert data["symbol"] == "BTCUSDT"
        assert data["price"] == "65000.00"
        assert data["notional_value"] == "6500.000"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "order_id": "order_123",
            "fill_id": "fill_456",
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "65000.00",
            "quantity": "0.1",
            "timestamp": "2024-01-01T12:00:00+00:00",
            "fee": "6.50",
            "fee_currency": "USDT",
            "exchange": "bybit",
        }

        fill = Fill.from_dict(data)

        assert fill.order_id == "order_123"
        assert fill.price == Decimal("65000.00")
        assert fill.quantity == Decimal("0.1")

    def test_from_bybit_response(self):
        """Test creating fill from Bybit API response."""
        response = {
            "orderId": "order_123",
            "execId": "exec_456",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execPrice": "65000.00",
            "execQty": "0.1",
            "execTime": "1704067200000",
            "execFee": "6.50",
            "feeCurrency": "USDT",
            "execType": "Trade",
            "isMaker": False,
        }

        fill = Fill.from_bybit_response(response)

        assert fill.order_id == "order_123"
        assert fill.fill_id == "exec_456"
        assert fill.side == "buy"
        assert fill.exchange == "bybit"
        assert fill.price == Decimal("65000.00")
        assert fill.metadata["exec_type"] == "Trade"

    def test_from_bitget_response(self):
        """Test creating fill from Bitget API response."""
        response = {
            "orderId": "order_123",
            "tradeId": "trade_456",
            "symbol": "BTCUSDT",
            "side": "buy",
            "price": "65000.00",
            "baseVolume": "0.1",
            "cTime": "1704067200000",
            "fee": "6.50",
            "feeCoin": "USDT",
            "tradeScope": "web",
        }

        fill = Fill.from_bitget_response(response)

        assert fill.order_id == "order_123"
        assert fill.fill_id == "trade_456"
        assert fill.side == "buy"
        assert fill.exchange == "bitget"
        assert fill.price == Decimal("65000.00")

    def test_normalize_side(self):
        """Test side normalization."""
        fill1 = Fill(
            order_id="1",
            fill_id="1",
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("1"),
            quantity=Decimal("1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("0"),
            fee_currency="USDT",
            exchange="bybit",
        )
        assert fill1.side == "buy"

        fill2 = Fill(
            order_id="2",
            fill_id="2",
            symbol="BTCUSDT",
            side="SELL",
            price=Decimal("1"),
            quantity=Decimal("1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("0"),
            fee_currency="USDT",
            exchange="bybit",
        )
        assert fill2.side == "sell"


class TestFillBatch:
    """Test FillBatch dataclass."""

    def test_create_batch(self):
        """Test creating a fill batch."""
        fill1 = Fill(
            order_id="order_1",
            fill_id="fill_1",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )
        fill2 = Fill(
            order_id="order_2",
            fill_id="fill_2",
            symbol="ETHUSDT",
            side="sell",
            price=Decimal("3500.00"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("3.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        batch = FillBatch(fills=[fill1, fill2], exchange="bybit")

        assert len(batch) == 2
        assert batch.exchange == "bybit"

    def test_total_notional(self):
        """Test total notional calculation."""
        fill1 = Fill(
            order_id="order_1",
            fill_id="fill_1",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )
        fill2 = Fill(
            order_id="order_2",
            fill_id="fill_2",
            symbol="ETHUSDT",
            side="sell",
            price=Decimal("3500.00"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("3.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        batch = FillBatch(fills=[fill1, fill2], exchange="bybit")

        # 6500 + 3500 = 10000
        assert batch.total_notional == Decimal("10000.00")

    def test_total_fees(self):
        """Test total fees calculation."""
        fill1 = Fill(
            order_id="order_1",
            fill_id="fill_1",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )
        fill2 = Fill(
            order_id="order_2",
            fill_id="fill_2",
            symbol="ETHUSDT",
            side="sell",
            price=Decimal("3500.00"),
            quantity=Decimal("1.0"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("3.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        batch = FillBatch(fills=[fill1, fill2], exchange="bybit")

        # 6.50 + 3.50 = 10.00
        assert batch.total_fees == Decimal("10.00")

    def test_to_dict(self):
        """Test batch serialization."""
        fill = Fill(
            order_id="order_1",
            fill_id="fill_1",
            symbol="BTCUSDT",
            side="buy",
            price=Decimal("65000.00"),
            quantity=Decimal("0.1"),
            timestamp=datetime.now(timezone.utc),
            fee=Decimal("6.50"),
            fee_currency="USDT",
            exchange="bybit",
        )

        batch = FillBatch(fills=[fill], exchange="bybit")
        data = batch.to_dict()

        assert data["count"] == 1
        assert data["exchange"] == "bybit"
        assert data["total_notional"] == "6500.000"
        assert len(data["fills"]) == 1
