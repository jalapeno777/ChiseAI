"""Tests for position query API.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from portfolio.state_management.models import PositionDirection, PositionStatus
from portfolio.state_management.position_query import (
    PositionQueryAPI,
    StopOrder,
)


class TestPositionQueryAPI:
    """Test PositionQueryAPI functionality."""

    @pytest.fixture
    def mock_bybit(self):
        """Create mock Bybit connector."""
        return MagicMock()

    @pytest.fixture
    def mock_bitget(self):
        """Create mock Bitget connector."""
        return MagicMock()

    @pytest.fixture
    def api(self, mock_bybit, mock_bitget):
        """Create PositionQueryAPI instance."""
        return PositionQueryAPI(
            bybit_connector=mock_bybit,
            bitget_connector=mock_bitget,
        )

    @pytest.mark.asyncio
    async def test_get_bybit_positions(self, api, mock_bybit):
        """Test getting positions from Bybit."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "64000.00",
                        "leverage": "10",
                        "markPrice": "65000.00",
                        "positionIdx": "pos_1",
                        "unrealisedPnl": "500",
                        "cumRealisedPnl": "100",
                        "liqPrice": "50000",
                        "positionValue": "32500",
                    }
                ]
            }
        }
        mock_bybit.get_positions = AsyncMock(return_value=mock_response)

        positions = await api.get_positions("bybit", "BTCUSDT")

        assert len(positions) == 1
        assert positions[0].token == "BTC"
        assert positions[0].direction == PositionDirection.LONG
        assert positions[0].quantity == 0.5
        assert positions[0].status == PositionStatus.OPEN

    @pytest.mark.asyncio
    async def test_get_bitget_positions(self, api, mock_bitget):
        """Test getting positions from Bitget."""
        mock_response = {
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "holdSide": "short",
                    "total": "0.3",
                    "averageOpenPrice": "66000.00",
                    "leverage": 5,
                    "marketPrice": "65000.00",
                    "posId": "pos_2",
                    "unrealizedPL": "-300",
                    "realizedPL": "50",
                    "liquidationPrice": "80000",
                    "marginMode": "crossed",
                }
            ]
        }
        mock_bitget.get_positions = AsyncMock(return_value=mock_response)

        positions = await api.get_positions("bitget", "BTCUSDT")

        assert len(positions) == 1
        assert positions[0].token == "BTC"
        assert positions[0].direction == PositionDirection.SHORT
        assert positions[0].quantity == 0.3

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, api, mock_bybit):
        """Test getting positions with empty response."""
        mock_bybit.get_positions = AsyncMock(return_value={"result": {"list": []}})

        positions = await api.get_positions("bybit", "BTCUSDT")

        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_get_positions_closed_filtered(self, api, mock_bybit):
        """Test that closed positions (size=0) are filtered."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0",  # Closed position
                        "avgPrice": "64000.00",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "Buy",
                        "size": "1.0",
                        "avgPrice": "3500.00",
                        "leverage": "10",
                        "markPrice": "3600.00",
                        "positionIdx": "pos_1",
                    },
                ]
            }
        }
        mock_bybit.get_positions = AsyncMock(return_value=mock_response)

        positions = await api.get_positions("bybit")

        assert len(positions) == 1
        assert positions[0].token == "ETH"

    @pytest.mark.asyncio
    async def test_get_stop_loss_bybit(self, api, mock_bybit):
        """Test getting stop loss from Bybit."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "stopLoss": "60000.00",
                    }
                ]
            }
        }
        mock_bybit.get_positions = AsyncMock(return_value=mock_response)

        sl = await api.get_stop_loss("bybit", "BTCUSDT")

        assert sl == Decimal("60000.00")

    @pytest.mark.asyncio
    async def test_get_stop_loss_none(self, api, mock_bybit):
        """Test getting stop loss when not set."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "stopLoss": "0",
                    }
                ]
            }
        }
        mock_bybit.get_positions = AsyncMock(return_value=mock_response)

        sl = await api.get_stop_loss("bybit", "BTCUSDT")

        assert sl is None

    @pytest.mark.asyncio
    async def test_get_take_profit_bitget(self, api, mock_bitget):
        """Test getting take profit from Bitget."""
        mock_response = {
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "takeProfitPrice": "70000.00",
                }
            ]
        }
        mock_bitget.get_positions = AsyncMock(return_value=mock_response)

        tp = await api.get_take_profit("bitget", "BTCUSDT")

        assert tp == Decimal("70000.00")

    @pytest.mark.asyncio
    async def test_get_stop_orders_bybit(self, api, mock_bybit):
        """Test getting stop orders from Bybit."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "orderId": "stop_1",
                        "symbol": "BTCUSDT",
                        "stopOrderType": "StopLoss",
                        "triggerPrice": "60000.00",
                        "price": "59900.00",
                        "qty": "0.5",
                        "side": "Sell",
                        "orderStatus": "Untriggered",
                        "updatedTime": "1704067200000",
                    },
                    {
                        "orderId": "tp_1",
                        "symbol": "BTCUSDT",
                        "stopOrderType": "TakeProfit",
                        "triggerPrice": "70000.00",
                        "qty": "0.5",
                        "side": "Sell",
                        "orderStatus": "Untriggered",
                        "updatedTime": "1704067200000",
                    },
                ]
            }
        }
        mock_bybit.get_stop_orders = AsyncMock(return_value=mock_response)

        orders = await api.get_stop_orders("bybit", "BTCUSDT")

        assert len(orders) == 2
        assert orders[0].order_type == "stop_loss"
        assert orders[1].order_type == "take_profit"

    @pytest.mark.asyncio
    async def test_get_stop_orders_bitget(self, api, mock_bitget):
        """Test getting stop orders from Bitget."""
        mock_response = {
            "data": [
                {
                    "orderId": "plan_1",
                    "symbol": "BTCUSDT",
                    "planType": "loss_plan",
                    "triggerPrice": "60000.00",
                    "executePrice": "59900.00",
                    "size": "0.5",
                    "side": "sell",
                    "status": "live",
                    "cTime": "1704067200000",
                }
            ]
        }
        mock_bitget.get_stop_orders = AsyncMock(return_value=mock_response)

        orders = await api.get_stop_orders("bitget", "BTCUSDT")

        assert len(orders) == 1
        assert orders[0].order_type == "stop_loss"
        assert orders[0].trigger_price == Decimal("60000.00")

    @pytest.mark.asyncio
    async def test_get_position_summary(self, api, mock_bybit):
        """Test getting position summary."""
        mock_response = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.5",
                        "avgPrice": "64000.00",
                        "leverage": "10",
                        "markPrice": "65000.00",
                        "positionIdx": "pos_1",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "Sell",
                        "size": "2.0",
                        "avgPrice": "3500.00",
                        "leverage": "5",
                        "markPrice": "3400.00",
                        "positionIdx": "pos_2",
                    },
                ]
            }
        }
        mock_bybit.get_positions = AsyncMock(return_value=mock_response)

        summary = await api.get_position_summary("bybit")

        assert summary["exchange"] == "bybit"
        assert summary["total_positions"] == 2
        assert summary["long_positions"] == 1
        assert summary["short_positions"] == 1
        assert "BTC" in summary["symbols"]
        assert "ETH" in summary["symbols"]

    def test_unsupported_exchange(self, api):
        """Test handling of unsupported exchange."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            # Use asyncio.run to properly handle the async call
            import asyncio

            asyncio.run(api.get_positions("unsupported", "BTCUSDT"))


class TestStopOrder:
    """Test StopOrder dataclass."""

    def test_create_stop_order(self):
        """Test creating a stop order."""
        order = StopOrder(
            order_id="stop_1",
            symbol="BTCUSDT",
            order_type="stop_loss",
            trigger_price=Decimal("60000.00"),
            price=Decimal("59900.00"),
            quantity=Decimal("0.5"),
            side="sell",
            status="active",
            timestamp=1704067200000,
        )

        assert order.order_id == "stop_1"
        assert order.order_type == "stop_loss"
        assert order.trigger_price == Decimal("60000.00")

    def test_to_dict(self):
        """Test serialization."""
        order = StopOrder(
            order_id="stop_1",
            symbol="BTCUSDT",
            order_type="stop_loss",
            trigger_price=Decimal("60000.00"),
            price=None,
            quantity=Decimal("0.5"),
            side="sell",
            status="active",
            timestamp=1704067200000,
        )

        data = order.to_dict()

        assert data["order_id"] == "stop_1"
        assert data["trigger_price"] == "60000.00"
        assert data["price"] is None
