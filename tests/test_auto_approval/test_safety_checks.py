"""Tests for auto-approval safety checks."""

import pytest
from src.autonomous_git.auto_approval.safety_checks import (
    CheckResult,
    CheckStatus,
    SafetyChecker,
    SafetyCheckResult,
)


class TestSafetyChecker:
    """Test cases for SafetyChecker."""

    def test_init_default_values(self):
        """Test safety checker initializes with default values."""
        checker = SafetyChecker()

        assert checker.require_green_ci is True
        assert checker.require_story_id is True
        assert checker.check_merge_conflicts is True
        assert checker.gitea is None

    def test_init_custom_values(self):
        """Test safety checker initializes with custom values."""
        checker = SafetyChecker(
            require_green_ci=False,
            require_story_id=False,
            check_merge_conflicts=False,
        )

        assert checker.require_green_ci is False
        assert checker.require_story_id is False
        assert checker.check_merge_conflicts is False

    @pytest.mark.asyncio
    async def test_run_checks_all_pass(self):
        """Test all safety checks pass."""
        checker = SafetyChecker()

        pr_data = {
            "title": "Fix bug ST-123",
            "user": {"login": "dev1"},
            "mergeable": True,
            "base": {"ref": "main"},
            "status_checks": [
                {"name": "ci/build", "status": "success", "required": True},
                {"name": "ci/test", "status": "success", "required": True},
            ],
        }

        result = await checker.run_checks(123, pr_data)

        assert result.all_passed is True
        assert result.pr_number == 123
        assert len(result.checks) == 5

    @pytest.mark.asyncio
    async def test_run_checks_merge_conflict(self):
        """Test fails when merge conflict exists."""
        checker = SafetyChecker()

        pr_data = {
            "title": "Fix bug ST-123",
            "user": {"login": "dev1"},
            "mergeable": False,
            "base": {"ref": "main"},
            "status_checks": [],
        }

        result = await checker.run_checks(123, pr_data)

        assert result.all_passed is False

        conflict_check = [c for c in result.checks if c.name == "merge_conflicts"][0]
        assert conflict_check.status == CheckStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_checks_ci_failure(self):
        """Test fails when CI fails."""
        checker = SafetyChecker()

        pr_data = {
            "title": "Fix bug ST-123",
            "user": {"login": "dev1"},
            "mergeable": True,
            "base": {"ref": "main"},
            "status_checks": [
                {"name": "ci/build", "status": "failure", "required": True},
            ],
        }

        result = await checker.run_checks(123, pr_data)

        assert result.all_passed is False

        ci_check = [c for c in result.checks if c.name == "ci_status"][0]
        assert ci_check.status == CheckStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_checks_missing_story_id(self):
        """Test fails when story ID is missing."""
        checker = SafetyChecker()

        pr_data = {
            "title": "Fix bug without story ID",
            "user": {"login": "dev1"},
            "mergeable": True,
            "base": {"ref": "main"},
            "status_checks": [],
        }

        result = await checker.run_checks(123, pr_data)

        assert result.all_passed is False

        story_check = [c for c in result.checks if c.name == "story_id"][0]
        assert story_check.status == CheckStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_checks_story_id_variations(self):
        """Test various story ID formats are recognized."""
        checker = SafetyChecker()

        valid_titles = [
            "Fix bug ST-123",
            "Feature CH-456",
            "Update FT-789",
            "Reward fix REWARD-001",
            "Repo cleanup REPO-42",
            "Safety fix SAFETY-999",
            "Branch fix BRANCH-1",
            "Paper trading PAPER-55",
            "Reconciliation RECON-100",
        ]

        for title in valid_titles:
            pr_data = {
                "title": title,
                "user": {"login": "dev1"},
                "mergeable": True,
                "base": {"ref": "main"},
                "status_checks": [],
            }

            result = await checker._check_story_id(pr_data)
            assert (
                result.status == CheckStatus.PASSED
            ), f"Title '{title}' should be valid"

    @pytest.mark.asyncio
    async def test_run_checks_disabled_checks(self):
        """Test that disabled checks are skipped."""
        checker = SafetyChecker(
            require_green_ci=False,
            require_story_id=False,
            check_merge_conflicts=False,
        )

        pr_data = {
            "title": "No story ID here",
            "user": {"login": "dev1"},
            "mergeable": False,
            "base": {"ref": "main"},
            "status_checks": [
                {"name": "ci/build", "status": "failure", "required": True},
            ],
        }

        result = await checker.run_checks(123, pr_data)

        assert result.all_passed is True  # All checks skipped

        # Verify checks were skipped
        for check in result.checks:
            if check.name in ["merge_conflicts", "ci_status", "story_id"]:
                assert check.status == CheckStatus.SKIPPED

    def test_has_story_id_valid(self):
        """Test has_story_id with valid tokens."""
        checker = SafetyChecker()

        assert checker.has_story_id("Fix ST-123") is True
        assert checker.has_story_id("Feature CH-456") is True
        assert checker.has_story_id("Update FT-789") is True
        assert checker.has_story_id("REWARD-001: Fix") is True

    def test_has_story_id_invalid(self):
        """Test has_story_id with invalid tokens."""
        checker = SafetyChecker()

        assert checker.has_story_id("Fix bug") is False
        assert checker.has_story_id("Update docs") is False
        assert checker.has_story_id("ST without number") is False

    @pytest.mark.asyncio
    async def test_safety_check_result_to_dict(self):
        """Test SafetyCheckResult serialization."""
        checks = [
            CheckResult(name="test1", status=CheckStatus.PASSED, message="OK"),
            CheckResult(name="test2", status=CheckStatus.FAILED, message="Error"),
        ]

        result = SafetyCheckResult(
            all_passed=False,
            checks=checks,
            pr_number=123,
            timestamp="2025-02-21T10:00:00+00:00",
        )

        data = result.to_dict()

        assert data["all_passed"] is False
        assert data["pr_number"] == 123
        assert data["timestamp"] == "2025-02-21T10:00:00+00:00"
        assert len(data["checks"]) == 2
        assert data["checks"][0]["name"] == "test1"
        assert data["checks"][0]["status"] == "passed"
