"""Canary PnL instrumentation for G-Exit-24h gate.

Tracks canary position close events with timestamps and realized PnL.
Provides a query interface to verify the canary has closed positions
and the realized PnL path is functioning correctly within 24-48h.

Keys:
- bmad:chiseai:canary:closes: Sorted set (timestamp as score, position_id as member)
- bmad:chiseai:canary:realized_pnl: Running total of realized PnL

For G-EXIT-24H: Canary Close & PnL Instrumentation
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Redis key constants
CANARY_CLOSES_KEY = "bmad:chiseai:canary:closes"
CANARY_REALIZED_PNL_KEY = "bmad:chiseai:canary:realized_pnl"

# Fallback file path when Redis is unavailable
CANARY_FALLBACK_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "canary_closes.json"
)


class CanaryMetrics:
    """Track canary position close events for G-Exit-24h verification.

    Stores close events in Redis sorted set (timestamp as score) for efficient
    time-window queries. Falls back to file-based logging when Redis is unavailable.

    Attributes:
        _redis: Redis client (sync) for storage
        _redis_async: Redis client (async) for async operations
        _fallback_enabled: Whether to log to file when Redis unavailable
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        redis_async_client: Any | None = None,
        fallback_enabled: bool = True,
    ) -> None:
        """Initialize canary metrics tracker.

        Args:
            redis_client: Synchronous Redis client for storage
            redis_async_client: Async Redis client for async operations
            fallback_enabled: Whether to log to file when Redis unavailable
        """
        self._redis = redis_client
        self._redis_async = redis_async_client
        self._fallback_enabled = fallback_enabled

    def _get_redis(self) -> Any | None:
        """Get sync Redis client, initializing if needed."""
        if self._redis is None:
            try:
                import redis

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
                # Test connection
                self._redis.ping()
                logger.debug("CanaryMetrics connected to Redis (sync)")
            except Exception as e:
                logger.warning(f"CanaryMetrics Redis (sync) unavailable: {e}")
                self._redis = None
        return self._redis

    async def _get_redis_async(self) -> Any | None:
        """Get async Redis client, initializing if needed."""
        if self._redis_async is None:
            try:
                from redis.asyncio import Redis

                redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
                redis_port = int(os.getenv("REDIS_PORT", "6380"))
                self._redis_async = Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                )
                # Test connection
                await self._redis_async.ping()
                logger.debug("CanaryMetrics connected to Redis (async)")
            except Exception as e:
                logger.warning(f"CanaryMetrics Redis (async) unavailable: {e}")
                self._redis_async = None
        return self._redis_async

    def record_canary_close(
        self,
        position_id: str,
        realized_pnl: float,
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record a canary position close event.

        Stores the close event in Redis sorted set with timestamp as score.
        Also increments the running realized PnL total.

        Args:
            position_id: Unique position identifier
            realized_pnl: Realized PnL from the close
            timestamp: Unix timestamp (defaults to current time)
            metadata: Optional additional metadata to store

        Returns:
            True if recorded successfully, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).timestamp()

        redis = self._get_redis()
        if redis is not None:
            try:
                # Add to sorted set (score = timestamp, member = position_id)
                redis.zadd(CANARY_CLOSES_KEY, {position_id: timestamp})

                # Store realized PnL for this close as JSON in a hash
                close_data_key = f"bmad:chiseai:canary:close:{position_id}"
                close_data = {
                    "position_id": position_id,
                    "realized_pnl": realized_pnl,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                }
                redis.hset(
                    close_data_key,
                    mapping={k: json.dumps(v) for k, v in close_data.items()},
                )
                redis.expire(close_data_key, 604800)  # 7 day TTL

                # Increment running realized PnL total
                redis.incrbyfloat(CANARY_REALIZED_PNL_KEY, realized_pnl)

                logger.info(
                    f"Recorded canary close: position_id={position_id}, "
                    f"realized_pnl={realized_pnl:.4f}, timestamp={timestamp}"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to record canary close to Redis: {e}")

        # Fallback: log to file
        if self._fallback_enabled:
            return self._record_canary_close_fallback(
                position_id, realized_pnl, timestamp, metadata
            )

        return False

    async def record_canary_close_async(
        self,
        position_id: str,
        realized_pnl: float,
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Async version of record_canary_close.

        Args:
            position_id: Unique position identifier
            realized_pnl: Realized PnL from the close
            timestamp: Unix timestamp (defaults to current time)
            metadata: Optional additional metadata to store

        Returns:
            True if recorded successfully, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).timestamp()

        redis = await self._get_redis_async()
        if redis is not None:
            try:
                # Add to sorted set (score = timestamp, member = position_id)
                await redis.zadd(CANARY_CLOSES_KEY, {position_id: timestamp})

                # Store realized PnL for this close as JSON in a hash
                close_data_key = f"bmad:chiseai:canary:close:{position_id}"
                close_data = {
                    "position_id": position_id,
                    "realized_pnl": realized_pnl,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                }
                await redis.hset(
                    close_data_key,
                    mapping={k: json.dumps(v) for k, v in close_data.items()},
                )
                await redis.expire(close_data_key, 604800)  # 7 day TTL

                # Increment running realized PnL total
                await redis.incrbyfloat(CANARY_REALIZED_PNL_KEY, realized_pnl)

                logger.info(
                    f"Recorded canary close (async): position_id={position_id}, "
                    f"realized_pnl={realized_pnl:.4f}, timestamp={timestamp}"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to record canary close to Redis (async): {e}")

        # Fallback: log to file
        if self._fallback_enabled:
            return self._record_canary_close_fallback(
                position_id, realized_pnl, timestamp, metadata
            )

        return False

    def _record_canary_close_fallback(
        self,
        position_id: str,
        realized_pnl: float,
        timestamp: float,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Fallback file-based recording when Redis is unavailable.

        Args:
            position_id: Unique position identifier
            realized_pnl: Realized PnL from the close
            timestamp: Unix timestamp
            metadata: Optional additional metadata

        Returns:
            True if recorded successfully, False otherwise
        """
        try:
            import os
            from pathlib import Path

            # Ensure data directory exists
            data_dir = Path(CANARY_FALLBACK_FILE).parent
            data_dir.mkdir(parents=True, exist_ok=True)

            # Load existing data
            closes = []
            if os.path.exists(CANARY_FALLBACK_FILE):
                try:
                    with open(CANARY_FALLBACK_FILE) as f:
                        closes = json.load(f)
                except (OSError, json.JSONDecodeError):
                    closes = []

            # Add new close event
            closes.append(
                {
                    "position_id": position_id,
                    "realized_pnl": realized_pnl,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                }
            )

            # Write back
            with open(CANARY_FALLBACK_FILE, "w") as f:
                json.dump(closes, f, indent=2)

            logger.warning(
                f"CanaryMetrics: Redis unavailable, recorded close to fallback file: "
                f"position_id={position_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to record canary close to fallback file: {e}")
            return False

    def get_canary_close_count(self, since_hours: int = 24) -> int:
        """Get count of canary closes within time window.

        Args:
            since_hours: Number of hours to look back (default 24)

        Returns:
            Number of canary closes in the time window
        """
        redis = self._get_redis()
        if redis is not None:
            try:
                cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)
                count = redis.zcount(CANARY_CLOSES_KEY, cutoff, "+inf")
                logger.debug(f"Canary close count (since_hours={since_hours}): {count}")
                return count
            except Exception as e:
                logger.error(f"Failed to get canary close count from Redis: {e}")

        # Fallback: read from file
        return self._get_canary_close_count_fallback(since_hours)

    async def get_canary_close_count_async(self, since_hours: int = 24) -> int:
        """Async version of get_canary_close_count.

        Args:
            since_hours: Number of hours to look back (default 24)

        Returns:
            Number of canary closes in the time window
        """
        redis = await self._get_redis_async()
        if redis is not None:
            try:
                cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)
                count = await redis.zcount(CANARY_CLOSES_KEY, cutoff, "+inf")
                logger.debug(
                    f"Canary close count (async, since_hours={since_hours}): {count}"
                )
                return count
            except Exception as e:
                logger.error(
                    f"Failed to get canary close count from Redis (async): {e}"
                )

        # Fallback: read from file
        return self._get_canary_close_count_fallback(since_hours)

    def _get_canary_close_count_fallback(self, since_hours: int) -> int:
        """Fallback file-based close count when Redis is unavailable.

        Args:
            since_hours: Number of hours to look back

        Returns:
            Number of canary closes in the time window
        """
        try:
            if not os.path.exists(CANARY_FALLBACK_FILE):
                return 0

            cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)

            with open(CANARY_FALLBACK_FILE) as f:
                closes = json.load(f)

            count = sum(1 for c in closes if c.get("timestamp", 0) >= cutoff)
            logger.debug(
                f"Canary close count (fallback, since_hours={since_hours}): {count}"
            )
            return count

        except Exception as e:
            logger.error(f"Failed to get canary close count from fallback file: {e}")
            return 0

    def get_realized_pnl(self, since_hours: int = 24) -> float:
        """Get realized PnL from canary closes within time window.

        Note: This calculates from individual close records rather than
        using the running total, to provide time-window-specific PnL.

        Args:
            since_hours: Number of hours to look back (default 24)

        Returns:
            Total realized PnL in the time window
        """
        redis = self._get_redis()
        if redis is not None:
            try:
                cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)

                # Get all close events since cutoff
                close_ids = redis.zrangebyscore(CANARY_CLOSES_KEY, cutoff, "+inf")

                total_pnl = 0.0
                for position_id in close_ids:
                    close_data_key = f"bmad:chiseai:canary:close:{position_id}"
                    close_data = redis.hgetall(close_data_key)
                    if close_data and "realized_pnl" in close_data:
                        pnl = float(json.loads(close_data["realized_pnl"]))
                        total_pnl += pnl

                logger.debug(
                    f"Canary realized PnL (since_hours={since_hours}): {total_pnl}"
                )
                return total_pnl
            except Exception as e:
                logger.error(f"Failed to get realized PnL from Redis: {e}")

        # Fallback: calculate from file
        return self._get_realized_pnl_fallback(since_hours)

    async def get_realized_pnl_async(self, since_hours: int = 24) -> float:
        """Async version of get_realized_pnl.

        Args:
            since_hours: Number of hours to look back (default 24)

        Returns:
            Total realized PnL in the time window
        """
        redis = await self._get_redis_async()
        if redis is not None:
            try:
                cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)

                # Get all close events since cutoff
                close_ids = await redis.zrangebyscore(CANARY_CLOSES_KEY, cutoff, "+inf")

                total_pnl = 0.0
                for position_id in close_ids:
                    close_data_key = f"bmad:chiseai:canary:close:{position_id}"
                    close_data = await redis.hgetall(close_data_key)
                    if close_data and "realized_pnl" in close_data:
                        pnl = float(json.loads(close_data["realized_pnl"]))
                        total_pnl += pnl

                logger.debug(
                    f"Canary realized PnL (async, since_hours={since_hours}): {total_pnl}"
                )
                return total_pnl
            except Exception as e:
                logger.error(f"Failed to get realized PnL from Redis (async): {e}")

        # Fallback: calculate from file
        return self._get_realized_pnl_fallback(since_hours)

    def _get_realized_pnl_fallback(self, since_hours: int) -> float:
        """Fallback file-based realized PnL calculation.

        Args:
            since_hours: Number of hours to look back

        Returns:
            Total realized PnL in the time window
        """
        try:
            if not os.path.exists(CANARY_FALLBACK_FILE):
                return 0.0

            cutoff = datetime.now(UTC).timestamp() - (since_hours * 3600)

            with open(CANARY_FALLBACK_FILE) as f:
                closes = json.load(f)

            total_pnl = sum(
                c.get("realized_pnl", 0.0)
                for c in closes
                if c.get("timestamp", 0) >= cutoff
            )

            logger.debug(
                f"Canary realized PnL (fallback, since_hours={since_hours}): {total_pnl}"
            )
            return total_pnl

        except Exception as e:
            logger.error(f"Failed to get realized PnL from fallback file: {e}")
            return 0.0

    def get_running_realized_pnl(self) -> float:
        """Get the running total of realized PnL (all-time).

        Returns:
            Running total realized PnL
        """
        redis = self._get_redis()
        if redis is not None:
            try:
                value = redis.get(CANARY_REALIZED_PNL_KEY)
                if value is not None:
                    return float(value)
            except Exception as e:
                logger.error(f"Failed to get running realized PnL from Redis: {e}")

        # Fallback: calculate from file
        try:
            if not os.path.exists(CANARY_FALLBACK_FILE):
                return 0.0

            with open(CANARY_FALLBACK_FILE) as f:
                closes = json.load(f)

            return sum(c.get("realized_pnl", 0.0) for c in closes)

        except Exception as e:
            logger.error(f"Failed to get running realized PnL from fallback file: {e}")
            return 0.0

    def clear_canary_data(self) -> bool:
        """Clear all canary metrics data (for testing).

        Returns:
            True if cleared successfully, False otherwise
        """
        redis = self._get_redis()
        if redis is not None:
            try:
                # Get all close IDs to clean up individual records
                close_ids = redis.zrange(CANARY_CLOSES_KEY, 0, -1)
                for position_id in close_ids:
                    close_data_key = f"bmad:chiseai:canary:close:{position_id}"
                    redis.delete(close_data_key)

                redis.delete(CANARY_CLOSES_KEY)
                redis.delete(CANARY_REALIZED_PNL_KEY)

                logger.info("Cleared all canary metrics data from Redis")
                return True
            except Exception as e:
                logger.error(f"Failed to clear canary data from Redis: {e}")

        # Fallback: clear file
        try:
            if os.path.exists(CANARY_FALLBACK_FILE):
                os.remove(CANARY_FALLBACK_FILE)
                logger.info("Cleared canary metrics data from fallback file")
            return True
        except Exception as e:
            logger.error(f"Failed to clear canary data from fallback file: {e}")
            return False


# Singleton instance for convenience
_default_instance: CanaryMetrics | None = None


def get_canary_metrics(
    redis_client: Any | None = None,
    redis_async_client: Any | None = None,
) -> CanaryMetrics:
    """Get or create the default CanaryMetrics instance.

    Args:
        redis_client: Synchronous Redis client
        redis_async_client: Async Redis client

    Returns:
        CanaryMetrics instance
    """
    global _default_instance
    if _default_instance is None:
        _default_instance = CanaryMetrics(
            redis_client=redis_client,
            redis_async_client=redis_async_client,
        )
    return _default_instance
