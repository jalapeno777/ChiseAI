"""Bybit Demo Connector for authenticated demo trading.

This module provides a bridge between the paper trading orchestrator and
the actual Bybit demo API. It wraps BybitConnector to provide the same
interface as OrderSimulator while making real authenticated API calls to
Bybit demo endpoints.

For REMEDIATION-001: G8 Bybit Demo Provenance

Key Features:
- Authenticated execution to Bybit demo API
- Provenance logging for audit trail
- Mock/sim leakage prevention
- Compatible with OrderSimulator interface
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data.exchange.bybit_connector import BybitConfig, BybitConnector
    from execution.paper.models import PaperOrder
    from execution.paper.order_simulator import MarketDataProvider

from execution.paper.models import OrderState, PaperFill, PaperOrder

logger = logging.getLogger(__name__)


@dataclass
class DemoProvenance:
    """Provenance information for demo trading.

    Attributes:
        is_demo: Whether demo mode is active
        endpoint: The Bybit demo endpoint used
        api_key_prefix: First 4 chars of API key for identification
        timestamp: When the provenance was recorded
    """

    is_demo: bool
    endpoint: str
    api_key_prefix: str
    timestamp: str


class BybitDemoConnector:
    """Bybit demo connector for authenticated demo trading.

    This class wraps BybitConnector to provide the same interface as
    OrderSimulator while making real authenticated API calls to Bybit
    demo endpoints. It includes provenance logging to prove that trades
    are executed against the actual Bybit demo API.

    Attributes:
        connector: The underlying BybitConnector instance
        market_data: Market data provider for price lookups
        provenance: Provenance information proving demo execution
        _orders: Cache of orders placed via this connector
    """

    def __init__(
        self,
        connector: BybitConnector,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        """Initialize the Bybit demo connector.

        Args:
            connector: Configured BybitConnector instance (must be in demo mode)
            market_data: Optional market data provider for price lookups

        Raises:
            ValueError: If connector is not configured for demo mode
            SecurityException: If connector is using production endpoints
        """
        from data.exchange.bybit_safety import SecurityException, validate_endpoint_url

        self.connector = connector
        self.market_data = market_data
        self._orders: dict[str, PaperOrder] = {}

        # Validate demo mode
        config = connector.config

        # Check that demo mode is enabled
        if not config.demo:
            raise ValueError(
                "BybitDemoConnector requires demo mode. Ensure BybitConfig.demo=True"
            )

        # Validate endpoints are demo endpoints
        try:
            validate_endpoint_url(config.base_url)
            validate_endpoint_url(config.private_ws_url)
        except SecurityException as e:
            raise SecurityException(
                f"BybitDemoConnector requires demo endpoints. {e}",
                endpoint=config.base_url,
                operation="BybitDemoConnector.__init__",
            ) from e

        # Record provenance
        self.provenance = DemoProvenance(
            is_demo=True,
            endpoint=config.base_url,
            api_key_prefix=config.api_key[:4] if config.api_key else "****",
            timestamp=__import__("datetime")
            .datetime.now(__import__("datetime").UTC)
            .isoformat(),
        )

        # Log provenance
        logger.info(
            f"BybitDemoConnector initialized - DEMO MODE PROVENANCE: "
            f"endpoint={self.provenance.endpoint}, "
            f"api_key={self.provenance.api_key_prefix}..., "
            f"timestamp={self.provenance.timestamp}"
        )

    @classmethod
    def from_env(cls, load_env: bool = True) -> BybitDemoConnector:
        """Create connector from environment variables.

        Args:
            load_env: Whether to load .env file

        Returns:
            Configured BybitDemoConnector instance

        Raises:
            ValueError: If demo credentials are not available
        """
        from data.exchange.bybit_connector import BybitConfig, BybitConnector

        # Create config from env (will use BYBIT_DEMO_API_KEY if available)
        config = BybitConfig.from_env(load_env=load_env)

        # Ensure demo mode
        if not config.demo:
            raise ValueError(
                "BYBIT_DEMO_API_KEY not found. "
                "BybitDemoConnector requires demo credentials."
            )

        # Create connector
        connector = BybitConnector(config)

        return cls(connector)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> PaperOrder:
        """Place an order via Bybit demo API.

        This method makes an actual authenticated API call to Bybit demo
        endpoints. It returns a PaperOrder with the actual order details
        from Bybit.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side - "buy" or "sell"
            order_type: Order type - "market" or "limit"
            quantity: Order quantity
            price: Order price (required for limit orders)

        Returns:
            PaperOrder with actual Bybit order details
        """
        # Log provenance before placing order
        logger.info(
            f"DEMO EXECUTION: Placing {order_type} {side} order for {quantity} {symbol} "
            f"via Bybit demo API at {self.provenance.endpoint}"
        )

        try:
            # Ensure connector is connected
            if self.connector._session is None or self.connector._session.closed:
                await self.connector.connect()

            # Place order via Bybit API
            result = await self.connector.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                time_in_force="GTC",
            )

            # Create PaperOrder from Bybit response
            order = PaperOrder(
                order_id=result.get("order_id", ""),
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=quantity,
                price=price if price else 0.0,
            )

            # Record the fill if order is filled
            status = result.get("status", "Created")
            if status in ["Filled", "PartiallyFilled"]:
                fill_price = result.get("price", 0.0)
                if fill_price == 0.0 and self.market_data:
                    # Fallback to market data price
                    fill_price = self.market_data.get_price(symbol) or 0.0

                fill = PaperFill(
                    fill_id=f"fill_{order.order_id}",
                    order_id=order.order_id,
                    symbol=symbol.upper(),
                    side=side.lower(),
                    price=fill_price,
                    quantity=quantity,
                    timestamp=__import__("datetime")
                    .datetime.now(__import__("datetime").UTC)
                    .isoformat(),
                )
                order.add_fill(fill)
                order.state = OrderState.FILLED
            else:
                order.state = OrderState.PENDING

            # Store order
            self._orders[order.order_id] = order

            # Audit log
            from data.exchange.bybit_safety import audit_log_order_operation

            audit_log_order_operation(
                order_id=order.order_id,
                symbol=symbol,
                side=side,
                price=order.price,
                quantity=quantity,
                order_type=order_type,
                status=status,
                operation="place_order_demo",
            )

            logger.info(
                f"DEMO EXECUTION SUCCESS: Order {order.order_id} placed via Bybit demo API. "
                f"Status: {status}, Fills: {len(order.fills)}"
            )

            return order

        except Exception as e:
            logger.error(f"DEMO EXECUTION FAILED: {e}")

            # Create rejected order
            order = PaperOrder(
                order_id=f"rejected_{__import__('uuid').uuid4().hex[:12]}",
                symbol=symbol.upper(),
                side=side.lower(),
                order_type=order_type.lower(),
                quantity=float(quantity) if quantity else 0.001,
            )
            order.reject(f"Bybit demo API error: {e}")
            self._orders[order.order_id] = order

            return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Bybit demo API.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled, False otherwise
        """
        order = self._orders.get(order_id)
        if order is None:
            logger.warning(f"Cancel order failed: Order {order_id} not found")
            return False

        try:
            # Ensure connector is connected
            if self.connector._session is None or self.connector._session.closed:
                await self.connector.connect()

            result = await self.connector.cancel_order(
                symbol=order.symbol,
                order_id=order_id,
            )

            # Update order state
            order.cancel()

            # Audit log
            from data.exchange.bybit_safety import audit_log_order_operation

            audit_log_order_operation(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                order_type=order.order_type,
                status="Cancelled",
                operation="cancel_order_demo",
            )

            logger.info(
                f"DEMO EXECUTION: Order {order_id} cancelled via Bybit demo API"
            )
            return True

        except Exception as e:
            logger.error(f"DEMO EXECUTION: Cancel order {order_id} failed: {e}")
            return False

    def get_order(self, order_id: str) -> PaperOrder | None:
        """Get an order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order or None if not found
        """
        return self._orders.get(order_id)

    def get_orders(
        self,
        symbol: str | None = None,
        state: OrderState | None = None,
        side: str | None = None,
    ) -> list[PaperOrder]:
        """Get orders with optional filtering.

        Args:
            symbol: Filter by symbol
            state: Filter by order state
            side: Filter by side

        Returns:
            List of matching orders
        """
        orders = list(self._orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol.upper()]
        if state:
            orders = [o for o in orders if o.state == state]
        if side:
            orders = [o for o in orders if o.side == side.lower()]

        return orders

    def get_position(self, symbol: str) -> dict[str, Any]:
        """Get position for a symbol from Bybit demo API.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary with position data
        """
        # For now, calculate from local orders
        # In future, this could query Bybit API for actual positions
        symbol = symbol.upper()
        position_qty = 0.0
        total_value = 0.0
        total_filled = 0.0

        for order in self._orders.values():
            if order.symbol != symbol:
                continue

            for fill in order.fills:
                if order.side == "buy":
                    position_qty += fill.quantity
                else:
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

    def get_provenance(self) -> DemoProvenance:
        """Get provenance information proving demo execution.

        Returns:
            DemoProvenance with execution details
        """
        return self.provenance

    def is_demo_mode(self) -> bool:
        """Check if connector is in demo mode.

        Returns:
            True if using demo endpoints
        """
        return self.provenance.is_demo

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on Bybit demo connection.

        Returns:
            Health status dictionary
        """
        try:
            # Ensure connector is connected
            if self.connector._session is None or self.connector._session.closed:
                await self.connector.connect()

            # Try a simple API call
            health = await self.connector.health_check()

            return {
                "healthy": health.get("healthy", False),
                "demo_mode": self.provenance.is_demo,
                "endpoint": self.provenance.endpoint,
                "api_accessible": health.get("api_accessible", False),
                "provenance": {
                    "is_demo": self.provenance.is_demo,
                    "endpoint": self.provenance.endpoint,
                    "api_key_prefix": self.provenance.api_key_prefix,
                    "timestamp": self.provenance.timestamp,
                },
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "demo_mode": self.provenance.is_demo,
                "endpoint": self.provenance.endpoint,
                "error": str(e),
            }

    async def close(self) -> None:
        """Close the connector and cleanup resources."""
        await self.connector.close()
        logger.info("BybitDemoConnector closed")


class BybitDemoConnectorFactory:
    """Factory for creating BybitDemoConnector instances.

    This factory provides a way to create either a BybitDemoConnector
    (for authenticated demo trading) or fall back to OrderSimulator
    (if demo credentials are not available).
    """

    @staticmethod
    def create(
        prefer_demo: bool = True,
        market_data: MarketDataProvider | None = None,
    ) -> BybitDemoConnector | Any:
        """Create appropriate connector based on available credentials.

        Args:
            prefer_demo: Whether to prefer demo connector over simulator
            market_data: Optional market data provider

        Returns:
            BybitDemoConnector if demo credentials available, else OrderSimulator
        """
        from execution.paper.order_simulator import OrderSimulator

        if prefer_demo:
            try:
                connector = BybitDemoConnector.from_env()
                logger.info(
                    "BybitDemoConnectorFactory: Created BybitDemoConnector "
                    "with authenticated demo execution"
                )
                return connector
            except (ValueError, Exception) as e:
                logger.warning(
                    f"BybitDemoConnectorFactory: Demo credentials not available ({e}). "
                    "Falling back to OrderSimulator."
                )

        # Fall back to simulator
        simulator = OrderSimulator(market_data=market_data)
        logger.info(
            "BybitDemoConnectorFactory: Created OrderSimulator "
            "(simulated execution - no real API calls)"
        )
        return simulator

    @staticmethod
    def has_demo_credentials() -> bool:
        """Check if demo credentials are available.

        Returns:
            True if BYBIT_DEMO_API_KEY is set
        """
        import os

        return bool(os.environ.get("BYBIT_DEMO_API_KEY"))


def create_bybit_demo_connector(
    market_data: MarketDataProvider | None = None,
) -> BybitDemoConnector:
    """Create a BybitDemoConnector from environment.

    Convenience function for creating a demo connector.

    Args:
        market_data: Optional market data provider

    Returns:
        Configured BybitDemoConnector

    Raises:
        ValueError: If demo credentials are not available
    """
    return BybitDemoConnector.from_env(market_data=market_data)
