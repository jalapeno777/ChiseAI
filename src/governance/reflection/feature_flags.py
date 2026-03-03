"""Feature flag checking for reflection system.

Reads governance feature flags from Redis to enable/disable
reflection functionality at runtime.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_redis_client() -> Optional[object]:
    """Get Redis client if available.

    Returns:
        Redis client or None if unavailable
    """
    try:
        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        db = int(os.getenv("REDIS_DB", "0"))

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.debug(f"Redis unavailable: {e}")
        return None


def is_reflection_enabled() -> bool:
    """Check if reflection is enabled via feature flag.

    Reads from Redis hash 'chise:feature_flags:governance'.
    Defaults to True if Redis unavailable (fail open).

    Returns:
        True if reflection is enabled, False otherwise
    """
    client = get_redis_client()
    if client is None:
        # Default to enabled if Redis unavailable (fail open)
        logger.debug("Redis unavailable, defaulting reflection to enabled")
        return True

    try:
        flag = client.hget("chise:feature_flags:governance", "reflection_enabled")
        if flag is None:
            # Key doesn't exist, default to enabled
            logger.debug("reflection_enabled flag not set, defaulting to enabled")
            return True

        is_enabled = flag.lower() in ("true", "1", "yes", "on")
        logger.debug(f"reflection_enabled flag: {flag} -> {is_enabled}")
        return is_enabled
    except Exception as e:
        logger.warning(f"Error reading feature flag: {e}")
        return True  # Fail open


def check_feature_flag(flag_name: str) -> bool:
    """Check any governance feature flag.

    Args:
        flag_name: Name of the flag to check (e.g., 'memory_promotion_enabled')

    Returns:
        True if flag is enabled, False otherwise
    """
    client = get_redis_client()
    if client is None:
        return True  # Fail open

    try:
        flag = client.hget("chise:feature_flags:governance", flag_name)
        if flag is None:
            return True  # Default enabled
        return flag.lower() in ("true", "1", "yes", "on")
    except Exception as e:
        logger.warning(f"Error reading feature flag {flag_name}: {e}")
        return True  # Fail open
