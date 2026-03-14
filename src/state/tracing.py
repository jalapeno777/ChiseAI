"""Redis tracing instrumentation for cache operations.

TEMPO-2026-001: Redis span wrappers with operation type and key pattern tracking.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

from opentelemetry import trace

F = TypeVar("F", bound=Callable[..., Any])

# Redis operation types
REDIS_OPERATIONS = {
    "GET": "read",
    "SET": "write",
    "DELETE": "write",
    "DEL": "write",
    "HGET": "read",
    "HSET": "write",
    "HDEL": "write",
    "HGETALL": "read",
    "HMGET": "read",
    "HMSET": "write",
    "EXPIRE": "write",
    "TTL": "read",
    "EXISTS": "read",
    "KEYS": "read",
    "SCAN": "read",
    "LPUSH": "write",
    "RPUSH": "write",
    "LPOP": "write",
    "RPOP": "write",
    "LRANGE": "read",
    "LLEN": "read",
    "SADD": "write",
    "SREM": "write",
    "SMEMBERS": "read",
    "SISMEMBER": "read",
    "ZADD": "write",
    "ZREM": "write",
    "ZRANGE": "read",
    "ZSCORE": "read",
    "INCR": "write",
    "DECR": "write",
    "INCRBY": "write",
    "DECRBY": "write",
    "MGET": "read",
    "MSET": "write",
    "PUBLISH": "write",
    "SUBSCRIBE": "read",
    "UNSUBSCRIBE": "write",
    "PIPELINE": "write",
    "MULTI": "write",
    "EXEC": "write",
    "WATCH": "read",
    "UNWATCH": "write",
}


def get_operation_category(operation: str) -> str:
    """Get the category (read/write) for a Redis operation.

    Args:
        operation: Redis command name (e.g., "GET", "SET")

    Returns:
        Category: "read", "write", or "unknown"
    """
    return REDIS_OPERATIONS.get(operation.upper(), "unknown")


def sanitize_key_pattern(key: str) -> str:
    """Sanitize Redis key for span attributes (mask sensitive data).

    Args:
        key: Redis key string

    Returns:
        Sanitized key pattern suitable for tracing
    """
    if not key:
        return ""

    # Replace UUID-like patterns
    import re

    # Mask UUIDs
    key = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<uuid>",
        key,
        flags=re.IGNORECASE,
    )

    # Mask numeric IDs (common pattern: user:12345)
    key = re.sub(r":\d+", ":<id>", key)

    # Mask email addresses
    key = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "<email>", key)

    return key


def trace_redis_operation(operation_type: str | None = None):
    """Decorator to trace Redis operations.

    Creates spans with attributes for:
    - Operation type (GET, SET, DELETE, etc.)
    - Key pattern (sanitized)
    - Operation category (read/write)
    - Duration

    Args:
        operation_type: Redis operation type (e.g., "GET", "SET").
                       If None, will try to infer from function name.

    Returns:
        Decorator function

    Example:
        @trace_redis_operation("GET")
        def get_user(redis_client, user_id: str):
            return redis_client.get(f"user:{user_id}")

        # Or with auto-detection:
        @trace_redis_operation()
        def redis_get(redis_client, key: str):  # Will infer "GET"
            return redis_client.get(key)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Determine operation type
            op_type = operation_type
            if op_type is None:
                # Try to infer from function name
                op_type = _infer_operation_from_name(func.__name__)

            # Get key from args or kwargs
            key = _extract_key(args, kwargs)
            sanitized_key = sanitize_key_pattern(key) if key else ""

            # Get operation category
            category = get_operation_category(op_type)

            tracer = trace.get_tracer("chiseai-redis")
            span_name = f"redis.{op_type.lower() if op_type else 'operation'}"

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("chiseai.redis.operation", op_type)
                span.set_attribute("chiseai.redis.category", category)
                if sanitized_key:
                    span.set_attribute("chiseai.redis.key_pattern", sanitized_key)

                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    span.set_attribute("chiseai.redis.duration_ms", duration_ms)
                    span.set_attribute("chiseai.redis.success", True)

                    # Record result size if available
                    result_size = _get_result_size(result)
                    if result_size is not None:
                        span.set_attribute(
                            "chiseai.redis.result_size_bytes", result_size
                        )

                    return result
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    span.set_attribute("chiseai.redis.duration_ms", duration_ms)
                    span.set_attribute("chiseai.redis.success", False)
                    span.set_attribute("chiseai.redis.error", str(e))
                    span.set_attribute("chiseai.redis.error_type", type(e).__name__)
                    span.record_exception(e)
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


def _infer_operation_from_name(func_name: str) -> str:
    """Infer Redis operation type from function name.

    Args:
        func_name: Name of the function

    Returns:
        Inferred operation type or "UNKNOWN"
    """
    name_upper = func_name.upper()

    # Common patterns - check both prefix and suffix patterns
    # e.g., "redis_get", "get_value", "fetch_data"
    if "GET" in name_upper or name_upper.startswith("FETCH"):
        return "GET"
    elif "SET" in name_upper or name_upper.startswith("STORE"):
        return "SET"
    elif "DELETE" in name_upper or "REMOVE" in name_upper or "DEL" in name_upper:
        return "DELETE"
    elif "HGET" in name_upper:
        return "HGET"
    elif "HSET" in name_upper:
        return "HSET"
    elif "HDEL" in name_upper:
        return "HDEL"
    elif "EXPIRE" in name_upper:
        return "EXPIRE"
    elif "EXISTS" in name_upper:
        return "EXISTS"

    return "UNKNOWN"


def _extract_key(args: tuple, kwargs: dict) -> str:
    """Extract Redis key from function arguments.

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Key string or empty string
    """
    # Check kwargs first
    for key_name in ["key", "name", "redis_key", "cache_key"]:
        if key_name in kwargs:
            return str(kwargs[key_name])

    # Check args (typically second arg after self/client)
    if len(args) >= 2:
        return str(args[1])

    return ""


def _get_result_size(result: Any) -> int | None:
    """Get size of Redis result in bytes.

    Args:
        result: Redis operation result

    Returns:
        Size in bytes or None if not determinable
    """
    if result is None:
        return 0

    if isinstance(result, bytes):
        return len(result)

    if isinstance(result, str):
        return len(result.encode("utf-8"))

    if isinstance(result, list):
        total = 0
        for item in result:
            if isinstance(item, bytes):
                total += len(item)
            elif isinstance(item, str):
                total += len(item.encode("utf-8"))
        return total if total > 0 else None

    if isinstance(result, dict):
        total = 0
        for k, v in result.items():
            if isinstance(k, bytes):
                total += len(k)
            elif isinstance(k, str):
                total += len(k.encode("utf-8"))
            if isinstance(v, bytes):
                total += len(v)
            elif isinstance(v, str):
                total += len(v.encode("utf-8"))
        return total if total > 0 else None

    return None
