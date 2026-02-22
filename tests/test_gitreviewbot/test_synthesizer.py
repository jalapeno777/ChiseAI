"""Tests for GitReviewBot synthesizer."""

import pytest

from autonomous_git.gitreviewbot.confidence import ConfidenceScorer
from autonomous_git.gitreviewbot.models import (
    DecisionType,
    Finding,
    ReviewResult,
    Severity,
    Violation,
)
from autonomous_git.gitreviewbot.synthesizer import DecisionSynthesizer


@pytest.fixture
def synthesizer():
    """Create a DecisionSynthesizer for testing."""
    scorer = ConfidenceScorer()
    return DecisionSynthesizer(scorer)


@pytest.fixture
def senior_dev_result():
    """Create a sample SeniorDev review result."""
    return ReviewResult(
        role="SeniorDev",
        findings=[],
        summary="Code looks good",
        confidence=92.0,
        blockers=[],
    )


@pytest.fixture
def critic_result():
    """Create a sample Critic review result."""
    return ReviewResult(
        role="Critic",
        violations=[],
        summary="All compliance checks passed",
        confidence=90.0,
        blockers=[],
    )


class TestDecisionSynthesizer:
    """Test DecisionSynthesizer."""

    def test_synthesize_approve(self, synthesizer, senior_dev_result, critic_result):
        """Test synthesizing an APPROVE decision."""
        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev_result,
            critic_result=critic_result,
            pr_number=123,
            pr_title="ST-123: Test PR",
            story_id="ST-123",
            files_changed=2,
            lines_changed=100,
            ci_passed=True,
        )

        assert decision.decision == DecisionType.APPROVE
        assert decision.confidence >= 90.0
        assert decision.pr_number == 123

    def test_synthesize_with_blockers(
        self, synthesizer, senior_dev_result, critic_result
    ):
        """Test synthesizing with blockers results in REQUEST_CHANGES."""
        senior_dev_result.blockers = ["Missing tests"]

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev_result,
            critic_result=critic_result,
            pr_number=124,
            pr_title="ST-124: Test PR",
            story_id="ST-124",
        )

        assert decision.decision == DecisionType.REQUEST_CHANGES
        assert "Missing tests" in decision.blockers

    def test_synthesize_comment(self, synthesizer):
        """Test synthesizing COMMENT decision for medium confidence."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[
                Finding(
                    file="src/test.py",
                    severity=Severity.WARNING,
                    message="Consider refactoring",
                )
            ],
            summary="Some concerns",
            confidence=75.0,
        )

        critic = ReviewResult(
            role="Critic",
            violations=[],
            summary="Minor issues",
            confidence=80.0,
        )

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev,
            critic_result=critic,
            pr_number=125,
            pr_title="ST-125: Test PR",
            story_id="ST-125",
        )

        assert decision.decision == DecisionType.COMMENT

    def test_synthesize_request_changes_low_confidence(self, synthesizer):
        """Test REQUEST_CHANGES for low confidence."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[],
            summary="Many issues",
            confidence=50.0,
        )

        critic = ReviewResult(
            role="Critic",
            violations=[],
            summary="Compliance issues",
            confidence=55.0,
        )

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev,
            critic_result=critic,
            pr_number=126,
            pr_title="ST-126: Test PR",
            story_id="ST-126",
        )

        assert decision.decision == DecisionType.REQUEST_CHANGES

    def test_auto_merge_eligible(self, synthesizer, senior_dev_result, critic_result):
        """Test auto-merge eligibility."""
        senior_dev_result.confidence = 96.0
        critic_result.confidence = 95.0

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev_result,
            critic_result=critic_result,
            pr_number=127,
            pr_title="ST-127: Test PR",
            story_id="ST-127",
            ci_passed=True,
        )

        assert decision.auto_merge_eligible == True

    def test_auto_merge_not_eligible_with_blockers(
        self, synthesizer, senior_dev_result, critic_result
    ):
        """Test auto-merge not eligible with blockers."""
        senior_dev_result.confidence = 96.0
        critic_result.confidence = 95.0
        senior_dev_result.blockers = ["Security issue"]

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev_result,
            critic_result=critic_result,
            pr_number=128,
            pr_title="ST-128: Test PR",
            story_id="ST-128",
            ci_passed=True,
        )

        assert decision.auto_merge_eligible == False

    def test_combine_blockers(self, synthesizer):
        """Test combining blockers from both roles."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            blockers=["Bug in logic"],
            summary="Issues found",
            confidence=60.0,
        )

        critic = ReviewResult(
            role="Critic",
            blockers=["Missing story ID"],
            summary="Compliance issues",
            confidence=50.0,
        )

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev,
            critic_result=critic,
            pr_number=129,
            pr_title="Test PR",
            story_id=None,
        )

        assert len(decision.blockers) == 2
        assert "Bug in logic" in decision.blockers
        assert "Missing story ID" in decision.blockers

    def test_combine_findings_and_violations(self, synthesizer):
        """Test combining findings and violations."""
        finding = Finding(
            file="src/test.py",
            line=10,
            severity=Severity.WARNING,
            message="Consider refactoring",
        )

        violation = Violation(
            rule="debug_code",
            severity=Severity.WARNING,
            message="Debug print found",
        )

        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[finding],
            summary="Code review",
            confidence=85.0,
        )

        critic = ReviewResult(
            role="Critic",
            violations=[violation],
            summary="Compliance review",
            confidence=85.0,
        )

        decision = synthesizer.synthesize(
            senior_dev_result=senior_dev,
            critic_result=critic,
            pr_number=130,
            pr_title="ST-130: Test PR",
            story_id="ST-130",
        )

        assert len(decision.findings) == 1
        assert len(decision.violations) == 1
