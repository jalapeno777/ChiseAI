"""Tests for auto-approval module integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.autonomous_git.auto_approval import (
    AutoApprovalConfig,
    AutoApprover,
    DiscordNotifier,
    ExclusionManager,
    RateLimiter,
    SafetyChecker,
    load_config,
)
from src.autonomous_git.auto_approval.approver import (
    RiskClassification,
    RiskLevel,
)


class TestModuleIntegration:
    """Integration tests for the auto-approval module."""

    @pytest.mark.asyncio
    async def test_full_flow_success(self):
        """Test complete auto-approval flow with all components."""
        # Create config
        config = AutoApprovalConfig(
            enabled=True,
            merge_strategy="squash",
        )

        # Create approver with mocked dependencies
        approver = AutoApprover(config=config)

        # Mock path classification
        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py", "tests/test.py"],
                reasoning="Safe documentation changes",
                pr_number=123,
            )

            # Mock safety checks to pass
            approver.safety_checker.run_checks = AsyncMock(
                return_value=MagicMock(
                    all_passed=True,
                    checks=[],
                    pr_number=123,
                    timestamp="2025-02-21T10:00:00+00:00",
                    to_dict=lambda: {"all_passed": True},
                )
            )

            # Mock rate limiter to allow
            approver.rate_limiter.check_limits = AsyncMock(return_value=True)
            approver.rate_limiter.record_success = AsyncMock()

            # Mock approve/merge/log
            approver._approve_pr = AsyncMock()
            approver._merge_pr = AsyncMock()
            approver._log_approval = AsyncMock()
            approver.notifier.notify_auto_merge = AsyncMock()

            # Process PR
            pr_data = {
                "title": "Fix documentation ST-123",
                "user": {"login": "dev1"},
                "mergeable": True,
                "base": {"ref": "main"},
                "status_checks": [
                    {"name": "ci/build", "status": "success", "required": True},
                ],
            }

            result = await approver.process_pr(123, pr_data)

        # Verify success
        assert result.success is True
        assert result.pr_number == 123

        # Verify all steps were called
        approver._approve_pr.assert_called_once()
        approver._merge_pr.assert_called_once()
        approver.rate_limiter.record_success.assert_called_once()
        approver.notifier.notify_auto_merge.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_flow_blocked_by_exclusion(self):
        """Test flow blocked by exclusion list."""
        from src.autonomous_git.auto_approval.config import ExclusionConfig

        config = AutoApprovalConfig(
            exclusions=ExclusionConfig(paths=["docs/security/*.md"]),
        )
        approver = AutoApprover(config=config)

        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["docs/security/policy.md"],  # Excluded path
                reasoning="Safe changes",
                pr_number=123,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=MagicMock(
                    all_passed=True,
                    to_dict=lambda: {"all_passed": True},
                )
            )

            pr_data = {
                "title": "Update policy ST-123",
                "user": {"login": "dev1"},
            }

            result = await approver.process_pr(123, pr_data)

        # Should be blocked by exclusion
        assert result.success is False
        assert "excluded" in result.message.lower()

    @pytest.mark.asyncio
    async def test_full_flow_emergency_stop(self):
        """Test flow blocked by emergency stop."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "true"

        approver = AutoApprover(redis_client=mock_redis)

        result = await approver.process_pr(123)

        assert result.success is False
        assert "emergency stop" in result.message.lower()

    @pytest.mark.asyncio
    async def test_components_work_together(self):
        """Test that all components can be instantiated and work together."""
        # Create all components
        config = load_config()

        RateLimiter(
            max_per_hour=config.rate_limits.max_per_hour,
            max_consecutive=config.rate_limits.max_consecutive,
        )

        SafetyChecker(
            require_green_ci=config.safety_checks.require_green_ci,
            require_story_id=config.safety_checks.require_story_id,
        )

        ExclusionManager(
            paths=config.exclusions.paths,
            authors=config.exclusions.authors,
            title_patterns=config.exclusions.title_patterns,
        )

        DiscordNotifier(
            channel=config.notifications.discord_channel,
            rate_limit=config.notifications.rate_limit,
        )

        approver = AutoApprover(config=config)

        # Verify components are properly linked
        assert approver.rate_limiter is not None
        assert approver.safety_checker is not None
        assert approver.exclusion_manager is not None
        assert approver.notifier is not None

    def test_config_loading_integration(self):
        """Test config loading with all sections."""
        config = load_config()

        # Verify all config sections are present
        assert hasattr(config, "enabled")
        assert hasattr(config, "merge_strategy")
        assert hasattr(config, "rate_limits")
        assert hasattr(config, "safety_checks")
        assert hasattr(config, "exclusions")
        assert hasattr(config, "notifications")

        # Verify nested configs
        assert hasattr(config.rate_limits, "max_per_hour")
        assert hasattr(config.rate_limits, "max_consecutive")
        assert hasattr(config.safety_checks, "require_green_ci")
        assert hasattr(config.safety_checks, "require_story_id")
        assert hasattr(config.exclusions, "paths")
        assert hasattr(config.exclusions, "authors")
        assert hasattr(config.notifications, "discord_channel")

    @pytest.mark.asyncio
    async def test_rate_limiting_integration(self):
        """Test rate limiting across multiple approvals."""
        from src.autonomous_git.auto_approval.config import RateLimitConfig

        config = AutoApprovalConfig(
            rate_limits=RateLimitConfig(max_per_hour=2, max_consecutive=2),
        )
        approver = AutoApprover(config=config)

        # Mock everything to pass
        with patch(
            "src.autonomous_git.auto_approval.approver.get_path_classification"
        ) as mock_classify:
            mock_classify.return_value = RiskClassification(
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                files=["src/main.py"],
                reasoning="Safe",
                pr_number=1,
            )

            approver.safety_checker.run_checks = AsyncMock(
                return_value=MagicMock(
                    all_passed=True,
                    to_dict=lambda: {"all_passed": True},
                )
            )

            approver._approve_pr = AsyncMock()
            approver._merge_pr = AsyncMock()
            approver._log_approval = AsyncMock()
            approver.notifier.notify_auto_merge = AsyncMock()

            pr_data = {
                "title": "Fix ST-123",
                "user": {"login": "dev1"},
            }

            # First 2 should succeed
            result1 = await approver.process_pr(1, pr_data)
            assert result1.success is True

            result2 = await approver.process_pr(2, pr_data)
            assert result2.success is True

            # Third should be rate limited
            result3 = await approver.process_pr(3, pr_data)
            assert result3.success is False
            assert "rate limit" in result3.message.lower()
