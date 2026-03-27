"""Autonomous Cognition Belief Expansion.

Provides timeboxed belief expansion for autonomous cognition.
"""

from .belief_expansion import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TIME_LIMIT_SECONDS,
    BELIEF_EXPANSION_COLLECTION,
    ExpansionConfig,
    ExpansionProgress,
    ExpansionResult,
    ExpansionType,
    ExpandedBelief,
)
from .engine import BeliefExpander, expand_beliefs

__all__ = [
    # belief_expansion exports
    "ExpansionConfig",
    "ExpansionProgress",
    "ExpansionResult",
    "ExpansionType",
    "ExpandedBelief",
    "DEFAULT_TIME_LIMIT_SECONDS",
    "DEFAULT_MIN_RELEVANCE_SCORE",
    "DEFAULT_MIN_CONFIDENCE",
    "BELIEF_EXPANSION_COLLECTION",
    # engine exports
    "BeliefExpander",
    "expand_beliefs",
]
