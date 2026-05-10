"""Centralized Redis configuration for paper trading execution.

Provides a single source of truth for Redis connection parameters used
across the paper trading modules (signal consumer, kill switch, etc.).
"""

from __future__ import annotations

import os
from typing import Any

REDIS_HOST = os.getenv("PAPER_REDIS_HOST", "chiseai-redis")
REDIS_PORT = int(os.getenv("PAPER_REDIS_PORT", "6380"))
REDIS_DB = int(os.getenv("PAPER_REDIS_DB", "0"))
REDIS_SOCKET_CONNECT_TIMEOUT = 5
REDIS_SOCKET_TIMEOUT = 5


def get_redis_client(
    host: str | None = None,
    port: int | None = None,
    db: int | None = None,
    **kwargs: Any,
) -> Any:
    """Create a Redis client with centralized defaults.

    Args:
        host: Redis host. Falls back to REDIS_HOST env var or default.
        port: Redis port. Falls back to REDIS_PORT env var or default.
        db: Redis database number. Falls back to REDIS_DB env var or default.
        **kwargs: Additional keyword arguments passed to Redis constructor
                  (e.g., decode_responses, socket_connect_timeout).

    Returns:
        A Redis client instance.
    """
    import redis.asyncio as aioredis

    return aioredis.Redis(
        host=host or REDIS_HOST,
        port=port or REDIS_PORT,
        db=db or REDIS_DB,
        socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
        **kwargs,
    )


def get_redis_client_sync(
    host: str | None = None,
    port: int | None = None,
    db: int | None = None,
    **kwargs: Any,
) -> Any:
    """Create a synchronous Redis client with centralized defaults.

    Args:
        host: Redis host. Falls back to REDIS_HOST env var or default.
        port: Redis port. Falls back to REDIS_PORT env var or default.
        db: Redis database number. Falls back to REDIS_DB env var or default.
        **kwargs: Additional keyword arguments passed to Redis constructor.

    Returns:
        A synchronous Redis client instance.
    """
    import redis

    return redis.Redis(
        host=host or REDIS_HOST,
        port=port or REDIS_PORT,
        db=db or REDIS_DB,
        socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
        **kwargs,
    )
