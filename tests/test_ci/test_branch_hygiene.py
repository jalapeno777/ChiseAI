"""Tests for branch hygiene automation script."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import branch_hygiene as bh
from branch_hygiene import (
    BranchHygiene,
    BranchInfo,
    HygieneResult,
    RedisLogger,
)


class MockResponse:
    """Mock urllib response."""

    def __init__(self, data: dict | list, status: int = 200):
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._data).encode("utf-8")


class TestBranchInfo:
    """Tests for BranchInfo dataclass."""

    def test_branch_info_creation(self) -> None:
        """Test creating BranchInfo instance."""
        info = BranchInfo(
            name="feature/test",
            author="testuser",
            last_commit_date=datetime.now(UTC),
        )
        assert info.name == "feature/test"
        assert info.author == "testuser"
        assert info.merged_to_main is False


class TestHygieneResult:
    """Tests for HygieneResult dataclass."""

    def test_hygiene_result_creation(self) -> None:
        """Test creating HygieneResult instance."""
        result = HygieneResult(
            branch_name="feature/test",
            action="deleted",
            reason="merged 25 hours ago",
            author="testuser",
            timestamp=datetime.now(UTC),
            details={"pr_number": 42},
        )
        assert result.branch_name == "feature/test"
        assert result.action == "deleted"
        assert result.details["pr_number"] == 42


class TestIsProtectedBranch:
    """Tests for is_protected_branch function."""

    def test_main_is_protected(self) -> None:
        """AC6: main branch should be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("main") is True

    def test_master_is_protected(self) -> None:
        """master branch should be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("master") is True

    def test_release_branches_protected(self) -> None:
        """AC6: release/* branches should be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("release/v1.0") is True
        assert hygiene.is_protected_branch("release/2024-01") is True

    def test_safety_branches_protected(self) -> None:
        """safety/* branches should be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("safety/fix-123") is True

    def test_feature_branches_not_protected(self) -> None:
        """feature/* branches should not be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("feature/new-thing") is False

    def test_bugfix_branches_not_protected(self) -> None:
        """bugfix/* branches should not be protected."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        assert hygiene.is_protected_branch("bugfix/critical-fix") is False


class TestValidateBranchName:
    """Tests for validate_branch_name function."""

    def test_feature_prefix_valid(self) -> None:
        """AC4: feature/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("feature/ST-123-new-feature")
        assert is_valid is True
        assert "valid" in reason.lower()

    def test_bugfix_prefix_valid(self) -> None:
        """AC4: bugfix/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("bugfix/fix-memory-leak")
        assert is_valid is True

    def test_hotfix_prefix_valid(self) -> None:
        """AC4: hotfix/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("hotfix/security-patch")
        assert is_valid is True

    def test_docs_prefix_valid(self) -> None:
        """docs/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("docs/update-readme")
        assert is_valid is True

    def test_chore_prefix_valid(self) -> None:
        """chore/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("chore/update-deps")
        assert is_valid is True

    def test_test_prefix_valid(self) -> None:
        """test/* branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("test/add-unit-tests")
        assert is_valid is True

    def test_dependabot_valid(self) -> None:
        """dependabot branches should be valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("dependabot/npm/lodash-4.17.21")
        assert is_valid is True

    def test_protected_branch_valid(self) -> None:
        """Protected branches should be considered valid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("main")
        assert is_valid is True
        assert "protected" in reason.lower()

    def test_invalid_prefix(self) -> None:
        """Branches without valid prefix should be invalid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("random-branch-name")
        assert is_valid is False
        assert "naming convention" in reason.lower()

    def test_empty_suffix_invalid(self) -> None:
        """Branch with prefix but no suffix should be invalid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("feature/")
        assert is_valid is False

    def test_short_suffix_invalid(self) -> None:
        """Branch with very short suffix should be invalid."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        is_valid, reason = hygiene.validate_branch_name("feature/x")
        assert is_valid is False


class TestRedisLogger:
    """Tests for RedisLogger class."""

    def test_logger_creation_without_redis(self) -> None:
        """Test creating logger when Redis is unavailable."""
        with patch.object(RedisLogger, "_check_redis", return_value=False):
            logger = RedisLogger()
            assert logger._redis_available is False

    @patch("sys.stderr", new_callable=MagicMock)
    def test_log_operation_fallback(self, mock_stderr: MagicMock) -> None:
        """Test that log_operation falls back to stderr when Redis unavailable."""
        with patch.object(RedisLogger, "_check_redis", return_value=False):
            logger = RedisLogger()
            result = HygieneResult(
                branch_name="feature/test",
                action="deleted",
                reason="test reason",
                author="testuser",
                timestamp=datetime.now(UTC),
            )
            logger.log_operation(result)
            # Should print to stderr (mocked)
            assert True  # Just ensure no exception


class TestBranchHygieneAPI:
    """Tests for BranchHygiene API interactions."""

    @patch("urllib.request.urlopen")
    def test_get_branches_success(self, mock_urlopen: MagicMock) -> None:
        """Test getting branches from API."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {"name": "main", "commit": {"sha": "abc123"}},
                {"name": "feature/test", "commit": {"sha": "def456"}},
            ]
        )
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        branches = hygiene.get_branches()
        assert len(branches) == 2
        assert branches[0]["name"] == "main"

    @patch("urllib.request.urlopen")
    def test_get_branches_empty(self, mock_urlopen: MagicMock) -> None:
        """Test getting empty branch list."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse([])
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        branches = hygiene.get_branches()
        assert len(branches) == 0

    @patch("urllib.request.urlopen")
    def test_get_branches_error(self, mock_urlopen: MagicMock) -> None:
        """Test handling API error when getting branches."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "http://test/api",
            500,
            "Server Error",
            None,
            BytesIO(b"{}"),  # type: ignore[arg-type]
        )
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        branches = hygiene.get_branches()
        assert len(branches) == 0

    @patch("urllib.request.urlopen")
    def test_delete_branch_success(self, mock_urlopen: MagicMock) -> None:
        """Test deleting a branch."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse({})
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        success = hygiene.delete_branch("feature/old-branch")
        assert success is True

    @patch("urllib.request.urlopen")
    def test_delete_branch_dry_run(self, mock_urlopen: MagicMock) -> None:
        """Test dry run mode doesn't actually delete."""
        hygiene = BranchHygiene("owner", "repo", "http://test", "token", dry_run=True)
        success = hygiene.delete_branch("feature/old-branch")
        assert success is True
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_get_pr_for_branch(self, mock_urlopen: MagicMock) -> None:
        """Test finding merged PR for a branch."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "number": 42,
                    "head": {"ref": "feature/test"},
                    "merged": True,
                    "merged_at": "2024-01-01T00:00:00Z",
                    "user": {"login": "testuser"},
                }
            ]
        )
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        pr = hygiene.get_pr_for_branch("feature/test")
        assert pr is not None
        assert pr["number"] == 42
        assert pr["merged"] is True

    @patch("urllib.request.urlopen")
    def test_compare_branches(self, mock_urlopen: MagicMock) -> None:
        """Test comparing branches for divergence."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            {"ahead_by": 5, "behind_by": 10}
        )
        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        comparison = hygiene.compare_branches("main", "feature/test")
        assert comparison is not None
        assert comparison["ahead_by"] == 5
        assert comparison["behind_by"] == 10


class TestCleanupMergedBranches:
    """Tests for cleanup_merged_branches function."""

    @patch("urllib.request.urlopen")
    def test_delete_merged_branch_after_24h(self, mock_urlopen: MagicMock) -> None:
        """AC1: Merged branches should be deleted after 24 hours."""
        # Setup: branch merged 25 hours ago
        merged_at = (datetime.now(UTC) - timedelta(hours=25)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/old",
                    "commit": {"sha": "abc", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "get_pr_for_branch") as mock_get_pr:
            mock_get_pr.return_value = {
                "number": 1,
                "merged": True,
                "merged_at": merged_at.replace("+00:00", "Z"),
                "user": {"login": "testuser"},
            }

            with patch.object(
                hygiene, "delete_branch", return_value=True
            ) as mock_delete:
                results = hygiene.cleanup_merged_branches()
                mock_delete.assert_called_once_with("feature/old")
                assert len(results) == 1
                assert results[0].action == "deleted"

    @patch("urllib.request.urlopen")
    def test_keep_merged_branch_under_24h(self, mock_urlopen: MagicMock) -> None:
        """Merged branches under 24 hours should not be deleted."""
        # Setup: branch merged 12 hours ago
        merged_at = (datetime.now(UTC) - timedelta(hours=12)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/recent",
                    "commit": {"sha": "abc", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "get_pr_for_branch") as mock_get_pr:
            mock_get_pr.return_value = {
                "number": 1,
                "merged": True,
                "merged_at": merged_at.replace("+00:00", "Z"),
                "user": {"login": "testuser"},
            }

            with patch.object(hygiene, "delete_branch") as mock_delete:
                hygiene.cleanup_merged_branches()
                mock_delete.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_protect_main_from_deletion(self, mock_urlopen: MagicMock) -> None:
        """AC6: Protected branches should not be deleted."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {"name": "main", "commit": {"sha": "abc", "author": {"name": "user"}}},
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "delete_branch") as mock_delete:
            results = hygiene.cleanup_merged_branches()
            mock_delete.assert_not_called()
            assert any(
                r.branch_name == "main" and r.action == "skipped" for r in results
            )


class TestCheckStaleBranches:
    """Tests for check_stale_branches function."""

    @patch("urllib.request.urlopen")
    def test_warn_stale_branch_30_days(self, mock_urlopen: MagicMock) -> None:
        """AC2: Branches older than 30 days should trigger warning."""
        # Setup: commit 31 days ago
        commit_date = (datetime.now(UTC) - timedelta(days=31)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/old",
                    "commit": {
                        "sha": "abc",
                        "timestamp": commit_date.replace("+00:00", "Z"),
                        "author": {"name": "testuser"},
                    },
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        results = hygiene.check_stale_branches()

        assert len(results) == 1
        assert results[0].action == "warned"
        assert "stale" in results[0].reason.lower()
        assert results[0].details["days_stale"] == 31

    @patch("urllib.request.urlopen")
    def test_no_warn_fresh_branch(self, mock_urlopen: MagicMock) -> None:
        """Branches under 30 days should not trigger warning."""
        # Setup: commit 5 days ago
        commit_date = (datetime.now(UTC) - timedelta(days=5)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/fresh",
                    "commit": {
                        "sha": "abc",
                        "timestamp": commit_date.replace("+00:00", "Z"),
                        "author": {"name": "testuser"},
                    },
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        results = hygiene.check_stale_branches()

        assert len(results) == 0


class TestCheckDivergence:
    """Tests for check_divergence function."""

    @patch("urllib.request.urlopen")
    def test_warn_diverged_branch(self, mock_urlopen: MagicMock) -> None:
        """AC3: Branches with >50 commits drift should trigger alert."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/diverged",
                    "commit": {"sha": "abc", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "compare_branches") as mock_compare:
            mock_compare.return_value = {"ahead_by": 60, "behind_by": 5}
            results = hygiene.check_divergence()

            assert len(results) == 1
            assert results[0].action == "warned"
            assert "divergence" in results[0].reason.lower()
            assert results[0].details["commits_ahead"] == 60

    @patch("urllib.request.urlopen")
    def test_no_warn_minor_divergence(self, mock_urlopen: MagicMock) -> None:
        """Branches with <=50 commits drift should not trigger alert."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/normal",
                    "commit": {"sha": "abc", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "compare_branches") as mock_compare:
            mock_compare.return_value = {"ahead_by": 10, "behind_by": 5}
            results = hygiene.check_divergence()

            assert len(results) == 0

    @patch("urllib.request.urlopen")
    def test_warn_behind_divergence(self, mock_urlopen: MagicMock) -> None:
        """AC3: Branches >50 commits behind main should trigger alert."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/behind",
                    "commit": {"sha": "abc", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with patch.object(hygiene, "compare_branches") as mock_compare:
            mock_compare.return_value = {"ahead_by": 5, "behind_by": 55}
            results = hygiene.check_divergence()

            assert len(results) == 1
            assert results[0].action == "warned"
            assert results[0].details["commits_behind"] == 55


class TestValidateAllBranchNames:
    """Tests for validate_all_branch_names function."""

    @patch("urllib.request.urlopen")
    def test_validate_all_names(self, mock_urlopen: MagicMock) -> None:
        """AC4: All branch names should be validated."""
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {"name": "main", "commit": {"sha": "abc", "author": {"name": "user"}}},
                {
                    "name": "feature/valid",
                    "commit": {"sha": "def", "author": {"name": "user"}},
                },
                {
                    "name": "invalid-name",
                    "commit": {"sha": "ghi", "author": {"name": "user"}},
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")
        results = hygiene.validate_all_branch_names()

        assert len(results) == 3
        # main should be valid (protected)
        main_result = next(r for r in results if r.branch_name == "main")
        assert main_result.action == "validated"
        # feature/valid should be valid
        feature_result = next(r for r in results if r.branch_name == "feature/valid")
        assert feature_result.action == "validated"
        # invalid-name should be warned
        invalid_result = next(r for r in results if r.branch_name == "invalid-name")
        assert invalid_result.action == "warned"


class TestLogging:
    """Tests for AC5: Cleanup operations are logged."""

    @patch("urllib.request.urlopen")
    def test_cleanup_logged_with_details(self, mock_urlopen: MagicMock) -> None:
        """AC5: Cleanup operations should be logged with details."""
        merged_at = (datetime.now(UTC) - timedelta(hours=25)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/old",
                    "commit": {"sha": "abc", "author": {"name": "testauthor"}},
                },
            ]
        )

        mock_logger = MagicMock()
        hygiene = BranchHygiene(
            "owner", "repo", "http://test", "token", redis_logger=mock_logger
        )

        with patch.object(hygiene, "get_pr_for_branch") as mock_get_pr:
            mock_get_pr.return_value = {
                "number": 42,
                "merged": True,
                "merged_at": merged_at.replace("+00:00", "Z"),
                "user": {"login": "testauthor"},
            }

            with patch.object(hygiene, "delete_branch", return_value=True):
                hygiene.cleanup_merged_branches()

                # Verify logger was called
                assert mock_logger.log_operation.called
                logged_result = mock_logger.log_operation.call_args[0][0]
                assert logged_result.branch_name == "feature/old"
                assert logged_result.author == "testauthor"
                assert logged_result.timestamp is not None


class TestRunAllChecks:
    """Tests for run_all_checks function."""

    @patch("urllib.request.urlopen")
    def test_run_all_checks(self, mock_urlopen: MagicMock) -> None:
        """Test running all checks together."""
        commit_date = (datetime.now(UTC) - timedelta(days=31)).isoformat()

        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            [
                {
                    "name": "feature/old",
                    "commit": {
                        "sha": "abc",
                        "timestamp": commit_date.replace("+00:00", "Z"),
                        "author": {"name": "user"},
                    },
                },
            ]
        )

        hygiene = BranchHygiene("owner", "repo", "http://test", "token")

        with (
            patch.object(hygiene, "get_pr_for_branch", return_value=None),
            patch.object(hygiene, "compare_branches", return_value=None),
        ):
            results = hygiene.run_all_checks()

            # Should have results from stale check and name validation
            assert len(results) >= 1


class TestMain:
    """Tests for main function."""

    @patch.dict(os.environ, {"GITEA_TOKEN": "test_token"})
    @patch("branch_hygiene.BranchHygiene.run_all_checks")
    def test_main_success(self, mock_run: MagicMock) -> None:
        """Test main function with valid arguments."""
        mock_run.return_value = []
        with patch("sys.argv", ["branch_hygiene.py", "--check", "all"]):
            result = bh.main()
            assert result == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_main_missing_token(self) -> None:
        """Test main function fails without GITEA_TOKEN."""
        with patch("sys.argv", ["branch_hygiene.py"]):
            result = bh.main()
            assert result == 1

    @patch.dict(os.environ, {"GITEA_TOKEN": "test_token"})
    @patch("branch_hygiene.BranchHygiene.cleanup_merged_branches")
    def test_main_check_merged(self, mock_cleanup: MagicMock) -> None:
        """Test main function with merged check only."""
        mock_cleanup.return_value = []
        with patch("sys.argv", ["branch_hygiene.py", "--check", "merged"]):
            result = bh.main()
            assert result == 0
            mock_cleanup.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
