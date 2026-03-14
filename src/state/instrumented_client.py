"""Instrumented Redis client with automatic tracing.

TEMPO-2026-001: Redis client wrapper with automatic span creation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import redis
from opentelemetry import trace

from src.state.tracing import (
    get_operation_category,
    sanitize_key_pattern,
    trace_redis_operation,
)


class InstrumentedRedisClient:
    """Redis client wrapper with automatic tracing.

    Wraps a Redis client and creates spans for all operations with
    automatic instrumentation for common operations.

    Example:
        from src.state.instrumented_client import InstrumentedRedisClient

        client = InstrumentedRedisClient(host="localhost", port=6379)

        # All operations are automatically traced
        value = client.get("mykey")
        client.set("mykey", "value")
    """

    def __init__(self, redis_client: redis.Redis | None = None, **kwargs: Any):
        """Initialize instrumented Redis client.

        Args:
            redis_client: Existing Redis client to wrap
            **kwargs: Arguments to pass to redis.Redis() if creating new client
        """
        if redis_client is not None:
            self._client = redis_client
        else:
            self._client = redis.Redis(**kwargs)

    @property
    def client(self) -> redis.Redis:
        """Get the underlying Redis client."""
        return self._client

    def _trace_operation(
        self, operation: str, key: str, func: Callable, *args, **kwargs
    ):
        """Helper to trace a Redis operation."""
        tracer = trace.get_tracer("chiseai-redis")
        sanitized_key = sanitize_key_pattern(key)
        category = get_operation_category(operation)

        span_name = f"redis.{operation.lower()}"

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("chiseai.redis.operation", operation)
            span.set_attribute("chiseai.redis.category", category)
            if sanitized_key:
                span.set_attribute("chiseai.redis.key_pattern", sanitized_key)

            try:
                result = func(*args, **kwargs)
                span.set_attribute("chiseai.redis.success", True)
                return result
            except Exception as e:
                span.set_attribute("chiseai.redis.success", False)
                span.set_attribute("chiseai.redis.error", str(e))
                span.record_exception(e)
                raise

    # Basic operations
    def get(self, key: str) -> bytes | None:
        """Get value from Redis with tracing."""
        return self._trace_operation("GET", key, self._client.get, key)

    def set(
        self,
        key: str,
        value: str | bytes,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set value in Redis with tracing."""
        return self._trace_operation(
            "SET", key, self._client.set, key, value, ex=ex, px=px, nx=nx, xx=xx
        )

    def delete(self, *keys: str) -> int:
        """Delete keys from Redis with tracing."""
        # Use first key for span, log total count
        first_key = keys[0] if keys else ""
        return self._trace_operation("DELETE", first_key, self._client.delete, *keys)

    # Hash operations
    def hget(self, name: str, key: str) -> bytes | None:
        """Get hash field value with tracing."""
        return self._trace_operation(
            "HGET", f"{name}:{key}", self._client.hget, name, key
        )

    def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | bytes | None = None,
        mapping: dict | None = None,
    ) -> int:
        """Set hash field(s) with tracing."""
        return self._trace_operation(
            "HSET", name, self._client.hset, name, key, value, mapping=mapping
        )

    def hgetall(self, name: str) -> dict:
        """Get all hash fields with tracing."""
        return self._trace_operation("HGETALL", name, self._client.hgetall, name)

    def hdel(self, name: str, *keys: str) -> int:
        """Delete hash field(s) with tracing."""
        return self._trace_operation("HDEL", name, self._client.hdel, name, *keys)

    # List operations
    def lpush(self, name: str, *values: str | bytes) -> int:
        """Push values to list head with tracing."""
        return self._trace_operation("LPUSH", name, self._client.lpush, name, *values)

    def rpush(self, name: str, *values: str | bytes) -> int:
        """Push values to list tail with tracing."""
        return self._trace_operation("RPUSH", name, self._client.rpush, name, *values)

    def lpop(self, name: str) -> bytes | None:
        """Pop value from list head with tracing."""
        return self._trace_operation("LPOP", name, self._client.lpop, name)

    def rpop(self, name: str) -> bytes | None:
        """Pop value from list tail with tracing."""
        return self._trace_operation("RPOP", name, self._client.rpop, name)

    def lrange(self, name: str, start: int, end: int) -> list:
        """Get list range with tracing."""
        return self._trace_operation(
            "LRANGE", name, self._client.lrange, name, start, end
        )

    # Set operations
    def sadd(self, name: str, *values: str | bytes) -> int:
        """Add members to set with tracing."""
        return self._trace_operation("SADD", name, self._client.sadd, name, *values)

    def srem(self, name: str, *values: str | bytes) -> int:
        """Remove members from set with tracing."""
        return self._trace_operation("SREM", name, self._client.srem, name, *values)

    def smembers(self, name: str) -> set:
        """Get all set members with tracing."""
        return self._trace_operation("SMEMBERS", name, self._client.smembers, name)

    # Sorted set operations
    def zadd(self, name: str, mapping: dict, nx: bool = False) -> int:
        """Add members to sorted set with tracing."""
        return self._trace_operation(
            "ZADD", name, self._client.zadd, name, mapping, nx=nx
        )

    def zrem(self, name: str, *values: str | bytes) -> int:
        """Remove members from sorted set with tracing."""
        return self._trace_operation("ZREM", name, self._client.zrem, name, *values)

    def zrange(self, name: str, start: int, end: int, withscores: bool = False) -> list:
        """Get sorted set range with tracing."""
        return self._trace_operation(
            "ZRANGE", name, self._client.zrange, name, start, end, withscores=withscores
        )

    # Utility operations
    def expire(self, name: str, time: int) -> bool:
        """Set key expiration with tracing."""
        return self._trace_operation("EXPIRE", name, self._client.expire, name, time)

    def ttl(self, name: str) -> int:
        """Get key TTL with tracing."""
        return self._trace_operation("TTL", name, self._client.ttl, name)

    def exists(self, *names: str) -> int:
        """Check if keys exist with tracing."""
        first_name = names[0] if names else ""
        return self._trace_operation("EXISTS", first_name, self._client.exists, *names)

    def keys(self, pattern: str) -> list:
        """Get keys matching pattern with tracing."""
        return self._trace_operation("KEYS", pattern, self._client.keys, pattern)

    def ping(self) -> bool:
        """Ping Redis server with tracing."""
        return self._trace_operation("PING", "", self._client.ping)

    def pipeline(self, transaction: bool = True, shard_hint: str | None = None) -> Any:
        """Get pipeline with tracing."""
        tracer = trace.get_tracer("chiseai-redis")
        with tracer.start_as_current_span("redis.pipeline") as span:
            span.set_attribute("chiseai.redis.operation", "PIPELINE")
            span.set_attribute("chiseai.redis.category", "write")
            span.set_attribute("chiseai.redis.transaction", transaction)
            pipeline = self._client.pipeline(
                transaction=transaction, shard_hint=shard_hint
            )
            return InstrumentedPipeline(pipeline)


