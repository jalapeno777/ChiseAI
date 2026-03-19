"""
Constitutional governance module for STRONG system.

This module provides:
- ConstraintEngine: Framework for evaluating system outputs against constitutional constraints
- Self-critique generation for AI safety
- Actionable feedback for constraint violations
"""

from .constraints import (
    Constraint,
    ConstraintCategory,
    ConstraintEngine,
    ConstraintSeverity,
    ConstraintViolation,
)
from .critique import (
    Critique,
    CritiqueAccuracy,
    CritiqueGenerator,
    CritiqueResult,
)

__all__ = [
    "Constraint",
    "ConstraintViolation",
    "ConstraintEngine",
    "ConstraintCategory",
    "ConstraintSeverity",
    "Critique",
    "CritiqueGenerator",
    "CritiqueResult",
    "CritiqueAccuracy",
]
