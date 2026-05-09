"""Strategy module - execution protocol, registry, and engine.

Provides Protocol-based strategy interfaces, a lightweight strategy
registry, and the strategy execution engine.
"""

from __future__ import annotations

from .contracts import (
    ExecutionResult,
    SignalResult,
    StrategyMetadata,
    StrategyProtocol,
)
from .engine import StrategyEngine
from .registry import StrategyRegistry

__all__ = [
    "ExecutionResult",
    "SignalResult",
    "StrategyEngine",
    "StrategyMetadata",
    "StrategyProtocol",
    "StrategyRegistry",
]
