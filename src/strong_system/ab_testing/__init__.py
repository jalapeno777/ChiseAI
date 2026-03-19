"""A/B testing framework for STRONG.

Provides champion/challenger A/B testing capabilities with deterministic
traffic splitting, configurable test parameters, and full lifecycle management.

Example:
    >>> from src.strong_system.ab_testing import ABTestConfig, ABTestFramework
    >>> framework = ABTestFramework()
    >>> config = ABTestConfig(
    ...     test_id="test_001",
    ...     champion_version="v1.0",
    ...     challenger_version="v2.0",
    ...     traffic_split_percent=50,
    ...     metrics_to_track=["accuracy", "latency"],
    ...     min_sample_size=1000,
    ...     max_duration_hours=168,
    ... )
    >>> framework.create_test(config)
    >>> assignment = framework.get_traffic_assignment("test_001", "user_123")
    >>> print(assignment)  # 'champion' or 'challenger'
"""

from __future__ import annotations

from .framework import (
    ABTestConfig,
    ABTestFramework,
    ABTestResult,
    ABTestStatus,
    WinnerSelectionStrategy,
)

__all__ = [
    "ABTestConfig",
    "ABTestFramework",
    "ABTestResult",
    "ABTestStatus",
    "WinnerSelectionStrategy",
]
