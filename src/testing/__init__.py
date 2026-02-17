"""Testing infrastructure for ChiseAI.

Provides chaos engineering tools, failure injection, and E2E testing
utilities for validating system resilience and recovery.

For PAPER-003-002: E2E Integration Testing with Chaos Engineering
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .chaos_engine import ChaosEngine, ChaosReport
    from .failure_injector import (
        ErrorInjector,
        FailureInjector,
        LatencyInjector,
        NetworkPartitionInjector,
        ServiceFailureInjector,
    )

__all__ = [
    "FailureInjector",
    "NetworkPartitionInjector",
    "ServiceFailureInjector",
    "LatencyInjector",
    "ErrorInjector",
    "ChaosEngine",
    "ChaosReport",
]