class InstrumentedPipeline:
    """Instrumented Redis pipeline with tracing."""

    def __init__(self, pipeline: Any):
        """Initialize instrumented pipeline.

        Args:
            pipeline: Redis pipeline object
        """
        self._pipeline = pipeline
        self._commands: list[dict] = []

    def get(self, key: str) -> "InstrumentedPipeline":
        """Add GET command to pipeline."""
        self._pipeline.get(key)
        self._commands.append({"op": "GET", "key": key})
        return self

    def set(self, key: str, value: str | bytes, **kwargs) -> "InstrumentedPipeline":
        """Add SET command to pipeline."""
        self._pipeline.set(key, value, **kwargs)
        self._commands.append({"op": "SET", "key": key})
        return self

    def delete(self, *keys: str) -> "InstrumentedPipeline":
        """Add DELETE command to pipeline."""
        self._pipeline.delete(*keys)
        self._commands.append({"op": "DELETE", "key": keys[0] if keys else ""})
        return self

    def hget(self, name: str, key: str) -> "InstrumentedPipeline":
        """Add HGET command to pipeline."""
        self._pipeline.hget(name, key)
        self._commands.append({"op": "HGET", "key": f"{name}:{key}"})
        return self

    def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | bytes | None = None,
        mapping: dict | None = None,
    ) -> "InstrumentedPipeline":
        """Add HSET command to pipeline."""
        self._pipeline.hset(name, key, value, mapping=mapping)
        self._commands.append({"op": "HSET", "key": name})
        return self

    def execute(self, raise_on_error: bool = True) -> list:
        """Execute pipeline with tracing."""
        tracer = trace.get_tracer("chiseai-redis")

        with tracer.start_as_current_span("redis.pipeline.execute") as span:
            span.set_attribute("chiseai.redis.operation", "PIPELINE")
            span.set_attribute("chiseai.redis.category", "write")
            span.set_attribute("chiseai.redis.command_count", len(self._commands))

            # Log command types
            if self._commands:
                op_types = [cmd["op"] for cmd in self._commands]
                span.set_attribute("chiseai.redis.pipeline_operations", str(op_types))

            try:
                results = self._pipeline.execute(raise_on_error=raise_on_error)
                span.set_attribute("chiseai.redis.success", True)
                span.set_attribute("chiseai.redis.result_count", len(results))
                return results
            except Exception as e:
                span.set_attribute("chiseai.redis.success", False)
                span.set_attribute("chiseai.redis.error", str(e))
                span.record_exception(e)
                raise


def create_instrumented_redis_client(**kwargs: Any) -> InstrumentedRedisClient:
    """Create a new instrumented Redis client.

    Convenience function for creating an instrumented client
    with the given connection parameters.

    Args:
        **kwargs: Arguments passed to redis.Redis()

    Returns:
        InstrumentedRedisClient instance

    Example:
        client = create_instrumented_redis_client(
            host="localhost",
            port=6379,
            db=0
        )
    """
    return InstrumentedRedisClient(**kwargs)
