"""Outcome persistence module for paper trading.

Provides canonical persistence of signals, orders, fills, and outcomes
to Redis with structured key patterns.
"""

from execution.persistence.outcome_persistence import OutcomePersistence

__all__ = ["OutcomePersistence"]
