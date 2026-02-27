"""Unified persistence layer integrating all storage components.

Provides a single interface for persisting signals, orders, fills, and outcomes
with proper linkage across the signal→order→fill→outcome chain.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

from __future__ import annotations

import logging
from typing import Any

from execution.persistence.outcome_persistence import OutcomePersistence
from orders import OrderFillManager

logger = logging.getLogger(__name__)


class UnifiedPersistence:
    """Unified persistence layer for all trading data.

    Integrates:
    - OutcomePersistence (signals, outcomes)
    - OrderFillManager (orders, fills)

    Provides canonical storage with proper linkage:
    signal → order → fill → outcome

    Key patterns:
    - paper:signal:* - Signal data (via OutcomePersistence)
    - paper:outcome:* - Outcome data (via OutcomePersistence)
    - order:* - Order data (via OrderFillManager)
    - fill:* - Fill data (via OrderFillManager)

    Attributes:
        outcome_persistence: OutcomePersistence instance
        order_fill_manager: OrderFillManager instance
    """

    def __init__(
        self,
        outcome_persistence: OutcomePersistence | None = None,
        order_fill_manager: OrderFillManager | None = None,
        redis_client: Any | None = None,
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize unified persistence.

        Args:
            outcome_persistence: OutcomePersistence instance (created if None)
            order_fill_manager: OrderFillManager instance (created if None)
            redis_client: Redis client (passed to components if needed)
            ttl_seconds: TTL for persisted data
        """
        self.outcome_persistence = outcome_persistence or OutcomePersistence(
            redis_client=redis_client,
            ttl_seconds=ttl_seconds,
        )
        self.order_fill_manager = order_fill_manager or OrderFillManager(
            redis_client=redis_client,
            ttl_seconds=ttl_seconds,
        )

        logger.info("UnifiedPersistence initialized")

    def persist_signal(
        self,
        signal: Any,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist a signal.

        Args:
            signal: Trading signal to persist
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted signal or None if failed
        """
        return self.outcome_persistence.persist_signal(signal, correlation_id)

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
        """Create and persist an order.

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
        return self.order_fill_manager.create_order(
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
        return self.order_fill_manager.record_fill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            signal_id=signal_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def persist_outcome(
        self,
        outcome: Any,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist an outcome.

        Args:
            outcome: Signal outcome to persist
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted outcome or None if failed
        """
        return self.outcome_persistence.persist_outcome(outcome, correlation_id)

    def get_complete_chain(
        self,
        signal_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Get the complete signal→order→fill→outcome chain.

        Args:
            signal_id: Signal identifier (optional if order_id provided)
            order_id: Order identifier (optional if signal_id provided)

        Returns:
            Dictionary with complete chain data
        """
        if not signal_id and not order_id:
            return {"error": "Must provide signal_id or order_id"}

        result = {
            "signal": None,
            "orders": [],
            "fills": [],
            "outcomes": [],
        }

        # If we have a signal_id, get signal data and related orders
        if signal_id:
            signal_chain = self.order_fill_manager.get_signal_chain(signal_id)
            result["signal_id"] = signal_id
            result["orders"] = signal_chain.get("orders", [])
            result["order_chains"] = signal_chain.get("order_chains", [])

            # Collect all fills
            for chain in signal_chain.get("order_chains", []):
                result["fills"].extend(chain.get("fills", []))

        # If we have an order_id, get order-specific chain
        if order_id:
            order_chain = self.order_fill_manager.get_order_chain(order_id)
            result["order_id"] = order_id
            result["order"] = order_chain.get("order")
            result["order_fills"] = order_chain.get("fills", [])

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics from all storage layers.

        Returns:
            Dictionary with complete statistics
        """
        outcome_stats = self.outcome_persistence.get_stats()
        order_fill_stats = self.order_fill_manager.get_stats()

        return {
            "outcomes": outcome_stats,
            "orders_and_fills": order_fill_stats,
            "total_signals": outcome_stats.get("signal_count", 0),
            "total_outcomes": outcome_stats.get("outcome_count", 0),
            "total_orders": order_fill_stats.get("total_orders", 0),
            "total_fills": order_fill_stats.get("total_fills", 0),
        }

    def health_check(self) -> dict[str, Any]:
        """Check health of all persistence components.

        Returns:
            Health status dictionary
        """
        outcome_health = self.outcome_persistence.health_check()

        return {
            "healthy": outcome_health.get("healthy", False),
            "outcome_persistence": outcome_health,
            "order_fill_manager": {"initialized": True},
        }
