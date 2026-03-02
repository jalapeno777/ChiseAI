"""Order-Fill Manager for unified order and fill lifecycle management.

Provides high-level operations for creating orders, recording fills,
and maintaining the signal→order→fill→outcome chain.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

from __future__ import annotations

import logging
from typing import Any

from orders.fill_storage import FillStorage
from orders.storage import OrderStorage

logger = logging.getLogger(__name__)


class OrderFillManager:
    """Manages the complete order and fill lifecycle.

    Provides unified interface for:
    - Creating orders with signal linkage
    - Recording fills with order linkage
    - Querying the signal→order→fill chain
    - Maintaining consistency across storage layers

    Attributes:
        order_storage: OrderStorage instance
        fill_storage: FillStorage instance
    """

    def __init__(
        self,
        order_storage: OrderStorage | None = None,
        fill_storage: FillStorage | None = None,
        redis_client: Any | None = None,
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize order-fill manager.

        Args:
            order_storage: OrderStorage instance (created if None)
            fill_storage: FillStorage instance (created if None)
            redis_client: Redis client (passed to storage if they need creation)
            ttl_seconds: TTL for persisted data
        """
        self.order_storage = order_storage or OrderStorage(
            redis_client=redis_client,
            ttl_seconds=ttl_seconds,
        )
        self.fill_storage = fill_storage or FillStorage(
            redis_client=redis_client,
            ttl_seconds=ttl_seconds,
        )

        logger.info("OrderFillManager initialized")

    def create_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None,
        signal_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new order and store it.

        Args:
            order_id: Unique order identifier
            symbol: Trading pair symbol
            side: Order side (buy/sell)
            order_type: Order type (market/limit)
            quantity: Order quantity
            price: Order price (None for market orders)
            signal_id: Optional associated signal ID for signal→order linkage
            correlation_id: Optional correlation ID for tracing
            metadata: Additional order metadata

        Returns:
            Dictionary with order_key and order_data
        """
        # Store the order
        order_key = self.order_storage.store_order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            signal_id=signal_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )

        if not order_key:
            logger.error(f"Failed to create order: {order_id}")
            return {"success": False, "error": "Failed to store order"}

        # Retrieve stored data
        order_data = self.order_storage.get_order(order_id)

        logger.info(f"Created order: {order_id} (signal={signal_id})")

        return {
            "success": True,
            "order_key": order_key,
            "order_id": order_id,
            "order_data": order_data,
        }

    def record_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        signal_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a fill for an order.

        Args:
            order_id: Associated order identifier
            symbol: Trading pair symbol
            side: Fill side (buy/sell)
            quantity: Filled quantity
            price: Fill price
            signal_id: Optional associated signal ID
            correlation_id: Optional correlation ID for tracing
            metadata: Additional fill metadata

        Returns:
            Dictionary with fill_key, fill_data, and order_update status
        """
        # Store the fill
        fill_key = self.fill_storage.store_fill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            signal_id=signal_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )

        if not fill_key:
            logger.error(f"Failed to record fill for order: {order_id}")
            return {"success": False, "error": "Failed to store fill"}

        # Update order state
        fill_data = self.fill_storage.get_fill(fill_key.split(":")[1])

        # Get current fills for this order to calculate totals
        fill_summary = self.fill_storage.get_order_fill_summary(order_id)
        total_filled = fill_summary.get("total_quantity", 0.0)
        avg_price = fill_summary.get("avg_price", 0.0)

        # Determine new state
        order_data = self.order_storage.get_order(order_id)
        if order_data:
            order_quantity = order_data.get("quantity", 0.0)
            if total_filled >= order_quantity:
                new_state = "filled"
            elif total_filled > 0:
                new_state = "partial"
            else:
                new_state = "pending"

            # Update order with fill info
            self.order_storage.update_order_state(
                order_id=order_id,
                state=new_state,
                filled_quantity=total_filled,
                avg_fill_price=avg_price,
            )

        logger.info(
            f"Recorded fill for order {order_id}: "
            f"qty={quantity}, price={price}, total_filled={total_filled}"
        )

        return {
            "success": True,
            "fill_key": fill_key,
            "fill_data": fill_data,
            "order_updated": True,
            "order_state": new_state if order_data else None,
            "total_filled": total_filled,
            "avg_price": avg_price,
        }

    def get_order_chain(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        """Get the complete order→fill chain for an order.

        Args:
            order_id: Order identifier

        Returns:
            Dictionary with order, fills, and summary
        """
        order_data = self.order_storage.get_order(order_id)
        fills = self.fill_storage.get_fills_by_order(order_id)
        fill_summary = self.fill_storage.get_order_fill_summary(order_id)

        return {
            "order_id": order_id,
            "order": order_data,
            "fills": fills,
            "fill_count": len(fills),
            "fill_summary": fill_summary,
            "complete": (
                fill_summary.get("total_quantity", 0.0)
                >= order_data.get("quantity", 0.0)
                if order_data
                else False
            ),
        }

    def get_signal_chain(
        self,
        signal_id: str,
    ) -> dict[str, Any]:
        """Get the complete signal→order→fill chain for a signal.

        Args:
            signal_id: Signal identifier

        Returns:
            Dictionary with signal linkage to orders and fills
        """
        orders = self.order_storage.get_orders_by_signal(signal_id)

        order_chains = []
        for order in orders:
            order_id = order.get("order_id")
            chain = self.get_order_chain(order_id)
            order_chains.append(chain)

        total_fills = sum(chain["fill_count"] for chain in order_chains)
        complete_orders = sum(1 for chain in order_chains if chain["complete"])

        return {
            "signal_id": signal_id,
            "orders": orders,
            "order_count": len(orders),
            "order_chains": order_chains,
            "total_fills": total_fills,
            "complete_orders": complete_orders,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics.

        Returns:
            Dictionary with order and fill statistics
        """
        order_stats = self.order_storage.get_stats()
        fill_stats = self.fill_storage.get_stats()

        return {
            "orders": order_stats,
            "fills": fill_stats,
            "total_orders": order_stats.get("total_orders", 0),
            "total_fills": fill_stats.get("total_fills", 0),
            "fills_per_order": (
                fill_stats.get("total_fills", 0) / order_stats.get("total_orders", 1)
                if order_stats.get("total_orders", 0) > 0
                else 0.0
            ),
        }
