"""Fill storage module for canonical fill persistence.

Provides dedicated fill:* keys in Redis for tracking fill events
and linking them to orders.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class FillStorage:
    """Canonical storage for fills with dedicated fill:* keys.

    Key patterns:
    - fill:<fill_id> - Primary fill data
    - fill:index:by_order - Index for order-based queries
    - fill:index:by_symbol - Index for symbol-based queries
    - fill:index:by_time - Time-ordered index

    Attributes:
        redis_client: Redis client for persistence
        ttl_seconds: TTL for persisted data (default: 7 days)
    """

    # Key patterns
    FILL_KEY_PATTERN = "fill:{fill_id}"
    ORDER_INDEX_KEY = "fill:index:by_order"
    SYMBOL_INDEX_KEY = "fill:index:by_symbol"
    TIME_INDEX_KEY = "fill:index:by_time"

    def __init__(
        self,
        redis_client: Any | None = None,
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize fill storage.

        Args:
            redis_client: Redis client (created if None)
            ttl_seconds: TTL for persisted data
        """
        self._redis = redis_client
        self.ttl_seconds = ttl_seconds

        logger.info(f"FillStorage initialized: ttl={ttl_seconds}s")

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis as redis_lib
                import os

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

    def store_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        signal_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store a fill event with dedicated fill:* key.

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
            Key of stored fill or None if failed
        """
        try:
            redis = self._get_redis()

            # Generate fill ID
            fill_id = str(uuid.uuid4())

            # Build primary key
            key = self.FILL_KEY_PATTERN.format(fill_id=fill_id)

            # Prepare data
            data = {
                "fill_id": fill_id,
                "order_id": order_id,
                "symbol": symbol.upper(),
                "side": side.lower(),
                "quantity": float(quantity),
                "price": float(price),
                "notional_value": float(quantity * price),
                "signal_id": signal_id,
                "correlation_id": correlation_id,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to indices
            timestamp = datetime.now(UTC).timestamp()
            redis.zadd(self.TIME_INDEX_KEY, {key: timestamp})
            redis.expire(self.TIME_INDEX_KEY, self.ttl_seconds)

            # Order index (link fill to order)
            order_key = f"{order_id}:{fill_id}"
            redis.zadd(self.ORDER_INDEX_KEY, {order_key: timestamp})
            redis.expire(self.ORDER_INDEX_KEY, self.ttl_seconds)

            # Symbol index
            symbol_key = f"{symbol.upper()}:{fill_id}"
            redis.zadd(self.SYMBOL_INDEX_KEY, {symbol_key: timestamp})
            redis.expire(self.SYMBOL_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Stored fill: {key} for order {order_id}")
            return key

        except Exception as e:
            logger.error(f"Failed to store fill: {e}")
            return None

    def get_fill(self, fill_id: str) -> dict[str, Any] | None:
        """Get fill by ID.

        Args:
            fill_id: Fill identifier

        Returns:
            Fill data or None if not found
        """
        try:
            redis = self._get_redis()
            key = self.FILL_KEY_PATTERN.format(fill_id=fill_id)
            data = redis.get(key)

            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error(f"Failed to get fill: {e}")
            return None

    def get_fills_by_order(
        self,
        order_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get fills by order ID.

        Args:
            order_id: Order identifier
            limit: Maximum number of fills to return

        Returns:
            List of fill data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get fill IDs from order index
            fill_ids = []
            all_entries = redis.zrevrange(self.ORDER_INDEX_KEY, 0, -1)
            for entry in all_entries:
                if entry.startswith(f"{order_id}:"):
                    fill_id = entry.split(":", 1)[1]
                    fill_ids.append(fill_id)
                    if len(fill_ids) >= limit:
                        break

            # Fetch fill data
            results = []
            for fill_id in fill_ids:
                fill_data = self.get_fill(fill_id)
                if fill_data:
                    results.append(fill_data)

            return results

        except Exception as e:
            logger.error(f"Failed to get fills by order: {e}")
            return []

    def get_fills_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get fills by symbol.

        Args:
            symbol: Trading pair symbol
            limit: Maximum number of fills to return

        Returns:
            List of fill data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get fill IDs from symbol index
            fill_ids = []
            all_entries = redis.zrevrange(self.SYMBOL_INDEX_KEY, 0, -1)
            for entry in all_entries:
                if entry.startswith(f"{symbol.upper()}:"):
                    fill_id = entry.split(":", 1)[1]
                    fill_ids.append(fill_id)
                    if len(fill_ids) >= limit:
                        break

            # Fetch fill data
            results = []
            for fill_id in fill_ids:
                fill_data = self.get_fill(fill_id)
                if fill_data:
                    results.append(fill_data)

            return results

        except Exception as e:
            logger.error(f"Failed to get fills by symbol: {e}")
            return []

    def get_recent_fills(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent fills.

        Args:
            limit: Maximum number of fills to return

        Returns:
            List of fill data dictionaries
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
            logger.error(f"Failed to get recent fills: {e}")
            return []

    def get_order_fill_summary(self, order_id: str) -> dict[str, Any]:
        """Get fill summary for an order.

        Args:
            order_id: Order identifier

        Returns:
            Dictionary with fill summary statistics
        """
        try:
            fills = self.get_fills_by_order(order_id)

            if not fills:
                return {
                    "order_id": order_id,
                    "fill_count": 0,
                    "total_quantity": 0.0,
                    "avg_price": 0.0,
                    "total_notional": 0.0,
                }

            total_quantity = sum(f["quantity"] for f in fills)
            total_notional = sum(f["notional_value"] for f in fills)
            avg_price = total_notional / total_quantity if total_quantity > 0 else 0.0

            return {
                "order_id": order_id,
                "fill_count": len(fills),
                "total_quantity": total_quantity,
                "avg_price": avg_price,
                "total_notional": total_notional,
                "fills": fills,
            }

        except Exception as e:
            logger.error(f"Failed to get fill summary: {e}")
            return {
                "order_id": order_id,
                "error": str(e),
            }

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics.

        Returns:
            Dictionary with storage stats
        """
        try:
            redis = self._get_redis()

            return {
                "total_fills": redis.zcard(self.TIME_INDEX_KEY),
                "order_index_size": redis.zcard(self.ORDER_INDEX_KEY),
                "symbol_index_size": redis.zcard(self.SYMBOL_INDEX_KEY),
                "ttl_seconds": self.ttl_seconds,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total_fills": 0,
                "error": str(e),
            }
