"""Confidence scoring for GitReviewBot decisions."""

import math
from typing import List, Optional
from dataclasses import dataclass

from .models import ReviewResult, Finding, Violation, Severity


@dataclass
class ConfidenceFactors:
    """Factors contributing to confidence calculation."""

    base_confidence: float
    finding_penalty: float
    violation_penalty: float
    blocker_penalty: float
    coverage_bonus: float
    complexity_penalty: float
    final_confidence: float


class ConfidenceScorer:
    """Calculate confidence scores for reviews."""

    # Penalty weights
    ERROR_PENALTY = 15.0
    WARNING_PENALTY = 5.0
    INFO_PENALTY = 1.0
    BLOCKER_PENALTY = 25.0

    # Complexity thresholds
    MAX_FILES_FOR_FULL_CONFIDENCE = 20
    MAX_LINES_FOR_FULL_CONFIDENCE = 500

    def __init__(
        self,
        error_penalty: float = 15.0,
        warning_penalty: float = 5.0,
        info_penalty: float = 1.0,
        blocker_penalty: float = 25.0,
    ):
        self.error_penalty = error_penalty
        self.warning_penalty = warning_penalty
        self.info_penalty = info_penalty
        self.blocker_penalty = blocker_penalty

    def calculate(
        self,
        senior_dev_result: ReviewResult,
        critic_result: ReviewResult,
        files_changed: int = 0,
        lines_changed: int = 0,
    ) -> ConfidenceFactors:
        """Calculate combined confidence from both review results."""
        # Start with average of both confidences
        base_confidence = (senior_dev_result.confidence + critic_result.confidence) / 2

        # Calculate penalties
        finding_penalty = self._calculate_finding_penalty(senior_dev_result.findings)
        violation_penalty = self._calculate_violation_penalty(critic_result.violations)
        blocker_penalty = self._calculate_blocker_penalty(
            senior_dev_result.blockers + critic_result.blockers
        )

        # Calculate complexity penalty
        complexity_penalty = self._calculate_complexity_penalty(
            files_changed, lines_changed
        )

        # Calculate final confidence
        final_confidence = (
            base_confidence
            - finding_penalty
            - violation_penalty
            - blocker_penalty
            - complexity_penalty
        )

        # Clamp to 0-100
        final_confidence = max(0.0, min(100.0, final_confidence))

        # Coverage bonus (placeholder for actual coverage data)
        coverage_bonus = 0.0

        return ConfidenceFactors(
            base_confidence=base_confidence,
            finding_penalty=finding_penalty,
            violation_penalty=violation_penalty,
            blocker_penalty=blocker_penalty,
            coverage_bonus=coverage_bonus,
            complexity_penalty=complexity_penalty,
            final_confidence=final_confidence,
        )

    def _calculate_finding_penalty(self, findings: List[Finding]) -> float:
        """Calculate penalty from findings."""
        penalty = 0.0
        for finding in findings:
            if finding.severity == Severity.ERROR:
                penalty += self.error_penalty
            elif finding.severity == Severity.WARNING:
                penalty += self.warning_penalty
            elif finding.severity == Severity.INFO:
                penalty += self.info_penalty
        return penalty

    def _calculate_violation_penalty(self, violations: List[Violation]) -> float:
        """Calculate penalty from violations."""
        penalty = 0.0
        for violation in violations:
            if violation.severity == Severity.ERROR:
                penalty += self.error_penalty * 1.5  # Compliance errors weighted higher
            elif violation.severity == Severity.WARNING:
                penalty += self.warning_penalty
            elif violation.severity == Severity.INFO:
                penalty += self.info_penalty
        return penalty

    def _calculate_blocker_penalty(self, blockers: List[str]) -> float:
        """Calculate penalty from blockers."""
        return len(blockers) * self.blocker_penalty

    def _calculate_complexity_penalty(
        self, files_changed: int, lines_changed: int
    ) -> float:
        """Calculate penalty based on change complexity."""
        penalty = 0.0

        # Penalty for too many files
        if files_changed > self.MAX_FILES_FOR_FULL_CONFIDENCE:
            excess = files_changed - self.MAX_FILES_FOR_FULL_CONFIDENCE
            penalty += excess * 0.5  # 0.5% per file over limit

        # Penalty for too many lines
        if lines_changed > self.MAX_LINES_FOR_FULL_CONFIDENCE:
            excess = lines_changed - self.MAX_LINES_FOR_FULL_CONFIDENCE
            penalty += (excess / 100) * 0.3  # 0.3% per 100 lines over limit

        return penalty

    def is_auto_merge_eligible(
        self,
        confidence: float,
        senior_dev_confidence: float,
        critic_confidence: float,
        blockers: List[str],
        ci_passed: bool = False,
    ) -> bool:
        """Check if PR is eligible for auto-merge."""
        # Must have no blockers
        if blockers:
            return False

        # Must have high combined confidence
        if confidence < 95.0:
            return False

        # Both roles must have high confidence
        if senior_dev_confidence < 90.0 or critic_confidence < 90.0:
            return False

        # CI must pass
        if not ci_passed:
            return False

        return True

    def adjust_for_historical_accuracy(
        self,
        confidence: float,
        historical_accuracy: Optional[float],
    ) -> float:
        """Adjust confidence based on historical accuracy."""
        if historical_accuracy is None:
            return confidence

        # If historical accuracy is low, reduce confidence
        if historical_accuracy < 0.8:
            confidence *= 0.9
        elif historical_accuracy < 0.9:
            confidence *= 0.95

        return confidence

    def get_confidence_tier(self, confidence: float) -> str:
        """Get confidence tier label."""
        if confidence >= 95:
            return "excellent"
        elif confidence >= 90:
            return "high"
        elif confidence >= 70:
            return "medium"
        elif confidence >= 50:
            return "low"
        else:
            return "very_low"
