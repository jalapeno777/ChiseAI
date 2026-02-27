"""Outcome persistence layer for paper trading.

Provides canonical persistence of signals, orders, fills, and outcomes
to Redis with structured key patterns for reliable retrieval.

For ST-FINAL-CLOSURE-001: G4 - Persistence Activation in Hot Path
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from execution.paper.models import PaperOrder, PaperTradeResult
    from ml.models.signal_outcome import SignalOutcome
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


class OutcomePersistence:
    """Canonical persistence layer for paper trading outcomes.

    Persists signals, orders, fills, and outcomes to Redis with
    structured key patterns:
    - paper:signal:<timestamp>:<symbol>:<signal_id>
    - paper:order:<timestamp>:<symbol>:<order_id>
    - paper:fill:<timestamp>:<symbol>:<order_id>
    - paper:outcome:<timestamp>:<symbol>:<outcome_id>

    Attributes:
        redis_client: Redis client for persistence
        key_prefix: Prefix for all keys (default: "paper")
        ttl_seconds: TTL for persisted data (default: 7 days)
    """

    # Key patterns
    SIGNAL_KEY_PATTERN = "paper:signal:{timestamp}:{symbol}:{signal_id}"
    ORDER_KEY_PATTERN = "paper:order:{timestamp}:{symbol}:{order_id}"
    FILL_KEY_PATTERN = "paper:fill:{timestamp}:{symbol}:{order_id}"
    OUTCOME_KEY_PATTERN = "paper:outcome:{timestamp}:{symbol}:{outcome_id}"

    # Index keys for querying
    SIGNAL_INDEX_KEY = "paper:index:signals"
    ORDER_INDEX_KEY = "paper:index:orders"
    FILL_INDEX_KEY = "paper:index:fills"
    OUTCOME_INDEX_KEY = "paper:index:outcomes"

    def __init__(
        self,
        redis_client: Any | None = None,
        key_prefix: str = "paper",
        ttl_seconds: int = 604800,  # 7 days
    ):
        """Initialize outcome persistence.

        Args:
            redis_client: Redis client (created if None)
            key_prefix: Prefix for all keys
            ttl_seconds: TTL for persisted data
        """
        self._redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

        logger.info(
            f"OutcomePersistence initialized: prefix={key_prefix}, ttl={ttl_seconds}s"
        )

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

    def persist_signal(
        self,
        signal: Signal,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist a trading signal to Redis.

        Args:
            signal: Trading signal to persist
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted signal or None if failed
        """
        try:
            redis = self._get_redis()

            # Build key
            timestamp = signal.timestamp.strftime("%Y%m%d%H%M%S")
            key = self.SIGNAL_KEY_PATTERN.format(
                timestamp=timestamp,
                symbol=signal.token.upper(),
                signal_id=signal.signal_id,
            )

            # Prepare data
            data = {
                "signal_id": signal.signal_id,
                "token": signal.token,
                "direction": signal.direction.value,
                "confidence": signal.confidence,
                "confidence_percent": signal.confidence_percent,
                "base_score": signal.base_score,
                "timeframe": signal.timeframe,
                "timestamp": signal.timestamp.isoformat(),
                "generation_latency_ms": signal.generation_latency_ms,
                "stop_loss": signal.stop_loss,
                "stop_loss_method": signal.stop_loss_method,
                "metadata": signal.metadata or {},
                "correlation_id": correlation_id,
                "persisted_at": datetime.now(UTC).isoformat(),
            }

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to index
            redis.zadd(self.SIGNAL_INDEX_KEY, {key: signal.timestamp.timestamp()})
            redis.expire(self.SIGNAL_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Persisted signal: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to persist signal: {e}")
            return None

    def persist_order(
        self,
        order: PaperOrder,
        signal_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist an order to Redis.

        Args:
            order: Paper order to persist
            signal_id: Optional associated signal ID
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted order or None if failed
        """
        try:
            redis = self._get_redis()

            # Build key
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            key = self.ORDER_KEY_PATTERN.format(
                timestamp=timestamp,
                symbol=order.symbol.upper(),
                order_id=order.order_id,
            )

            # Prepare data
            data = {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": float(order.quantity),
                "price": float(order.price) if order.price else None,
                "state": order.state.value,
                "filled_quantity": float(order.filled_quantity),
                "avg_fill_price": float(order.avg_fill_price),
                "created_at": order.created_at.isoformat(),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "metadata": order.metadata or {},
                "signal_id": signal_id,
                "correlation_id": correlation_id,
                "persisted_at": datetime.now(UTC).isoformat(),
            }

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to index
            redis.zadd(self.ORDER_INDEX_KEY, {key: datetime.now(UTC).timestamp()})
            redis.expire(self.ORDER_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Persisted order: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to persist order: {e}")
            return None

    def persist_fill(
        self,
        order: PaperOrder,
        signal_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist a fill event to Redis.

        Args:
            order: Filled paper order
            signal_id: Optional associated signal ID
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted fill or None if failed
        """
        try:
            redis = self._get_redis()

            # Build key
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            key = self.FILL_KEY_PATTERN.format(
                timestamp=timestamp,
                symbol=order.symbol.upper(),
                order_id=order.order_id,
            )

            # Prepare data
            data = {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "filled_quantity": float(order.filled_quantity),
                "avg_fill_price": float(order.avg_fill_price),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "metadata": order.metadata or {},
                "signal_id": signal_id,
                "correlation_id": correlation_id,
                "persisted_at": datetime.now(UTC).isoformat(),
            }

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to index
            redis.zadd(self.FILL_INDEX_KEY, {key: datetime.now(UTC).timestamp()})
            redis.expire(self.FILL_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Persisted fill: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to persist fill: {e}")
            return None

    def persist_outcome(
        self,
        outcome: SignalOutcome,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist a signal outcome to Redis.

        Args:
            outcome: Signal outcome to persist
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted outcome or None if failed
        """
        try:
            redis = self._get_redis()

            # Build key
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            key = self.OUTCOME_KEY_PATTERN.format(
                timestamp=timestamp,
                symbol=outcome.symbol.upper(),
                outcome_id=str(outcome.outcome_id),
            )

            # Prepare data
            data = outcome.to_dict()
            data["correlation_id"] = correlation_id
            data["persisted_at"] = datetime.now(UTC).isoformat()

            # Persist to Redis
            redis.set(key, json.dumps(data))
            redis.expire(key, self.ttl_seconds)

            # Add to index
            redis.zadd(self.OUTCOME_INDEX_KEY, {key: datetime.now(UTC).timestamp()})
            redis.expire(self.OUTCOME_INDEX_KEY, self.ttl_seconds)

            logger.debug(f"Persisted outcome: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to persist outcome: {e}")
            return None

    def persist_trade_result(
        self,
        result: PaperTradeResult,
    ) -> dict[str, str | None]:
        """Persist all components of a trade result.

        Args:
            result: Paper trade result containing signal, order, position

        Returns:
            Dictionary with keys of persisted items
        """
        keys = {
            "signal": None,
            "order": None,
            "fill": None,
            "outcome": None,
        }

        correlation_id = result.correlation_id

        # Persist signal
        if result.signal:
            keys["signal"] = self.persist_signal(result.signal, correlation_id)

        # Persist order
        if result.order:
            signal_id = result.signal.signal_id if result.signal else None
            keys["order"] = self.persist_order(result.order, signal_id, correlation_id)

            # Persist fill if order is filled
            if result.order.state.value == "filled":
                keys["fill"] = self.persist_fill(
                    result.order, signal_id, correlation_id
                )

        return keys

    def get_recent_signals(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent persisted signals.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of signals to return

        Returns:
            List of signal data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get keys from index
            keys = redis.zrevrange(self.SIGNAL_INDEX_KEY, 0, limit - 1)

            results = []
            for key in keys:
                # Filter by symbol if specified
                if symbol and symbol.upper() not in key:
                    continue

                data = redis.get(key)
                if data:
                    results.append(json.loads(data))

            return results

        except Exception as e:
            logger.error(f"Failed to get recent signals: {e}")
            return []

    def get_recent_orders(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent persisted orders.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of orders to return

        Returns:
            List of order data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get keys from index
            keys = redis.zrevrange(self.ORDER_INDEX_KEY, 0, limit - 1)

            results = []
            for key in keys:
                # Filter by symbol if specified
                if symbol and symbol.upper() not in key:
                    continue

                data = redis.get(key)
                if data:
                    results.append(json.loads(data))

            return results

        except Exception as e:
            logger.error(f"Failed to get recent orders: {e}")
            return []

    def get_recent_fills(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent persisted fills.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of fills to return

        Returns:
            List of fill data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get keys from index
            keys = redis.zrevrange(self.FILL_INDEX_KEY, 0, limit - 1)

            results = []
            for key in keys:
                # Filter by symbol if specified
                if symbol and symbol.upper() not in key:
                    continue

                data = redis.get(key)
                if data:
                    results.append(json.loads(data))

            return results

        except Exception as e:
            logger.error(f"Failed to get recent fills: {e}")
            return []

    def get_recent_outcomes(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent persisted outcomes.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of outcomes to return

        Returns:
            List of outcome data dictionaries
        """
        try:
            redis = self._get_redis()

            # Get keys from index
            keys = redis.zrevrange(self.OUTCOME_INDEX_KEY, 0, limit - 1)

            results = []
            for key in keys:
                # Filter by symbol if specified
                if symbol and symbol.upper() not in key:
                    continue

                data = redis.get(key)
                if data:
                    results.append(json.loads(data))

            return results

        except Exception as e:
            logger.error(f"Failed to get recent outcomes: {e}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """Get persistence statistics.

        Returns:
            Dictionary with persistence stats
        """
        try:
            redis = self._get_redis()

            return {
                "signal_count": redis.zcard(self.SIGNAL_INDEX_KEY),
                "order_count": redis.zcard(self.ORDER_INDEX_KEY),
                "fill_count": redis.zcard(self.FILL_INDEX_KEY),
                "outcome_count": redis.zcard(self.OUTCOME_INDEX_KEY),
                "ttl_seconds": self.ttl_seconds,
                "key_prefix": self.key_prefix,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "signal_count": 0,
                "order_count": 0,
                "fill_count": 0,
                "outcome_count": 0,
                "error": str(e),
            }

    def health_check(self) -> dict[str, Any]:
        """Check persistence health.

        Returns:
            Health status dictionary
        """
        try:
            redis = self._get_redis()
            redis.ping()
            return {
                "healthy": True,
                "redis_connected": True,
                "stats": self.get_stats(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "redis_connected": False,
                "error": str(e),
            }
