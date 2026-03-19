"""
Self-critique generation engine for STRONG system.

This module provides:
- Critique: Data class for critique results
- CritiqueGenerator: Generates self-critiques for system outputs
- CritiqueResult: Structured result of critique generation
- CritiqueAccuracy: Tracks and calculates critique accuracy metrics
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .constraints import (
    ConstraintCategory,
    ConstraintEngine,
    ConstraintSeverity,
    ConstraintViolation,
)


class CritiqueType(Enum):
    """Types of critique."""

    SAFETY = "safety"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    IMPROVEMENT = "improvement"
    VERIFICATION = "verification"


class CritiqueStatus(Enum):
    """Status of the critique."""

    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"


@dataclass
class Critique:
    """A single critique item."""

    critique_id: str
    critique_type: CritiqueType
    status: CritiqueStatus
    message: str
    constraint_id: str | None = None
    severity: ConstraintSeverity | None = None
    suggested_fix: str | None = None
    confidence: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert critique to dictionary."""
        return {
            "critique_id": self.critique_id,
            "critique_type": self.critique_type.value,
            "status": self.status.value,
            "message": self.message,
            "constraint_id": self.constraint_id,
            "severity": self.severity.value if self.severity else None,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
            "details": self.details,
        }


@dataclass
class CritiqueResult:
    """Result of a critique generation operation."""

    output: str
    critiques: list[Critique]
    violations: list[ConstraintViolation]
    compliance_score: float
    passed: bool
    needs_human_review: bool = False
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "output": (
                self.output[:100] + "..." if len(self.output) > 100 else self.output
            ),
            "critiques": [c.to_dict() for c in self.critiques],
            "violations": [v.to_dict() for v in self.violations],
            "compliance_score": self.compliance_score,
            "passed": self.passed,
            "needs_human_review": self.needs_human_review,
            "error_message": self.error_message,
        }

    def get_critique_count(self) -> int:
        """Get total critique count."""
        return len(self.critiques)

    def get_failed_count(self) -> int:
        """Get count of failed critiques."""
        return sum(1 for c in self.critiques if c.status == CritiqueStatus.FAILED)

    def get_passed_count(self) -> int:
        """Get count of passed critiques."""
        return sum(1 for c in self.critiques if c.status == CritiqueStatus.PASSED)


