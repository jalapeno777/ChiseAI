"""Belief Expansion Engine.

Provides core expansion logic for generating new beliefs from existing ones.
"""

from .engine import BeliefExpander, expand_beliefs

__all__ = ["BeliefExpander", "expand_beliefs"]
