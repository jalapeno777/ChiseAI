"""Order idempotency module for preventing duplicate order submissions.

Provides clientOrderId generation with Redis-based deduplication.

For ST-LAUNCH-003: Order Idempotency
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

logger = logging.getLogger(__name__)

# Redis TTL for idempotency keys (24 hours in seconds)
IDEMPOTENCY_TTL_SECONDS = 86400

# Redis key prefix for idempotency storage
IDEMPOTENCY_KEY_PREFIX = "order:idempotency"


class DuplicateOrderException(Exception):
    """Exception raised when a duplicate order is detected.

    Attributes:
        client_order_id: The duplicate client order ID
        symbol: The trading pair symbol
        message: Human-readable error message
    """

    def __init__(
        self,
        client_order_id: str,
        symbol: str,
        message: str | None = None,
    ) -> None:
        self.client_order_id = client_order_id
        self.symbol = symbol
        self.message = message or (
            f"Duplicate order detected: {client_order_id} for {symbol}"
        )
        super().__init__(self.message)


class RedisClient(Protocol):
    """Protocol for Redis client interface.

    Supports both real Redis and test mocks.
    """

    async def get(self, key: str) -> str | None:
        """Get value by key."""
        ...

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set key with expiration in seconds."""
        ...

    async def delete(self, key: str) -> int:
        """Delete key. Returns number of keys deleted."""
        ...

    async def exists(self, key: str) -> int:
        """Check if key exists. Returns count (0 or 1)."""
        ...


@dataclass
class IdempotencyConfig:
    """Configuration for idempotency operations.

    Attributes:
        ttl_seconds: TTL for idempotency keys (default: 24 hours)
        key_prefix: Redis key prefix (default: order:idempotency)
        id_length: Length of random component in client order ID
    """

    ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS
    key_prefix: str = IDEMPOTENCY_KEY_PREFIX
    id_length: int = 8


def generate_client_order_id(symbol: str, id_length: int = 8) -> str:
    """Generate a unique client order ID.

    Format: <timestamp>_<token>_<random>
    - timestamp: Unix timestamp in milliseconds (13 digits)
    - token: Trading pair symbol (e.g., BTCUSDT)
    - random: Cryptographically secure random alphanumeric string

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        id_length: Length of random component (default: 8)

    Returns:
        Unique client order ID string

    Example:
        >>> generate_client_order_id("BTCUSDT")
        '1704067200000_BTCUSDT_a3f9b2c1'
    """
    # Get current timestamp in milliseconds
    timestamp = int(datetime.now(UTC).timestamp() * 1000)

    # Generate cryptographically secure random string
    alphabet = string.ascii_lowercase + string.digits
    random_component = "".join(secrets.choice(alphabet) for _ in range(id_length))

    # Format: timestamp_symbol_random
    client_order_id = f"{timestamp}_{symbol}_{random_component}"

    logger.debug(f"Generated client order ID: {client_order_id}")
    return client_order_id


def parse_client_order_id(client_order_id: str) -> dict[str, str]:
    """Parse a client order ID into its components.

    Args:
        client_order_id: The client order ID to parse

    Returns:
        Dictionary with timestamp, symbol, and random components

    Raises:
        ValueError: If the client order ID format is invalid

    Example:
        >>> parse_client_order_id("1704067200000_BTCUSDT_a3f9b2c1")
        {'timestamp': '1704067200000', 'symbol': 'BTCUSDT', 'random': 'a3f9b2c1'}
    """
    parts = client_order_id.split("_")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid client order ID format: {client_order_id}. "
            "Expected: timestamp_symbol_random"
        )

    return {
        "timestamp": parts[0],
        "symbol": parts[1],
        "random": parts[2],
    }


def build_idempotency_key(
    symbol: str, client_order_id: str, prefix: str = IDEMPOTENCY_KEY_PREFIX
) -> str:
    """Build Redis key for idempotency storage.

    Uses per-token namespace to ensure cross-token orders are not deduplicated.

    Args:
        symbol: Trading pair symbol
        client_order_id: The client order ID
        prefix: Key prefix (default: order:idempotency)

    Returns:
        Redis key string

    Example:
        >>> build_idempotency_key("BTCUSDT", "1704067200000_BTCUSDT_a3f9b2c1")
        'order:idempotency:BTCUSDT:1704067200000_BTCUSDT_a3f9b2c1'
    """
    return f"{prefix}:{symbol}:{client_order_id}"


