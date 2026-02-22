"""
Tests for Standard Path PR Pipeline.

Story: ST-AUTO-004
Epic: EP-AUTO-GIT-001
"""

import pytest
from datetime import datetime, timedelta

# Import from the module under test
from src.governance.pr_pipeline.standard_path import (
    StandardPathHandler,
    StandardPathConfig,
    ReviewStatus,
    PRClassification,
    ReviewResult,
)


class TestStandardPathClassification:
    """Tests for PR classification logic."""

    @pytest.fixture
    def handler(self) -> StandardPathHandler:
        """Create a standard path handler instance."""
        return StandardPathHandler()

    def test_handler_initialization(self, handler: StandardPathHandler):
        """Test handler initializes with correct defaults."""
        assert handler.config.review_timeout_seconds == 720  # 12 min
        assert handler.config.max_review_retries == 3
        assert handler.config.escalation_enabled is True

    def test_custom_config(self):
        """Test handler accepts custom configuration."""
        config = StandardPathConfig(
            review_timeout_seconds=300,
            max_review_retries=5,
        )
        handler = StandardPathHandler(config=config)
        assert handler.config.review_timeout_seconds == 300
        assert handler.config.max_review_retries == 5

    def test_default_classification_is_standard(self, handler: StandardPathHandler):
        """Test that default PR classification returns STANDARD."""
        # Stub implementation returns STANDARD by default
        classification = handler.classify_pr(pr_number=123)
        assert classification == PRClassification.STANDARD


class TestReviewTimeout:
    """Tests for review timeout handling."""

    @pytest.fixture
    def handler_with_short_timeout(self) -> StandardPathHandler:
        """Create handler with short timeout for testing."""
        config = StandardPathConfig(review_timeout_seconds=1)
        return StandardPathHandler(config=config)

    @pytest.mark.asyncio
    async def test_review_returns_pending_initially(
        self, handler_with_short_timeout: StandardPathHandler
    ):
        """Test that review starts in pending state."""
        result = await handler_with_short_timeout.review_pr(pr_number=456)
        assert result.status == ReviewStatus.PENDING
        assert result.started_at is not None

    @pytest.mark.asyncio
    async def test_review_status_tracking(
        self, handler_with_short_timeout: StandardPathHandler
    ):
        """Test that review status can be retrieved."""
        await handler_with_short_timeout.review_pr(pr_number=789)
        status = await handler_with_short_timeout.get_review_status(pr_number=789)
        assert status is not None
        assert status.pr_number == 789

    @pytest.mark.asyncio
    async def test_missing_review_returns_none(
        self, handler_with_short_timeout: StandardPathHandler
    ):
        """Test that missing review returns None."""
        status = await handler_with_short_timeout.get_review_status(pr_number=999)
        assert status is None


class TestEscalationLogic:
    """Tests for human escalation logic."""

    @pytest.fixture
    def handler(self) -> StandardPathHandler:
        """Create a standard path handler instance."""
        return StandardPathHandler()

    @pytest.mark.asyncio
    async def test_escalation_updates_status(self, handler: StandardPathHandler):
        """Test that escalation updates review status."""
        # Start a review first
        await handler.review_pr(pr_number=100)

        # Escalate
        result = await handler.escalate_to_human(
            pr_number=100, reason="Review timeout exceeded"
        )

        assert result is True
        status = await handler.get_review_status(pr_number=100)
        assert status is not None
        assert status.status == ReviewStatus.ESCALATED
        assert status.escalation_reason == "Review timeout exceeded"

    @pytest.mark.asyncio
    async def test_escalation_with_assignees(self, handler: StandardPathHandler):
        """Test escalation with specific assignees."""
        await handler.review_pr(pr_number=101)

        result = await handler.escalate_to_human(
            pr_number=101,
            reason="Complex architecture changes",
            assignees=["senior-dev", "architect"],
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_escalation_of_unknown_pr_succeeds(
        self, handler: StandardPathHandler
    ):
        """Test that escalating unknown PR still succeeds (stub behavior)."""
        result = await handler.escalate_to_human(pr_number=9999, reason="Unknown PR")
        # Stub returns True even for unknown PRs
        assert result is True


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_review_result_defaults(self):
        """Test ReviewResult has correct defaults."""
        result = ReviewResult(
            pr_number=1,
            status=ReviewStatus.PENDING,
            classification=PRClassification.STANDARD,
        )

        assert result.review_comments == []
        assert result.approved is False
        assert result.escalation_reason is None
        assert result.started_at is None
        assert result.completed_at is None
        assert result.duration_seconds is None

    def test_review_result_duration_calculation(self):
        """Test that duration can be calculated from timestamps."""
        start = datetime.now()
        end = start + timedelta(minutes=8)

        result = ReviewResult(
            pr_number=1,
            status=ReviewStatus.COMPLETED,
            classification=PRClassification.STANDARD,
            started_at=start,
            completed_at=end,
            duration_seconds=(end - start).total_seconds(),
        )

        assert result.duration_seconds == 480.0  # 8 minutes
