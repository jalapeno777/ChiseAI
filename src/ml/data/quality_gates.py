"""Quality Scoring and Quality Gates for ML Training Data.

This module provides quality scoring and threshold-based quality gates
for evaluating training data quality across multiple dimensions.

Components:
- QualityScore: Dataclass for quality evaluation results
- QualityGate: Class for evaluating quality against thresholds
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ml.data.validation import DataValidator, ValidationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QualityScore
# ---------------------------------------------------------------------------


@dataclass
class QualityScore:
    """Quality score result for a dataset.

    Attributes:
        overall_score: Overall quality score (0-100)
        category_scores: Dictionary of category scores (completeness, validity,
            consistency, timeliness, uniqueness)
        validation_pass_rate: Percentage of validation rules passed (0-1)
        anomaly_score: Anomaly score from drift/outlier detection (0-1)
        timestamp: When the score was computed
        dataset_id: Identifier for the dataset being evaluated
        details: Additional details about the evaluation
    """

    overall_score: float
    category_scores: dict[str, float]
    validation_pass_rate: float
    anomaly_score: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    dataset_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate score ranges."""
        self.overall_score = max(0.0, min(100.0, self.overall_score))
        self.validation_pass_rate = max(0.0, min(1.0, self.validation_pass_rate))
        self.anomaly_score = max(0.0, min(1.0, self.anomaly_score))
        for category in self.category_scores:
            self.category_scores[category] = max(
                0.0, min(100.0, self.category_scores[category])
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall_score": self.overall_score,
            "category_scores": self.category_scores,
            "validation_pass_rate": self.validation_pass_rate,
            "anomaly_score": self.anomaly_score,
            "timestamp": self.timestamp.isoformat(),
            "dataset_id": self.dataset_id,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# QualityGate
# ---------------------------------------------------------------------------


class QualityGate:
    """Quality gate for evaluating training data quality.

    Evaluates datasets against configurable thresholds across multiple
    quality categories and generates detailed reports.

    Usage:
        gate = QualityGate(min_score=80.0)
        score = gate.evaluate(dataset)
        passed = gate.check_threshold(score.overall_score, 80.0)
        report = gate.generate_report(score)
    """

    # Default category weights for overall score calculation
    DEFAULT_WEIGHTS = {
        "completeness": 0.25,
        "validity": 0.25,
        "consistency": 0.20,
        "timeliness": 0.15,
        "uniqueness": 0.15,
    }

    def __init__(
        self,
        min_score: float = 80.0,
        weights: dict[str, float] | None = None,
        validator: DataValidator | None = None,
    ) -> None:
        """Initialize quality gate.

        Args:
            min_score: Minimum acceptable overall quality score (0-100)
            weights: Category weights for overall score calculation.
                Must sum to 1.0. Defaults to DEFAULT_WEIGHTS.
            validator: Optional DataValidator instance for validation rules
        """
        self.min_score = min_score
        self.weights = weights or self.DEFAULT_WEIGHTS

        # Normalize weights
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

        self.validator = validator or DataValidator()
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up default validation rules if validator is empty."""
        if not self.validator.get_rules():
            from ml.data.validation import (
                DataFreshnessRule,
                NullCheckRule,
                RangeValidationRule,
                SchemaCompletenessRule,
                UniqueConstraintRule,
            )

            # Add essential rules
            self.validator.register_rule(
                SchemaCompletenessRule(
                    required_fields=["timestamp", "feature", "label"],
                    severity="error",
                )
            )
            self.validator.register_rule(
                NullCheckRule(fields=["timestamp", "feature", "label"])
            )
            self.validator.register_rule(
                RangeValidationRule(
                    field_ranges={"feature": {"min": -1e10, "max": 1e10}}
                )
            )

    def evaluate(self, dataset: Any, dataset_id: str = "") -> QualityScore:
        """Evaluate dataset quality.

        Args:
            dataset: Dataset to evaluate (list of dicts, DataFrame, or single dict)
            dataset_id: Optional identifier for the dataset

        Returns:
            QualityScore with evaluation results
        """
        # Run validation
        validation_results = self.validator.validate(dataset)

        # Calculate validation pass rate
        passed_count = sum(1 for r in validation_results if r.passed)
        total_count = len(validation_results)
        pass_rate = passed_count / total_count if total_count > 0 else 0.0

        # Calculate category scores
        category_scores = self._calculate_category_scores(dataset, validation_results)

        # Calculate overall score
        overall_score = self._calculate_overall_score(category_scores, pass_rate)

        # Anomaly score (placeholder - would be calculated by AnomalyDetector)
        anomaly_score = 0.0

        return QualityScore(
            overall_score=overall_score,
            category_scores=category_scores,
            validation_pass_rate=pass_rate,
            anomaly_score=anomaly_score,
            dataset_id=dataset_id,
            details={
                "validation_results": [r.to_dict() for r in validation_results],
                "total_rules": total_count,
                "passed_rules": passed_count,
            },
        )

    def _calculate_category_scores(
        self, dataset: Any, validation_results: list[ValidationResult]
    ) -> dict[str, float]:
        """Calculate scores for each quality category.

        Args:
            dataset: The dataset being evaluated
            validation_results: Results from validation rules

        Returns:
            Dictionary of category scores (0-100)
        """
        scores: dict[str, float] = {}

        # Completeness: based on null checks and schema completeness
        completeness_failures = [
            r
            for r in validation_results
            if r.rule_name in ("null_check", "schema_completeness") and not r.passed
        ]
        completeness_pass_rate = 1.0 - (
            len(completeness_failures) / max(1, len(validation_results))
        )
        scores["completeness"] = completeness_pass_rate * 100

        # Validity: based on type validation and range validation
        validity_failures = [
            r
            for r in validation_results
            if r.rule_name in ("data_type_validation", "range_validation")
            and not r.passed
        ]
        validity_pass_rate = 1.0 - (
            len(validity_failures) / max(1, len(validation_results))
        )
        scores["validity"] = validity_pass_rate * 100

        # Consistency: based on cross-field validation and monotonic rules
        consistency_failures = [
            r
            for r in validation_results
            if r.rule_name in ("cross_field_validation", "monotonic_field")
            and not r.passed
        ]
        consistency_pass_rate = 1.0 - (
            len(consistency_failures) / max(1, len(validation_results))
        )
        scores["consistency"] = consistency_pass_rate * 100

        # Timeliness: based on data freshness
        freshness_results = [
            r for r in validation_results if r.rule_name == "data_freshness"
        ]
        if freshness_results:
            freshness_pass_rate = sum(1 for r in freshness_results if r.passed) / len(
                freshness_results
            )
            scores["timeliness"] = freshness_pass_rate * 100
        else:
            scores["timeliness"] = 100.0

        # Uniqueness: based on unique constraints and duplicate detection
        uniqueness_failures = [
            r
            for r in validation_results
            if r.rule_name in ("unique_constraint", "duplicate_detection")
            and not r.passed
        ]
        uniqueness_pass_rate = 1.0 - (
            len(uniqueness_failures) / max(1, len(validation_results))
        )
        scores["uniqueness"] = uniqueness_pass_rate * 100

        return scores

    def _calculate_overall_score(
        self, category_scores: dict[str, float], validation_pass_rate: float
    ) -> float:
        """Calculate weighted overall quality score.

        Args:
            category_scores: Scores for each category
            validation_pass_rate: Overall validation pass rate (0-1)

        Returns:
            Overall quality score (0-100)
        """
        # Weight category scores
        weighted_score = sum(
            category_scores.get(category, 0.0) * weight
            for category, weight in self.weights.items()
        )

        # Blend with validation pass rate (50% weight each)
        overall = 0.5 * weighted_score + 0.5 * (validation_pass_rate * 100)

        return round(overall, 2)

    @staticmethod
    def check_threshold(score: float, min_score: float) -> bool:
        """Check if score meets minimum threshold.

        Args:
            score: Quality score to check
            min_score: Minimum acceptable score

        Returns:
            True if score >= min_score
        """
        return score >= min_score

    def generate_report(self, score: QualityScore) -> dict[str, Any]:
        """Generate detailed quality report.

        Args:
            score: QualityScore to generate report from

        Returns:
            Dictionary containing the report
        """
        passed = self.check_threshold(score.overall_score, self.min_score)

        report = {
            "dataset_id": score.dataset_id,
            "timestamp": score.timestamp.isoformat(),
            "overall_score": score.overall_score,
            "threshold": self.min_score,
            "passed": passed,
            "category_scores": score.category_scores,
            "validation_pass_rate": score.validation_pass_rate,
            "anomaly_score": score.anomaly_score,
            "details": score.details,
            "recommendations": self._generate_recommendations(score),
        }

        return report

    def _generate_recommendations(self, score: QualityScore) -> list[str]:
        """Generate recommendations based on quality scores.

        Args:
            score: QualityScore to analyze

        Returns:
            List of recommendation strings
        """
        recommendations: list[str] = []

        # Check each category
        if score.category_scores.get("completeness", 100) < 80:
            recommendations.append("Address missing values and incomplete records")

        if score.category_scores.get("validity", 100) < 80:
            recommendations.append("Fix invalid data types and out-of-range values")

        if score.category_scores.get("consistency", 100) < 80:
            recommendations.append(
                "Resolve data inconsistencies and cross-field violations"
            )

        if score.category_scores.get("timeliness", 100) < 80:
            recommendations.append("Refresh data to meet freshness requirements")

        if score.category_scores.get("uniqueness", 100) < 80:
            recommendations.append(
                "Remove duplicate records and ensure unique constraints"
            )

        # Check validation pass rate
        if score.validation_pass_rate < 0.8:
            recommendations.append(
                f"Validation pass rate is {score.validation_pass_rate:.1%}. "
                "Review and fix failing validation rules."
            )

        # Check anomaly score
        if score.anomaly_score > 0.5:
            recommendations.append(
                f"High anomaly score ({score.anomaly_score:.2f}). "
                "Investigate potential data drift or outliers."
            )

        if not recommendations:
            recommendations.append("Data quality is good. No immediate actions needed.")

        return recommendations
