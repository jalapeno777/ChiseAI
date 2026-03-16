"""Paper trading order simulator.

Implements a realistic order simulator that mimics exchange behavior
without hitting live APIs. Supports market and limit orders with
realistic fill simulation, slippage, and order state tracking.

For PAPER-LOOP-001: Paper Trading Order Simulator
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .fill_model import FillModel, create_fill_model
from .models import OrderState, PaperFill, PaperOrder


@dataclass
class MarketDataProvider:
    """Provider for market price data.

    In a real implementation, this would connect to market data feeds.
    For paper trading, it can be a mock or use stored price data.

    Attributes:
        price_cache: Cache of current prices by symbol
    """

    price_cache: dict[str, float] = field(default_factory=dict)

    def get_price(self, symbol: str) -> float | None:
        """Get current market price for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Current price or None if not available
        """
        return self.price_cache.get(symbol.upper())

    def set_price(self, symbol: str, price: float) -> None:
        """Set market price for a symbol.

        Args:
            symbol: Trading pair symbol
            price: Current price
        """
        self.price_cache[symbol.upper()] = price

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update multiple prices at once.

        Args:
            prices: Dictionary of symbol -> price
        """
        self.price_cache.update({k.upper(): v for k, v in prices.items()})


class OrderSimulator:
    """Paper trading order simulator.

    Simulates exchange order behavior including:
    - Order placement with validation
    - Market orders that fill immediately with slippage
    - Limit orders that fill when price crosses
    - Order cancellation
    - Order state tracking (PENDING -> PARTIAL -> FILLED/REJECTED)

    Attributes:
        fill_model: Model for fill price calculation and latency
        market_data: Provider for market prices
        orders: Dictionary of orders by order_id
        _order_counter: Counter for generating order IDs
    """

    def __init__(
        self,
        fill_model: FillModel | None = None,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        """Initialize the order simulator.

        Args:
            fill_model: Fill model for slippage and latency (uses defaults if None)
            market_data: Market data provider (uses empty cache if None)
        """
        self.fill_model = fill_model or create_fill_model()
        self.market_data = market_data or MarketDataProvider()
        self.orders: dict[str, PaperOrder] = {}
        self._order_counter = 0

    def _generate_order_id(self) -> str:
        """Generate a unique order ID.

        Returns:
            Unique order identifier
        """
        self._order_counter += 1
        return f"paper_{uuid.uuid4().hex[:12]}_{self._order_counter}"

    def _validate_order(self, order: PaperOrder) -> tuple[bool, str | None]:
        """Validate an order before placement.

        Args:
            order: Order to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check symbol
        if not order.symbol or not isinstance(order.symbol, str):
            return False, "Invalid symbol"

        # Check quantity
        if order.quantity <= 0:
            return False, f"Invalid quantity: {order.quantity}. Must be positive"

        # Check price for limit orders
        if order.order_type == "limit":
            if order.price is None:
                return False, "Limit orders require a price"
            if order.price <= 0:
                return False, f"Invalid limit price: {order.price}. Must be positive"

        # Check for market price availability for market orders
        if order.order_type == "market":
            market_price = self.market_data.get_price(order.symbol)
            if market_price is None:
                return False, f"No market price available for {order.symbol}"

        return True, None

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        **_: Any,
    ) -> PaperOrder:
        """Place a new order.

        Creates and validates the order, then attempts to fill it:
        - Market orders fill immediately with slippage
        - Limit orders are placed and may fill later if price crosses

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side - "buy" or "sell"
            order_type: Order type - "market" or "limit"
            quantity: Order quantity in base currency
            price: Order price (required for limit, ignored for market)

        Returns:
            The placed order with updated state

        Note:
            Invalid orders are returned with REJECTED state and reject_reason set
        """
        # Pre-validate before creating PaperOrder
        # (PaperOrder validates in __post_init__, so we need to check first)
        quantity_float = float(quantity)
        if quantity_float <= 0:
            # Create a minimal PaperOrder for tracking (with valid quantity)
            order_id = self._generate_order_id()
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol.upper() if symbol else "UNKNOWN",
                side="buy",  # Use valid side
                order_type="market",  # Use valid type
                quantity=0.001,  # Use minimum valid quantity for PaperOrder
            )
            # Store original values and rejection reason in metadata
            order.metadata["original_quantity"] = quantity
            order.reject(f"Invalid quantity: {quantity}. Must be positive")
            self.orders[order.order_id] = order
            return order

        # Create order
        try:
            order = PaperOrder(
                order_id=self._generate_order_id(),
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=quantity_float,
                price=float(price) if price is not None else None,
            )
        except ValueError as e:
            # Create rejected order for validation errors
            order_id = self._generate_order_id()
            order = PaperOrder(
                order_id=order_id,
                symbol=symbol.upper() if symbol else "UNKNOWN",
                side="buy",  # Use valid default
                order_type="market",  # Use valid default
                quantity=0.001,  # Use minimum valid quantity
            )
            order.metadata["original_side"] = side
            order.metadata["original_order_type"] = order_type
            order.metadata["original_quantity"] = quantity
            order.metadata["original_price"] = price
            order.reject(str(e))
            self.orders[order.order_id] = order
            return order

        # Additional validation
        is_valid, error = self._validate_order(order)
        if not is_valid:
            order.reject(error or "Validation failed")
            self.orders[order.order_id] = order
            return order

        # Store order
        self.orders[order.order_id] = order

        # Try to fill based on order type
        try:
            if order.order_type == "market":
                await self._fill_market_order(order)
            elif order.order_type == "limit":
                await self._try_fill_limit_order(order)
        except Exception as e:
            order.reject(f"Fill error: {str(e)}")

        return order

    async def _fill_market_order(self, order: PaperOrder) -> None:
        """Fill a market order completely.

        Args:
            order: The market order to fill
        """
        market_price = self.market_data.get_price(order.symbol)
        if market_price is None:
            order.reject(f"No market price for {order.symbol}")
            return

        fill = await self.fill_model.fill_market_order(order, market_price)
        order.add_fill(fill)

    async def _try_fill_limit_order(self, order: PaperOrder) -> None:
        """Try to fill a limit order immediately if price crosses.

        Args:
            order: The limit order to fill
        """
        market_price = self.market_data.get_price(order.symbol)
        if market_price is None:
            # Can't check if order should fill, leave it pending
            return

        fill = await self.fill_model.fill_limit_order(order, market_price)
        if fill:
            order.add_fill(fill)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.

        Only pending or partially filled orders can be cancelled.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False if order not found or can't be cancelled
        """
        order = self.orders.get(order_id)
        if order is None:
            return False

        return order.cancel()

    def get_order(self, order_id: str) -> PaperOrder | None:
        """Get an order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order or None if not found
        """
        return self.orders.get(order_id)

    def get_orders(
        self,
        symbol: str | None = None,
        state: OrderState | None = None,
        side: str | None = None,
    ) -> list[PaperOrder]:
        """Get orders with optional filtering.

        Args:
            symbol: Filter by symbol (optional)
            state: Filter by order state (optional)
            side: Filter by side (optional)

        Returns:
            List of matching orders
        """
        orders = list(self.orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol.upper()]
        if state:
            orders = [o for o in orders if o.state == state]
        if side:
            orders = [o for o in orders if o.side == side.lower()]

        return orders

    async def update_limit_orders(self, symbol: str | None = None) -> list[PaperFill]:
        """Check and fill limit orders that should execute.

        Call this when market prices change to check if any pending
        or partially filled limit orders should be filled.

        Args:
            symbol: Only check orders for this symbol (optional)

        Returns:
            List of new fills created
        """
        fills = []

        # Get orders to check
        orders_to_check = [
            o for o in self.orders.values() if o.is_active() and o.order_type == "limit"
        ]

        if symbol:
            orders_to_check = [o for o in orders_to_check if o.symbol == symbol.upper()]

        for order in orders_to_check:
            market_price = self.market_data.get_price(order.symbol)
            if market_price is None:
                continue

            fill = await self.fill_model.fill_limit_order(order, market_price)
            if fill:
                order.add_fill(fill)
                fills.append(fill)

        return fills

    def set_market_price(self, symbol: str, price: float) -> None:
        """Set market price for a symbol.

        Convenience method for updating market data.

        Args:
            symbol: Trading pair symbol
            price: Current price
        """
        self.market_data.set_price(symbol.upper(), price)

    def get_market_price(self, symbol: str) -> float | None:
        """Get current market price for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Current price or None if not available
        """
        return self.market_data.get_price(symbol.upper())

    def get_position(self, symbol: str) -> dict[str, Any]:
        """Calculate current position for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with position data:
                - symbol: Trading pair
                - quantity: Net position quantity (positive=long, negative=short)
                - avg_entry_price: Average entry price
                - total_filled: Total quantity filled
        """
        symbol = symbol.upper()
        position_qty = 0.0
        total_value = 0.0
        total_filled = 0.0

        for order in self.orders.values():
            if order.symbol != symbol:
                continue

            for fill in order.fills:
                if order.side == "buy":
                    position_qty += fill.quantity
                else:  # sell
                    position_qty -= fill.quantity

                total_value += fill.quantity * fill.price
                total_filled += fill.quantity

        avg_price = total_value / total_filled if total_filled > 0 else 0.0

        return {
            "symbol": symbol,
            "quantity": round(position_qty, 8),
            "avg_entry_price": round(avg_price, 8),
            "total_filled": round(total_filled, 8),
        }

    def reset(self) -> None:
        """Reset the simulator, clearing all orders."""
        self.orders.clear()
        self._order_counter = 0
        self.market_data.price_cache.clear()


class OrderSimulatorConfig:
    """Configuration for OrderSimulator.

    Attributes:
        min_slippage_pct: Minimum slippage percentage
        max_slippage_pct: Maximum slippage percentage
        min_latency_ms: Minimum latency in milliseconds
        max_latency_ms: Maximum latency in milliseconds
    """

    def __init__(
        self,
        min_slippage_pct: float = 0.01,
        max_slippage_pct: float = 0.05,
        min_latency_ms: float = 50.0,
        max_latency_ms: float = 200.0,
    ):
        self.min_slippage_pct = min_slippage_pct
        self.max_slippage_pct = max_slippage_pct
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms

    def create_simulator(self) -> OrderSimulator:
        """Create an OrderSimulator with this configuration.

        Returns:
            Configured OrderSimulator instance
        """
        fill_model = create_fill_model(
            min_slippage_pct=self.min_slippage_pct,
            max_slippage_pct=self.max_slippage_pct,
            min_latency_ms=self.min_latency_ms,
            max_latency_ms=self.max_latency_ms,
        )
        return OrderSimulator(fill_model=fill_model)
