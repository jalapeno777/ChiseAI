#!/usr/bin/env python3
"""
Tests for branch deletion guard functionality.

These tests verify that:
1. Branches without PR/evidence are blocked from deletion
2. Branches with PRs are allowed for deletion
3. Branches merged to main are allowed for deletion
4. Force override works correctly
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts/swarm to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "swarm"))

# Mock config.bootstrap before importing branch_hygiene_check
sys.modules["config"] = MagicMock()
sys.modules["config.bootstrap"] = MagicMock()

from branch_hygiene_check import (
    check_branch_deletion_eligibility,
    check_pr_exists,
    log_deletion_attempt_to_redis,
)


class TestBranchDeletionEligibility(unittest.TestCase):
    """Test branch deletion eligibility checking."""

    @patch("branch_hygiene_check.subprocess.run")
    def test_branch_merged_to_main(self, mock_run):
        """Test that merged branches are eligible for deletion."""
        # Mock the git branch --merged command to show branch is merged
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="feature/test-branch\n",
            stderr="",
        )

        result = check_branch_deletion_eligibility("feature/test-branch")

        self.assertTrue(result["eligible"])
        self.assertTrue(result["is_merged"])
        self.assertTrue(result["has_merge_evidence"])
        self.assertIn("merged to main", result["reason"])

    @patch("branch_hygiene_check.subprocess.run")
    def test_branch_not_merged_no_pr(self, mock_run):
        """Test that unmerged branches without PRs are blocked."""

        # Mock git commands to show branch is not merged
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n", stderr="")
            elif "merge-base" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="")  # Not ancestor
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        # Mock PR check to return no PR
        with patch("branch_hygiene_check.check_pr_exists") as mock_pr:
            mock_pr.return_value = (False, "No PR found")

            result = check_branch_deletion_eligibility("feature/test-branch")

            self.assertFalse(result["eligible"])
            self.assertFalse(result["is_merged"])
            self.assertFalse(result["has_pr"])
            self.assertIn("No PR or merge evidence", result["reason"])

    @patch("branch_hygiene_check.subprocess.run")
    def test_branch_with_open_pr(self, mock_run):
        """Test that branches with open PRs are eligible."""

        # Mock git commands to show branch is not merged
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n", stderr="")
            elif "merge-base" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        # Mock PR check to return open PR
        with patch("branch_hygiene_check.check_pr_exists") as mock_pr:
            mock_pr.return_value = (True, "open PR #42")

            result = check_branch_deletion_eligibility("feature/test-branch")

            self.assertTrue(result["eligible"])
            self.assertTrue(result["has_pr"])
            self.assertEqual(result["pr_detail"], "open PR #42")
            self.assertIn("open PR #42", result["reason"])

    @patch("branch_hygiene_check.subprocess.run")
    def test_branch_with_merged_pr(self, mock_run):
        """Test that branches with merged PRs are eligible."""

        # Mock git commands to show branch is not merged (locally)
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n", stderr="")
            elif "merge-base" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        # Mock PR check to return merged PR
        with patch("branch_hygiene_check.check_pr_exists") as mock_pr:
            mock_pr.return_value = (True, "merged PR #42")

            result = check_branch_deletion_eligibility("feature/test-branch")

            self.assertTrue(result["eligible"])
            self.assertTrue(result["has_pr"])
            self.assertEqual(result["pr_detail"], "merged PR #42")

    @patch("branch_hygiene_check.subprocess.run")
    def test_branch_ancestor_of_main(self, mock_run):
        """Test that branches whose commits are ancestors of main are eligible."""

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n", stderr="")
            elif "merge-base" in cmd:
                # Returncode 0 means it IS an ancestor
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        result = check_branch_deletion_eligibility("feature/test-branch")

        self.assertTrue(result["eligible"])
        self.assertFalse(result["is_merged"])  # Not in --merged list
        self.assertTrue(result["has_merge_evidence"])
        self.assertIn("ancestor", result["reason"])


class TestPRExists(unittest.TestCase):
    """Test PR existence checking."""

    @patch("urllib.request.urlopen")
    @patch.dict(
        os.environ,
        {
            "GITEA_TOKEN": "test-token",
            "GITEA_OWNER": "test-owner",
            "GITEA_REPO": "test-repo",
            "GITEA_BASE_URL": "http://test.example.com",
        },
    )
    def test_open_pr_exists(self, mock_urlopen):
        """Test detection of open PR."""
        # Mock response with open PR
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [
                {
                    "number": 42,
                    "state": "open",
                    "head": {"ref": "feature/test-branch"},
                    "base": {"ref": "main"},
                    "merged": False,
                }
            ]
        ).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        has_pr, detail = check_pr_exists("feature/test-branch")

        self.assertTrue(has_pr)
        self.assertIn("open PR #42", detail)

    @patch("urllib.request.urlopen")
    @patch.dict(
        os.environ,
        {
            "GITEA_TOKEN": "test-token",
            "GITEA_OWNER": "test-owner",
            "GITEA_REPO": "test-repo",
            "GITEA_BASE_URL": "http://test.example.com",
        },
    )
    def test_merged_pr_exists(self, mock_urlopen):
        """Test detection of merged PR."""
        # Mock response with merged PR
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [
                {
                    "number": 42,
                    "state": "closed",
                    "head": {"ref": "feature/test-branch"},
                    "base": {"ref": "main"},
                    "merged": True,
                }
            ]
        ).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        has_pr, detail = check_pr_exists("feature/test-branch")

        self.assertTrue(has_pr)
        self.assertIn("merged PR #42", detail)

    @patch("urllib.request.urlopen")
    @patch.dict(
        os.environ,
        {
            "GITEA_TOKEN": "test-token",
            "GITEA_OWNER": "test-owner",
            "GITEA_REPO": "test-repo",
            "GITEA_BASE_URL": "http://test.example.com",
        },
    )
    def test_no_pr_exists(self, mock_urlopen):
        """Test when no PR exists."""
        # Mock response with no matching PRs
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            [
                {
                    "number": 1,
                    "state": "open",
                    "head": {"ref": "other-branch"},
                    "base": {"ref": "main"},
                    "merged": False,
                }
            ]
        ).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        has_pr, detail = check_pr_exists("feature/test-branch")

        self.assertFalse(has_pr)
        self.assertIn("No open/merged PR found", detail)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_vars(self):
        """Test handling of missing environment variables."""
        has_pr, detail = check_pr_exists("feature/test-branch")

        self.assertFalse(has_pr)
        self.assertIn("env vars missing", detail)


class TestRedisLogging(unittest.TestCase):
    """Test Redis logging functionality."""

    @patch("branch_hygiene_check.REDIS_AVAILABLE", True)
    @patch("branch_hygiene_check.redis.Redis")
    @patch.dict(
        os.environ,
        {
            "CHISE_REDIS_HOST": "localhost",
            "CHISE_REDIS_PORT": "6379",
            "CHISE_REDIS_DB": "0",
        },
    )
    def test_log_eligible_deletion(self, mock_redis_class):
        """Test logging an eligible deletion."""
        mock_redis = MagicMock()
        mock_redis_class.return_value = mock_redis

        result = {
            "eligible": True,
            "reason": "Branch is merged to main",
            "has_pr": False,
            "is_merged": True,
            "has_merge_evidence": True,
        }

        log_deletion_attempt_to_redis("feature/test-branch", result, force_used=False)

        # Verify lpush was called
        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        self.assertEqual(call_args[0][0], "bmad:chiseai:branch_hygiene:deletion_checks")

        # Verify ltrim was called to limit list size
        mock_redis.ltrim.assert_called_once_with(
            "bmad:chiseai:branch_hygiene:deletion_checks", 0, 999
        )

    @patch("branch_hygiene_check.REDIS_AVAILABLE", True)
    @patch("branch_hygiene_check.redis.Redis")
    @patch.dict(
        os.environ,
        {
            "CHISE_REDIS_HOST": "localhost",
            "CHISE_REDIS_PORT": "6379",
            "CHISE_REDIS_DB": "0",
        },
    )
    def test_log_blocked_deletion(self, mock_redis_class):
        """Test logging a blocked deletion."""
        mock_redis = MagicMock()
        mock_redis_class.return_value = mock_redis

        result = {
            "eligible": False,
            "reason": "No PR or merge evidence found",
            "has_pr": False,
            "is_merged": False,
            "has_merge_evidence": False,
        }

        log_deletion_attempt_to_redis("feature/test-branch", result, force_used=True)

        # Verify lpush was called
        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        self.assertEqual(call_args[0][0], "bmad:chiseai:branch_hygiene:deletion_checks")

        # Verify ltrim was called to limit list size
        mock_redis.ltrim.assert_called_once_with(
            "bmad:chiseai:branch_hygiene:deletion_checks", 0, 999
        )

    @patch("branch_hygiene_check.REDIS_AVAILABLE", False)
    def test_redis_not_available(self):
        """Test graceful handling when Redis is not available."""
        result = {
            "eligible": True,
            "reason": "Test",
            "has_pr": False,
            "is_merged": True,
            "has_merge_evidence": True,
        }

        # Should not raise exception
        log_deletion_attempt_to_redis("feature/test-branch", result)


class TestPreDeleteGuardHook(unittest.TestCase):
    """Test the pre-delete-guard hook functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.hook_path = (
            Path(__file__).parent.parent.parent / ".git" / "hooks" / "pre-delete-guard"
        )

    def test_hook_exists(self):
        """Test that the pre-delete-guard hook exists."""
        self.assertTrue(self.hook_path.exists(), "pre-delete-guard hook should exist")

    def test_hook_is_executable(self):
        """Test that the hook is executable."""
        if self.hook_path.exists():
            self.assertTrue(
                os.access(self.hook_path, os.X_OK),
                "pre-delete-guard hook should be executable",
            )

    def test_hook_contains_required_checks(self):
        """Test that hook contains required check functions."""
        if not self.hook_path.exists():
            self.skipTest("Hook does not exist")

        content = self.hook_path.read_text()

        # Check for required functions
        self.assertIn("_pr_exists_for_branch", content)
        self.assertIn("_is_merged_to_main", content)
        self.assertIn("_has_merge_commit", content)
        self.assertIn("check_deletion_eligibility", content)

        # Check for force override
        self.assertIn("--force", content)
        self.assertIn("Force override", content)


