"""
Memory governance module.

Provides tools for memory management, deduplication, and optimization.
"""

from .audit_capture import (
    MemoryHealthMetrics,
    MemoryHealthSummary,
    capture_baseline_metrics,
    get_memory_health_summary,
)
from .context_assembler import (
    MemoryContext,
    assert_no_runtime_staleness_compute_in_context,
    build_session_context,
)
from .deduplication import MemoryDeduplicationEngine
from .invariants import (
    StalenessComputeError,
    assert_no_runtime_staleness_compute,
    validate_payload_staleness,
)
from .observer import Observer
from .reflector_agent import Reflector, SupersededObservation
from .tiered_recall import (
    FEATURE_FLAG_KEY,
    L0_MAX_AGE_HOURS,
    L1_MAX_AGE_HOURS,
    L2_MAX_AGE_HOURS,
    FreshnessSummary,
    RecallEngine,
    TierContext,
)

__all__ = [
    # Context Assembler
    "MemoryContext",
    "build_session_context",
    "assert_no_runtime_staleness_compute_in_context",
    # Invariants
    "StalenessComputeError",
    "assert_no_runtime_staleness_compute",
    "validate_payload_staleness",
    # Audit Capture
    "MemoryHealthMetrics",
    "MemoryHealthSummary",
    "capture_baseline_metrics",
    "get_memory_health_summary",
    # Existing exports
    "MemoryDeduplicationEngine",
    "Observer",
    "RecallEngine",
    "Reflector",
    "SupersededObservation",
    "FreshnessSummary",
    "TierContext",
    # Constants
    "FEATURE_FLAG_KEY",
    "L0_MAX_AGE_HOURS",
    "L1_MAX_AGE_HOURS",
    "L2_MAX_AGE_HOURS",
    "FRESHNESS_SCORE_TTL",
]
