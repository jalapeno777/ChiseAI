"""Symbol Position Registry for Paper Trading.

Implements the one-trade-per-symbol invariant by maintaining a Redis-backed
registry of symbol → position_id mappings with atomic operations.

This module is part of PAPER-2025-001: One-Trade-Per-Symbol Invariant.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SymbolPositionRegistry:
    """Redis-backed registry for symbol → position_id mappings.

    Enforces the one-trade-per-symbol invariant by using atomic Redis
    operations (SET NX) to ensure only one position can be active per
    symbol at any given time.

    Attributes:
        _redis: Redis client instance
        _default_ttl_seconds: Default TTL for registry entries
        _key_prefix: Redis key prefix for all registry entries
        _lock: Async lock for thread-safe operations
    """

    KEY_PREFIX = "paper:symbol_registry"

    def __init__(
        self,
        redis_client: Any | None = None,
        default_ttl_seconds: int = 3600,
    ) -> None:
        """Initialize the symbol position registry.

        Args:
            redis_client: Redis client instance. If None, a new connection
                will be created on first use.
            default_ttl_seconds: Default TTL for registry entries in seconds.
                Default is 1 hour (3600 seconds).
        """
        self._redis = redis_client
        self._owns_redis = redis_client is None
        self._default_ttl_seconds = default_ttl_seconds
        self._lock = asyncio.Lock()

        logger.info(
            f"SymbolPositionRegistry initialized: default_ttl={default_ttl_seconds}s"
        )

    async def _get_redis(self) -> Any:
        """Get or create Redis client.

        Returns:
            Redis client instance

        Raises:
            RedisConnectionError: If unable to connect to Redis
        """
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.Redis(
                host="host.docker.internal",
                port=6380,
                decode_responses=True,
            )
        return self._redis

    def _make_key(self, symbol: str) -> str:
        """Create Redis key for a symbol.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")

        Returns:
            Redis key string
        """
        # Normalize symbol to uppercase and replace special chars
        normalized = symbol.upper().replace("/", "_").replace("-", "_")
        return f"{self.KEY_PREFIX}:{normalized}"

    async def try_acquire_symbol(
        self,
        symbol: str,
        position_id: str,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Attempt to acquire a symbol for a position.

        Uses atomic SET NX (set if not exists) operation to ensure only
        one position can be active per symbol at any time.

        Args:
            symbol: Trading symbol to acquire (e.g., "BTC/USDT")
            position_id: Unique position identifier to associate with symbol
            ttl_seconds: Optional TTL override. Uses default_ttl_seconds if None.

        Returns:
            True if symbol was acquired (no existing position),
            False if symbol is already held by another position.

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        if not symbol or not position_id:
            raise ValueError("symbol and position_id are required")

        redis = await self._get_redis()
        key = self._make_key(symbol)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds

        try:
            # Use SET with NX (only set if not exists) and EX (expire)
            # This is atomic - no race condition possible
            result = await redis.set(key, position_id, nx=True, ex=ttl)

            if result is True:
                logger.info(
                    f"Acquired symbol '{symbol}' for position '{position_id}' "
                    f"(ttl={ttl}s)"
                )
                return True
            else:
                # Key already exists - symbol is held by another position
                existing = await redis.get(key)
                logger.debug(
                    f"Failed to acquire symbol '{symbol}': "
                    f"already held by position '{existing}'"
                )
                return False

        except Exception as e:
            logger.error(f"Redis error acquiring symbol '{symbol}': {e}")
            raise

    async def release_symbol(self, symbol: str, position_id: str) -> bool:
        """Release a symbol when position closes.

        Verifies the position_id matches before releasing to prevent
        accidentally releasing a symbol held by a different position.

        Args:
            symbol: Trading symbol to release (e.g., "BTC/USDT")
            position_id: Position ID that should be holding the symbol

        Returns:
            True if symbol was released successfully,
            False if symbol was not held or held by different position.

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        if not symbol or not position_id:
            raise ValueError("symbol and position_id are required")

        redis = await self._get_redis()
        key = self._make_key(symbol)

        try:
            # Get current holder
            current_holder = await redis.get(key)

            if current_holder is None:
                logger.warning(
                    f"Attempted to release symbol '{symbol}' "
                    f"but it was not held by any position"
                )
                return False

            if current_holder != position_id:
                logger.warning(
                    f"Position ID mismatch releasing symbol '{symbol}': "
                    f"expected '{position_id}', found '{current_holder}'"
                )
                return False

            # Delete the key
            deleted = await redis.delete(key)

            if deleted > 0:
                logger.info(f"Released symbol '{symbol}' from position '{position_id}'")
                return True
            else:
                # Key was deleted between get and delete (race condition)
                logger.warning(
                    f"Race condition releasing symbol '{symbol}': "
                    f"key disappeared between check and delete"
                )
                return False

        except Exception as e:
            logger.error(f"Redis error releasing symbol '{symbol}': {e}")
            raise

    async def get_position_for_symbol(self, symbol: str) -> str | None:
        """Get the current position_id for a symbol.

        Args:
            symbol: Trading symbol to query (e.g., "BTC/USDT")

        Returns:
            Position ID if symbol is held, None otherwise.

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        if not symbol:
            raise ValueError("symbol is required")

        redis = await self._get_redis()
        key = self._make_key(symbol)

        try:
            result = await redis.get(key)
            return result

        except Exception as e:
            logger.error(f"Redis error getting position for symbol '{symbol}': {e}")
            raise

    async def get_all_active_symbols(self) -> dict[str, str]:
        """Get mapping of all active symbols to their position IDs.

        Returns:
            Dictionary mapping symbol → position_id for all active symbols.

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        redis = await self._get_redis()
        pattern = f"{self.KEY_PREFIX}:*"

        try:
            keys = await redis.keys(pattern)
            if not keys:
                return {}

            # Get all values using pipeline
            pipe = redis.pipeline()
            for key in keys:
                pipe.get(key)
            values = await pipe.execute()

            # Build result dictionary
            result = {}
            for key, value in zip(keys, values, strict=True):
                if value is not None:
                    # Extract symbol from key (remove prefix)
                    symbol = key.replace(f"{self.KEY_PREFIX}:", "").replace("_", "/")
                    result[symbol] = value

            return result

        except Exception as e:
            logger.error(f"Redis error getting all active symbols: {e}")
            raise

    async def extend_ttl(self, symbol: str, additional_seconds: int) -> bool:
        """Extend TTL for an active position.

        Args:
            symbol: Trading symbol to extend (e.g., "BTC/USDT")
            additional_seconds: Number of seconds to add to current TTL

        Returns:
            True if TTL was extended, False if symbol not found or expired.

        Raises:
            RedisConnectionError: If Redis connection fails
            ValueError: If additional_seconds is negative
        """
        if not symbol:
            raise ValueError("symbol is required")
        if additional_seconds < 0:
            raise ValueError("additional_seconds must be non-negative")

        redis = await self._get_redis()
        key = self._make_key(symbol)

        try:
            # Get current TTL
            current_ttl = await redis.ttl(key)

            if current_ttl < 0:
                # Key doesn't exist (-2) or has no TTL (-1)
                logger.debug(
                    f"Cannot extend TTL for '{symbol}': key not found or persistent"
                )
                return False

            # Calculate new TTL
            new_ttl = current_ttl + additional_seconds

            # Extend TTL
            result = await redis.expire(key, new_ttl)

            if result:
                logger.info(
                    f"Extended TTL for symbol '{symbol}': {current_ttl}s → {new_ttl}s"
                )
                return True
            else:
                # Key expired between ttl check and expire call
                logger.warning(
                    f"Race condition extending TTL for '{symbol}': "
                    f"key expired during operation"
                )
                return False

        except Exception as e:
            logger.error(f"Redis error extending TTL for symbol '{symbol}': {e}")
            raise

    async def close(self) -> None:
        """Close Redis connection if owned by this registry.

        Should be called when done using the registry to clean up resources.
        """
        if self._owns_redis and self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.info("SymbolPositionRegistry Redis connection closed")

    async def clear_all(self) -> int:
        """Clear all registry entries (for testing/reset).

        Returns:
            Number of keys deleted

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        redis = await self._get_redis()
        pattern = f"{self.KEY_PREFIX}:*"

        try:
            keys = await redis.keys(pattern)
            if not keys:
                return 0

            deleted = await redis.delete(*keys)
            logger.info(f"Cleared {deleted} symbol registry entries")
            return deleted

        except Exception as e:
            logger.error(f"Redis error clearing registry: {e}")
            raise

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dictionary with registry configuration
        """
        return {
            "key_prefix": self.KEY_PREFIX,
            "default_ttl_seconds": self._default_ttl_seconds,
            "owns_redis_connection": self._owns_redis,
        }
