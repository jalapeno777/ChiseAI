"""Kill-switch execution package.

Provides emergency position closure and risk control functionality
for ChiseAI trading system.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

from execution.kill_switch.cli import kill_switch_cli, register_commands
from execution.kill_switch.drawdown_monitor import (
    DrawdownMetrics,
    DrawdownMonitor,
    PortfolioValuePoint,
)
from execution.kill_switch.executor import KillSwitchExecutor
from execution.kill_switch.state import (
    CloseResult,
    CloseStatus,
    KillSwitchConfig,
    KillSwitchLogEntry,
    KillSwitchResult,
    KillSwitchState,
)

__all__ = [
    # Main executor
    "KillSwitchExecutor",
    # State management
    "KillSwitchState",
    "KillSwitchConfig",
    "KillSwitchResult",
    "KillSwitchLogEntry",
    # Close results
    "CloseResult",
    "CloseStatus",
    # Drawdown monitoring
    "DrawdownMonitor",
    "DrawdownMetrics",
    "PortfolioValuePoint",
    # CLI
    "kill_switch_cli",
    "register_commands",
]
