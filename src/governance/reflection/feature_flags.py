"""Feature flag checking for reflection system."""

import os
from typing import Optional


def get_redis_client():
    """Get Redis client if available."""
    try:
        import redis

        host = os.getenv("REDIS_HOST", "host.docker.internal")
        port = int(os.getenv("REDIS_PORT", "6380"))
        client = redis.Redis(host=host, port=port, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def is_reflection_enabled() -> bool:
    """Check if reflection is enabled via feature flag."""
    client = get_redis_client()
    if client is None:
        # Default to enabled if Redis unavailable (fail open for now)
        return True

    flag = client.hget("chise:feature_flags:governance", "reflection_enabled")
    return flag == "true" or flag == "1" or flag is None  # Default enabled


def check_feature_flag(flag_name: str) -> bool:
    """Check any governance feature flag."""
    client = get_redis_client()
    if client is None:
        return True  # Fail open

    flag = client.hget("chise:feature_flags:governance", flag_name)
    return flag == "true" or flag == "1"
