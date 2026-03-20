"""Tests for GitReviewBot calibration."""

from datetime import UTC, datetime, timedelta

import pytest

from autonomous_git.gitreviewbot.calibration import (
    CalibrationTracker,
    ReviewRecord,
)
from autonomous_git.gitreviewbot.models import Decision, DecisionType


@pytest.fixture
def tracker():
    """Create a CalibrationTracker for testing."""
    return CalibrationTracker()


@pytest.fixture
def sample_decision():
    """Create a sample decision."""
    return Decision(
        decision=DecisionType.APPROVE,
        confidence=95.0,
        senior_dev_confidence=92.0,
        critic_confidence=93.0,
        summary="LGTM",
        pr_number=123,
        pr_title="ST-123: Test",
        story_id="ST-123",
        decided_at=datetime.now(UTC),
    )


class TestReviewRecord:
    """Test ReviewRecord dataclass."""

    def test_to_dict(self):
        """Test conversion to dict."""
        record = ReviewRecord(
            pr_number=123,
            review_id="abc",
            decision="APPROVE",
            confidence=95.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        d = record.to_dict()
        assert d["pr_number"] == 123
        assert d["decision"] == "APPROVE"
        assert d["confidence"] == 95.0

    def test_from_dict(self):
        """Test creation from dict."""
        data = {
            "pr_number": 123,
            "review_id": "abc",
            "decision": "APPROVE",
            "confidence": 95.0,
            "timestamp": "2024-01-01T12:00:00",
        }

        record = ReviewRecord.from_dict(data)
        assert record.pr_number == 123
        assert record.decision == "APPROVE"


class TestLogReview:
    """Test logging reviews."""

    async def test_log_review(self, tracker, sample_decision):
        """Test logging a review."""
        review_id = await tracker.log_review(sample_decision)

        assert review_id is not None
        assert len(review_id) > 0

    async def test_log_review_with_custom_id(self, tracker, sample_decision):
        """Test logging with custom review ID."""
        custom_id = "custom-123"
        review_id = await tracker.log_review(sample_decision, review_id=custom_id)

        assert review_id == custom_id


class TestRecordFeedback:
    """Test recording feedback."""

    async def test_record_thumbs_up(self, tracker):
        """Test recording thumbs up feedback."""
        await tracker.record_feedback(
            pr_number=123,
            review_id="abc",
            feedback_type="👍",
            reviewer="human",
            comment="Good review",
        )

        # Should not raise
        assert True

    async def test_record_thumbs_down(self, tracker):
        """Test recording thumbs down feedback."""
        await tracker.record_feedback(
            pr_number=123,
            review_id="abc",
            feedback_type="👎",
            reviewer="human",
            comment="Missed an issue",
        )

        # Should not raise
        assert True


class TestCalculateMetrics:
    """Test metrics calculation."""

    async def test_empty_metrics(self, tracker):
        """Test metrics with no reviews."""
        metrics = await tracker.calculate_metrics(days=7)

        assert metrics.total_reviews == 0
        assert metrics.accuracy_rate == 0.0
        assert metrics.avg_confidence == 0.0

    async def test_metrics_with_local_cache(self, tracker):
        """Test metrics with local cache data."""
        # Add some records to local cache
        tracker._local_cache = [
            ReviewRecord(
                pr_number=1,
                review_id="r1",
                decision="APPROVE",
                confidence=95.0,
                timestamp=datetime.now(UTC),
                human_feedback="👍",
            ),
            ReviewRecord(
                pr_number=2,
                review_id="r2",
                decision="COMMENT",
                confidence=80.0,
                timestamp=datetime.now(UTC),
                human_feedback="👍",
            ),
            ReviewRecord(
                pr_number=3,
                review_id="r3",
                decision="REQUEST_CHANGES",
                confidence=60.0,
                timestamp=datetime.now(UTC),
                human_override="APPROVE",
            ),
        ]

        metrics = await tracker.calculate_metrics(days=7)

        assert metrics.total_reviews == 3
        assert metrics.approved_reviews == 1
        assert metrics.commented_reviews == 1
        assert metrics.requested_changes_reviews == 1
        assert metrics.human_overrides == 1
        assert metrics.human_agreements == 2


class TestRecommendedThresholds:
    """Test recommended threshold calculation."""

    async def test_default_thresholds_low_data(self, tracker):
        """Test default thresholds with insufficient data."""
        thresholds = await tracker.get_recommended_thresholds()

        assert thresholds["approve"] == 90.0
        assert thresholds["comment"] == 70.0
        assert thresholds["auto_merge"] == 95.0


class TestExportToGrafana:
    """Test Grafana export."""

    async def test_export_format(self, tracker, sample_decision):
        """Test Grafana export format."""
        from autonomous_git.gitreviewbot.models import CalibrationMetrics

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
            period_start=datetime.now(UTC) - timedelta(days=7),
            period_end=datetime.now(UTC),
        )

        data = await tracker.export_to_grafana(metrics)

        assert data["measurement"] == "gitreviewbot_calibration"
        assert data["tags"]["bot"] == "gitreviewbot"
        assert data["fields"]["total_reviews"] == 100
        assert data["fields"]["accuracy_rate"] == 85.0
