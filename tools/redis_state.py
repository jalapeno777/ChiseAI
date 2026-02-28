"""Redis state management utilities.

This module provides a simple interface for Redis operations used throughout
the ChiseAI codebase. It wraps the redis library with error handling and
connection management.

All functions gracefully handle Redis unavailability by returning None or
appropriate defaults.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Redis connection singleton
_redis_client = None


def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis

        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", None)

        _redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        return _redis_client
    except Exception as e:
        logger.debug(f"Redis client initialization failed: {e}")
        return None


def _serialize(value: Any) -> str:
    """Serialize value for Redis storage."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return json.dumps(value)


def _deserialize(value: str | None) -> Any:
    """Deserialize value from Redis."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


# Hash operations
def redis_state_hset(
    name: str, key: str, value: Any, expire_seconds: int | None = None
) -> bool:
    """Set a field in a Redis hash."""
    client = _get_redis_client()
    if client is None:
        logger.debug("Redis unavailable, skipping hset")
        return False
    try:
        result = client.hset(name, key, _serialize(value))
        if expire_seconds:
            client.expire(name, expire_seconds)
        return bool(result)
    except Exception as e:
        logger.debug(f"Redis hset failed: {e}")
        return False


def redis_state_hget(name: str, key: str) -> Any:
    """Get a field from a Redis hash."""
    client = _get_redis_client()
    if client is None:
        logger.debug("Redis unavailable, returning None for hget")
        return None
    try:
        value = client.hget(name, key)
        return _deserialize(value)
    except Exception as e:
        logger.debug(f"Redis hget failed: {e}")
        return None


def redis_state_hgetall(name: str) -> dict[str, Any]:
    """Get all fields from a Redis hash."""
    client = _get_redis_client()
    if client is None:
        logger.debug("Redis unavailable, returning empty dict for hgetall")
        return {}
    try:
        result = client.hgetall(name)
        return {k: _deserialize(v) for k, v in result.items()}
    except Exception as e:
        logger.debug(f"Redis hgetall failed: {e}")
        return {}


def redis_state_hdel(name: str, key: str) -> bool:
    """Delete a field from a Redis hash."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.hdel(name, key))
    except Exception as e:
        logger.debug(f"Redis hdel failed: {e}")
        return False


def redis_state_hexists(name: str, key: str) -> bool:
    """Check if a field exists in a Redis hash."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.hexists(name, key))
    except Exception as e:
        logger.debug(f"Redis hexists failed: {e}")
        return False


# String operations
def redis_state_set(key: str, value: Any, expiration: int | None = None) -> bool:
    """Set a string value in Redis."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        if expiration:
            client.setex(key, expiration, _serialize(value))
        else:
            client.set(key, _serialize(value))
        return True
    except Exception as e:
        logger.debug(f"Redis set failed: {e}")
        return False


def redis_state_get(key: str) -> Any:
    """Get a string value from Redis."""
    client = _get_redis_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        return _deserialize(value)
    except Exception as e:
        logger.debug(f"Redis get failed: {e}")
        return None


def redis_state_delete(key: str) -> bool:
    """Delete a key from Redis."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.delete(key))
    except Exception as e:
        logger.debug(f"Redis delete failed: {e}")
        return False


# List operations
def redis_state_lpush(name: str, value: Any, expire: int | None = None) -> bool:
    """Push a value onto the left of a Redis list."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        client.lpush(name, _serialize(value))
        if expire:
            client.expire(name, expire)
        return True
    except Exception as e:
        logger.debug(f"Redis lpush failed: {e}")
        return False


def redis_state_rpush(name: str, value: Any, expire: int | None = None) -> bool:
    """Push a value onto the right of a Redis list."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        client.rpush(name, _serialize(value))
        if expire:
            client.expire(name, expire)
        return True
    except Exception as e:
        logger.debug(f"Redis rpush failed: {e}")
        return False


def redis_state_lpop(name: str) -> Any:
    """Pop a value from the left of a Redis list."""
    client = _get_redis_client()
    if client is None:
        return None
    try:
        value = client.lpop(name)
        return _deserialize(value)
    except Exception as e:
        logger.debug(f"Redis lpop failed: {e}")
        return None


def redis_state_rpop(name: str) -> Any:
    """Pop a value from the right of a Redis list."""
    client = _get_redis_client()
    if client is None:
        return None
    try:
        value = client.rpop(name)
        return _deserialize(value)
    except Exception as e:
        logger.debug(f"Redis rpop failed: {e}")
        return None


def redis_state_lrange(name: str, start: int, stop: int) -> list[Any]:
    """Get a range of elements from a Redis list."""
    client = _get_redis_client()
    if client is None:
        return []
    try:
        values = client.lrange(name, start, stop)
        return [_deserialize(v) for v in values]
    except Exception as e:
        logger.debug(f"Redis lrange failed: {e}")
        return []


def redis_state_llen(name: str) -> int:
    """Get the length of a Redis list."""
    client = _get_redis_client()
    if client is None:
        return 0
    try:
        return client.llen(name)
    except Exception as e:
        logger.debug(f"Redis llen failed: {e}")
        return 0


# Set operations
def redis_state_sadd(name: str, value: Any, expire_seconds: int | None = None) -> bool:
    """Add a value to a Redis set."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        result = client.sadd(name, _serialize(value))
        if expire_seconds:
            client.expire(name, expire_seconds)
        return bool(result)
    except Exception as e:
        logger.debug(f"Redis sadd failed: {e}")
        return False


def redis_state_srem(name: str, value: Any) -> bool:
    """Remove a value from a Redis set."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.srem(name, _serialize(value)))
    except Exception as e:
        logger.debug(f"Redis srem failed: {e}")
        return False


def redis_state_smembers(name: str) -> set[Any]:
    """Get all members of a Redis set."""
    client = _get_redis_client()
    if client is None:
        return set()
    try:
        values = client.smembers(name)
        return {_deserialize(v) for v in values}
    except Exception as e:
        logger.debug(f"Redis smembers failed: {e}")
        return set()


# Sorted set operations
def redis_state_zadd(
    key: str, score: float, member: Any, expiration: int | None = None
) -> bool:
    """Add a member to a Redis sorted set."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        result = client.zadd(key, {str(member): score})
        if expiration:
            client.expire(key, expiration)
        return bool(result)
    except Exception as e:
        logger.debug(f"Redis zadd failed: {e}")
        return False


def redis_state_zrange(
    key: str, start: int, end: int, with_scores: bool = False
) -> list[Any]:
    """Get a range of members from a Redis sorted set."""
    client = _get_redis_client()
    if client is None:
        return []
    try:
        values = client.zrange(key, start, end, withscores=with_scores)
        if with_scores:
            return [(member, float(score)) for member, score in values]
        return [member for member in values]
    except Exception as e:
        logger.debug(f"Redis zrange failed: {e}")
        return []


def redis_state_zrem(key: str, member: Any) -> bool:
    """Remove a member from a Redis sorted set."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.zrem(key, str(member)))
    except Exception as e:
        logger.debug(f"Redis zrem failed: {e}")
        return False


# Key operations
def redis_state_expire(name: str, expire_seconds: int) -> bool:
    """Set expiration on a Redis key."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.expire(name, expire_seconds))
    except Exception as e:
        logger.debug(f"Redis expire failed: {e}")
        return False
