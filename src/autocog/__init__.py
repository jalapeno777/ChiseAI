"""Autocog Belief Expansion Module.

Provides timeboxed belief expansion for autonomous cognition.
"""

from .belief_expansion import (
    BELIEF_EXPANSION_COLLECTION,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TIME_LIMIT_SECONDS,
    ExpandedBelief,
    ExpansionConfig,
    ExpansionProgress,
    ExpansionResult,
    ExpansionType,
)

__all__ = [
    "ExpansionConfig",
    "ExpansionProgress",
    "ExpansionResult",
    "ExpansionType",
    "ExpandedBelief",
    "DEFAULT_TIME_LIMIT_SECONDS",
    "DEFAULT_MIN_RELEVANCE_SCORE",
    "DEFAULT_MIN_CONFIDENCE",
    "BELIEF_EXPANSION_COLLECTION",
]
