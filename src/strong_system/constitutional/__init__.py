"""Constitutional Constraints Module for STRONG Neuro-Symbolic AI System.

Provides a framework for defining, evaluating, and tracking constitutional
constraints on AI outputs. Ensures system outputs adhere to safety, transparency,
fairness, and operational guardrails defined by the constitutional framework.

Components:
    - ConstraintSeverity: Severity levels for constraint violations
    - ConstraintCategory: Categories of constitutional constraints
    - ConstitutionalConstraint: Definition of a single constraint
    - ConstraintEvaluation: Result of evaluating an output against constraints
    - ConstraintViolation: Record of a constraint violation
    - ViolationTrend: Tracking violation patterns over time
    - ConstraintEngine: Main engine for evaluating outputs against constraints

Example:
    >>> from src.strong_system.constitutional import (
    ...     ConstraintEngine,
    ...     ConstitutionalConstraint,
    ...     ConstraintCategory,
    ... )
    >>> engine = ConstraintEngine()
    >>> result = engine.evaluate(
    ...     output="The market will definitely go up by 50%",
    ...     context={"domain": "trading"},
    ... )
    >>> print(f"Violations: {len(result.violations)}")
"""

from __future__ import annotations

from src.strong_system.constitutional.constraints import (
    ConstitutionalConstraint,
    ConstraintCategory,
    ConstraintEngine,
    ConstraintEvaluation,
    ConstraintSeverity,
    ViolationTrend,
    build_default_constraints,
)

__all__ = [
    "ConstitutionalConstraint",
    "ConstraintCategory",
    "ConstraintEngine",
    "ConstraintEvaluation",
    "ConstraintSeverity",
    "ViolationTrend",
    "build_default_constraints",
]
