"""Position query API for risk calculations.

Provides query interface for positions, stop losses, and take profits
from Bybit and Bitget exchanges.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio.state_management.models import (
    Position,
    PositionDirection,
    PositionStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class StopOrder:
    """Stop loss or take profit order.

    Attributes:
        order_id: Exchange order ID
        symbol: Trading pair
        order_type: "stop_loss" or "take_profit"
        trigger_price: Price at which order triggers
        price: Execution price (for limit orders)
        quantity: Order quantity
        side: "buy" or "sell"
        status: Order status
        timestamp: Order timestamp
    """

    order_id: str
    symbol: str
    order_type: str  # stop_loss or take_profit
    trigger_price: Decimal
    price: Decimal | None
    quantity: Decimal
    side: str
    status: str
    timestamp: int  # Unix ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "order_type": self.order_type,
            "trigger_price": str(self.trigger_price),
            "price": str(self.price) if self.price else None,
            "quantity": str(self.quantity),
            "side": self.side,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class PositionQueryAPI:
    """Query API for positions, SL, and TP data.

    Provides unified interface for querying position and stop order data
    from Bybit and Bitget exchanges.

    Usage:
        # With existing connectors
        from data.exchange.bybit_connector import BybitConnector
        from data.exchange.bitget_connector import BitgetConnector

        bybit = BybitConnector(config)
        bitget = BitgetConnector(config)

        api = PositionQueryAPI(bybit_connector=bybit, bitget_connector=bitget)

        # Query positions
        positions = await api.get_positions("bybit", "BTCUSDT")

        # Query stop loss
        sl = await api.get_stop_loss("bybit", "BTCUSDT")

        # Query take profit
        tp = await api.get_take_profit("bybit", "BTCUSDT")
    """

    def __init__(
        self,
        bybit_connector: Any | None = None,
        bitget_connector: Any | None = None,
    ):
        """Initialize position query API.

        Args:
            bybit_connector: BybitConnector instance
            bitget_connector: BitgetConnector instance
        """
        self._bybit = bybit_connector
        self._bitget = bitget_connector

    async def get_positions(
        self,
        exchange: str,
        symbol: str | None = None,
    ) -> list[Position]:
        """Get positions for exchange and optional symbol.

        Args:
            exchange: Exchange name ("bybit" or "bitget")
            symbol: Trading pair filter (optional)

        Returns:
            List of Position objects
        """
        exchange = exchange.lower()

        if exchange == "bybit":
            return await self._get_bybit_positions(symbol)
        elif exchange == "bitget":
            return await self._get_bitget_positions(symbol)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")

    async def _get_bybit_positions(self, symbol: str | None = None) -> list[Position]:
        """Get positions from Bybit."""
        if not self._bybit:
            raise RuntimeError("Bybit connector not configured")

        try:
            response = await self._bybit.get_positions(symbol=symbol)
            positions = []

            for pos_data in response.get("result", {}).get("list", []):
                # Skip closed positions
                if pos_data.get("size", "0") == "0":
                    continue

                position = self._parse_bybit_position(pos_data)
                if position:
                    positions.append(position)

            return positions

        except Exception as e:
            logger.error(f"Failed to get Bybit positions: {e}")
            return []

    def _parse_bybit_position(self, data: dict[str, Any]) -> Position | None:
        """Parse Bybit position data into Position model."""
        try:
            symbol = data.get("symbol", "")
            side = data.get("side", "")
            size = data.get("size", "0")

            if not symbol or not size or size == "0":
                return None

            # Determine direction
            direction = (
                PositionDirection.LONG if side == "Buy" else PositionDirection.SHORT
            )

            # Parse values
            entry_price = float(data.get("avgPrice", data.get("entryPrice", 0)))
            quantity = abs(float(size))
            current_price = float(data.get("markPrice", entry_price))
            leverage = float(data.get("leverage", "1"))

            # Calculate margin used
            notional = entry_price * quantity
            margin_used = notional / leverage

            return Position(
                position_id=data.get("positionIdx", f"{symbol}_{side}"),
                token=symbol.replace("USDT", "").replace("USD", ""),
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                current_price=current_price,
                leverage=leverage,
                margin_used=margin_used,
                status=PositionStatus.OPEN,
                metadata={
                    "symbol": symbol,
                    "unrealized_pnl": data.get("unrealisedPnl", "0"),
                    "realized_pnl": data.get("cumRealisedPnl", "0"),
                    "liquidation_price": data.get("liqPrice", "0"),
                    "position_value": data.get("positionValue", "0"),
                },
            )

        except Exception as e:
            logger.error(f"Failed to parse Bybit position: {e}")
            return None

    async def _get_bitget_positions(self, symbol: str | None = None) -> list[Position]:
        """Get positions from Bitget."""
        if not self._bitget:
            raise RuntimeError("Bitget connector not configured")

        try:
            response = await self._bitget.get_positions(symbol=symbol)
            positions = []

            for pos_data in response.get("data", []):
                # Skip closed positions
                if pos_data.get("total", "0") == "0":
                    continue

                position = self._parse_bitget_position(pos_data)
                if position:
                    positions.append(position)

            return positions

        except Exception as e:
            logger.error(f"Failed to get Bitget positions: {e}")
            return []

    def _parse_bitget_position(self, data: dict[str, Any]) -> Position | None:
        """Parse Bitget position data into Position model."""
        try:
            symbol = data.get("symbol", "")
            hold_side = data.get("holdSide", "")
            total = data.get("total", "0")

            if not symbol or not total or total == "0":
                return None

            # Determine direction
            direction = (
                PositionDirection.LONG
                if hold_side == "long"
                else PositionDirection.SHORT
            )

            # Parse values
            entry_price = float(data.get("averageOpenPrice", 0))
            quantity = abs(float(total))
            current_price = float(data.get("marketPrice", entry_price))
            leverage = float(data.get("leverage", 1))

            # Calculate margin used
            notional = entry_price * quantity
            margin_used = notional / leverage

            return Position(
                position_id=data.get("posId", f"{symbol}_{hold_side}"),
                token=symbol.replace("USDT", "").replace("USD", ""),
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                current_price=current_price,
                leverage=leverage,
                margin_used=margin_used,
                status=PositionStatus.OPEN,
                metadata={
                    "symbol": symbol,
                    "unrealized_pnl": data.get("unrealizedPL", "0"),
                    "realized_pnl": data.get("realizedPL", "0"),
                    "liquidation_price": data.get("liquidationPrice", "0"),
                    "margin_mode": data.get("marginMode", ""),
                },
            )

        except Exception as e:
            logger.error(f"Failed to parse Bitget position: {e}")
            return None

    async def get_stop_loss(
        self,
        exchange: str,
        symbol: str,
    ) -> Decimal | None:
        """Get stop loss price for a symbol.

        Args:
            exchange: Exchange name ("bybit" or "bitget")
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Stop loss trigger price or None if not set
        """
        exchange = exchange.lower()

        if exchange == "bybit":
            return await self._get_bybit_stop_loss(symbol)
        elif exchange == "bitget":
            return await self._get_bitget_stop_loss(symbol)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")

    async def _get_bybit_stop_loss(self, symbol: str) -> Decimal | None:
        """Get stop loss from Bybit."""
        if not self._bybit:
            return None

        try:
            # Get positions which include SL/TP info
            response = await self._bybit.get_positions(symbol=symbol)

            for pos_data in response.get("result", {}).get("list", []):
                if pos_data.get("symbol") == symbol:
                    sl_price = pos_data.get("stopLoss", "0")
                    if sl_price and sl_price != "0":
                        return Decimal(sl_price)

            return None

        except Exception as e:
            logger.error(f"Failed to get Bybit stop loss: {e}")
            return None

    async def _get_bitget_stop_loss(self, symbol: str) -> Decimal | None:
        """Get stop loss from Bitget."""
        if not self._bitget:
            return None

        try:
            # Get positions which include SL/TP info
            response = await self._bitget.get_positions(symbol=symbol)

            for pos_data in response.get("data", []):
                if pos_data.get("symbol") == symbol:
                    sl_price = pos_data.get("stopLossPrice", "0")
                    if sl_price and sl_price != "0":
                        return Decimal(sl_price)

            return None

        except Exception as e:
            logger.error(f"Failed to get Bitget stop loss: {e}")
            return None

    async def get_take_profit(
        self,
        exchange: str,
        symbol: str,
    ) -> Decimal | None:
        """Get take profit price for a symbol.

        Args:
            exchange: Exchange name ("bybit" or "bitget")
            symbol: Trading pair (e.g., "BTCUSDT")

        Returns:
            Take profit trigger price or None if not set
        """
        exchange = exchange.lower()

        if exchange == "bybit":
            return await self._get_bybit_take_profit(symbol)
        elif exchange == "bitget":
            return await self._get_bitget_take_profit(symbol)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")

    async def _get_bybit_take_profit(self, symbol: str) -> Decimal | None:
        """Get take profit from Bybit."""
        if not self._bybit:
            return None

        try:
            response = await self._bybit.get_positions(symbol=symbol)

            for pos_data in response.get("result", {}).get("list", []):
                if pos_data.get("symbol") == symbol:
                    tp_price = pos_data.get("takeProfit", "0")
                    if tp_price and tp_price != "0":
                        return Decimal(tp_price)

            return None

        except Exception as e:
            logger.error(f"Failed to get Bybit take profit: {e}")
            return None

    async def _get_bitget_take_profit(self, symbol: str) -> Decimal | None:
        """Get take profit from Bitget."""
        if not self._bitget:
            return None

        try:
            response = await self._bitget.get_positions(symbol=symbol)

            for pos_data in response.get("data", []):
                if pos_data.get("symbol") == symbol:
                    tp_price = pos_data.get("takeProfitPrice", "0")
                    if tp_price and tp_price != "0":
                        return Decimal(tp_price)

            return None

        except Exception as e:
            logger.error(f"Failed to get Bitget take profit: {e}")
            return None

    async def get_stop_orders(
        self,
        exchange: str,
        symbol: str | None = None,
    ) -> list[StopOrder]:
        """Get all stop orders (SL/TP) for exchange.

        Args:
            exchange: Exchange name ("bybit" or "bitget")
            symbol: Trading pair filter (optional)

        Returns:
            List of StopOrder objects
        """
        exchange = exchange.lower()

        if exchange == "bybit":
            return await self._get_bybit_stop_orders(symbol)
        elif exchange == "bitget":
            return await self._get_bitget_stop_orders(symbol)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")

    async def _get_bybit_stop_orders(
        self, symbol: str | None = None
    ) -> list[StopOrder]:
        """Get stop orders from Bybit."""
        if not self._bybit:
            return []

        try:
            response = await self._bybit.get_stop_orders(symbol=symbol)
            orders = []

            for order_data in response.get("result", {}).get("list", []):
                order_type = order_data.get("stopOrderType", "")
                if order_type in ("StopLoss", "TakeProfit"):
                    order = self._parse_bybit_stop_order(order_data)
                    if order:
                        orders.append(order)

            return orders

        except Exception as e:
            logger.error(f"Failed to get Bybit stop orders: {e}")
            return []

    def _parse_bybit_stop_order(self, data: dict[str, Any]) -> StopOrder | None:
        """Parse Bybit stop order data."""
        try:
            order_type_str = data.get("stopOrderType", "")
            order_type = "stop_loss" if order_type_str == "StopLoss" else "take_profit"

            return StopOrder(
                order_id=data.get("orderId", ""),
                symbol=data.get("symbol", ""),
                order_type=order_type,
                trigger_price=Decimal(data.get("triggerPrice", "0")),
                price=Decimal(data.get("price", "0")) if data.get("price") else None,
                quantity=Decimal(data.get("qty", "0")),
                side=data.get("side", "").lower(),
                status=data.get("orderStatus", "").lower(),
                timestamp=int(data.get("updatedTime", 0)),
            )

        except Exception as e:
            logger.error(f"Failed to parse Bybit stop order: {e}")
            return None

    async def _get_bitget_stop_orders(
        self, symbol: str | None = None
    ) -> list[StopOrder]:
        """Get stop orders from Bitget."""
        if not self._bitget:
            return []

        try:
            response = await self._bitget.get_stop_orders(symbol=symbol)
            orders = []

            for order_data in response.get("data", []):
                # Bitget uses planType to identify stop orders
                plan_type = order_data.get("planType", "")
                if plan_type in ("loss_plan", "profit_plan"):
                    order = self._parse_bitget_stop_order(order_data)
                    if order:
                        orders.append(order)

            return orders

        except Exception as e:
            logger.error(f"Failed to get Bitget stop orders: {e}")
            return []

    def _parse_bitget_stop_order(self, data: dict[str, Any]) -> StopOrder | None:
        """Parse Bitget stop order data."""
        try:
            plan_type = data.get("planType", "")
            order_type = "stop_loss" if plan_type == "loss_plan" else "take_profit"

            return StopOrder(
                order_id=data.get("orderId", ""),
                symbol=data.get("symbol", ""),
                order_type=order_type,
                trigger_price=Decimal(data.get("triggerPrice", "0")),
                price=(
                    Decimal(data.get("executePrice", "0"))
                    if data.get("executePrice")
                    else None
                ),
                quantity=Decimal(data.get("size", "0")),
                side=data.get("side", "").lower(),
                status=data.get("status", "").lower(),
                timestamp=int(data.get("cTime", 0)),
            )

        except Exception as e:
            logger.error(f"Failed to parse Bitget stop order: {e}")
            return None

    async def get_position_summary(self, exchange: str) -> dict[str, Any]:
        """Get summary of all positions for an exchange.

        Args:
            exchange: Exchange name ("bybit" or "bitget")

        Returns:
            Summary dictionary with position counts, total exposure, etc.
        """
        positions = await self.get_positions(exchange)

        long_positions = [p for p in positions if p.is_long]
        short_positions = [p for p in positions if p.is_short]

        total_margin = sum(p.margin_used for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)

        return {
            "exchange": exchange,
            "total_positions": len(positions),
            "long_positions": len(long_positions),
            "short_positions": len(short_positions),
            "total_margin_used": total_margin,
            "total_unrealized_pnl": total_unrealized_pnl,
            "symbols": list(set(p.token for p in positions)),
        }
