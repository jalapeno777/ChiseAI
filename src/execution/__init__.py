"""Execution module for ChiseAI.

Provides order execution, idempotency, kill switches, and canary deployment support.
"""

from execution.order_idempotency import (
    DuplicateOrderException,
    IdempotencyConfig,
    IdempotencyStore,
    generate_client_order_id,
    get_default_store,
    reset_default_store,
)

__all__ = [
    "DuplicateOrderException",
    "IdempotencyConfig",
    "IdempotencyStore",
    "generate_client_order_id",
    "get_default_store",
    "reset_default_store",
]
