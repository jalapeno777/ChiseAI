"""Tests for auto-approval approver."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.autonomous_git.auto_approval.approver import (
    AutoApprover,
    process_safe_pr,
    is_auto_approval_disabled,
    RiskLevel,
    RiskClassification,
    ApprovalResult,
)
from src.autonomous_git.auto_approval.config import AutoApprovalConfig
from src.autonomous_git.auto_approval.safety_checks import (
    SafetyCheckResult,
    CheckResult,
    CheckStatus,
)


class TestAutoApprover:
    """Test cases for AutoApprover."""

    def test_init_default(self):
        """Test auto-approver initializes with default config."""
        approver = AutoApprover()

        assert approver.config.enabled is True
        assert approver.config.merge_strategy == "squash"
        assert approver.redis is None
        assert approver.gitea is None

    def test_init_with_config(self):
        """Test auto-approver initializes with custom config."""
        config = AutoApprovalConfig(enabled=False, merge_strategy="merge")
        approver = AutoApprover(config=config)

        assert approver.config.enabled is False
        assert approver.config.merge_strategy == "merge"

    @pytest.mark.asyncio
    async def test_process_pr_emergency_stop(self):
        """Test PR processing blocked by emergency stop."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "true"

        approver = AutoApprover(redis_client=mock_redis)

        result = await approver.process_pr(123)

        assert result.success is False
        assert "emergency stop" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_disabled(self):
        """Test PR processing when auto-approval is disabled."""
        config = AutoApprovalConfig(enabled=False)
        approver = AutoApprover(config=config)

        result = await approver.process_pr(123)

        assert result.success is False
        assert "disabled" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_not_safe(self):
        """Test PR processing when risk level is not SAFE."""
        approver = AutoApprover()

        # Mock the path classification to return MEDIUM_RISK
        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.MEDIUM_RISK,
                confidence=0.8,
                files=["src/main.py"],
                reasoning="Medium risk files",
                pr_number=123,
            )

            result = await approver.process_pr(123)

        assert result.success is False
        assert "not eligible" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_safety_checks_fail(self):
        """Test PR processing when safety checks fail."""
        approver = AutoApprover()

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe change",
                pr_number=123,
            )

            # Mock safety checker to fail
            approver.safety_checker.run_checks = AsyncMock(
                return_value=SafetyCheckResult(
                    all_passed=False,
                    checks=[
                        CheckResult(
                            name="story_id",
                            status=CheckStatus.FAILED,
                            message="No story ID",
                        ),
                    ],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                )
            )

            result = await approver.process_pr(123)

        assert result.success is False
        assert "safety checks failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_excluded(self):
        """Test PR processing when PR is excluded."""
        from src.autonomous_git.auto_approval.config import ExclusionConfig

        config = AutoApprovalConfig(
            exclusions=ExclusionConfig(authors=["external"]),
        )
        approver = AutoApprover(config=config)

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe change",
                pr_number=123,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=SafetyCheckResult(
                    all_passed=True,
                    checks=[],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                )
            )

            pr_data = {
                "title": "Fix bug ST-123",
                "user": {"login": "external"},
            }

            result = await approver.process_pr(123, pr_data)

        assert result.success is False
        assert "excluded" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_rate_limited(self):
        """Test PR processing when rate limited."""
        approver = AutoApprover()

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe change",
                pr_number=123,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=SafetyCheckResult(
                    all_passed=True,
                    checks=[],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                )
            )

            # Mock rate limiter to fail
            approver.rate_limiter.check_limits = AsyncMock(return_value=False)

            pr_data = {
                "title": "Fix bug ST-123",
                "user": {"login": "dev1"},
            }

            result = await approver.process_pr(123, pr_data)

        assert result.success is False
        assert "rate limit" in result.message.lower()

    @pytest.mark.asyncio
    async def test_process_pr_success(self):
        """Test successful PR processing."""
        approver = AutoApprover()

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe change",
                pr_number=123,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=SafetyCheckResult(
                    all_passed=True,
                    checks=[],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                )
            )

            approver.rate_limiter.check_limits = AsyncMock(return_value=True)
            approver.rate_limiter.record_success = AsyncMock()
            approver._approve_pr = AsyncMock()
            approver._merge_pr = AsyncMock()
            approver._log_approval = AsyncMock()
            approver.notifier.notify_auto_merge = AsyncMock()

            pr_data = {
                "title": "Fix bug ST-123",
                "user": {"login": "dev1"},
            }

            result = await approver.process_pr(123, pr_data)

        assert result.success is True
        assert "successfully" in result.message.lower()
        approver._approve_pr.assert_called_once()
        approver._merge_pr.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_pr_approve_merge_failure(self):
        """Test PR processing when approve/merge fails."""
        approver = AutoApprover()

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe change",
                pr_number=123,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=SafetyCheckResult(
                    all_passed=True,
                    checks=[],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                )
            )

            approver.rate_limiter.check_limits = AsyncMock(return_value=True)
            approver._approve_pr = AsyncMock(side_effect=Exception("API error"))
            approver.notifier.notify_failure = AsyncMock()

            pr_data = {
                "title": "Fix bug ST-123",
                "user": {"login": "dev1"},
            }

            result = await approver.process_pr(123, pr_data)

        assert result.success is False
        assert "approval/merge failed" in result.message.lower()
        approver.notifier.notify_failure.assert_called_once()


class TestIsAutoApprovalDisabled:
    """Test cases for is_auto_approval_disabled."""

    @pytest.mark.asyncio
    async def test_disabled_true(self):
        """Test when emergency stop is set to true."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "true"

        result = await is_auto_approval_disabled(mock_redis)

        assert result is True

    @pytest.mark.asyncio
    async def test_disabled_false(self):
        """Test when emergency stop is not set."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        result = await is_auto_approval_disabled(mock_redis)

        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_variations(self):
        """Test various true values."""
        mock_redis = AsyncMock()

        for value in ["true", "True", "TRUE", "1", "yes", "YES"]:
            mock_redis.get.return_value = value
            result = await is_auto_approval_disabled(mock_redis)
            assert result is True, f"Value '{value}' should be considered true"

    @pytest.mark.asyncio
    async def test_no_redis(self):
        """Test when no Redis client provided."""
        result = await is_auto_approval_disabled(None)

        assert result is False


class TestProcessSafePr:
    """Test cases for process_safe_pr convenience function."""

    @pytest.mark.asyncio
    async def test_process_safe_pr(self):
        """Test convenience function."""
        with patch.object(AutoApprover, "process_pr") as mock_process:
            mock_process.return_value = ApprovalResult(
                success=True,
                pr_number=123,
                message="Success",
                timestamp="2025-02-21T10:00:00+00:00",
            )

            result = await process_safe_pr(123)

        assert result.success is True
        mock_process.assert_called_once_with(123)


class TestApprovalResult:
    """Test cases for ApprovalResult."""

    def test_to_dict(self):
        """Test ApprovalResult serialization."""
        classification = RiskClassification(
            risk_level=RiskLevel.SAFE,
            confidence=0.95,
            files=["src/main.py"],
            reasoning="Safe",
            pr_number=123,
        )

        result = ApprovalResult(
            success=True,
            pr_number=123,
            message="Success",
            timestamp="2025-02-21T10:00:00+00:00",
            classification=classification,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["pr_number"] == 123
        assert data["message"] == "Success"
        assert data["classification"]["risk_level"] == "safe"
        assert data["classification"]["confidence"] == 0.95
