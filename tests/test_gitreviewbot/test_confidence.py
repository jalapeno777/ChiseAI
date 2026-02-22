"""Tests for GitReviewBot confidence scoring."""

import pytest

from autonomous_git.gitreviewbot.confidence import ConfidenceScorer
from autonomous_git.gitreviewbot.models import (
    Finding,
    ReviewResult,
    Severity,
    Violation,
)


@pytest.fixture
def scorer():
    """Create a ConfidenceScorer for testing."""
    return ConfidenceScorer()


@pytest.fixture
def clean_senior_dev_result():
    """Create a clean SeniorDev result."""
    return ReviewResult(
        role="SeniorDev",
        findings=[],
        summary="Clean code",
        confidence=95.0,
        blockers=[],
    )


@pytest.fixture
def clean_critic_result():
    """Create a clean Critic result."""
    return ReviewResult(
        role="Critic",
        violations=[],
        summary="All checks passed",
        confidence=95.0,
        blockers=[],
    )


class TestConfidenceScorer:
    """Test ConfidenceScorer."""

    def test_calculate_clean_review(
        self, scorer, clean_senior_dev_result, clean_critic_result
    ):
        """Test confidence calculation for clean review."""
        factors = scorer.calculate(
            clean_senior_dev_result,
            clean_critic_result,
            files_changed=2,
            lines_changed=100,
        )

        assert factors.final_confidence == 95.0
        assert factors.base_confidence == 95.0
        assert factors.finding_penalty == 0.0
        assert factors.violation_penalty == 0.0

    def test_finding_penalties(self, scorer, clean_critic_result):
        """Test penalties for findings."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[
                Finding(file="test.py", severity=Severity.ERROR, message="Bug"),
                Finding(file="test.py", severity=Severity.WARNING, message="Style"),
                Finding(file="test.py", severity=Severity.INFO, message="Suggestion"),
            ],
            summary="Issues found",
            confidence=90.0,
        )

        factors = scorer.calculate(
            senior_dev,
            clean_critic_result,
            files_changed=1,
            lines_changed=50,
        )

        expected_penalty = 15.0 + 5.0 + 1.0  # error + warning + info
        # Base confidence is (90 + 95) / 2 = 92.5
        expected_confidence = 92.5 - expected_penalty
        assert factors.finding_penalty == expected_penalty
        assert factors.final_confidence == expected_confidence

    def test_violation_penalties(self, scorer, clean_senior_dev_result):
        """Test penalties for violations."""
        critic = ReviewResult(
            role="Critic",
            violations=[
                Violation(rule="test", severity=Severity.ERROR, message="Error"),
                Violation(rule="test", severity=Severity.WARNING, message="Warning"),
            ],
            summary="Violations found",
            confidence=90.0,
        )

        factors = scorer.calculate(
            clean_senior_dev_result,
            critic,
            files_changed=1,
            lines_changed=50,
        )

        # Compliance errors weighted higher (1.5x)
        expected_penalty = (15.0 * 1.5) + 5.0
        assert factors.violation_penalty == expected_penalty

    def test_blocker_penalty(self, scorer):
        """Test penalty for blockers."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[],
            summary="Issues",
            confidence=90.0,
            blockers=["Blocker 1", "Blocker 2"],
        )

        critic = ReviewResult(
            role="Critic",
            violations=[],
            summary="Issues",
            confidence=90.0,
            blockers=[],
        )

        factors = scorer.calculate(
            senior_dev,
            critic,
            files_changed=1,
            lines_changed=50,
        )

        assert factors.blocker_penalty == 50.0  # 2 * 25.0

    def test_complexity_penalty_many_files(
        self, scorer, clean_senior_dev_result, clean_critic_result
    ):
        """Test penalty for many files."""
        factors = scorer.calculate(
            clean_senior_dev_result,
            clean_critic_result,
            files_changed=30,  # Over limit of 20
            lines_changed=100,
        )

        expected_penalty = (30 - 20) * 0.5  # 10 * 0.5
        assert factors.complexity_penalty == expected_penalty

    def test_complexity_penalty_many_lines(
        self, scorer, clean_senior_dev_result, clean_critic_result
    ):
        """Test penalty for many lines."""
        factors = scorer.calculate(
            clean_senior_dev_result,
            clean_critic_result,
            files_changed=5,
            lines_changed=1000,  # Over limit of 500
        )

        expected_penalty = ((1000 - 500) / 100) * 0.3  # 5 * 0.3
        assert factors.complexity_penalty == expected_penalty

    def test_confidence_clamped_to_zero(self, scorer):
        """Test confidence is clamped to minimum of 0."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[Finding(file="t.py", severity=Severity.ERROR, message="Bug")]
            * 10,
            summary="Many issues",
            confidence=50.0,
            blockers=["Blocker"] * 5,
        )

        critic = ReviewResult(
            role="Critic",
            violations=[],
            summary="Issues",
            confidence=50.0,
        )

        factors = scorer.calculate(
            senior_dev,
            critic,
            files_changed=1,
            lines_changed=50,
        )

        assert factors.final_confidence == 0.0

    def test_confidence_clamped_to_100(
        self, scorer, clean_senior_dev_result, clean_critic_result
    ):
        """Test confidence is clamped to maximum of 100."""
        senior_dev = ReviewResult(
            role="SeniorDev",
            findings=[],
            summary="Perfect",
            confidence=100.0,
        )

        critic = ReviewResult(
            role="Critic",
            violations=[],
            summary="Perfect",
            confidence=100.0,
        )

        factors = scorer.calculate(
            senior_dev,
            critic,
            files_changed=1,
            lines_changed=50,
        )

        assert factors.final_confidence == 100.0


class TestAutoMergeEligibility:
    """Test auto-merge eligibility checks."""

    def test_eligible(self, scorer):
        """Test eligible for auto-merge."""
        eligible = scorer.is_auto_merge_eligible(
            confidence=96.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            blockers=[],
            ci_passed=True,
        )

        assert eligible == True

    def test_not_eligible_low_confidence(self, scorer):
        """Test not eligible with low confidence."""
        eligible = scorer.is_auto_merge_eligible(
            confidence=94.0,  # Below 95
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            blockers=[],
            ci_passed=True,
        )

        assert eligible == False

    def test_not_eligible_low_role_confidence(self, scorer):
        """Test not eligible with low role confidence."""
        eligible = scorer.is_auto_merge_eligible(
            confidence=96.0,
            senior_dev_confidence=85.0,  # Below 90
            critic_confidence=93.0,
            blockers=[],
            ci_passed=True,
        )

        assert eligible == False

    def test_not_eligible_with_blockers(self, scorer):
        """Test not eligible with blockers."""
        eligible = scorer.is_auto_merge_eligible(
            confidence=96.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            blockers=["Blocker"],
            ci_passed=True,
        )

        assert eligible == False

    def test_not_eligible_ci_failed(self, scorer):
        """Test not eligible when CI failed."""
        eligible = scorer.is_auto_merge_eligible(
            confidence=96.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            blockers=[],
            ci_passed=False,
        )

        assert eligible == False


class TestConfidenceTiers:
    """Test confidence tier classification."""

    def test_excellent_tier(self, scorer):
        """Test excellent tier."""
        assert scorer.get_confidence_tier(95) == "excellent"
        assert scorer.get_confidence_tier(100) == "excellent"

    def test_high_tier(self, scorer):
        """Test high tier."""
        assert scorer.get_confidence_tier(90) == "high"
        assert scorer.get_confidence_tier(94) == "high"

    def test_medium_tier(self, scorer):
        """Test medium tier."""
        assert scorer.get_confidence_tier(70) == "medium"
        assert scorer.get_confidence_tier(89) == "medium"

    def test_low_tier(self, scorer):
        """Test low tier."""
        assert scorer.get_confidence_tier(50) == "low"
        assert scorer.get_confidence_tier(69) == "low"

    def test_very_low_tier(self, scorer):
        """Test very low tier."""
        assert scorer.get_confidence_tier(0) == "very_low"
        assert scorer.get_confidence_tier(49) == "very_low"


class TestHistoricalAccuracyAdjustment:
    """Test historical accuracy adjustments."""

    def test_no_adjustment_without_history(self, scorer):
        """Test no adjustment when no historical data."""
        adjusted = scorer.adjust_for_historical_accuracy(90.0, None)
        assert adjusted == 90.0

    def test_adjustment_low_accuracy(self, scorer):
        """Test adjustment for low historical accuracy."""
        adjusted = scorer.adjust_for_historical_accuracy(90.0, 0.75)
        assert adjusted == 81.0  # 90 * 0.9

    def test_adjustment_medium_accuracy(self, scorer):
        """Test adjustment for medium historical accuracy."""
        adjusted = scorer.adjust_for_historical_accuracy(90.0, 0.85)
        assert adjusted == 85.5  # 90 * 0.95

    def test_adjustment_high_accuracy(self, scorer):
        """Test no adjustment for high historical accuracy."""
        adjusted = scorer.adjust_for_historical_accuracy(90.0, 0.95)
        assert adjusted == 90.0
