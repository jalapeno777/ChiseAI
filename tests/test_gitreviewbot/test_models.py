"""Tests for GitReviewBot models."""

from datetime import UTC, datetime, timedelta

from autonomous_git.gitreviewbot.models import (
    CalibrationMetrics,
    Decision,
    DecisionType,
    Finding,
    PRDetails,
    ReviewFeedback,
    ReviewResult,
    Severity,
    Violation,
)


class TestDecision:
    """Test Decision model."""

    def test_decision_creation(self):
        """Test creating a Decision."""
        decision = Decision(
            decision=DecisionType.APPROVE,
            confidence=95.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            summary="LGTM",
            pr_number=123,
            pr_title="ST-123: Test PR",
            story_id="ST-123",
        )

        assert decision.decision == DecisionType.APPROVE
        assert decision.confidence == 95.0
        assert decision.pr_number == 123
        assert decision.story_id == "ST-123"

    def test_decision_with_blockers(self):
        """Test Decision with blockers."""
        decision = Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=50.0,
            senior_dev_confidence=60.0,
            critic_confidence=40.0,
            blockers=["Missing tests", "Security issue"],
            summary="Needs work",
            pr_number=124,
            pr_title="ST-124: Another PR",
        )

        assert len(decision.blockers) == 2
        assert "Missing tests" in decision.blockers


class TestFinding:
    """Test Finding model."""

    def test_finding_creation(self):
        """Test creating a Finding."""
        finding = Finding(
            file="src/test.py",
            line=42,
            severity=Severity.ERROR,
            message="Undefined variable",
            suggestion="Define the variable before use",
        )

        assert finding.file == "src/test.py"
        assert finding.line == 42
        assert finding.severity == Severity.ERROR
        assert finding.suggestion == "Define the variable before use"


class TestViolation:
    """Test Violation model."""

    def test_violation_creation(self):
        """Test creating a Violation."""
        violation = Violation(
            rule="missing_story_id",
            severity=Severity.WARNING,
            message="PR title missing story ID",
        )

        assert violation.rule == "missing_story_id"
        assert violation.severity == Severity.WARNING


class TestReviewResult:
    """Test ReviewResult model."""

    def test_senior_dev_result(self):
        """Test SeniorDev review result."""
        finding = Finding(
            file="src/test.py",
            line=10,
            severity=Severity.WARNING,
            message="Consider using list comprehension",
        )

        result = ReviewResult(
            role="SeniorDev",
            findings=[finding],
            summary="Code looks good overall",
            confidence=85.0,
        )

        assert result.role == "SeniorDev"
        assert len(result.findings) == 1
        assert result.confidence == 85.0

    def test_critic_result(self):
        """Test Critic review result."""
        violation = Violation(
            rule="debug_code",
            severity=Severity.WARNING,
            message="Debug print statement found",
        )

        result = ReviewResult(
            role="Critic",
            violations=[violation],
            summary="Minor compliance issues",
            confidence=90.0,
        )

        assert result.role == "Critic"
        assert len(result.violations) == 1


class TestReviewFeedback:
    """Test ReviewFeedback model."""

    def test_feedback_creation(self):
        """Test creating feedback."""
        feedback = ReviewFeedback(
            pr_number=123,
            review_id="abc123",
            feedback_type="👍",
            reviewer="human_reviewer",
            comment="Good catch on the bug",
        )

        assert feedback.pr_number == 123
        assert feedback.feedback_type == "👍"
        assert feedback.reviewer == "human_reviewer"


class TestPRDetails:
    """Test PRDetails model."""

    def test_pr_details_creation(self):
        """Test creating PR details."""
        pr = PRDetails(
            number=123,
            title="ST-123: Add feature",
            author="developer",
            branch="feature/ST-123-test",
            base_branch="main",
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            files_changed=["src/feature.py", "tests/test_feature.py"],
            labels=["enhancement"],
        )

        assert pr.number == 123
        assert pr.title == "ST-123: Add feature"
        assert len(pr.files_changed) == 2


class TestCalibrationMetrics:
    """Test CalibrationMetrics model."""

    def test_metrics_creation(self):
        """Test creating calibration metrics."""
        now = datetime.now(UTC)
        metrics = CalibrationMetrics(
            total_reviews=100,
            approved_reviews=60,
            commented_reviews=25,
            requested_changes_reviews=15,
            human_overrides=5,
            human_agreements=85,
            accuracy_rate=85.0,
            avg_confidence=88.0,
            false_positive_rate=3.0,
            false_negative_rate=2.0,
            period_start=now - timedelta(days=7),
            period_end=now,
        )

        assert metrics.total_reviews == 100
        assert metrics.accuracy_rate == 85.0
        assert metrics.false_positive_rate == 3.0