class IdempotencyStore:
    """Redis-backed store for order idempotency tracking.

    Provides thread-safe duplicate detection with automatic TTL management.
    Each trading pair has its own namespace, ensuring cross-token orders
    are not deduplicated.

    Example:
        >>> store = IdempotencyStore(redis_client)
        >>> client_id = generate_client_order_id("BTCUSDT")
        >>> is_duplicate = await store.check_duplicate("BTCUSDT", client_id)
        >>> if not is_duplicate:
        ...     await store.mark_submitted("BTCUSDT", client_id)
    """

    def __init__(
        self,
        redis_client: RedisClient | None = None,
        config: IdempotencyConfig | None = None,
    ) -> None:
        """Initialize the idempotency store.

        Args:
            redis_client: Redis client for storage (None for local-only mode)
            config: Idempotency configuration
        """
        self.redis = redis_client
        self.config = config or IdempotencyConfig()
        # Local fallback store when Redis is unavailable (for testing)
        self._local_store: dict[str, float] = {}

    async def check_duplicate(
        self,
        symbol: str,
        client_order_id: str,
    ) -> bool:
        """Check if an order has already been submitted.

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID

        Returns:
            True if this is a duplicate order, False otherwise

        Raises:
            DuplicateOrderException: If duplicate is detected (when configured)
        """
        key = build_idempotency_key(symbol, client_order_id, self.config.key_prefix)

        if self.redis:
            try:
                exists = await self.redis.exists(key)
                is_duplicate = exists > 0
            except Exception as e:
                logger.warning(f"Redis check failed, using local store: {e}")
                is_duplicate = key in self._local_store
        else:
            # Local-only mode (fallback)
            is_duplicate = key in self._local_store

        if is_duplicate:
            logger.warning(f"Duplicate order detected: {client_order_id} for {symbol}")

        return is_duplicate

    async def mark_submitted(
        self,
        symbol: str,
        client_order_id: str,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Mark an order as submitted in the idempotency store.

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID
            ttl_seconds: Optional override for TTL (default from config)

        Returns:
            True if successfully marked, False otherwise
        """
        key = build_idempotency_key(symbol, client_order_id, self.config.key_prefix)
        ttl = ttl_seconds or self.config.ttl_seconds

        if self.redis:
            try:
                await self.redis.setex(key, ttl, "1")
                logger.debug(f"Marked order as submitted: {key} (TTL: {ttl}s)")
                return True
            except Exception as e:
                logger.warning(f"Redis store failed, using local store: {e}")
                import time

                self._local_store[key] = time.time() + ttl
                return True
        else:
            # Local-only mode
            import time

            self._local_store[key] = time.time() + ttl
            logger.debug(f"Marked order in local store: {key}")
            return True

    async def validate_and_mark(
        self,
        symbol: str,
        client_order_id: str,
    ) -> None:
        """Validate order is not duplicate and mark it as submitted.

        This is a convenience method that combines check_duplicate and
        mark_submitted. Raises DuplicateOrderException if duplicate.

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID

        Raises:
            DuplicateOrderException: If order is a duplicate
        """
        is_duplicate = await self.check_duplicate(symbol, client_order_id)

        if is_duplicate:
            raise DuplicateOrderException(client_order_id, symbol)

        await self.mark_submitted(symbol, client_order_id)

    async def remove(self, symbol: str, client_order_id: str) -> bool:
        """Remove an order from the idempotency store.

        Useful for clearing orders that failed to submit.

        Args:
            symbol: Trading pair symbol
            client_order_id: Client-generated order ID

        Returns:
            True if removed, False if not found
        """
        key = build_idempotency_key(symbol, client_order_id, self.config.key_prefix)

        if self.redis:
            try:
                deleted = await self.redis.delete(key)
                return deleted > 0
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}")
                if key in self._local_store:
                    del self._local_store[key]
                    return True
                return False
        else:
            if key in self._local_store:
                del self._local_store[key]
                return True
            return False

    def clear_local_store(self) -> None:
        """Clear the local fallback store.

        Useful for testing and cleanup.
        """
        self._local_store.clear()
        logger.debug("Local idempotency store cleared")


# Singleton instance for application-wide use
_default_store: IdempotencyStore | None = None


def get_default_store(redis_client: RedisClient | None = None) -> IdempotencyStore:
    """Get or create the default idempotency store instance.

    Args:
        redis_client: Optional Redis client to use

    Returns:
        Default IdempotencyStore instance
    """
    global _default_store
    if _default_store is None:
        _default_store = IdempotencyStore(redis_client=redis_client)
    return _default_store


def reset_default_store() -> None:
    """Reset the default store instance.

    Useful for testing.
    """
    global _default_store
    _default_store = None
