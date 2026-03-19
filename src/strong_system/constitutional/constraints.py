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

    id: str
    name: str
    description: str
    category: ConstraintCategory
    severity: ConstraintSeverity
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
