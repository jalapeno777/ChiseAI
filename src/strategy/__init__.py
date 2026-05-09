"""Strategy module - execution protocol, registry, engine, and adapter.

Provides Protocol-based strategy interfaces, a lightweight strategy
registry, the strategy execution engine, and a DSL-to-strategy adapter
with backtest runner.
"""

from __future__ import annotations

from .adapter import StrategyAdapter, StrategyValidationError
from .backtest_runner import StrategyBacktestRunner, WalkForwardWindow
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
    "StrategyAdapter",
    "StrategyBacktestRunner",
    "StrategyEngine",
    "StrategyMetadata",
    "StrategyProtocol",
    "StrategyRegistry",
    "StrategyValidationError",
    "WalkForwardWindow",
]
