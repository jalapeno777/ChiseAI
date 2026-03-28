"""Autonomous Cognition Belief Expansion.

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
from .engine import (
    BeliefExpander,
    belief_to_expanded_belief,
    expand_beliefs,
    expanded_belief_to_belief,
)

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
    # conversion exports
    "expanded_belief_to_belief",
    "belief_to_expanded_belief",
]
