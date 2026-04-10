"""Outcome persistence layer for paper trading.

Provides canonical persistence of signals, orders, fills, and outcomes
to Redis with structured key patterns for reliable retrieval.
Also syncs outcomes to PostgreSQL for long-term storage and analytics.

For ST-FINAL-CLOSURE-001: G4 - Persistence Activation in Hot Path
For HOTFIX-REDIS-PSQL-SYNC-001: Add PostgreSQL sync for paper trading outcomes
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.paper.models import PaperOrder, PaperTradeResult
    from ml.models.signal_outcome import SignalOutcome
    from signal_generation.models import Signal

logger = logging.getLogger(__name__)


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime.

    Args:
        ts: ISO format timestamp string or None

    Returns:
        datetime object or None
    """
    if not ts:
        return None
    try:
        # Handle both Z suffix and +00:00 timezone
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


class OutcomePersistence:
    """Canonical persistence layer for paper trading outcomes.

    Persists signals, orders, fills, and outcomes to Redis with
    structured key patterns:
    - paper:signal:<timestamp>:<symbol>:<signal_id>
    - paper:order:<timestamp>:<symbol>:<order_id>
    - paper:fill:<timestamp>:<symbol>:<order_id>
    - paper:outcome:<timestamp>:<symbol>:<outcome_id>

    Also syncs outcomes to PostgreSQL for long-term storage.

    Attributes:
        redis_client: Redis client for persistence
        key_prefix: Prefix for all keys (default: "paper")
        ttl_seconds: TTL for persisted data (default: 7 days)
        db_pool: Optional PostgreSQL connection pool for sync
        enable_postgres_sync: Whether to sync outcomes to PostgreSQL
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

    # Stream keys for event-driven consumption (REPO-PAPER-003-S4)
    SIGNAL_STREAM_KEY = "paper:signals:stream"

    def __init__(
        self,
        redis_client: Any | None = None,
        key_prefix: str = "paper",
        ttl_seconds: int = 604800,  # 7 days
        db_pool: Any | None = None,
        enable_postgres_sync: bool = True,
    ):
        """Initialize outcome persistence.

        Args:
            redis_client: Redis client (created if None)
            key_prefix: Prefix for all keys
            ttl_seconds: TTL for persisted data
            db_pool: Optional PostgreSQL connection pool for sync
            enable_postgres_sync: Whether to sync outcomes to PostgreSQL
        """
        self._redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
        self._db_pool = db_pool
        self.enable_postgres_sync = enable_postgres_sync
        self._owned_pool = False

        logger.info(
            f"OutcomePersistence initialized: prefix={key_prefix}, ttl={ttl_seconds}s, "
            f"postgres_sync={enable_postgres_sync}"
        )

    def _get_redis(self) -> Any:
        """Get or create Redis client."""
        if self._redis is None:
            try:
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

    async def _get_db_pool(self) -> Any:
        """Get or create PostgreSQL connection pool."""
        if self._db_pool is None and self.enable_postgres_sync:
            try:
                import asyncpg

                db_host = os.getenv("DB_HOST", "host.docker.internal")
                db_port = int(os.getenv("DB_PORT", "5434"))
                db_name = os.getenv("DB_NAME", "chiseai")
                db_user = os.getenv("DB_USER", "chiseai")
                db_pass = os.getenv("DB_PASSWORD", "chiseai")

                self._db_pool = await asyncpg.create_pool(
                    host=db_host,
                    port=db_port,
                    database=db_name,
                    user=db_user,
                    password=db_pass,
                    min_size=1,
                    max_size=5,
                )
                self._owned_pool = True
                logger.debug(f"Connected to PostgreSQL at {db_host}:{db_port}")
            except Exception as e:
                logger.warning(f"Failed to connect to PostgreSQL, sync disabled: {e}")
                self.enable_postgres_sync = False
        return self._db_pool

    async def _sync_outcome_to_postgres(self, outcome: SignalOutcome) -> bool:
        """Sync an outcome to PostgreSQL.

        Args:
            outcome: Signal outcome to sync

        Returns:
            True if synced successfully, False otherwise
        """
        if not self.enable_postgres_sync:
            return False

        try:
            pool = await self._get_db_pool()
            if pool is None:
                return False

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO signal_outcomes (
                        outcome_id, signal_id, order_id, symbol, token, side, direction,
                        fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                        status, created_at, metadata,
                        entry_price, exit_price, entry_time, exit_time,
                        leverage, entry_reason, position_size,
                        execution_venue, execution_mode, execution_source, venue_metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                              $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27)
                    ON CONFLICT (outcome_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        exit_price = EXCLUDED.exit_price,
                        exit_time = EXCLUDED.exit_time,
                        pnl = EXCLUDED.pnl,
                        metadata = EXCLUDED.metadata,
                        execution_venue = EXCLUDED.execution_venue,
                        execution_mode = EXCLUDED.execution_mode,
                        execution_source = EXCLUDED.execution_source,
                        venue_metadata = EXCLUDED.venue_metadata
                    """,
                    str(outcome.outcome_id),
                    str(outcome.signal_id) if outcome.signal_id else None,
                    outcome.order_id,
                    outcome.symbol,
                    outcome.token,
                    outcome.side,
                    outcome.direction,
                    float(outcome.fill_price) if outcome.fill_price else None,
                    float(outcome.fill_quantity) if outcome.fill_quantity else None,
                    outcome.fill_timestamp,
                    outcome.outcome_type.value if outcome.outcome_type else "unknown",
                    float(outcome.pnl) if outcome.pnl else None,
                    float(outcome.fee) if outcome.fee else None,
                    outcome.status.value if outcome.status else "filled",
                    outcome.created_at,
                    json.dumps(outcome.metadata) if outcome.metadata else None,
                    float(outcome.entry_price) if outcome.entry_price else None,
                    float(outcome.exit_price) if outcome.exit_price else None,
                    outcome.entry_time,
                    outcome.exit_time,
                    float(outcome.leverage) if outcome.leverage else 1.0,
                    outcome.entry_reason,
                    float(outcome.position_size) if outcome.position_size else None,
                    # PAPER-FORENSIC-001: Provenance fields for audit trail
                    outcome.execution_venue if outcome.execution_venue else None,
                    outcome.execution_mode if outcome.execution_mode else None,
                    outcome.execution_source if outcome.execution_source else None,
                    (
                        json.dumps(outcome.venue_metadata)
                        if outcome.venue_metadata
                        else None
                    ),
                )

            logger.debug(f"Synced outcome {outcome.outcome_id} to PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to sync outcome to PostgreSQL: {e}")
            return False

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

            # Append to stream for event-driven consumption (XREADGROUP)
            redis.xadd(
                self.SIGNAL_STREAM_KEY,
                {"data": json.dumps(data)},
            )

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
            # Extract exchange IDs from first fill if available
            exchange_order_id = None
            exchange_fill_id = None
            if order.fills:
                first_fill = order.fills[0]
                exchange_order_id = getattr(first_fill, "exchange_order_id", None)
                exchange_fill_id = getattr(first_fill, "exchange_fill_id", None)

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
                # Native exchange IDs for reconciliation
                "exchange_order_id": exchange_order_id,
                "exchange_fill_id": exchange_fill_id,
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
        """Persist a signal outcome to Redis (sync version).

        Note: This only persists to Redis. For PostgreSQL sync, use
        persist_outcome_async() instead.

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

    async def persist_outcome_async(
        self,
        outcome: SignalOutcome,
        correlation_id: str | None = None,
    ) -> str | None:
        """Persist a signal outcome to Redis and sync to PostgreSQL.

        This is the async version that also syncs to PostgreSQL for
        long-term storage and analytics.

        Args:
            outcome: Signal outcome to persist
            correlation_id: Optional correlation ID for tracing

        Returns:
            Key of persisted outcome or None if failed
        """
        # First persist to Redis (sync)
        key = self.persist_outcome(outcome, correlation_id)
        if key is None:
            return None

        # Then sync to PostgreSQL (async)
        if self.enable_postgres_sync:
            await self._sync_outcome_to_postgres(outcome)

        return key

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
                "postgres_sync_enabled": self.enable_postgres_sync,
                "stats": self.get_stats(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "redis_connected": False,
                "error": str(e),
            }

    async def sync_outcomes_from_redis(
        self,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Sync all outcomes from Redis to PostgreSQL.

        This is useful for backfilling PostgreSQL with existing Redis data.

        Args:
            batch_size: Number of outcomes to sync per batch

        Returns:
            Dictionary with sync statistics
        """
        if not self.enable_postgres_sync:
            return {
                "synced": 0,
                "failed": 0,
                "skipped": True,
                "reason": "PostgreSQL sync disabled",
            }

        stats = {"synced": 0, "failed": 0, "total": 0}
        redis = self._get_redis()

        try:
            # Get all outcome keys from the index
            keys = redis.zrange(self.OUTCOME_INDEX_KEY, 0, -1)
            stats["total"] = len(keys)

            logger.info(
                f"Starting sync of {len(keys)} outcomes from Redis to PostgreSQL"
            )

            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i : i + batch_size]
                batch_synced = 0
                batch_failed = 0

                for key in batch_keys:
                    try:
                        data = redis.get(key)
                        if not data:
                            continue

                        outcome_data = json.loads(data)

                        # Sync to PostgreSQL
                        pool = await self._get_db_pool()
                        if pool is None:
                            batch_failed += 1
                            continue

                        async with pool.acquire() as conn:
                            await conn.execute(
                                """
                                INSERT INTO signal_outcomes (
                                    outcome_id, signal_id, order_id, symbol, token, side, direction,
                                    fill_price, fill_quantity, fill_timestamp, outcome_type, pnl, fee,
                                    status, created_at, metadata,
                                    entry_price, exit_price, entry_time, exit_time,
                                    leverage, entry_reason, position_size,
                                    execution_venue, execution_mode, execution_source, venue_metadata
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                                          $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27)
                                ON CONFLICT (outcome_id) DO NOTHING
                                """,
                                outcome_data.get("outcome_id"),
                                outcome_data.get("signal_id"),
                                outcome_data.get("order_id"),
                                outcome_data.get("symbol"),
                                outcome_data.get("token"),
                                outcome_data.get("side"),
                                outcome_data.get("direction"),
                                (
                                    float(outcome_data["fill_price"])
                                    if outcome_data.get("fill_price")
                                    else None
                                ),
                                (
                                    float(outcome_data["fill_quantity"])
                                    if outcome_data.get("fill_quantity")
                                    else None
                                ),
                                _parse_timestamp(outcome_data.get("fill_timestamp")),
                                outcome_data.get("outcome_type", "unknown"),
                                (
                                    float(outcome_data["pnl"])
                                    if outcome_data.get("pnl")
                                    else None
                                ),
                                (
                                    float(outcome_data["fee"])
                                    if outcome_data.get("fee")
                                    else None
                                ),
                                outcome_data.get("status", "filled"),
                                _parse_timestamp(outcome_data.get("created_at")),
                                (
                                    json.dumps(outcome_data.get("metadata"))
                                    if outcome_data.get("metadata")
                                    else None
                                ),
                                (
                                    float(outcome_data["entry_price"])
                                    if outcome_data.get("entry_price")
                                    else None
                                ),
                                (
                                    float(outcome_data["exit_price"])
                                    if outcome_data.get("exit_price")
                                    else None
                                ),
                                _parse_timestamp(outcome_data.get("entry_time")),
                                _parse_timestamp(outcome_data.get("exit_time")),
                                (
                                    float(outcome_data["leverage"])
                                    if outcome_data.get("leverage")
                                    else 1.0
                                ),
                                outcome_data.get("entry_reason"),
                                (
                                    float(outcome_data["position_size"])
                                    if outcome_data.get("position_size")
                                    else None
                                ),
                                # PAPER-FORENSIC-001: Provenance fields for audit trail
                                outcome_data.get("execution_venue"),
                                outcome_data.get("execution_mode"),
                                outcome_data.get("execution_source"),
                                (
                                    json.dumps(outcome_data.get("venue_metadata"))
                                    if outcome_data.get("venue_metadata")
                                    else None
                                ),
                            )

                        batch_synced += 1

                    except Exception as e:
                        logger.error(f"Failed to sync outcome {key}: {e}")
                        batch_failed += 1

                stats["synced"] += batch_synced
                stats["failed"] += batch_failed

                logger.info(
                    f"Synced batch {i // batch_size + 1}: "
                    f"{batch_synced} synced, {batch_failed} failed"
                )

            logger.info(
                f"Sync complete: {stats['synced']} synced, {stats['failed']} failed, "
                f"{stats['total']} total"
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to sync outcomes from Redis: {e}")
            stats["error"] = str(e)
            return stats

    async def close(self) -> None:
        """Close the PostgreSQL connection pool if owned."""
        if self._owned_pool and self._db_pool:
            await self._db_pool.close()
            self._db_pool = None
            logger.info("PostgreSQL connection pool closed")
