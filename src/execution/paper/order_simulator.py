"""Paper trading order simulator.

Simulates order placement, execution, and fills for paper trading.
Integrates with FillModel for realistic price simulation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from execution.paper.fill_model import FillModel
    from execution.paper.models import PaperFill, PaperOrder

from execution.paper.models import OrderState, OrderSide, OrderType, PaperFill

logger = logging.getLogger(__name__)


class OrderSimulator:
    """Simulates order placement and execution for paper trading.

    Provides realistic order lifecycle:
    1. Order validation
    2. Price determination
    3. Fill simulation
    4. State updates

    Thread-safe for concurrent order processing.
    """

    def __init__(
        self,
        fill_model: FillModel | None = None,
        price_provider: Callable[[str], float] | None = None,
        fee_rate: float = 0.0006,
    ):
        """Initialize order simulator.

        Args:
            fill_model: Fill model for price simulation
            price_provider: Function to get current prices (symbol -> price)
            fee_rate: Trading fee rate (default 0.06%)
        """
        self.fill_model = fill_model
        self.price_provider = price_provider
        self.fee_rate = fee_rate

        # Order storage
        self._orders: dict[str, PaperOrder] = {}
        self._fills: dict[str, list[PaperFill]] = {}
        self._lock = asyncio.Lock()

        logger.info("OrderSimulator initialized")

    async def place_order(self, order: PaperOrder) -> PaperOrder:
        """Place and simulate execution of an order.

        Args:
            order: The order to place

        Returns:
            Updated order with fill state
        """
        correlation_id = order.correlation_id or str(uuid.uuid4())

        logger.info(
            f"Placing {order.order_type.value} order: {order.symbol} "
            f"{order.side.value} {order.quantity} (correlation_id={correlation_id})"
        )

        async with self._lock:
            # Store order
            self._orders[order.order_id] = order
            self._fills[order.order_id] = []

            # Validate order
            if not self._validate_order(order):
                order.state = OrderState.REJECTED
                order.updated_at = __import__("datetime").datetime.now().isoformat()
                logger.warning(f"Order {order.order_id} rejected: validation failed")
                return order

            # Update state to open
            order.state = OrderState.OPEN
            order.updated_at = __import__("datetime").datetime.now().isoformat()

        # Simulate fill delay (outside lock)
        if self.fill_model:
            delay_ms = self.fill_model.calculate_fill_delay_ms()
            await asyncio.sleep(delay_ms / 1000)

        # Execute fill
        try:
            filled_order = await self._execute_fill(order)

            logger.info(
                f"Order {order.order_id} {filled_order.state.value}: "
                f"filled={filled_order.filled_quantity}/{filled_order.quantity} "
                f"@ avg_price={filled_order.avg_fill_price:.2f}"
            )

            return filled_order

        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            async with self._lock:
                order.state = OrderState.FAILED
                order.updated_at = __import__("datetime").datetime.now().isoformat()
            return order

    def _validate_order(self, order: PaperOrder) -> bool:
        """Validate order parameters.

        Args:
            order: Order to validate

        Returns:
            True if valid, False otherwise
        """
        # Check quantity is positive
        if order.quantity <= 0:
            logger.error(f"Invalid quantity: {order.quantity}")
            return False

        # Check limit price for limit orders
        if order.order_type == OrderType.LIMIT and (
            order.price is None or order.price <= 0
        ):
            logger.error(f"Invalid limit price: {order.price}")
            return False

        # Check stop price for stop orders
        if order.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            if order.stop_price is None or order.stop_price <= 0:
                logger.error(f"Invalid stop price: {order.stop_price}")
                return False

        return True

    async def _execute_fill(self, order: PaperOrder) -> PaperOrder:
        """Execute the order fill.

        Args:
            order: Order to fill

        Returns:
            Updated order with fill details
        """
        # Get current market price
        market_price = await self._get_market_price(order.symbol)

        if market_price <= 0:
            logger.error(f"Invalid market price for {order.symbol}: {market_price}")
            order.state = OrderState.REJECTED
            return order

        # Calculate fill price
        if self.fill_model:
            fill_price = self.fill_model.calculate_fill_price(order, market_price)
        else:
            fill_price = market_price

        # Create fill record
        fill = PaperFill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            correlation_id=order.correlation_id,
        )

        # Calculate fee
        if self.fill_model:
            fill.fee = self.fill_model.calculate_fee(fill.notional_value, self.fee_rate)
        else:
            fill.fee = fill.notional_value * self.fee_rate

        # Update order with fill
        async with self._lock:
            order.filled_quantity = order.quantity
            order.avg_fill_price = fill_price
            order.state = OrderState.FILLED
            order.updated_at = __import__("datetime").datetime.now().isoformat()

            self._fills[order.order_id].append(fill)

        return order

    async def _get_market_price(self, symbol: str) -> float:
        """Get current market price for symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Current market price
        """
        if self.price_provider:
            try:
                price = self.price_provider(symbol)
                if price > 0:
                    return price
            except Exception as e:
                logger.warning(f"Price provider failed for {symbol}: {e}")

        # Fallback: return simulated price based on symbol
        # In real implementation, this would fetch from exchange API
        return self._get_simulated_price(symbol)

    def _get_simulated_price(self, symbol: str) -> float:
        """Get simulated price for testing.

        Args:
            symbol: Trading pair symbol

        Returns:
            Simulated price
        """
        # Simple hash-based price simulation for testing
        import hashlib

        hash_val = int(hashlib.md5(symbol.encode()).hexdigest(), 16)
        base_price = 100.0 + (hash_val % 90000) / 100  # $100 - $1000 range

        return base_price

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False if not found or not cancellable
        """
        async with self._lock:
            if order_id not in self._orders:
                return False

            order = self._orders[order_id]

            if order.state not in (
                OrderState.OPEN,
                OrderState.PENDING,
                OrderState.PARTIALLY_FILLED,
            ):
                return False

            order.state = OrderState.CANCELLED
            order.updated_at = __import__("datetime").datetime.now().isoformat()

        logger.info(f"Order {order_id} cancelled")
        return True

    async def get_order(self, order_id: str) -> PaperOrder | None:
        """Get order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order if found, None otherwise
        """
        async with self._lock:
            return self._orders.get(order_id)

    async def get_fills(self, order_id: str) -> list[PaperFill]:
        """Get fills for an order.

        Args:
            order_id: Order identifier

        Returns:
            List of fills for the order
        """
        async with self._lock:
            return self._fills.get(order_id, []).copy()

    async def get_all_orders(self) -> list[PaperOrder]:
        """Get all orders.

        Returns:
            List of all orders
        """
        async with self._lock:
            return list(self._orders.values())

    async def clear_all_orders(self) -> None:
        """Clear all orders and fills."""
        async with self._lock:
            self._orders.clear()
            self._fills.clear()

        logger.info("All orders cleared")
