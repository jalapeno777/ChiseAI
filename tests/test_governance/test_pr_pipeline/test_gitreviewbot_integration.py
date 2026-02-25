"""Tests for GitReviewBot integration in PR Pipeline standard path.

Story: DEBT-CODE-003
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.autonomous_git.gitreviewbot.models import Decision, DecisionType
from src.governance.pr_pipeline.standard_path import (
    PRClassification,
    ReviewResult,
    ReviewStatus,
    StandardPathConfig,
    StandardPathHandler,
)


class TestGitReviewBotIntegration:
    """Validate GitReviewBot integration in PR pipeline."""

    @pytest.fixture
    def handler(self):
        """Create a StandardPathHandler with test config."""
        config = StandardPathConfig(
            review_timeout_seconds=720,
            max_review_retries=3,
            escalation_enabled=True,
            git_review_bot_timeout_seconds=600,
        )
        return StandardPathHandler(config=config)

    @pytest.fixture
    def mock_approve_decision(self):
        """Create a mock APPROVE decision from GitReviewBot."""
        return Decision(
            decision=DecisionType.APPROVE,
            confidence=85.0,
            senior_dev_confidence=90.0,
            critic_confidence=80.0,
            blockers=[],
            findings=[],
            violations=[],
            summary="Code looks good, approved for merge",
            auto_merge_eligible=True,
            pr_number=123,
            pr_title="feat: add new feature (ST-001)",
            story_id="ST-001",
        )

    @pytest.fixture
    def mock_reject_decision(self):
        """Create a mock REQUEST_CHANGES decision from GitReviewBot."""
        return Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=75.0,
            senior_dev_confidence=70.0,
            critic_confidence=80.0,
            blockers=["Missing error handling", "TODO found in code"],
            findings=[],
            violations=[],
            summary="Changes required before approval",
            auto_merge_eligible=False,
            pr_number=123,
            pr_title="feat: add new feature (ST-001)",
            story_id="ST-001",
        )

    @pytest.fixture
    def mock_uncertain_decision(self):
        """Create a mock COMMENT decision from GitReviewBot."""
        return Decision(
            decision=DecisionType.COMMENT,
            confidence=45.0,
            senior_dev_confidence=50.0,
            critic_confidence=40.0,
            blockers=[],
            findings=[],
            violations=[],
            summary="Uncertain about some changes, needs human review",
            auto_merge_eligible=False,
            pr_number=123,
            pr_title="feat: add new feature (ST-001)",
            story_id="ST-001",
        )

    @pytest.mark.asyncio
    async def test_gitreviewbot_called_during_pr_processing(self, handler):
        """Verify GitReviewBot is called when processing PR."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = Decision(
                decision=DecisionType.APPROVE,
                confidence=85.0,
                senior_dev_confidence=90.0,
                critic_confidence=80.0,
                blockers=[],
                findings=[],
                violations=[],
                summary="Approved",
                auto_merge_eligible=True,
                pr_number=pr_number,
                pr_title="test",
                story_id="ST-001",
            )

            await handler.review_pr(pr_number)

            mock_call.assert_called_once_with(pr_number)

    @pytest.mark.asyncio
    async def test_pr_approved_when_gitreviewbot_approves(
        self, handler, mock_approve_decision
    ):
        """Verify PR approved when GitReviewBot returns approved."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_approve_decision

            result = await handler.review_pr(pr_number)

            assert result.status == ReviewStatus.COMPLETED
            assert result.approved is True
            assert result.pr_number == pr_number
            assert len(result.review_comments) > 0
            assert result.completed_at is not None
            assert result.duration_seconds is not None

    @pytest.mark.asyncio
    async def test_pr_rejected_when_gitreviewbot_rejects(
        self, handler, mock_reject_decision
    ):
        """Verify PR rejected when GitReviewBot returns rejected."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_reject_decision

            result = await handler.review_pr(pr_number)

            assert result.status == ReviewStatus.COMPLETED
            assert result.approved is False
            assert result.pr_number == pr_number
            assert len(result.review_comments) > 0
            # Should include blockers in comments
            assert any(
                "Missing error handling" in comment
                for comment in result.review_comments
            )

    @pytest.mark.asyncio
    async def test_pr_needs_review_when_gitreviewbot_uncertain(
        self, handler, mock_uncertain_decision
    ):
        """Verify PR flagged for human review when GitReviewBot uncertain."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_uncertain_decision

            result = await handler.review_pr(pr_number)

            assert result.status == ReviewStatus.ESCALATED
            assert result.approved is False
            assert result.pr_number == pr_number
            assert result.escalation_reason is not None
            assert "confidence" in result.escalation_reason.lower()

    @pytest.mark.asyncio
    async def test_pr_escalated_on_timeout(self, handler):
        """Verify PR escalated when GitReviewBot times out."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = asyncio.TimeoutError()

            with patch.object(
                handler, "escalate_to_human", new_callable=AsyncMock
            ) as mock_escalate:
                result = await handler.review_pr(pr_number)

                assert result.status == ReviewStatus.TIMEOUT
                assert result.escalation_reason is not None
                assert "timed out" in result.escalation_reason.lower()
                mock_escalate.assert_called_once()

    @pytest.mark.asyncio
    async def test_pr_escalated_on_exception(self, handler):
        """Verify PR escalated when GitReviewBot raises exception."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = Exception("API Error")

            with patch.object(
                handler, "escalate_to_human", new_callable=AsyncMock
            ) as mock_escalate:
                result = await handler.review_pr(pr_number)

                assert result.status == ReviewStatus.FAILED
                assert result.escalation_reason is not None
                assert "failed" in result.escalation_reason.lower()
                mock_escalate.assert_called_once()

    def test_all_four_methods_exist(self):
        """Verify all 4 required GitReviewBot methods exist."""
        handler = StandardPathHandler()

        # Check all 4 methods exist
        assert hasattr(handler, "_call_gitreviewbot")
        assert hasattr(handler, "_check_gitreviewbot_status")
        assert hasattr(handler, "_process_gitreviewbot_result")
        assert hasattr(handler, "_handle_gitreviewbot_failure")

        # Check they are callable
        assert callable(handler._call_gitreviewbot)
        assert callable(handler._check_gitreviewbot_status)
        assert callable(handler._process_gitreviewbot_result)
        assert callable(handler._handle_gitreviewbot_failure)

    @pytest.mark.asyncio
    async def test_call_gitreviewbot_returns_decision(self, handler):
        """Verify _call_gitreviewbot returns a Decision object."""
        pr_number = 123
        mock_decision = Decision(
            decision=DecisionType.APPROVE,
            confidence=85.0,
            senior_dev_confidence=90.0,
            critic_confidence=80.0,
            blockers=[],
            findings=[],
            violations=[],
            summary="Approved",
            auto_merge_eligible=True,
            pr_number=pr_number,
            pr_title="test",
            story_id="ST-001",
        )

        with patch(
            "src.autonomous_git.gitreviewbot.bot.GitReviewBot"
        ) as mock_bot_class:
            mock_bot = MagicMock()
            mock_bot.review_pr = AsyncMock(return_value=mock_decision)
            mock_bot_class.return_value = mock_bot

            result = await handler._call_gitreviewbot(pr_number)

            assert result == mock_decision
            mock_bot.review_pr.assert_called_once_with(pr_number)

    def test_process_gitreviewbot_result_approve(self, handler, mock_approve_decision):
        """Verify _process_gitreviewbot_result handles APPROVE correctly."""
        pr_number = 123

        result = handler._process_gitreviewbot_result(pr_number, mock_approve_decision)

        assert result.status == ReviewStatus.COMPLETED
        assert result.approved is True
        assert result.pr_number == pr_number

    def test_process_gitreviewbot_result_reject(self, handler, mock_reject_decision):
        """Verify _process_gitreviewbot_result handles REQUEST_CHANGES correctly."""
        pr_number = 123

        result = handler._process_gitreviewbot_result(pr_number, mock_reject_decision)

        assert result.status == ReviewStatus.COMPLETED
        assert result.approved is False
        assert result.pr_number == pr_number

    def test_process_gitreviewbot_result_uncertain(
        self, handler, mock_uncertain_decision
    ):
        """Verify _process_gitreviewbot_result handles COMMENT correctly."""
        pr_number = 123

        result = handler._process_gitreviewbot_result(
            pr_number, mock_uncertain_decision
        )

        assert result.status == ReviewStatus.ESCALATED
        assert result.approved is False
        assert result.escalation_reason is not None

    @pytest.mark.asyncio
    async def test_check_gitreviewbot_status_pending(self, handler):
        """Verify _check_gitreviewbot_status returns PENDING for unknown PR."""
        pr_number = 999  # Unknown PR

        status = await handler._check_gitreviewbot_status(pr_number)

        assert status == ReviewStatus.PENDING

    @pytest.mark.asyncio
    async def test_check_gitreviewbot_status_existing(self, handler):
        """Verify _check_gitreviewbot_status returns correct status for known PR."""
        pr_number = 123
        handler._active_reviews[pr_number] = ReviewResult(
            pr_number=pr_number,
            status=ReviewStatus.IN_PROGRESS,
            classification=PRClassification.STANDARD,
            started_at=datetime.now(),
        )

        status = await handler._check_gitreviewbot_status(pr_number)

        assert status == ReviewStatus.IN_PROGRESS

    def test_handle_gitreviewbot_failure(self, handler):
        """Verify _handle_gitreviewbot_failure creates proper result."""
        pr_number = 123
        error = Exception("Test error")

        result = handler._handle_gitreviewbot_failure(pr_number, error)

        assert result.status == ReviewStatus.FAILED
        assert result.pr_number == pr_number
        assert result.escalation_reason is not None
        assert "Test error" in result.escalation_reason
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_review_pr_tracks_duration(self, handler, mock_approve_decision):
        """Verify review_pr tracks start and completion times."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_approve_decision

            result = await handler.review_pr(pr_number)

            assert result.started_at is not None
            assert result.completed_at is not None
            assert result.duration_seconds is not None
            assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_review_pr_classifies_as_standard(
        self, handler, mock_approve_decision
    ):
        """Verify review_pr classifies PR as STANDARD."""
        pr_number = 123

        with patch.object(
            handler, "_call_gitreviewbot", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_approve_decision

            result = await handler.review_pr(pr_number)

            assert result.classification == PRClassification.STANDARD
