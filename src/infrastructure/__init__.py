"""Infrastructure package.

This package contains infrastructure-level components for ChiseAI,
including persistence, networking, and containerization utilities.
"""

from __future__ import annotations


def __getattr__(name: str):
    """Lazy import to avoid eager loading of asyncpg-dependent modules."""
    if name == "PostgresSignalsPersistence":
        from src.infrastructure.persistence.postgres_signals import (
            PostgresSignalsPersistence,
        )

        return PostgresSignalsPersistence
    if name == "get_postgres_signals":
        from src.infrastructure.persistence.postgres_signals import (
            get_postgres_signals,
        )

        return get_postgres_signals
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PostgresSignalsPersistence",
    "get_postgres_signals",
]