class TestIntegration(unittest.TestCase):
    """Integration tests for the full deletion guard workflow."""

    @patch("branch_hygiene_check.subprocess.run")
    def test_full_workflow_merged_branch(self, mock_run):
        """Test full workflow for a merged branch."""

        # Mock all git commands for merged branch
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(
                    returncode=0, stdout="feature/merged-branch\n", stderr=""
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        # Check eligibility
        result = check_branch_deletion_eligibility("feature/merged-branch")

        # Verify result
        self.assertTrue(result["eligible"])
        self.assertTrue(result["is_merged"])

        # Simulate the guard check
        is_eligible = result["eligible"]
        self.assertTrue(is_eligible, "Merged branch should pass guard")

    @patch("branch_hygiene_check.subprocess.run")
    def test_full_workflow_unmerged_no_pr(self, mock_run):
        """Test full workflow for unmerged branch without PR."""

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            if "branch" in cmd and "--merged" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123\n", stderr="")
            elif "merge-base" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        with patch("branch_hygiene_check.check_pr_exists") as mock_pr:
            mock_pr.return_value = (False, "No PR found")

            result = check_branch_deletion_eligibility("feature/unmerged-branch")

            # Verify result
            self.assertFalse(result["eligible"])
            self.assertFalse(result["is_merged"])
            self.assertFalse(result["has_pr"])

            # Simulate the guard blocking
            is_eligible = result["eligible"]
            self.assertFalse(
                is_eligible, "Unmerged branch without PR should be blocked"
            )


if __name__ == "__main__":
    unittest.main()
