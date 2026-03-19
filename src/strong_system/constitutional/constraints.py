<<<<<<< HEAD
"""
Constitutional constraint framework for STRONG system.

This module provides the constraint engine for evaluating system outputs
against constitutional constraints. Implements 11 core constraints for
AI safety and governance.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConstraintCategory(Enum):
    """Categories of constitutional constraints."""

    SAFETY = "safety"
    TRANSPARENCY = "transparency"
    FAIRNESS = "fairness"
    PRIVACY = "privacy"
    SECURITY = "security"
    ROBUSTNESS = "robustness"
    ACCOUNTABILITY = "accountability"
    HUMAN_OVERRIDE = "human_override"
    EXPLAINABILITY = "explainability"
    BOUNDED_SCOPE = "bounded_scope"
    AUDITABILITY = "auditability"


class ConstraintSeverity(Enum):
    """Severity levels for constraint violations."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ConstraintViolation:
    """Represents a constraint violation."""

    constraint_id: str
    constraint_name: str
    category: ConstraintCategory
    severity: ConstraintSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary."""
        return {
            "constraint_id": self.constraint_id,
            "constraint_name": self.constraint_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class Constraint:
    """A constitutional constraint definition."""
=======
"""Constitutional constraints framework for AI output governance.

Defines constraint types, evaluation logic, violation detection, and trend
tracking to ensure STRONG system outputs adhere to constitutional principles.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Protocol


class ConstraintSeverity(Enum):
    """Severity levels for constraint violations.

    CRITICAL violations indicate outputs that must never be produced.
    HIGH violations indicate significant safety or ethical concerns.
    MEDIUM violations indicate operational concerns needing attention.
    LOW violations indicate minor deviations from best practices.
    """

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


class ConstraintCategory(Enum):
    """Categories of constitutional constraints.

    Each category groups related constraints that govern a specific
    aspect of AI output quality and safety.
    """

    SAFETY = auto()
    TRANSPARENCY = auto()
    FAIRNESS = auto()
    ACCURACY = auto()
    PRIVACY = auto()
    ACCOUNTABILITY = auto()
    ROBUSTNESS = auto()
    HARMONIZATION = auto()
    TEMPORAL_CONSISTENCY = auto()
    SCOPE_BOUNDARY = auto()
    OPERATIONAL = auto()
    ETHICAL = auto()


@dataclass
class ConstitutionalConstraint:
    """Definition of a single constitutional constraint.

    Attributes:
        id: Unique identifier for the constraint (e.g., "CC-SAFETY-001")
        name: Human-readable constraint name
        description: Detailed description of what the constraint enforces
        category: The category this constraint belongs to
        severity: Severity level if violated
        check_pattern: Regex pattern or keyword list to detect violations
        threshold: Threshold for numeric-based checks
        is_active: Whether the constraint is currently active
        metadata: Additional metadata about the constraint
    """
>>>>>>> feature/STRONG-003-B-constraints

    id: str
    name: str
    description: str
    category: ConstraintCategory
    severity: ConstraintSeverity
<<<<<<< HEAD
    check_fn: Callable[[str], tuple[bool, str | None]]
    suggested_fix_template: str = ""

    def evaluate(self, output: str) -> tuple[bool, ConstraintViolation | None]:
        """
        Evaluate output against this constraint.

        Returns:
            Tuple of (is_satisfied, violation_if_not)
        """
        is_satisfied, details = self.check_fn(output)

        if is_satisfied:
            return True, None

        violation = ConstraintViolation(
            constraint_id=self.id,
            constraint_name=self.name,
            category=self.category,
            severity=self.severity,
            message=details or f"Constraint {self.id} violated",
            details={"output_length": len(output)} if details is None else {},
            suggested_fix=(
                self.suggested_fix_template.format(output=output[:100])
                if self.suggested_fix_template
                else None
            ),
        )
        return False, violation


