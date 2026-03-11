"""Kill-switch bootstrap and initialization module.

Provides automatic initialization of kill-switch state in Redis,
ensuring the kill-switch is properly configured on system startup.

For ST-AUTONOMY-BURNIN-001-A: Kill-Switch Bootstrap/Initialization Guard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# Redis key constants
KILL_SWITCH_HASH_KEY = "bmad:chiseai:kill_switch"
ENABLED_FIELD = "enabled"
TRIGGERED_FIELD = "triggered"
INITIALIZED_AT_FIELD = "initialized_at"
INITIALIZED_BY_FIELD = "initialized_by"

# Default values
DEFAULT_ENABLED = "1"  # Armed by default
DEFAULT_TRIGGERED = "0"  # Not triggered by default


def bootstrap_kill_switch(redis_client: Any | None = None) -> bool:
    """Bootstrap kill-switch state in Redis.

    Initializes kill-switch Redis keys with safe defaults:
    - enabled=1 (armed/active)
    - triggered=0 (not triggered)
    - initialized_at=timestamp
    - initialized_by=bootstrap

    This function is idempotent - safe to call multiple times.
    If keys already exist, they are NOT overwritten.

    Args:
        redis_client: Redis client instance. If None, will attempt to
                     create a new connection using environment variables.

    Returns:
        True if initialization was successful (or already initialized),
        False if Redis connection failed.
    """
    try:
        # Get or create Redis client
        r = redis_client or _get_redis_client()
        if r is None:
            logger.error("Failed to bootstrap kill-switch: Redis unavailable")
            return False

        # Check if already initialized
        if is_kill_switch_initialized(r):
            logger.debug("Kill-switch already initialized, skipping bootstrap")
            return True

        # Initialize with safe defaults (only set if not exists)
        now = datetime.now(UTC).isoformat()
        mapping = {
            ENABLED_FIELD: DEFAULT_ENABLED,
            TRIGGERED_FIELD: DEFAULT_TRIGGERED,
            INITIALIZED_AT_FIELD: now,
            INITIALIZED_BY_FIELD: "bootstrap",
        }

        # Use hsetnx to only set if field doesn't exist (idempotent)
        for field, value in mapping.items():
            r.hsetnx(KILL_SWITCH_HASH_KEY, field, value)

        logger.info(
            f"Kill-switch bootstrapped: enabled={DEFAULT_ENABLED}, "
            f"triggered={DEFAULT_TRIGGERED}, at={now}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to bootstrap kill-switch: {e}")
        return False


def is_kill_switch_initialized(redis_client: Any | None = None) -> bool:
    """Check if kill-switch has been initialized in Redis.

    A kill-switch is considered initialized if:
    - The kill_switch hash exists in Redis
    - It has the 'enabled' field set
    - It has the 'triggered' field set

    Args:
        redis_client: Redis client instance. If None, will attempt to
                     create a new connection using environment variables.

    Returns:
        True if kill-switch is initialized, False otherwise.
        Also returns False if Redis connection fails.
    """
    try:
        r = redis_client or _get_redis_client()
        if r is None:
            logger.warning("Cannot check kill-switch initialization: Redis unavailable")
            return False

        # Check if the hash exists and has required fields
        enabled = r.hget(KILL_SWITCH_HASH_KEY, ENABLED_FIELD)
        triggered = r.hget(KILL_SWITCH_HASH_KEY, TRIGGERED_FIELD)

        # Initialized if both fields exist
        return enabled is not None and triggered is not None

    except Exception as e:
        logger.error(f"Error checking kill-switch initialization: {e}")
        return False


def get_kill_switch_status(redis_client: Any | None = None) -> dict[str, Any]:
    """Get full kill-switch status from Redis.

    Args:
        redis_client: Redis client instance. If None, will attempt to
                     create a new connection using environment variables.

    Returns:
        Dictionary with kill-switch status:
        - initialized: bool - whether kill-switch is initialized
        - enabled: bool - whether kill-switch is enabled (armed)
        - triggered: bool - whether kill-switch has been triggered
        - initialized_at: str | None - ISO timestamp of initialization
        - initialized_by: str | None - what initialized the kill-switch
        - error: str | None - error message if status check failed
    """
    try:
        r = redis_client or _get_redis_client()
        if r is None:
            return {
                "initialized": False,
                "enabled": False,
                "triggered": False,
                "initialized_at": None,
                "initialized_by": None,
                "error": "Redis unavailable",
            }

        # Get all fields from hash
        data = r.hgetall(KILL_SWITCH_HASH_KEY)

        if not data:
            return {
                "initialized": False,
                "enabled": False,
                "triggered": False,
                "initialized_at": None,
                "initialized_by": None,
                "error": None,
            }

        return {
            "initialized": True,
            "enabled": data.get(ENABLED_FIELD) == "1",
            "triggered": data.get(TRIGGERED_FIELD) == "1",
            "initialized_at": data.get(INITIALIZED_AT_FIELD),
            "initialized_by": data.get(INITIALIZED_BY_FIELD),
            "error": None,
        }

    except Exception as e:
        logger.error(f"Error getting kill-switch status: {e}")
        return {
            "initialized": False,
            "enabled": False,
            "triggered": False,
            "initialized_at": None,
            "initialized_by": None,
            "error": str(e),
        }


def _get_redis_client() -> Any | None:
    """Create a Redis client from environment variables.

    Returns:
        Redis client instance or None if connection fails.
    """
    try:
        import os

        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))

        client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        # Test connection
        client.ping()
        return client

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None
