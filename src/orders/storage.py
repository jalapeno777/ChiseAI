"""Order storage module for canonical order persistence.

Provides dedicated order:* keys in Redis for tracking orders
through their lifecycle from creation to fill.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

logger = logging.getLogger(__name__)


class OrderStorage:
    """Canonical storage for orders with dedicated order:* keys.

    Key patterns:
    - order:<order_id> - Primary order data
    - order:index:by_symbol - Index for symbol-based queries
    - order:index:by_signal - Index for signal-based queries
    - order:index:by_time - Time-ordered index

    Attributes:
        redis_client: Redis client for persistence
        ttl_seconds: TTL for persisted data (default: 7 days)
    """

    # Key patterns
    ORDER_KEY_PATTERN = "order:{order_id}"
    SYMBOL_INDEX_KEY = "order:index:by_symbol"
    SIGNAL_INDEX_KEY = "order:index:by_signal"
    TIME_INDEX_KEY = "order:index:by_time"

    def __init__(
        self,
        redis_client: Any | None = None,
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize order storage.

        Args:
            redis_client: Redis client (created if None)
            ttl_seconds: TTL for persisted data
        """
        self._redis = redis_client
        self.ttl_seconds = ttl_seconds

        logger.info(f"OrderStorage initialized: ttl={ttl_seconds}s")

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import os

                import redis as redis_lib

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis = redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
                logger.debug(f"Connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._redis

    def store_order(
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
    ) -> str | None:
        """Store an order with dedicated order:* key.

        Args:
            order_id: Unique order identifier
            symbol: Trading pair symbol
            side: Order side (buy/sell)
            order_type: Order type (market/limit)
            quantity: Order quantity
            price: Order price (None for market orders)
            signal_id: Optional associated signal ID
            correlation_id: Optional correlation ID for tracing
            metadata: Additional order metadata

        Returns:
            Key of stored order or None if failed
        """
        try:
            redis = self._get_redis()

            # Build primary key
            key = self.ORDER_KEY_PATTERN.format(order_id=order_id)

            # Prepare data
            data = {
                "order_id": order_id,
                "symbol": symbol.upper(),
                "side": side.lower(),
                "order_type": order_type.lower(),
                "quantity": float(quantity),
                "price": float(price) if price else None,
                "state": "pending",
                "filled_quantity": 0.0,
                "avg_fill_price": None,
                "signal_id": signal_id,
                "correlation_id": correlation_id,
                "metadata": metadata or {},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to indices
            timestamp = datetime.now(UTC).timestamp()
            redis.zadd(self.TIME_INDEX_KEY, {key: timestamp})
            redis.expire(self.TIME_INDEX_KEY, self.ttl_seconds)

            # Symbol index (sorted by timestamp)
            symbol_key = f"{symbol.upper()}:{order_id}"
            redis.zadd(self.SYMBOL_INDEX_KEY, {symbol_key: timestamp})
            redis.expire(self.SYMBOL_INDEX_KEY, self.ttl_seconds)

            # Signal index if signal_id provided
            if signal_id:
                signal_key = f"{signal_id}:{order_id}"
                redis.zadd(self.SIGNAL_INDEX_KEY, {signal_key: timestamp})
                redis.expire(self.SIGNAL_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Stored order: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to store order: {e}")
            return None

    def update_order_state(
        self,
        order_id: str,
        state: str,
        filled_quantity: float | None = None,
        avg_fill_price: float | None = None,
    ) -> bool:
        """Update order state and fill information.

        Args:
            order_id: Order identifier
            state: New order state (pending, partial, filled, etc.)
            filled_quantity: Optional filled quantity
            avg_fill_price: Optional average fill price

        Returns:
            True if updated successfully
        """
        try:
            redis = self._get_redis()

            key = self.ORDER_KEY_PATTERN.format(order_id=order_id)
            data = redis.get(key)

            if not data:
                logger.warning(f"Order not found: {order_id}")
                return False

            order_data = json.loads(data)
            order_data["state"] = state
            order_data["updated_at"] = datetime.now(UTC).isoformat()

            if filled_quantity is not None:
                order_data["filled_quantity"] = float(filled_quantity)

            if avg_fill_price is not None:
                order_data["avg_fill_price"] = float(avg_fill_price)

            redis.set(key, json.dumps(order_data))
            redis.expire(key, self.ttl_seconds)

            logger.debug(f"Updated order state: {key} -> {state}")
            return True

        except Exception as e:
            logger.error(f"Failed to update order state: {e}")
            return False

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Get order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order data or None if not found
        """
        try:
            redis = self._get_redis()
            key = self.ORDER_KEY_PATTERN.format(order_id=order_id)
            data = redis.get(key)

            if data:
                decoded = json.loads(data)
                if isinstance(decoded, dict):
                    return cast(dict[str, Any], decoded)
            return None

        except Exception as e:
            logger.error(f"Failed to get order: {e}")
            return None

    def get_orders_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get orders by symbol.

        Args:
            symbol: Trading pair symbol
            limit: Maximum number of orders to return

        Returns:
            List of order data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get order IDs from symbol index
            f"{symbol.upper()}:*"
            order_ids = []

            # Use zrange to get recent orders
            all_entries = redis.zrevrange(self.SYMBOL_INDEX_KEY, 0, -1)
            for entry in all_entries:
                if entry.startswith(f"{symbol.upper()}:"):
                    order_id = entry.split(":", 1)[1]
                    order_ids.append(order_id)
                    if len(order_ids) >= limit:
                        break

            # Fetch order data
            results = []
            for order_id in order_ids:
                order_data = self.get_order(order_id)
                if order_data:
                    results.append(order_data)

            return results

        except Exception as e:
            logger.error(f"Failed to get orders by symbol: {e}")
            return []

    def get_orders_by_signal(
        self,
        signal_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get orders by signal ID.

        Args:
            signal_id: Signal identifier
            limit: Maximum number of orders to return

        Returns:
            List of order data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get order IDs from signal index
            order_ids = []
            all_entries = redis.zrevrange(self.SIGNAL_INDEX_KEY, 0, -1)
            for entry in all_entries:
                if entry.startswith(f"{signal_id}:"):
                    order_id = entry.split(":", 1)[1]
                    order_ids.append(order_id)
                    if len(order_ids) >= limit:
                        break

            # Fetch order data
            results = []
            for order_id in order_ids:
                order_data = self.get_order(order_id)
                if order_data:
                    results.append(order_data)

            return results

        except Exception as e:
            logger.error(f"Failed to get orders by signal: {e}")
            return []

    def get_recent_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent orders.

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of order data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get keys from time index
            keys = redis.zrevrange(self.TIME_INDEX_KEY, 0, limit - 1)

            results = []
            for key in keys:
                data = redis.get(key)
                if data:
                    results.append(json.loads(data))

            return results

        except Exception as e:
            logger.error(f"Failed to get recent orders: {e}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics.

        Returns:
            Dictionary with storage stats
        """
        try:
            redis = self._get_redis()

            return {
                "total_orders": redis.zcard(self.TIME_INDEX_KEY),
                "symbol_index_size": redis.zcard(self.SYMBOL_INDEX_KEY),
                "signal_index_size": redis.zcard(self.SIGNAL_INDEX_KEY),
                "ttl_seconds": self.ttl_seconds,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total_orders": 0,
                "error": str(e),
            }
