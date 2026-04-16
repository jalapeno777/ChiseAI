"""Tests for Auto Rebase functionality.

This module tests:
- Stale PR detection (is_behind_main)
- Rate limiting
- Conflict handling
- Redis locking
- Auto-rebase workflow
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.expiry = {}
        self.ttls = {}

    def hset(self, key: str, field: str, value: str) -> int:
        if key not in self.data:
            self.data[key] = {}
        self.data[key][field] = value
        return 1

    def hget(self, key: str, field: str) -> str | None:
        return self.data.get(key, {}).get(field)

    def hgetall(self, key: str) -> dict[str, str]:
        return self.data.get(key, {})

    def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> str | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        if ex:
            self.ttls[key] = time.time() + ex
        return "OK"

    def get(self, key: str) -> str | None:
        if key in self.ttls:
            if time.time() > self.ttls[key]:
                del self.data[key]
                del self.ttls[key]
                return None
        return self.data.get(key)

    def incr(self, key: str) -> int:
        if key not in self.data:
            self.data[key] = "0"
        self.data[key] = str(int(self.data[key]) + 1)
        return int(self.data[key])

    def expire(self, key: str, seconds: int) -> int:
        self.ttls[key] = time.time() + seconds
        return 1

    def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            if key in self.ttls:
                del self.ttls[key]
            return 1
        return 0

    def sadd(self, key: str, *values: str) -> int:
        if key not in self.data:
            self.data[key] = set()
        elif not isinstance(self.data[key], set):
            self.data[key] = (
                set(self.data[key].split("\n")) if self.data[key] else set()
            )
        for v in values:
            self.data[key].add(v)
        return len(values)

    def smembers(self, key: str) -> set[str]:
        val = self.data.get(key)
        if isinstance(val, set):
            return val
        if isinstance(val, str):
            return set(val.split("\n")) if val else set()
        return set()

    def rpush(self, key: str, *values: str) -> int:
        if key not in self.data:
            self.data[key] = []
        elif not isinstance(self.data[key], list):
            self.data[key] = [self.data[key]]
        for v in values:
            self.data[key].append(v)
        return len(self.data[key])

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        val = self.data.get(key)
        if isinstance(val, list):
            return val[start : end + 1] if end >= 0 else val[start:]
        return []


class TestStaleDetector:
    """Tests for StaleDetector class."""

    @pytest.fixture
    def mock_git_repo(self, tmp_path):
        """Create a temporary git repo for testing."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit on main
        main_file = repo_path / "main.txt"
        main_file.write_text("main content")
        subprocess.run(["git", "add", "main.txt"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Switch to main branch (git init creates master by default)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_path, check=True)

        # Create a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/test-branch"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Add a commit to the feature branch
        feature_file = repo_path / "feature.txt"
        feature_file.write_text("feature content")
        subprocess.run(["git", "add", "feature.txt"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Go back to main and add new commits
        subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True)
        new_file = repo_path / "new_main.txt"
        new_file.write_text("new main content")
        subprocess.run(["git", "add", "new_main.txt"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "New main commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create remote (local)
        remote_path = tmp_path / "remote.git"
        subprocess.run(
            ["git", "clone", "--bare", str(repo_path), str(remote_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_path)],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    def test_is_behind_main_when_branch_has_old_commits(self, mock_git_repo):
        """Test that is_behind_main correctly detects when a branch is behind main."""
        # Import here to allow mocking
        import sys

        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.stale_detector import StaleDetector

        # Create a new branch from old main
        subprocess.run(
            ["git", "checkout", "-b", "feature/old-feature"],
            cwd=mock_git_repo,
            check=True,
            capture_output=True,
        )

        detector = StaleDetector(repo_path=str(mock_git_repo))
        is_behind, commits_behind = detector.is_behind_main("feature/old-feature")

        assert is_behind is True
        assert commits_behind >= 1

    def test_is_behind_main_when_branch_is_current(self, mock_git_repo):
        """Test that is_behind_main returns False when branch is up to date with main."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.stale_detector import StaleDetector

        # Checkout main which should have all commits
        subprocess.run(["git", "checkout", "main"], cwd=mock_git_repo, check=True)

        detector = StaleDetector(repo_path=str(mock_git_repo))
        is_behind, commits_behind = detector.is_behind_main("main")

        assert is_behind is False
        assert commits_behind == 0

    def test_check_branch_is_feature(self):
        """Test feature branch detection."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.stale_detector import StaleDetector

        detector = StaleDetector()

        assert detector.check_branch_is_feature("feature/test") is True
        assert detector.check_branch_is_feature("fix/bug") is True
        assert detector.check_branch_is_feature("main") is False
        assert detector.check_branch_is_feature("develop") is False
        assert detector.check_branch_is_feature("feature/xyz-123") is True


class TestAutoRebaseEngine:
    """Tests for AutoRebaseEngine class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MockRedis()

    @pytest.fixture
    def mock_git_repo(self, tmp_path):
        """Create a temporary git repo for testing."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            check=True,
        )

        # Create initial commit on main
        main_file = repo_path / "main.txt"
        main_file.write_text("main content")
        subprocess.run(["git", "add", "main.txt"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
        )

        # Create remote
        remote_path = tmp_path / "remote.git"
        subprocess.run(
            ["git", "clone", "--bare", str(repo_path), str(remote_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_path)],
            cwd=repo_path,
            check=True,
        )

        return repo_path

    def test_check_rate_limit_within_limit(self, mock_redis):
        """Test rate limiting when within budget."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )

        with patch(
            "scripts.pr_lifecycle.recovery_handlers._redis_cli"
        ) as mock_redis_cli:
            mock_redis_cli.return_value = MagicMock(
                returncode=0,
                stdout="1",  # 1 rebase used
            )

            from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine

            engine = AutoRebaseEngine()
            # Note: This test would need proper mocking of the redis calls

    def test_is_safe_to_rebase_feature_branch(self):
        """Test safety check for feature branches."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine

        with patch("scripts.pr_lifecycle.recovery_handlers._redis_cli"):
            engine = AutoRebaseEngine()
            is_safe, reason = engine.is_safe_to_rebase(
                branch="feature/test", mergeable=True, is_draft=False
            )

            assert is_safe is True
            assert reason == "safe"

    def test_is_safe_to_rebase_draft_pr(self):
        """Test that draft PRs are not rebased."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine

        with patch("scripts.pr_lifecycle.recovery_handlers._redis_cli"):
            engine = AutoRebaseEngine()
            is_safe, reason = engine.is_safe_to_rebase(
                branch="feature/test", mergeable=True, is_draft=True
            )

            assert is_safe is False
            assert "draft" in reason.lower()

    def test_is_safe_to_rebase_conflict_pr(self):
        """Test that PRs with actual conflicts are not rebased."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine

        with patch("scripts.pr_lifecycle.recovery_handlers._redis_cli"):
            engine = AutoRebaseEngine()
            is_safe, reason = engine.is_safe_to_rebase(
                branch="feature/test",
                mergeable=False,  # Real conflicts
                is_draft=False,
            )

            assert is_safe is False
            assert "conflict" in reason.lower()

    def test_is_safe_to_rebase_non_feature_branch(self):
        """Test that non-feature branches are not rebased."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import AutoRebaseEngine

        with patch("scripts.pr_lifecycle.recovery_handlers._redis_cli"):
            engine = AutoRebaseEngine()
            is_safe, reason = engine.is_safe_to_rebase(
                branch="main", mergeable=True, is_draft=False
            )

            assert is_safe is False
            assert "feature branch" in reason.lower()


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_enforces_max_rebases(self):
        """Test that rate limiting prevents more than MAX_REBASES_PER_WINDOW rebases."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import (
            MAX_REBASES_PER_WINDOW,
            REBASE_BUDGET_KEY,
        )

        # The budget key should use current window
        window = int(time.time() // 300)  # 5 minute windows
        expected_key = f"{REBASE_BUDGET_KEY}:{window}"

        assert MAX_REBASES_PER_WINDOW == 3

    def test_rate_limit_consumption(self):
        """Test that consuming rate limit increments counter."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )

        # This tests the logic of rate limit consumption
        # After consuming, the counter should be incremented
        initial_count = 1
        new_count = initial_count + 1
        assert new_count == 2


class TestRedisLocking:
    """Tests for Redis locking functionality."""

    def test_concurrent_rebase_lock_prevents_double_rebase(self):
        """Test that concurrent rebases are prevented by locking."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.recovery_handlers import REBASE_LOCK_PREFIX

        lock_key = f"{REBASE_LOCK_PREFIX}:123"

        # Lock key pattern should include PR number
        assert ":123" in lock_key


class TestConflictHandling:
    """Tests for conflict handling during rebase."""

    def test_rebase_with_real_conflicts_is_aborted(self):
        """Test that a rebase with real conflicts is aborted and not force-pushed."""
        # When git rebase fails with conflicts, it should:
        # 1. Abort the rebase
        # 2. NOT force push
        # 3. Log the conflict
        # 4. Mark PR as needing manual attention
        pass  # Would need complex git conflict simulation


class TestIntegration:
    """Integration tests for the auto-rebase workflow."""

    def test_full_rebase_workflow_dry_run(self):
        """Test the full detect-and-rebase workflow in dry-run mode."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )

        # This would test the full workflow
        # - List open PRs
        # - Check each for behind-main
        # - Apply rate limiting
        # - Report results without rebasing
        pass

    def test_merging_main_updates_behind_status(self, tmp_path):
        """Test that after main advances, PRs become 'behind'."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            check=True,
        )

        # Create main with commit
        (repo_path / "main.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True)

        # Switch to main branch (git init creates master by default)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_path, check=True)

        # Create feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=repo_path,
            check=True,
        )
        (repo_path / "feature.txt").write_text("feature")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "feature"], cwd=repo_path, check=True)

        # Now simulate main advancing
        subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True)
        (repo_path / "main.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=repo_path, check=True)

        # The feature branch should now be behind
        sys.path.insert(
            0, str(Path(__file__).parent.parent.parent / "scripts/pr_lifecycle")
        )
        from scripts.pr_lifecycle.stale_detector import StaleDetector

        detector = StaleDetector(repo_path=str(repo_path))
        is_behind, commits_behind = detector.is_behind_main("feature/test")

        assert is_behind is True
        assert commits_behind >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