@dataclass
class CritiqueAccuracy:
    """Tracks critique accuracy metrics."""

    total_critiques: int = 0
    correct_critiques: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def accuracy(self) -> float:
        """Calculate accuracy percentage."""
        if self.total_critiques == 0:
            return 0.0
        return (self.correct_critiques / self.total_critiques) * 100

    @property
    def precision(self) -> float:
        """Calculate precision."""
        total_predicted = self.correct_critiques + self.false_positives
        if total_predicted == 0:
            return 0.0
        return (self.correct_critiques / total_predicted) * 100

    @property
    def recall(self) -> float:
        """Calculate recall."""
        total_actual = self.correct_critiques + self.false_negatives
        if total_actual == 0:
            return 0.0
        return (self.correct_critiques / total_actual) * 100

    @property
    def f1_score(self) -> float:
        """Calculate F1 score."""
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * (self.precision * self.recall) / (self.precision + self.recall)

    def record_critique(
        self,
        is_correct: bool,
        is_false_positive: bool = False,
        is_false_negative: bool = False,
    ) -> None:
        """Record a critique result."""
        self.total_critiques += 1
        if is_correct:
            self.correct_critiques += 1
        elif not is_false_positive and not is_false_negative:
            is_false_positive = True
        if is_false_positive:
            self.false_positives += 1
        if is_false_negative:
            self.false_negatives += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert accuracy metrics to dictionary."""
        return {
            "total_critiques": self.total_critiques,
            "correct_critiques": self.correct_critiques,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "accuracy": round(self.accuracy, 2),
            "precision": round(self.precision, 2),
            "recall": round(self.recall, 2),
            "f1_score": round(self.f1_score, 2),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.total_critiques = 0
        self.correct_critiques = 0
        self.false_positives = 0
        self.false_negatives = 0


class CritiqueGenerator:
    """
    Self-critique generation engine for AI safety.

    Generates actionable critiques for system outputs by:
    1. Evaluating against constitutional constraints
    2. Generating specific critique items
    3. Providing actionable feedback
    4. Tracking accuracy metrics
    """

    def __init__(self, constraint_engine: ConstraintEngine | None = None):
        """
        Initialize the critique generator.

        Args:
            constraint_engine: Optional constraint engine (creates default if not provided)
        """
        self.constraint_engine = constraint_engine or ConstraintEngine()
        self.accuracy = CritiqueAccuracy()
        self._critique_counter = 0

    def generate_critique(self, output: str) -> CritiqueResult:
        """
        Generate a self-critique for the given output.

        Args:
            output: The system output to critique

        Returns:
            CritiqueResult with all critiques and violations
        """
        self._critique_counter += 1

        try:
            # Evaluate against constraints
            violations = self.constraint_engine.evaluate(output)
            score, _ = self.constraint_engine.evaluate_with_score(output)

            # Generate critique items from violations
            critiques = self._generate_critiques(output, violations)

            # Determine overall status
            passed = len(violations) == 0
            needs_review = any(
                v.severity == ConstraintSeverity.CRITICAL for v in violations
            )

            # Record for accuracy tracking
            self.accuracy.record_critique(
                is_correct=passed,
                is_false_positive=not passed and len(violations) == 0,
                is_false_negative=passed and len(violations) > 0,
            )

            return CritiqueResult(
                output=output,
                critiques=critiques,
                violations=violations,
                compliance_score=score,
                passed=passed,
                needs_human_review=needs_review,
            )

        except Exception as e:
            return CritiqueResult(
                output=output,
                critiques=[],
                violations=[],
                compliance_score=0.0,
                passed=False,
                error_message=str(e),
            )

    def _generate_critiques(
        self, output: str, violations: list[ConstraintViolation]
    ) -> list[Critique]:
        """Generate critique items from violations."""
        critiques = []

        # Add a critique for each violation
        for violation in violations:
            critique = Critique(
                critique_id=f"CRITIQUE_{self._critique_counter}_{violation.constraint_id}",
                critique_type=self._map_category_to_type(violation.category),
                status=CritiqueStatus.FAILED,
                message=violation.message,
                constraint_id=violation.constraint_id,
                severity=violation.severity,
                suggested_fix=violation.suggested_fix,
                confidence=0.9,
                details=violation.details,
            )
            critiques.append(critique)

        # Add passing critiques for constraints that passed
        for constraint in self.constraint_engine.constraints:
            has_violation = any(v.constraint_id == constraint.id for v in violations)
            if not has_violation:
                critique = Critique(
                    critique_id=f"CRITIQUE_{self._critique_counter}_{constraint.id}_PASS",
                    critique_type=self._map_category_to_type(constraint.category),
                    status=CritiqueStatus.PASSED,
                    message=f"Constraint {constraint.id} ({constraint.name}) satisfied",
                    constraint_id=constraint.id,
                    severity=constraint.severity,
                    confidence=0.85,
                )
                critiques.append(critique)

        return critiques

    def _map_category_to_type(self, category: ConstraintCategory) -> CritiqueType:
        """Map constraint category to critique type."""
        mapping = {
            ConstraintCategory.SAFETY: CritiqueType.SAFETY,
            ConstraintCategory.TRANSPARENCY: CritiqueType.QUALITY,
            ConstraintCategory.FAIRNESS: CritiqueType.COMPLIANCE,
            ConstraintCategory.PRIVACY: CritiqueType.SAFETY,
            ConstraintCategory.SECURITY: CritiqueType.SAFETY,
            ConstraintCategory.ROBUSTNESS: CritiqueType.QUALITY,
            ConstraintCategory.ACCOUNTABILITY: CritiqueType.VERIFICATION,
            ConstraintCategory.HUMAN_OVERRIDE: CritiqueType.COMPLIANCE,
            ConstraintCategory.EXPLAINABILITY: CritiqueType.QUALITY,
            ConstraintCategory.BOUNDED_SCOPE: CritiqueType.COMPLIANCE,
            ConstraintCategory.AUDITABILITY: CritiqueType.VERIFICATION,
        }
        return mapping.get(category, CritiqueType.QUALITY)

    def generate_actionable_critique(self, output: str) -> str:
        """
        Generate a human-readable actionable critique.

        Args:
            output: The system output to critique

        Returns:
            Formatted critique string with actionable feedback
        """
        result = self.generate_critique(output)

        lines = ["=== Self-Critique Report ===", ""]

        # Summary
        status = "PASSED" if result.passed else "FAILED"
        lines.append(f"Status: {status}")
        lines.append(f"Compliance Score: {result.compliance_score:.1%}")
        lines.append(f"Total Critiques: {result.get_critique_count()}")
        lines.append(f"Passed: {result.get_passed_count()}")
        lines.append(f"Failed: {result.get_failed_count()}")
        lines.append("")

        if result.violations:
            lines.append("## Violations Found:")
            for v in result.violations:
                lines.append(f"  - [{v.severity.value.upper()}] {v.constraint_name}")
                lines.append(f"    {v.message}")
                if v.suggested_fix:
                    lines.append(f"    Fix: {v.suggested_fix}")
            lines.append("")

        if result.needs_human_review:
            lines.append("⚠️  Human review required for critical issues")

        return "\n".join(lines)

    def batch_critique(self, outputs: list[str]) -> list[CritiqueResult]:
        """
        Generate critiques for multiple outputs.

        Args:
            outputs: List of outputs to critique

        Returns:
            List of CritiqueResults
        """
        return [self.generate_critique(output) for output in outputs]

    def get_accuracy_metrics(self) -> dict[str, float]:
        """Get current accuracy metrics."""
        return self.accuracy.to_dict()

    def reset_accuracy(self) -> None:
        """Reset accuracy metrics."""
        self.accuracy.reset()

    def get_constraint_summary(self) -> dict[str, Any]:
        """Get summary of all constraints."""
        return {
            "total_constraints": len(self.constraint_engine.constraints),
            "constraints": [
                {
                    "id": c.id,
                    "name": c.name,
                    "category": c.category.value,
                    "severity": c.severity.value,
                }
                for c in self.constraint_engine.constraints
            ],
        }
