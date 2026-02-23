"""Quality Gate for PR Blocking.

Implements the blocking mechanism for PRs with quality score < 80%.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.governance.quality_gate.override import OverrideManager
from src.governance.quality_gate.scorer import (
    QualityScore,
    QualityScorer,
    ScoreComponent,
)

logger = logging.getLogger(__name__)


class BlockReason(str, Enum):
    """Reasons for blocking a PR."""

    LOW_QUALITY_SCORE = "low_quality_score"
    SECURITY_ISSUES = "security_issues"
    MISSING_TESTS = "missing_tests"
    SCOPE_VIOLATION = "scope_violation"
    CONSTITUTION_VIOLATION = "constitution_violation"
    PENDING_REVIEW = "pending_review"


@dataclass
class QualityGateResult:
    """Result of quality gate evaluation."""

    passed: bool
    score: QualityScore
    blocked: bool
    block_reasons: list[BlockReason]
    override_active: bool = False
    override_id: str | None = None
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    review_time_seconds: float = 0.0
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "block_reasons": [r.value for r in self.block_reasons],
            "override_active": self.override_active,
            "override_id": self.override_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "review_time_seconds": round(self.review_time_seconds, 2),
            "score": self.score.to_dict(),
            "recommendations": self.recommendations,
        }


class QualityGate:
    """Evaluates and optionally blocks PRs based on quality score."""

    def __init__(
        self,
        scorer: QualityScorer | None = None,
        override_manager: OverrideManager | None = None,
        blocking_threshold: float = 0.80,
        security_threshold: float = 0.70,
        enable_blocking: bool = True,
    ):
        """Initialize the quality gate.

        Args:
            scorer: Quality scorer instance
            override_manager: Override manager for human overrides
            blocking_threshold: Threshold below which PRs are blocked (default 80%)
            security_threshold: Minimum security score required (default 70%)
            enable_blocking: Whether to actually block PRs
        """
        self.scorer = scorer or QualityScorer(passing_threshold=blocking_threshold)
        self.override_manager = override_manager or OverrideManager()
        self.blocking_threshold = blocking_threshold
        self.security_threshold = security_threshold
        self.enable_blocking = enable_blocking

        # Validation gates from contract
        self.validation_gates = {
            "false_negative_rate": 0.05,  # < 5%
            "false_positive_rate": 0.10,  # < 10%
            "review_time_seconds": 120,  # < 2 minutes
        }

        # Stats for live validation
        self._stats = {
            "total_reviews": 0,
            "blocked_reviews": 0,
            "overridden_reviews": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "total_review_time": 0.0,
        }

    def evaluate(
        self,
        pr_number: int,
        changed_files: list[str],
        branch: str,
        repo_path: str = ".",
        check_override: bool = True,
    ) -> QualityGateResult:
        """Evaluate a PR through the quality gate.

        Args:
            pr_number: PR number
            changed_files: List of changed file paths
            branch: Branch name
            repo_path: Path to repository root
            check_override: Whether to check for active overrides

        Returns:
            QualityGateResult with pass/fail status
        """
        start_time = datetime.utcnow()
        self._stats["total_reviews"] += 1

        # Calculate quality score
        score = self.scorer.calculate_score(
            changed_files=changed_files,
            pr_number=pr_number,
            branch=branch,
            repo_path=repo_path,
        )

        # Determine block reasons
        block_reasons: list[BlockReason] = []

        if score.overall_score < self.blocking_threshold:
            block_reasons.append(BlockReason.LOW_QUALITY_SCORE)

        # Check security threshold separately (hard requirement)
        security_score = score.component_scores.get(ScoreComponent.SECURITY)
        if security_score and security_score.score < self.security_threshold:
            block_reasons.append(BlockReason.SECURITY_ISSUES)

        # Check for failing components
        for component, comp_score in score.component_scores.items():
            if not comp_score.passed:
                if component == ScoreComponent.TEST_COVERAGE:
                    block_reasons.append(BlockReason.MISSING_TESTS)
                elif component == ScoreComponent.CONSTITUTION:
                    block_reasons.append(BlockReason.CONSTITUTION_VIOLATION)

        # Determine if blocked
        should_block = len(block_reasons) > 0
        override_active = False
        override_id = None

        # Check for active override if blocked
        if should_block and check_override:
            override = self.override_manager.get_active_override_for_pr(pr_number)
            if override:
                override_active = True
                override_id = override.id
                should_block = False  # Override allows merge
                self._stats["overridden_reviews"] += 1

        # Apply blocking if enabled
        blocked = should_block and self.enable_blocking

        if blocked:
            self._stats["blocked_reviews"] += 1

        # Generate recommendations
        recommendations = self._generate_recommendations(score, block_reasons)

        # Calculate review time
        review_time = (datetime.utcnow() - start_time).total_seconds()
        self._stats["total_review_time"] += review_time

        return QualityGateResult(
            passed=score.passed and not blocked,
            score=score,
            blocked=blocked,
            block_reasons=block_reasons,
            override_active=override_active,
            override_id=override_id,
            review_time_seconds=review_time,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self, score: QualityScore, block_reasons: list[BlockReason]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if BlockReason.LOW_QUALITY_SCORE in block_reasons:
            failing = score.get_failing_components()
            if failing:
                recommendations.append(
                    f"Improve scores in: {', '.join(c.value for c in failing)}"
                )

        if BlockReason.SECURITY_ISSUES in block_reasons:
            recommendations.append(
                "Address security findings before merging. "
                "Run 'bandit -r src/' for details."
            )

        if BlockReason.MISSING_TESTS in block_reasons:
            recommendations.append(
                "Add tests for new code. Target 80% coverage minimum."
            )

        if BlockReason.CONSTITUTION_VIOLATION in block_reasons:
            recommendations.append(
                "Review constitution compliance. "
                "Ensure changes align with governance rules."
            )

        return recommendations

    def request_override(
        self,
        pr_number: int,
        requester: str,
        justification: str,
        risk_assessment: str,
        rollback_plan: str,
    ) -> str:
        """Request a human override for a blocked PR.

        Args:
            pr_number: PR number
            requester: ID of person requesting override
            justification: Reason for override (min 50 chars)
            risk_assessment: Risk level (low/medium/high/critical)
            rollback_plan: Plan for rolling back changes

        Returns:
            Override request ID
        """
        override = self.override_manager.create_request(
            pr_number=pr_number,
            requester=requester,
            justification=justification,
            risk_assessment=risk_assessment,
            rollback_plan=rollback_plan,
        )

        logger.info(f"Override requested for PR #{pr_number}: {override.id}")
        return override.id

    def approve_override(self, override_id: str, approver: str) -> bool:
        """Approve an override request.

        Args:
            override_id: Override request ID
            approver: ID of approver

        Returns:
            True if approved successfully
        """
        try:
            self.override_manager.approve_request(override_id, approver)
            logger.info(f"Override {override_id} approved by {approver}")
            return True
        except Exception as e:
            logger.error(f"Failed to approve override: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get quality gate statistics.

        Returns:
            Dictionary with stats for live validation
        """
        total = self._stats["total_reviews"]
        avg_review_time = self._stats["total_review_time"] / total if total > 0 else 0

        # Calculate rates
        false_positive_rate = self._stats["false_positives"] / total if total > 0 else 0
        false_negative_rate = self._stats["false_negatives"] / total if total > 0 else 0

        return {
            "total_reviews": total,
            "blocked_reviews": self._stats["blocked_reviews"],
            "overridden_reviews": self._stats["overridden_reviews"],
            "block_rate": self._stats["blocked_reviews"] / total if total > 0 else 0,
            "false_positives": self._stats["false_positives"],
            "false_negatives": self._stats["false_negatives"],
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "avg_review_time_seconds": round(avg_review_time, 2),
            "validation_gates": {
                "false_negative_rate_pass": false_negative_rate
                < self.validation_gates["false_negative_rate"],
                "false_positive_rate_pass": false_positive_rate
                < self.validation_gates["false_positive_rate"],
                "review_time_pass": avg_review_time
                < self.validation_gates["review_time_seconds"],
            },
        }

    def record_validation_result(
        self, was_false_positive: bool = False, was_false_negative: bool = False
    ) -> None:
        """Record validation result for accuracy tracking.

        Args:
            was_false_positive: Gate blocked incorrectly
            was_false_negative: Gate passed but should have blocked
        """
        if was_false_positive:
            self._stats["false_positives"] += 1
        if was_false_negative:
            self._stats["false_negatives"] += 1
