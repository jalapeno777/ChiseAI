"""Execution alerts module for Discord integration.

Provides Discord alert integration for the execution hot path,
ensuring trade events generate appropriate notifications.
"""

from execution.alerts.integration import ExecutionAlertIntegration

__all__ = ["ExecutionAlertIntegration"]
