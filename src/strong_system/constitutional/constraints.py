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

    id: str
    name: str
    description: str
    category: ConstraintCategory
    severity: ConstraintSeverity
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
