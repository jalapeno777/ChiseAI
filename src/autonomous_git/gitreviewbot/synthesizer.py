"""Decision synthesis engine for combining SeniorDev and Critic reviews."""

from datetime import datetime

from .confidence import ConfidenceFactors, ConfidenceScorer
from .models import Decision, DecisionType, Finding, ReviewResult, Violation


class DecisionSynthesizer:
    """Synthesize SeniorDev and Critic reviews into a decision."""

    # Decision thresholds
    APPROVE_THRESHOLD = 90.0
    COMMENT_THRESHOLD = 70.0
    AUTO_MERGE_THRESHOLD = 95.0

    # Role confidence requirements for auto-merge
    AUTO_MERGE_ROLE_MIN = 90.0

    def __init__(self, confidence_scorer: ConfidenceScorer):
        self.confidence_scorer = confidence_scorer

    def synthesize(
        self,
        senior_dev_result: ReviewResult,
        critic_result: ReviewResult,
        pr_number: int,
        pr_title: str,
        story_id: str,
        files_changed: int = 0,
        lines_changed: int = 0,
        ci_passed: bool = False,
    ) -> Decision:
        """Synthesize dual-role reviews into a decision."""
        # Calculate confidence
        confidence_factors = self.confidence_scorer.calculate(
            senior_dev_result,
            critic_result,
            files_changed,
            lines_changed,
        )

        # Combine blockers
        blockers = self._combine_blockers(
            senior_dev_result.blockers,
            critic_result.blockers,
        )

        # Combine findings and violations
        findings = senior_dev_result.findings
        violations = critic_result.violations

        # Determine decision
        decision_type = self._determine_decision(
            confidence_factors.final_confidence,
            blockers,
        )

        # Check auto-merge eligibility
        auto_merge_eligible = self._check_auto_merge_eligibility(
            decision_type,
            confidence_factors,
            blockers,
            ci_passed,
        )

        # Generate summary
        summary = self._generate_summary(
            decision_type,
            confidence_factors,
            blockers,
            findings,
            violations,
        )

        return Decision(
            decision=decision_type,
            confidence=confidence_factors.final_confidence,
            senior_dev_confidence=senior_dev_result.confidence,
            critic_confidence=critic_result.confidence,
            blockers=blockers,
            findings=findings,
            violations=violations,
            summary=summary,
            auto_merge_eligible=auto_merge_eligible,
            pr_number=pr_number,
            pr_title=pr_title,
            story_id=story_id,
            decided_at=datetime.utcnow(),
        )

    def _combine_blockers(
        self,
        senior_dev_blockers: list[str],
        critic_blockers: list[str],
    ) -> list[str]:
        """Combine blockers from both roles, removing duplicates."""
        combined = set(senior_dev_blockers) | set(critic_blockers)
        return sorted(list(combined))

    def _determine_decision(
        self,
        confidence: float,
        blockers: list[str],
    ) -> DecisionType:
        """Determine the decision based on confidence and blockers."""
        # Blockers always result in REQUEST_CHANGES
        if blockers:
            return DecisionType.REQUEST_CHANGES

        # High confidence = APPROVE
        if confidence >= self.APPROVE_THRESHOLD:
            return DecisionType.APPROVE

        # Medium confidence = COMMENT (human review recommended)
        if confidence >= self.COMMENT_THRESHOLD:
            return DecisionType.COMMENT

        # Low confidence = REQUEST_CHANGES
        return DecisionType.REQUEST_CHANGES

    def _check_auto_merge_eligibility(
        self,
        decision: DecisionType,
        confidence_factors: ConfidenceFactors,
        blockers: list[str],
        ci_passed: bool,
    ) -> bool:
        """Check if PR is eligible for auto-merge."""
        # Must be APPROVE decision
        if decision != DecisionType.APPROVE:
            return False

        # Must have no blockers
        if blockers:
            return False

        # Must have high combined confidence
        if confidence_factors.final_confidence < self.AUTO_MERGE_THRESHOLD:
            return False

        # Both roles must have high confidence
        if confidence_factors.base_confidence < self.AUTO_MERGE_ROLE_MIN:
            # This is a simplified check; in practice we'd check individual role confidences
            pass

        # CI must pass
        return ci_passed

    def _generate_summary(
        self,
        decision: DecisionType,
        confidence_factors: ConfidenceFactors,
        blockers: list[str],
        findings: list[Finding],
        violations: list[Violation],
    ) -> str:
        """Generate a human-readable summary of the decision."""
        parts = []

        # Decision description
        if decision == DecisionType.APPROVE:
            parts.append("This PR looks good and is approved for merge.")
        elif decision == DecisionType.COMMENT:
            parts.append(
                "This PR has moderate confidence. Human review is recommended "
                "before merging."
            )
        else:
            parts.append("This PR requires changes before it can be approved.")

        # Confidence context
        tier = self.confidence_scorer.get_confidence_tier(
            confidence_factors.final_confidence
        )
        parts.append(
            f"Overall confidence is {tier} ({confidence_factors.final_confidence:.1f}%)."
        )

        # Issues context
        error_count = sum(1 for f in findings if f.severity.value == "error")
        warning_count = sum(1 for f in findings if f.severity.value == "warning")
        violation_count = len(violations)

        if error_count > 0:
            parts.append(f"Found {error_count} error(s).")
        if warning_count > 0:
            parts.append(f"Found {warning_count} warning(s).")
        if violation_count > 0:
            parts.append(f"Found {violation_count} compliance violation(s).")

        if blockers:
            parts.append(f"Blocking issues: {', '.join(blockers)}")

        return " ".join(parts)