class ConstraintEngine:
    """
    Engine for evaluating system outputs against constitutional constraints.

    Implements 11 core constraints for AI safety:
    1. SAFETY - No harmful outputs
    2. TRANSPARENCY - Clear reasoning
    3. FAIRNESS - Unbiased outputs
    4. PRIVACY - No sensitive data leakage
    5. SECURITY - No security vulnerabilities
    6. ROBUSTNESS - Handle edge cases
    7. ACCOUNTABILITY - Traceable decisions
    8. HUMAN_OVERRIDE - Allow human intervention
    9. EXPLAINABILITY - Justify outputs
    10. BOUNDED_SCOPE - Stay within scope
    11. AUDITABILITY - Log decisions
    """

    def __init__(self):
        """Initialize the constraint engine with all 11 constraints."""
        self.constraints: list[Constraint] = []
        self._register_constraints()

    def _register_constraints(self) -> None:
        """Register all 11 constitutional constraints."""

        # 1. SAFETY - No harmful outputs
        self.constraints.append(
            Constraint(
                id="CONST_001",
                name="Safety Constraint",
                description="Output must not contain harmful content",
                category=ConstraintCategory.SAFETY,
                severity=ConstraintSeverity.CRITICAL,
                check_fn=self._check_safety,
                suggested_fix_template="Remove harmful content from output",
            )
        )

        # 2. TRANSPARENCY - Clear reasoning
        self.constraints.append(
            Constraint(
                id="CONST_002",
                name="Transparency Constraint",
                description="Output must include clear reasoning",
                category=ConstraintCategory.TRANSPARENCY,
                severity=ConstraintSeverity.ERROR,
                check_fn=self._check_transparency,
                suggested_fix_template="Add reasoning explanation to output",
            )
        )

        # 3. FAIRNESS - Unbiased outputs
        self.constraints.append(
            Constraint(
                id="CONST_003",
                name="Fairness Constraint",
                description="Output must not contain biased content",
                category=ConstraintCategory.FAIRNESS,
                severity=ConstraintSeverity.ERROR,
                check_fn=self._check_fairness,
                suggested_fix_template="Review and remove biased language",
            )
        )

        # 4. PRIVACY - No sensitive data leakage
        self.constraints.append(
            Constraint(
                id="CONST_004",
                name="Privacy Constraint",
                description="Output must not leak sensitive data",
                category=ConstraintCategory.PRIVACY,
                severity=ConstraintSeverity.CRITICAL,
                check_fn=self._check_privacy,
                suggested_fix_template="Redact sensitive information from output",
            )
        )

        # 5. SECURITY - No security vulnerabilities
        self.constraints.append(
            Constraint(
                id="CONST_005",
                name="Security Constraint",
                description="Output must not introduce security risks",
                category=ConstraintCategory.SECURITY,
                severity=ConstraintSeverity.CRITICAL,
                check_fn=self._check_security,
                suggested_fix_template="Fix security vulnerability in output",
            )
        )

        # 6. ROBUSTNESS - Handle edge cases
        self.constraints.append(
            Constraint(
                id="CONST_006",
                name="Robustness Constraint",
                description="Output must handle edge cases gracefully",
                category=ConstraintCategory.ROBUSTNESS,
                severity=ConstraintSeverity.WARNING,
                check_fn=self._check_robustness,
                suggested_fix_template="Add edge case handling to output",
            )
        )

        # 7. ACCOUNTABILITY - Traceable decisions
        self.constraints.append(
            Constraint(
                id="CONST_007",
                name="Accountability Constraint",
                description="Output must have traceable decision path",
                category=ConstraintCategory.ACCOUNTABILITY,
                severity=ConstraintSeverity.ERROR,
                check_fn=self._check_accountability,
                suggested_fix_template="Add decision trace to output",
            )
        )

        # 8. HUMAN_OVERRIDE - Allow human intervention
        self.constraints.append(
            Constraint(
                id="CONST_008",
                name="Human Override Constraint",
                description="Output must allow human override capability",
                category=ConstraintCategory.HUMAN_OVERRIDE,
                severity=ConstraintSeverity.WARNING,
                check_fn=self._check_human_override,
                suggested_fix_template="Add human override option to output",
            )
        )

        # 9. EXPLAINABILITY - Justify outputs
        self.constraints.append(
            Constraint(
                id="CONST_009",
                name="Explainability Constraint",
                description="Output must be explainable",
                category=ConstraintCategory.EXPLAINABILITY,
                severity=ConstraintSeverity.ERROR,
                check_fn=self._check_explainability,
                suggested_fix_template="Add explanation to output",
            )
        )

        # 10. BOUNDED_SCOPE - Stay within scope
        self.constraints.append(
            Constraint(
                id="CONST_010",
                name="Bounded Scope Constraint",
                description="Output must stay within defined scope",
                category=ConstraintCategory.BOUNDED_SCOPE,
                severity=ConstraintSeverity.ERROR,
                check_fn=self._check_bounded_scope,
                suggested_fix_template="Restrict output to defined scope",
            )
        )

        # 11. AUDITABILITY - Log decisions
        self.constraints.append(
            Constraint(
                id="CONST_011",
                name="Auditability Constraint",
                description="Output must be auditable",
                category=ConstraintCategory.AUDITABILITY,
                severity=ConstraintSeverity.WARNING,
                check_fn=self._check_auditability,
                suggested_fix_template="Add audit logging to output",
            )
        )

    def _check_safety(self, output: str) -> tuple[bool, str | None]:
        """Check for harmful content."""
        harmful_patterns = [
            r"hack",
            r"steal\s+(money|data|identity)",
            r"harm\s+(human|person|animal)",
            r"weaponize",
            r"malware",
            r"exploit\s+vulnerability",
        ]
        output_lower = output.lower()
        for pattern in harmful_patterns:
            if re.search(pattern, output_lower):
                return False, f"Found harmful content matching: {pattern}"
        return True, None

    def _check_transparency(self, output: str) -> tuple[bool, str | None]:
        """Check for clear reasoning."""
        reasoning_indicators = [
            "because",
            "therefore",
            "thus",
            "since",
            "reason",
            "explain",
        ]
        has_reasoning = any(
            indicator in output.lower() for indicator in reasoning_indicators
        )
        if not has_reasoning and len(output) > 100:
            return False, "Output lacks clear reasoning"
        return True, None

    def _check_fairness(self, output: str) -> tuple[bool, str | None]:
        """Check for biased content."""
        bias_patterns = [
            r"\b(bias|discriminat|stereotype)\b.*\w+",
            r"(women|men|black|white|asian|hispanic).*(inferior|superior|stupid|smart)",
            r"all\s+\w+\s+are\s+(bad|good|stupid)",
        ]
        output_lower = output.lower()
        for pattern in bias_patterns:
            if re.search(pattern, output_lower):
                return False, f"Found potential bias: {pattern}"
        return True, None

    def _check_privacy(self, output: str) -> tuple[bool, str | None]:
        """Check for sensitive data leakage."""
        sensitive_patterns = [
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
            r"\b\d{16}\b",  # Credit card
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
            r"password\s*[=:]\s*\S+",
            r"api[_-]?key\s*[=:]\s*\S+",
            r"secret\s*[=:]\s*\S+",
        ]
        for pattern in sensitive_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return False, f"Found potential sensitive data: {pattern}"
        return True, None

    def _check_security(self, output: str) -> tuple[bool, str | None]:
        """Check for security vulnerabilities."""
        security_issues = [
            r"eval\s*\(",
            r"exec\s*\(",
            r"__import__\s*\(",
            r"subprocess.*shell\s*=\s*True",
            r"password\s*=\s*['\"](?!.*<.*>).*['\"]",
            r"hack",
            r"breach",
            r"exploit",
        ]
        for pattern in security_issues:
            if re.search(pattern, output, re.IGNORECASE):
                return False, f"Found security issue: {pattern}"
        return True, None

    def _check_robustness(self, output: str) -> tuple[bool, str | None]:
        """Check for edge case handling."""
        # Check if output handles error cases
        error_handling = ["error", "exception", "fallback", "default", "unknown"]
        if len(output) > 200 and not any(
            word in output.lower() for word in error_handling
        ):
            return False, "Output may not handle edge cases"
        return True, None

    def _check_accountability(self, output: str) -> tuple[bool, str | None]:
        """Check for traceable decision path."""
        accountability_indicators = [
            "decision",
            "based on",
            "criteria",
            "analysis",
            "assessment",
            "conclusion",
            "recommendation",
            "reasoning",
        ]
        has_indicators = any(
            indicator in output.lower() for indicator in accountability_indicators
        )
        if not has_indicators and len(output) > 100:
            return False, "Output lacks accountability trace"
        return True, None

    def _check_human_override(self, output: str) -> tuple[bool, str | None]:
        """Check for human override capability."""
        override_indicators = [
            "human",
            "user",
            "override",
            "confirm",
            "approve",
            "review",
            "check",
            "verify",
            "manual",
        ]
        # Only check for longer outputs that make decisions
        if len(output) > 200:
            has_override = any(
                indicator in output.lower() for indicator in override_indicators
            )
            if not has_override:
                return False, "Output may not allow human override"
        return True, None

    def _check_explainability(self, output: str) -> tuple[bool, str | None]:
        """Check for explainability."""
        explain_indicators = [
            "explain",
            "reason",
            "because",
            "therefore",
            "thus",
            "means",
            "indicates",
            "suggests",
            "shows",
        ]
        if len(output) > 150:
            has_explain = any(
                indicator in output.lower() for indicator in explain_indicators
            )
            if not has_explain:
                return False, "Output may not be explainable"
        return True, None

    def _check_bounded_scope(self, output: str) -> tuple[bool, str | None]:
        """Check for bounded scope."""
        # Check for scope creep indicators
        scope_creep = ["unrelated", "outside scope", "beyond scope", "not relevant"]
        if any(phrase in output.lower() for phrase in scope_creep):
            return False, "Output may be outside scope"
        return True, None

    def _check_auditability(self, output: str) -> tuple[bool, str | None]:
        """Check for auditability."""
        audit_indicators = [
            "log",
            "record",
            "track",
            "timestamp",
            "version",
            "history",
            "audit",
            "trace",
            "id",
            "reference",
        ]
        # For important outputs, check for audit capability
        if len(output) > 300:
            has_audit = any(
                indicator in output.lower() for indicator in audit_indicators
            )
            if not has_audit:
                return False, "Output may not be auditable"
        return True, None

    def evaluate(self, output: str) -> list[ConstraintViolation]:
        """
        Evaluate output against all constraints.

        Returns:
            List of constraint violations (empty if all pass)
        """
        violations = []
        for constraint in self.constraints:
            is_satisfied, violation = constraint.evaluate(output)
            if not is_satisfied and violation:
                violations.append(violation)
        return violations

    def evaluate_with_score(
        self, output: str
    ) -> tuple[float, list[ConstraintViolation]]:
        """
        Evaluate output and return a compliance score.

        Returns:
            Tuple of (score 0-1, violations)
        """
        violations = self.evaluate(output)
        if not violations:
            return 1.0, []

        # Calculate score based on severity weights
        severity_weights = {
            ConstraintSeverity.CRITICAL: 0.3,
            ConstraintSeverity.ERROR: 0.2,
            ConstraintSeverity.WARNING: 0.1,
            ConstraintSeverity.INFO: 0.05,
        }

        total_weight = sum(severity_weights[v.severity] for v in violations)
        score = max(0.0, 1.0 - total_weight)

        return score, violations

    def get_constraint_by_id(self, constraint_id: str) -> Constraint | None:
        """Get constraint by ID."""
        for constraint in self.constraints:
            if constraint.id == constraint_id:
                return constraint
        return None

    def get_constraints_by_category(
        self, category: ConstraintCategory
    ) -> list[Constraint]:
        """Get all constraints in a category."""
        return [c for c in self.constraints if c.category == category]

    def get_all_constraint_ids(self) -> list[str]:
        """Get all constraint IDs."""
        return [c.id for c in self.constraints]
