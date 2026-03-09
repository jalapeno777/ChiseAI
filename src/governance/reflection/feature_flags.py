"""Feature flag checking for reflection and governance loops.

Uses a canonical hash key with legacy scalar-key fallback for compatibility.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

GOVERNANCE_FLAGS_HASH_KEY = os.getenv(
    "CHISE_GOVERNANCE_FLAGS_HASH_KEY", "chise:feature_flags:governance"
)
LEGACY_GOVERNANCE_FLAG_PREFIX = f"{GOVERNANCE_FLAGS_HASH_KEY}:"


def _to_bool(raw_value: str | None) -> bool:
    """Parse a string feature-flag value into bool."""
    if raw_value is None:
        return False
    return raw_value.lower() in ("true", "1", "yes", "on", "enabled")


def _default_enabled() -> bool:
    """Default flag value when not explicitly set."""
    return _to_bool(os.getenv("CHISE_GOVERNANCE_FLAGS_DEFAULT_ENABLED", "false"))


def _fail_open() -> bool:
    """Behavior when Redis is unavailable or lookups fail."""
    return _to_bool(os.getenv("CHISE_GOVERNANCE_FLAGS_FAIL_OPEN", "false"))


def _redis_hosts() -> list[str]:
    """Host fallback order for Redis connectivity."""
    hosts = [
        os.getenv("REDIS_HOST"),
        os.getenv("CHISE_REDIS_HOST"),
        os.getenv("ACP_REDIS_HOST"),
        "chiseai-redis",
        "host.docker.internal",
        "localhost",
    ]
    return [host for i, host in enumerate(hosts) if host and host not in hosts[:i]]


def get_redis_client() -> object | None:
    """Get Redis client if available.

    Returns:
        Redis client or None if unavailable
    """
    try:
        import redis

        port = int(
            os.getenv("REDIS_PORT")
            or os.getenv("CHISE_REDIS_PORT")
            or os.getenv("ACP_REDIS_PORT")
            or "6380"
        )
        db = int(os.getenv("REDIS_DB", "0"))

        for host in _redis_hosts():
            try:
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
            except Exception as exc:
                logger.debug(f"Redis probe failed for {host}:{port}: {exc}")

    except Exception as e:
        logger.debug(f"Redis unavailable: {e}")

    return None


def is_flag_enabled(flag_name: str, default: bool | None = None) -> bool:
    """Check governance feature flag with hash-first and legacy fallback."""
    if default is None:
        default = _default_enabled()

    client = get_redis_client()
    if client is None:
        fallback = _fail_open() or default
        logger.debug(f"Redis unavailable, returning fallback={fallback} for {flag_name}")
        return fallback

    try:
        flag = client.hget(GOVERNANCE_FLAGS_HASH_KEY, flag_name)
        if flag is None:
            flag = client.get(f"{LEGACY_GOVERNANCE_FLAG_PREFIX}{flag_name}")

        if flag is None:
            logger.debug(f"{flag_name} not set, defaulting to {default}")
            return default

        is_enabled = _to_bool(flag)
        logger.debug(f"{flag_name}={flag} -> {is_enabled}")
        return is_enabled
    except Exception as e:
        logger.warning(f"Error reading feature flag {flag_name}: {e}")
        return _fail_open() or default


def set_flag_enabled(flag_name: str, enabled: bool, write_legacy: bool = True) -> bool:
    """Set governance feature flag in canonical hash and optional legacy key."""
    client = get_redis_client()
    if client is None:
        return False

    try:
        value = "true" if enabled else "false"
        client.hset(GOVERNANCE_FLAGS_HASH_KEY, flag_name, value)
        if write_legacy:
            client.set(f"{LEGACY_GOVERNANCE_FLAG_PREFIX}{flag_name}", value)
        return True
    except Exception as e:
        logger.warning(f"Error setting feature flag {flag_name}: {e}")
        return False


def get_flag_status(flag_name: str) -> dict:
    """Get detailed status for a governance flag."""
    status = {
        "hash_key": GOVERNANCE_FLAGS_HASH_KEY,
        "field": flag_name,
        "legacy_key": f"{LEGACY_GOVERNANCE_FLAG_PREFIX}{flag_name}",
        "enabled": False,
        "raw_hash_value": None,
        "raw_legacy_value": None,
        "default_enabled": _default_enabled(),
        "fail_open": _fail_open(),
    }

    client = get_redis_client()
    if client is None:
        status["enabled"] = _fail_open() or _default_enabled()
        status["default"] = True
        status["error"] = "Redis unavailable"
        return status

    try:
        hash_value = client.hget(GOVERNANCE_FLAGS_HASH_KEY, flag_name)
        legacy_value = client.get(f"{LEGACY_GOVERNANCE_FLAG_PREFIX}{flag_name}")
        status["raw_hash_value"] = hash_value
        status["raw_legacy_value"] = legacy_value

        raw = hash_value if hash_value is not None else legacy_value
        if raw is None:
            status["enabled"] = _default_enabled()
            status["default"] = True
        else:
            status["enabled"] = _to_bool(raw)
            status["default"] = False
    except Exception as e:
        status["enabled"] = _fail_open() or _default_enabled()
        status["default"] = True
        status["error"] = str(e)

    return status


def is_reflection_enabled() -> bool:
    """Check if reflection is enabled via feature flag."""
    return is_flag_enabled("reflection_enabled")


def check_feature_flag(flag_name: str) -> bool:
    """Backward-compatible alias for generic feature-flag checks."""
    return is_flag_enabled(flag_name)
