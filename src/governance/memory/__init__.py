"""
Memory governance module.

Provides tools for memory management, deduplication, and optimization.
"""

from .deduplication import MemoryDeduplicationEngine
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
