"""State management module with Redis tracing instrumentation.

Provides Redis operations with automatic tracing and instrumented client.
"""

from src.state.instrumented_client import (
    InstrumentedPipeline,
    InstrumentedRedisClient,
    create_instrumented_redis_client,
)
from src.state.tracing import (
    get_operation_category,
    sanitize_key_pattern,
    trace_redis_operation,
)

__all__ = [
    "trace_redis_operation",
    "get_operation_category",
    "sanitize_key_pattern",
    "InstrumentedRedisClient",
    "InstrumentedPipeline",
    "create_instrumented_redis_client",
]