=======
    check_pattern: str | list[str] | None = None
    threshold: float | None = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate constraint fields."""
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Constraint ID must be a non-empty string")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Constraint name must be a non-empty string")
        if not self.description:
            raise ValueError("Constraint description must not be empty")

    def check(self, output: str, context: dict[str, Any] | None = None) -> bool:
        """Check if the output violates this constraint.

        Args:
            output: The AI output text to evaluate
            context: Optional context dictionary with additional data

        Returns:
            True if the output violates this constraint, False otherwise
        """
        if not self.is_active:
            return False

        ctx = context or {}

        # Pattern-based check
        if self.check_pattern is not None:
            return self._check_pattern(output, ctx)

        # Threshold-based check
        if self.threshold is not None:
            return self._check_threshold(output, ctx)

        return False

    def _check_pattern(self, output: str, context: dict[str, Any]) -> bool:
        """Check output against pattern-based rules."""
        if isinstance(self.check_pattern, str):
            # Single regex pattern
            return bool(re.search(self.check_pattern, output, re.IGNORECASE))
        if isinstance(self.check_pattern, list):
            # List of keywords/phrases
            output_lower = output.lower()
            return any(kw.lower() in output_lower for kw in self.check_pattern)
        return False

    def _check_threshold(self, output: str, context: dict[str, Any]) -> bool:
        """Check output against threshold-based rules."""
        if "confidence" in context and self.threshold is not None:
            return context["confidence"] > self.threshold
        if "certainty_score" in context and self.threshold is not None:
            return context["certainty_score"] > self.threshold
        if "numeric_value" in context and self.threshold is not None:
            return context["numeric_value"] > self.threshold
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert constraint to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.name,
            "severity": self.severity.name,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


@dataclass
class ConstraintViolation:
    """Record of a single constraint violation.

    Attributes:
        constraint_id: ID of the violated constraint
        constraint_name: Name of the violated constraint
        category: Category of the violated constraint
        severity: Severity of the violation
        output_excerpt: Excerpt from the output that triggered the violation
        timestamp: When the violation was detected
        context: The evaluation context at time of violation
    """

    constraint_id: str
    constraint_name: str
    category: ConstraintCategory
    severity: ConstraintSeverity
    output_excerpt: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary representation."""
        return {
            "constraint_id": self.constraint_id,
            "constraint_name": self.constraint_name,
            "category": self.category.name,
            "severity": self.severity.name,
            "output_excerpt": self.output_excerpt,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConstraintEvaluation:
    """Result of evaluating an output against all constraints.

    Attributes:
        passed: Whether the evaluation passed (no violations)
        violations: List of detected violations
        total_constraints_checked: Total number of constraints evaluated
        passed_constraints: Number of constraints that passed
        failed_constraints: Number of constraints that failed
        evaluation_timestamp: When the evaluation was performed
        output_hash: Hash of the evaluated output for traceability
        severity_summary: Count of violations per severity level
    """

    passed: bool
    violations: list[ConstraintViolation]
    total_constraints_checked: int
    passed_constraints: int
    failed_constraints: int
    evaluation_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    output_hash: str = ""
    severity_summary: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute severity summary."""
        if not self.severity_summary and self.violations:
            self.severity_summary = {}
            for violation in self.violations:
                key = violation.severity.name
                self.severity_summary[key] = self.severity_summary.get(key, 0) + 1

    @property
    def has_critical_violations(self) -> bool:
        """Check if any critical violations exist."""
        return any(v.severity == ConstraintSeverity.CRITICAL for v in self.violations)

    @property
    def has_high_violations(self) -> bool:
        """Check if any high-severity violations exist."""
        return any(v.severity == ConstraintSeverity.HIGH for v in self.violations)

    @property
    def violation_rate(self) -> float:
        """Compute the ratio of failed to total constraints."""
        if self.total_constraints_checked == 0:
            return 0.0
        return self.failed_constraints / self.total_constraints_checked

    def to_dict(self) -> dict[str, Any]:
        """Convert evaluation to dictionary representation."""
        return {
            "passed": self.passed,
            "total_constraints_checked": self.total_constraints_checked,
            "passed_constraints": self.passed_constraints,
            "failed_constraints": self.failed_constraints,
            "violation_rate": round(self.violation_rate, 4),
            "has_critical_violations": self.has_critical_violations,
            "has_high_violations": self.has_high_violations,
            "severity_summary": self.severity_summary,
            "evaluation_timestamp": self.evaluation_timestamp.isoformat(),
            "violations": [v.to_dict() for v in self.violations],
        }


@dataclass
class ViolationTrend:
    """Tracks violation patterns over time for trend analysis.

    Maintains a rolling window of evaluation results and computes
    trend metrics to identify worsening or improving compliance.

    Attributes:
        max_history_size: Maximum number of evaluations to keep in history
        history: Deque of recent evaluation results
        trend_direction: Current trend direction
        trend_slope: Numeric slope of violation rate trend
    """

    max_history_size: int = 1000
    history: deque[ConstraintEvaluation] = field(default_factory=deque)
    trend_direction: str = "stable"
    trend_slope: float = 0.0

    def __post_init__(self) -> None:
        """Ensure history deque respects max_history_size."""
        if self.history.maxlen != self.max_history_size:
            self.history = deque(self.history, maxlen=self.max_history_size)

    def record(self, evaluation: ConstraintEvaluation) -> None:
        """Record a new evaluation and update trend metrics.

        Args:
            evaluation: The evaluation result to record
        """
        self.history.append(evaluation)
        self._update_trend()

    def _update_trend(self) -> None:
        """Update trend direction and slope based on recent history."""
        if len(self.history) < 3:
            self.trend_direction = "insufficient_data"
            self.trend_slope = 0.0
            return

        # Compute violation rates for recent window
        window_size = min(10, len(self.history))
        recent_rates = [
            list(self.history)[-i].violation_rate for i in range(window_size, 0, -1)
        ]

        # Simple linear regression slope
        n = len(recent_rates)
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent_rates) / n

        numerator = sum(
            (i - x_mean) * (rate - y_mean) for i, rate in enumerate(recent_rates)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            self.trend_slope = 0.0
        else:
            self.trend_slope = numerator / denominator

        # Determine trend direction
        if abs(self.trend_slope) < 0.005:
            self.trend_direction = "stable"
        elif self.trend_slope > 0:
            self.trend_direction = "worsening"
        else:
            self.trend_direction = "improving"

    @property
    def total_evaluations(self) -> int:
        """Total number of evaluations recorded."""
        return len(self.history)

    @property
    def total_violations(self) -> int:
        """Total violations across all evaluations."""
        return sum(len(e.violations) for e in self.history)

    @property
    def average_violation_rate(self) -> float:
        """Average violation rate across all evaluations."""
        if not self.history:
            return 0.0
        return sum(e.violation_rate for e in self.history) / len(self.history)

    @property
    def critical_violation_count(self) -> int:
        """Count of critical violations in history."""
        return sum(
            1
            for e in self.history
            for v in e.violations
            if v.severity == ConstraintSeverity.CRITICAL
        )

    def recent_violation_count(self, window: int = 10) -> int:
        """Count violations in the most recent N evaluations.

        Args:
            window: Number of recent evaluations to consider

        Returns:
            Total violation count in the window
        """
        recent = (
            list(self.history)[-window:]
            if len(self.history) >= window
            else list(self.history)
        )
        return sum(len(e.violations) for e in recent)

    def get_category_breakdown(self) -> dict[str, int]:
        """Get violation counts broken down by constraint category.

        Returns:
            Dictionary mapping category names to violation counts
        """
        breakdown: dict[str, int] = {}
        for evaluation in self.history:
            for violation in evaluation.violations:
                cat = violation.category.name
                breakdown[cat] = breakdown.get(cat, 0) + 1
        return breakdown

    def to_dict(self) -> dict[str, Any]:
        """Convert trend data to dictionary representation."""
        return {
            "total_evaluations": self.total_evaluations,
            "total_violations": self.total_violations,
            "average_violation_rate": round(self.average_violation_rate, 4),
            "critical_violation_count": self.critical_violation_count,
            "trend_direction": self.trend_direction,
            "trend_slope": round(self.trend_slope, 6),
            "category_breakdown": self.get_category_breakdown(),
        }


class OutputEvaluator(Protocol):
    """Protocol for objects that produce outputs for constraint evaluation.

    This enables integration with the STRONG system's hypothesis
    generator and other output-producing components.
    """

    def get_output(self) -> str:
        """Return the output text to evaluate."""
        ...

    def get_context(self) -> dict[str, Any]:
        """Return the evaluation context."""
        ...


class ConstraintEngine:
    """Main engine for evaluating outputs against constitutional constraints.

    Manages constraint registry, performs evaluations, detects violations,
    and tracks trends over time.

    Attributes:
        constraints: Registry of all loaded constraints
        violation_trend: Trend tracker for violation patterns
        strict_mode: If True, any violation causes evaluation to fail
        category_filter: Optional filter to only evaluate specific categories

    Example:
        >>> engine = ConstraintEngine()
        >>> result = engine.evaluate(
        ...     output="This will definitely make you rich!",
        ...     context={"domain": "trading"},
        ... )
        >>> print(f"Passed: {result.passed}")
    """

    def __init__(
        self,
        constraints: list[ConstitutionalConstraint] | None = None,
        strict_mode: bool = True,
        category_filter: list[ConstraintCategory] | None = None,
    ) -> None:
        """Initialize the constraint engine.

        Args:
            constraints: Initial set of constraints (defaults to built-in set)
            strict_mode: Whether any violation causes failure
            category_filter: Optional filter for specific constraint categories
        """
        self.constraints: dict[str, ConstitutionalConstraint] = {}
        self.violation_trend = ViolationTrend()
        self.strict_mode = strict_mode
        self.category_filter = category_filter

        if constraints is None:
            self._load_default_constraints()
        else:
            for constraint in constraints:
                self.register(constraint)

    def register(self, constraint: ConstitutionalConstraint) -> None:
        """Register a new constraint.

        Args:
            constraint: The constraint to register

        Raises:
            ValueError: If a constraint with the same ID already exists
        """
        if constraint.id in self.constraints:
            raise ValueError(f"Constraint '{constraint.id}' already registered")
        self.constraints[constraint.id] = constraint

    def unregister(self, constraint_id: str) -> bool:
        """Unregister a constraint by ID.

        Args:
            constraint_id: ID of the constraint to remove

        Returns:
            True if the constraint was found and removed, False otherwise
        """
        if constraint_id in self.constraints:
            del self.constraints[constraint_id]
            return True
        return False

    def activate(self, constraint_id: str) -> bool:
        """Activate a constraint.

        Args:
            constraint_id: ID of the constraint to activate

        Returns:
            True if the constraint was found and activated
        """
        if constraint_id in self.constraints:
            self.constraints[constraint_id].is_active = True
            return True
        return False

    def deactivate(self, constraint_id: str) -> bool:
        """Deactivate a constraint without removing it.

        Args:
            constraint_id: ID of the constraint to deactivate

        Returns:
            True if the constraint was found and deactivated
        """
        if constraint_id in self.constraints:
            self.constraints[constraint_id].is_active = False
            return True
        return False

    def evaluate(
        self,
        output: str,
        context: dict[str, Any] | None = None,
        track_trend: bool = True,
    ) -> ConstraintEvaluation:
        """Evaluate an output against all registered constraints.

        Args:
            output: The text output to evaluate
            context: Optional evaluation context (domain, confidence, etc.)
            track_trend: Whether to record the evaluation in trend tracking

        Returns:
            ConstraintEvaluation with full results
        """
        violations: list[ConstraintViolation] = []
        passed_count = 0
        total_checked = 0
        ctx = context or {}

        for constraint in self.constraints.values():
            # Skip inactive constraints
            if not constraint.is_active:
                continue

            # Skip if category filter is set and doesn't match
            if (
                self.category_filter is not None
                and constraint.category not in self.category_filter
            ):
                continue

            total_checked += 1

            if constraint.check(output, ctx):
                # Constraint was violated
                excerpt = self._extract_excerpt(output, constraint)
                violation = ConstraintViolation(
                    constraint_id=constraint.id,
                    constraint_name=constraint.name,
                    category=constraint.category,
                    severity=constraint.severity,
                    output_excerpt=excerpt,
                    context=ctx,
                )
                violations.append(violation)
            else:
                passed_count += 1

        failed_count = len(violations)

        # Determine if evaluation passed
        if self.strict_mode:
            passed = len(violations) == 0
        else:
            passed = not any(
                v.severity in (ConstraintSeverity.CRITICAL, ConstraintSeverity.HIGH)
                for v in violations
            )

        evaluation = ConstraintEvaluation(
            passed=passed,
            violations=violations,
            total_constraints_checked=total_checked,
            passed_constraints=passed_count,
            failed_constraints=failed_count,
            output_hash=self._compute_hash(output),
        )

        if track_trend:
            self.violation_trend.record(evaluation)

        return evaluation

    def evaluate_output_source(
        self,
        source: OutputEvaluator,
        track_trend: bool = True,
    ) -> ConstraintEvaluation:
        """Evaluate an output from an OutputEvaluator protocol object.

        Enables integration with STRONG system components.

        Args:
            source: Object implementing OutputEvaluator protocol
            track_trend: Whether to record in trend tracking

        Returns:
            ConstraintEvaluation with full results
        """
        return self.evaluate(
            output=source.get_output(),
            context=source.get_context(),
            track_trend=track_trend,
        )

    def get_constraint(self, constraint_id: str) -> ConstitutionalConstraint | None:
        """Retrieve a constraint by ID.

        Args:
            constraint_id: ID of the constraint to retrieve

        Returns:
            The constraint if found, None otherwise
        """
        return self.constraints.get(constraint_id)

    def get_constraints_by_category(
        self, category: ConstraintCategory
    ) -> list[ConstitutionalConstraint]:
        """Get all constraints in a specific category.

        Args:
            category: The category to filter by

        Returns:
            List of constraints in the category
        """
        return [c for c in self.constraints.values() if c.category == category]

    def get_active_constraint_count(self) -> int:
        """Count of currently active constraints.

        Returns:
            Number of active constraints
        """
        return sum(1 for c in self.constraints.values() if c.is_active)

    def get_trend_report(self) -> dict[str, Any]:
        """Get a comprehensive trend report.

        Returns:
            Dictionary with trend metrics and category breakdown
        """
        return {
            "total_constraints": len(self.constraints),
            "active_constraints": self.get_active_constraint_count(),
            "strict_mode": self.strict_mode,
            "trend": self.violation_trend.to_dict(),
        }

    def reset_trend(self) -> None:
        """Reset the violation trend history."""
        self.violation_trend = ViolationTrend(
            max_history_size=self.violation_trend.max_history_size
        )

    def _load_default_constraints(self) -> None:
        """Load the default set of constitutional constraints."""
        for constraint in build_default_constraints():
            self.register(constraint)

    @staticmethod
    def _extract_excerpt(output: str, constraint: ConstitutionalConstraint) -> str:
        """Extract a relevant excerpt from the output for the violation.

        Args:
            output: The full output text
            constraint: The constraint that was violated

        Returns:
            An excerpt from the output relevant to the violation
        """
        if constraint.check_pattern is None:
            return output[:200] + "..." if len(output) > 200 else output

        if isinstance(constraint.check_pattern, list):
            for keyword in constraint.check_pattern:
                idx = output.lower().find(keyword.lower())
                if idx != -1:
                    start = max(0, idx - 30)
                    end = min(len(output), idx + len(keyword) + 30)
                    excerpt = output[start:end]
                    if start > 0:
                        excerpt = "..." + excerpt
                    if end < len(output):
                        excerpt = excerpt + "..."
                    return excerpt

        if isinstance(constraint.check_pattern, str):
            match = re.search(constraint.check_pattern, output, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 30)
                end = min(len(output), match.end() + 30)
                excerpt = output[start:end]
                if start > 0:
                    excerpt = "..." + excerpt
                if end < len(output):
                    excerpt = excerpt + "..."
                return excerpt

        return output[:200] + "..." if len(output) > 200 else output

    @staticmethod
    def _compute_hash(output: str) -> str:
        """Compute a simple hash of the output for traceability.

        Args:
            output: The output text to hash

        Returns:
            Hexadecimal hash string
        """
        return str(hash(output))


def build_default_constraints() -> list[ConstitutionalConstraint]:
    """Build the default set of 12 constitutional constraints.

    These constraints cover safety, transparency, fairness, accuracy,
    privacy, accountability, robustness, and operational guardrails.

    Returns:
        List of default ConstitutionalConstraint instances
    """
    return [
        # --- SAFETY (3 constraints) ---
        ConstitutionalConstraint(
            id="CC-SAFETY-001",
            name="No Financial Guarantees",
            description="Outputs must not guarantee financial returns or promise profits",
            category=ConstraintCategory.SAFETY,
            severity=ConstraintSeverity.CRITICAL,
            check_pattern=[
                "guaranteed return",
                "guaranteed profit",
                "risk-free profit",
                "guaranteed to make money",
                "can't lose",
                "will definitely profit",
                "guaranteed gain",
                "sure thing profit",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        ConstitutionalConstraint(
            id="CC-SAFETY-002",
            name="No Excessive Leverage Advice",
            description="Outputs must not recommend extreme leverage or position sizes",
            category=ConstraintCategory.SAFETY,
            severity=ConstraintSeverity.HIGH,
            check_pattern=[
                "100x leverage",
                "maximum leverage",
                "all-in",
                "bet everything",
                "put all your money",
                "margin your entire",
                "full leverage",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        ConstitutionalConstraint(
            id="CC-SAFETY-003",
            name="No Manipulation Encouragement",
            description="Outputs must not encourage market manipulation or illegal activities",
            category=ConstraintCategory.SAFETY,
            severity=ConstraintSeverity.CRITICAL,
            check_pattern=[
                "manipulate the market",
                "pump and dump",
                "paint the tape",
                "wash trading",
                "spoofing",
                "front-running",
                "insider trading",
                "market manipulation",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        # --- TRANSPARENCY (2 constraints) ---
        ConstitutionalConstraint(
            id="CC-TRANSP-001",
            name="Confidence Disclosure Required",
            description="High-confidence claims must include confidence scores",
            category=ConstraintCategory.TRANSPARENCY,
            severity=ConstraintSeverity.MEDIUM,
            check_pattern=r"(definitely|certainly|absolutely|without doubt|for sure)\s+(will|is going to|shall)",
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        ConstitutionalConstraint(
            id="CC-TRANSP-002",
            name="Source Attribution",
            description="Outputs claiming data-backed insights should reference data sources",
            category=ConstraintCategory.TRANSPARENCY,
            severity=ConstraintSeverity.LOW,
            check_pattern=[
                "data shows",
                "according to data",
                "based on data",
                "data indicates",
                "data confirms",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        # --- ACCURACY (2 constraints) ---
        ConstitutionalConstraint(
            id="CC-ACCUR-001",
            name="No Hallucinated Precision",
            description="Outputs must not present imprecise data as exact figures",
            category=ConstraintCategory.ACCURACY,
            severity=ConstraintSeverity.HIGH,
            check_pattern=r"\b\d+\.\d{4,}\b.*?(percent|%)",
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        ConstitutionalConstraint(
            id="CC-ACCUR-002",
            name="Overconfidence Threshold",
            description="Flag outputs with confidence scores above 0.95 as overconfident",
            category=ConstraintCategory.ACCURACY,
            severity=ConstraintSeverity.MEDIUM,
            threshold=0.95,
            metadata={
                "version": "1.0",
                "owner": "STRONG-003-B",
                "check_key": "confidence",
            },
        ),
        # --- FAIRNESS (1 constraint) ---
        ConstitutionalConstraint(
            id="CC-FAIR-001",
            name="No Discriminatory Content",
            description="Outputs must not contain discriminatory or biased language",
            category=ConstraintCategory.FAIRNESS,
            severity=ConstraintSeverity.CRITICAL,
            check_pattern=[
                "inferior market",
                "superior market",
                "dumb money",
                "smart money only",
                "retail is stupid",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        # --- ACCOUNTABILITY (1 constraint) ---
        ConstitutionalConstraint(
            id="CC-ACCT-001",
            name="No Absolution of Responsibility",
            description="Outputs must not absolve the system of responsibility for bad advice",
            category=ConstraintCategory.ACCOUNTABILITY,
            severity=ConstraintSeverity.HIGH,
            check_pattern=[
                "not my fault",
                "blame the market",
                "i take no responsibility",
                "at your own risk only",
                "don't hold me liable",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        # --- ROBUSTNESS (1 constraint) ---
        ConstitutionalConstraint(
            id="CC-ROBUST-001",
            name="No Single-Point Reasoning",
            description="Outputs must not rely on a single indicator or data point",
            category=ConstraintCategory.ROBUSTNESS,
            severity=ConstraintSeverity.MEDIUM,
            check_pattern=[
                "only indicator",
                "sole reason",
                "single indicator shows",
                "the only signal",
                "just one indicator",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
        # --- PRIVACY (1 constraint) ---
        ConstitutionalConstraint(
            id="CC-PRIV-001",
            name="No Personal Data Exposure",
            description="Outputs must not contain or reference personal user data",
            category=ConstraintCategory.PRIVACY,
            severity=ConstraintSeverity.CRITICAL,
            check_pattern=[
                "user's email",
                "user's phone",
                "user's address",
                "personal information",
                "social security",
                "bank account number",
            ],
            metadata={"version": "1.0", "owner": "STRONG-003-B"},
        ),
    ]
>>>>>>> feature/STRONG-003-B-constraints
