"""
Task Decomposition Sentinel Module.

This module provides task size validation and decomposition enforcement
to prevent oversized tasks from being committed without proper approval.

Feature Flag: chise:feature_flags:governance:task_sentinel_active
"""

from .task_sentinel import TaskSentinel, SentinelConfig

__all__ = ["TaskSentinel", "SentinelConfig"]
