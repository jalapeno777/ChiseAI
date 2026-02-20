"""PR Lifecycle Management module for autonomous AI swarm.

This module provides comprehensive PR lifecycle management including:
- State tracking and transitions
- Continuous monitoring
- Automatic failure recovery
- Health monitoring and stuck PR detection
- Escalation management

Usage:
    from scripts.pr_lifecycle import PRStateManager, PRMonitor

    # Register a PR for monitoring
    state_mgr = PRStateManager()
    state = PRState(pr_number=123, story_id="ST-001", ...)
    state_mgr.register_pr(state)

    # Monitor until terminal state
    monitor = PRMonitor()
    monitor.monitor_single_pr(123)
"""

from .pr_state_manager import PRStateManager, PRState, PREvent
from .pr_monitor import PRMonitor
from .health_monitor import PRHealthMonitor
from .recovery_handlers import RecoveryHandlers, RecoveryResult

__all__ = [
    "PRStateManager",
    "PRState",
    "PREvent",
    "PRMonitor",
    "PRHealthMonitor",
    "RecoveryHandlers",
    "RecoveryResult",
]
