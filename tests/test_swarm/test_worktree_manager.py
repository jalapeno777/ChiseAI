#!/usr/bin/env python3
"""
Tests for worktree_manager.py

Story: ST-AUTO-007
"""

import json
import os

# Add project root to path
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.swarm.worktree_manager import (
    WorktreeConflictError,
    WorktreeError,
    WorktreeInfo,
    WorktreeManager,
)


class TestWorktreeInfo(unittest.TestCase):
    """Test WorktreeInfo dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        info = WorktreeInfo(
            path="/tmp/test-worktree",
            branch="feature/test",
            commit="abc123",
            story_id="ST-TEST-001",
            agent="test-agent",
            created_at="2026-02-26T10:00:00Z",
            status="active",
            last_heartbeat="2026-02-26T10:05:00Z",
            metadata={"key": "value"},
        )

        data = info.to_dict()

        self.assertEqual(data["path"], "/tmp/test-worktree")
        self.assertEqual(data["branch"], "feature/test")
        self.assertEqual(data["commit"], "abc123")
        self.assertEqual(data["story_id"], "ST-TEST-001")
        self.assertEqual(data["agent"], "test-agent")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["metadata"], {"key": "value"})

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "path": "/tmp/test-worktree",
            "branch": "feature/test",
            "commit": "abc123",
            "story_id": "ST-TEST-001",
            "agent": "test-agent",
            "created_at": "2026-02-26T10:00:00Z",
            "status": "active",
            "last_heartbeat": "2026-02-26T10:05:00Z",
            "metadata": {"key": "value"},
        }

        info = WorktreeInfo.from_dict(data)

        self.assertEqual(info.path, "/tmp/test-worktree")
        self.assertEqual(info.branch, "feature/test")
        self.assertEqual(info.commit, "abc123")
        self.assertEqual(info.story_id, "ST-TEST-001")
        self.assertEqual(info.agent, "test-agent")


class TestWorktreeManager(unittest.TestCase):
    """Test WorktreeManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path(__file__).parent.parent.parent
        self.temp_dir = tempfile.mkdtemp()
        self.worktree_root = Path(self.temp_dir) / "worktrees"

        # Mock Redis
        with patch.object(WorktreeManager, "_check_redis", return_value=False):
            self.manager = WorktreeManager(
                repo_root=self.repo_root,
                worktree_root=self.worktree_root,
            )

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.manager.repo_root, self.repo_root)
        self.assertEqual(self.manager.worktree_root, self.worktree_root)
        self.assertFalse(self.manager._redis_available)

    def test_find_repo_root(self):
        """Test finding repository root."""
        root = self.manager._find_repo_root()
        self.assertTrue(root.exists())
        self.assertTrue((root / ".git").exists() or (root / ".git").is_file())

    def test_utc_now(self):
        """Test UTC timestamp generation."""
        ts = self.manager._utc_now()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)  # ISO format
        self.assertTrue(ts.endswith("Z"))

    def test_worktree_key(self):
        """Test worktree key generation."""
        key = self.manager._worktree_key("/tmp/test-worktree")
        self.assertTrue(key.startswith("bmad:chiseai:swarm:worktree:"))

    def test_agent_key(self):
        """Test agent key generation."""
        key = self.manager._agent_key("ST-TEST-001", "agent-1")
        self.assertEqual(key, "bmad:chiseai:swarm:agent:ST-TEST-001:agent-1")

    @patch("subprocess.run")
    def test_list_worktrees(self, mock_run):
        """Test listing worktrees."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="worktree /tmp/wt1\nbranch refs/heads/feature/test1\nHEAD abc123\n\nworktree /tmp/wt2\nbranch refs/heads/feature/test2\nHEAD def456\n",
        )

        worktrees = self.manager.list_worktrees()

        self.assertEqual(len(worktrees), 2)
        self.assertEqual(worktrees[0]["path"], "/tmp/wt1")
        self.assertEqual(worktrees[0]["branch"], "feature/test1")
        self.assertEqual(worktrees[1]["path"], "/tmp/wt2")

    @patch("subprocess.run")
    def test_list_worktrees_failure(self, mock_run):
        """Test listing worktrees failure."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with self.assertRaises(WorktreeError):
            self.manager.list_worktrees()

    @patch("subprocess.run")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists", return_value=True)
    def test_create_worktree_new_branch(self, mock_exists, mock_mkdir, mock_run):
        """Test creating worktree with new branch."""
        # Mock branch does not exist
        mock_run.side_effect = [
            MagicMock(returncode=1),  # Branch doesn't exist
            MagicMock(returncode=0),  # worktree add success
            MagicMock(returncode=0, stdout="abc123"),  # rev-parse
        ]

        info = self.manager.create_worktree(
            story_id="ST-TEST-001",
            agent="test-agent",
            branch="feature/ST-TEST-001-test",
            base_ref="main",
        )

        self.assertEqual(info.story_id, "ST-TEST-001")
        self.assertEqual(info.agent, "test-agent")
        self.assertEqual(info.branch, "feature/ST-TEST-001-test")

    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_create_worktree_existing_branch(self, mock_exists, mock_run):
        """Test creating worktree with existing branch."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Branch exists
            MagicMock(returncode=0),  # worktree add success
            MagicMock(returncode=0, stdout="abc123"),  # rev-parse
        ]

        info = self.manager.create_worktree(
            story_id="ST-TEST-001",
            agent="test-agent",
            branch="feature/existing",
        )

        self.assertEqual(info.branch, "feature/existing")

    def test_create_worktree_conflict(self):
        """Test worktree creation conflict."""
        # Create existing worktree info
        existing_path = str(self.worktree_root / "ST-TEST-001-test-agent")

        with patch.object(
            self.manager,
            "_get_worktree_by_path",
            return_value=WorktreeInfo(
                path=existing_path,
                branch="feature/test",
                commit="abc123",
                story_id="ST-TEST-001",
                agent="test-agent",
                created_at="2026-02-26T10:00:00Z",
            ),
        ):
            with self.assertRaises(WorktreeConflictError):
                self.manager.create_worktree(
                    story_id="ST-TEST-001",
                    agent="test-agent",
                    branch="feature/test",
                )

    @patch("subprocess.run")
    def test_cleanup_worktree(self, mock_run):
        """Test cleaning up worktree."""
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(
            self.manager,
            "_get_worktree_by_path",
            return_value=WorktreeInfo(
                path="/tmp/test-worktree",
                branch="feature/test",
                commit="abc123",
                story_id="ST-TEST-001",
                agent="test-agent",
                created_at="2026-02-26T10:00:00Z",
            ),
        ):
            result = self.manager.cleanup_worktree("/tmp/test-worktree", force=True)

        self.assertTrue(result)

    @patch("subprocess.run")
    def test_cleanup_worktree_locked(self, mock_run):
        """Test cleaning up locked worktree."""
        with patch.object(self.manager, "_redis_available", True):
            with patch.object(
                self.manager, "_redis_cli", return_value=(0, "lock-value", "")
            ):
                with self.assertRaises(WorktreeError):
                    self.manager.cleanup_worktree("/tmp/test-worktree")

    def test_check_worktree_health_missing(self):
        """Test health check for missing worktree."""
        with patch.object(self.manager, "_get_worktree_by_path", return_value=None):
            health = self.manager.check_worktree_health("/nonexistent/path")

        self.assertEqual(health["status"], "missing")
        self.assertFalse(health["exists"])

    @patch("subprocess.run")
    def test_check_worktree_health_healthy(self, mock_run):
        """Test health check for healthy worktree."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=".git"),  # rev-parse
            MagicMock(returncode=0, stdout=""),  # status (no changes)
        ]

        with patch.object(
            self.manager,
            "_get_worktree_by_path",
            return_value=WorktreeInfo(
                path="/tmp/test-worktree",
                branch="feature/test",
                commit="abc123",
                story_id="ST-TEST-001",
                agent="test-agent",
                created_at="2026-02-26T10:00:00Z",
                last_heartbeat="2026-02-26T13:00:00Z",  # Recent
            ),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                health = self.manager.check_worktree_health("/tmp/test-worktree")

        self.assertTrue(health["exists"])
        self.assertTrue(health["is_git_repo"])
        self.assertFalse(health["has_changes"])

    @patch("subprocess.run")
    def test_check_worktree_health_dirty(self, mock_run):
        """Test health check for dirty worktree."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=".git"),  # rev-parse
            MagicMock(returncode=0, stdout="M file.py"),  # status (has changes)
        ]

        # Use a recent heartbeat timestamp so it's not stale
        # Current time is 2026-02-26T19:xx, so use a timestamp within 30 minutes
        recent_heartbeat = "2026-02-26T18:55:00Z"  # 5 minutes ago

        with patch.object(
            self.manager,
            "_get_worktree_by_path",
            return_value=WorktreeInfo(
                path="/tmp/test-worktree",
                branch="feature/test",
                commit="abc123",
                story_id="ST-TEST-001",
                agent="test-agent",
                created_at="2026-02-26T10:00:00Z",
                last_heartbeat=recent_heartbeat,
            ),
        ):
            with patch("pathlib.Path.exists", return_value=True):
                health = self.manager.check_worktree_health("/tmp/test-worktree")

        self.assertTrue(health["has_changes"])
        self.assertEqual(health["status"], "dirty")

    def test_cleanup_stale_worktrees(self):
        """Test cleaning up stale worktrees."""
        old_time = "2026-02-26T09:00:00Z"  # More than 60 minutes ago

        with patch.object(
            self.manager,
            "get_all_active_worktrees",
            return_value=[
                WorktreeInfo(
                    path="/tmp/stale-worktree",
                    branch="feature/stale",
                    commit="abc123",
                    story_id="ST-STALE-001",
                    agent="stale-agent",
                    created_at="2026-02-26T08:00:00Z",
                    last_heartbeat=old_time,
                ),
            ],
        ):
            with patch.object(self.manager, "cleanup_worktree", return_value=True):
                cleaned = self.manager.cleanup_stale_worktrees(max_age_minutes=60)

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0], "/tmp/stale-worktree")

    def test_cleanup_stale_worktrees_dry_run(self):
        """Test dry run of stale worktree cleanup."""
        old_time = "2026-02-26T09:00:00Z"

        with patch.object(
            self.manager,
            "get_all_active_worktrees",
            return_value=[
                WorktreeInfo(
                    path="/tmp/stale-worktree",
                    branch="feature/stale",
                    commit="abc123",
                    story_id="ST-STALE-001",
                    agent="stale-agent",
                    created_at="2026-02-26T08:00:00Z",
                    last_heartbeat=old_time,
                ),
            ],
        ):
            cleaned = self.manager.cleanup_stale_worktrees(
                max_age_minutes=60, dry_run=True
            )

        self.assertEqual(len(cleaned), 1)

    def test_lock_worktree(self):
        """Test locking worktree."""
        with patch.object(self.manager, "_redis_available", True):
            with patch.object(self.manager, "_redis_cli", return_value=(0, "OK", "")):
                result = self.manager.lock_worktree(
                    "/tmp/test-worktree",
                    "ST-TEST-001",
                    "test-agent",
                )

        self.assertTrue(result)

    def test_lock_worktree_unavailable(self):
        """Test locking worktree when Redis unavailable."""
        with patch.object(self.manager, "_redis_available", False):
            result = self.manager.lock_worktree(
                "/tmp/test-worktree",
                "ST-TEST-001",
                "test-agent",
            )

        self.assertTrue(result)  # Should return True when Redis unavailable

    def test_unlock_worktree(self):
        """Test unlocking worktree."""
        with patch.object(self.manager, "_redis_available", True):
            with patch.object(self.manager, "_redis_cli", return_value=(0, "1", "")):
                result = self.manager.unlock_worktree("/tmp/test-worktree")

        self.assertTrue(result)


class TestWorktreeManagerRedis(unittest.TestCase):
    """Test WorktreeManager Redis integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path(__file__).parent.parent.parent

        with patch.object(WorktreeManager, "_check_redis", return_value=True):
            self.manager = WorktreeManager(
                repo_root=self.repo_root,
                redis_host="localhost",
                redis_port=6380,
            )

    def test_redis_available(self):
        """Test Redis availability check."""
        self.assertTrue(self.manager._redis_available)

    @patch("subprocess.run")
    def test_redis_cli(self, mock_run):
        """Test Redis CLI execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="PONG", stderr="")

        rc, stdout, stderr = self.manager._redis_cli("PING")

        self.assertEqual(rc, 0)
        self.assertEqual(stdout, "PONG")

    def test_store_worktree_info(self):
        """Test storing worktree info in Redis."""
        info = WorktreeInfo(
            path="/tmp/test-worktree",
            branch="feature/test",
            commit="abc123",
            story_id="ST-TEST-001",
            agent="test-agent",
            created_at="2026-02-26T10:00:00Z",
        )

        with patch.object(self.manager, "_redis_cli", return_value=(0, "OK", "")):
            self.manager._store_worktree_info(info)

    def test_get_worktree_by_path(self):
        """Test getting worktree by path from Redis."""
        info = WorktreeInfo(
            path="/tmp/test-worktree",
            branch="feature/test",
            commit="abc123",
            story_id="ST-TEST-001",
            agent="test-agent",
            created_at="2026-02-26T10:00:00Z",
        )

        with patch.object(
            self.manager, "_redis_cli", return_value=(0, json.dumps(info.to_dict()), "")
        ):
            result = self.manager._get_worktree_by_path("/tmp/test-worktree")

        self.assertIsNotNone(result)
        self.assertEqual(result.story_id, "ST-TEST-001")


class TestWorktreeManagerIntegration(unittest.TestCase):
    """Integration tests for WorktreeManager."""

    @unittest.skipIf(
        not os.path.exists("/tmp/worktrees"),
        "Integration test requires /tmp/worktrees directory",
    )
    def test_full_lifecycle(self):
        """Test full worktree lifecycle."""
        # This test requires actual git repository and Redis
        pass


if __name__ == "__main__":
    unittest.main()
