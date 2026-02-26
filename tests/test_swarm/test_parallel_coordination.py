#!/usr/bin/env python3
"""
Tests for parallel coordination (agent_coordinator.py)

Story: ST-AUTO-007
"""

import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.swarm.agent_coordinator import (
    AgentCoordinator,
    AgentInfo,
    AgentStatus,
    AgentRole,
    DashboardData,
    FailureRecord,
    MAX_AGENTS,
    STALE_THRESHOLD_MINUTES,
)


class TestAgentStatus(unittest.TestCase):
    """Test AgentStatus enum."""

    def test_enum_values(self):
        """Test enum values."""
        self.assertEqual(AgentStatus.PENDING.value, "pending")
        self.assertEqual(AgentStatus.STARTING.value, "starting")
        self.assertEqual(AgentStatus.ACTIVE.value, "active")
        self.assertEqual(AgentStatus.WORKING.value, "working")
        self.assertEqual(AgentStatus.COMPLETING.value, "completing")
        self.assertEqual(AgentStatus.CLEANUP.value, "cleanup")
        self.assertEqual(AgentStatus.COMPLETED.value, "completed")
        self.assertEqual(AgentStatus.FAILED.value, "failed")
        self.assertEqual(AgentStatus.TIMEOUT.value, "timeout")


class TestAgentRole(unittest.TestCase):
    """Test AgentRole enum."""

    def test_enum_values(self):
        """Test enum values."""
        self.assertEqual(AgentRole.WORKER.value, "worker")
        self.assertEqual(AgentRole.COORDINATOR.value, "coordinator")
        self.assertEqual(AgentRole.MERGER.value, "merger")
        self.assertEqual(AgentRole.VALIDATOR.value, "validator")


class TestAgentInfo(unittest.TestCase):
    """Test AgentInfo dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        info = AgentInfo(
            story_id="ST-001",
            agent_id="agent-1",
            role=AgentRole.WORKER,
            status=AgentStatus.ACTIVE,
            branch="feature/test",
            worktree_path="/tmp/wt1",
            started_at="2026-02-26T10:00:00Z",
            last_heartbeat="2026-02-26T10:05:00Z",
            pr_url="http://example.com/pr/1",
            pr_number=1,
            scope_globs=["src/test/*"],
            metadata={"key": "value"},
        )

        data = info.to_dict()

        self.assertEqual(data["story_id"], "ST-001")
        self.assertEqual(data["agent_id"], "agent-1")
        self.assertEqual(data["role"], "worker")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["pr_number"], 1)
        self.assertEqual(data["scope_globs"], ["src/test/*"])

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "story_id": "ST-001",
            "agent_id": "agent-1",
            "role": "worker",
            "status": "active",
            "branch": "feature/test",
            "worktree_path": "/tmp/wt1",
            "started_at": "2026-02-26T10:00:00Z",
            "last_heartbeat": "2026-02-26T10:05:00Z",
        }

        info = AgentInfo.from_dict(data)

        self.assertEqual(info.story_id, "ST-001")
        self.assertEqual(info.role, AgentRole.WORKER)
        self.assertEqual(info.status, AgentStatus.ACTIVE)


class TestDashboardData(unittest.TestCase):
    """Test DashboardData dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        data = DashboardData(
            timestamp="2026-02-26T10:00:00Z",
            total_agents=10,
            active_agents=5,
            completed_agents=3,
            failed_agents=2,
            agents=[],
            prs=[],
        )

        result = data.to_dict()

        self.assertEqual(result["total_agents"], 10)
        self.assertEqual(result["active_agents"], 5)
        self.assertEqual(result["completed_agents"], 3)
        self.assertEqual(result["failed_agents"], 2)


class TestFailureRecord(unittest.TestCase):
    """Test FailureRecord dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        record = FailureRecord(
            story_id="ST-001",
            agent_id="agent-1",
            failed_at="2026-02-26T10:00:00Z",
            reason="Test failure",
            stack_trace="Traceback...",
            recovery_attempted=True,
            recovery_successful=False,
            cleanup_completed=True,
        )

        data = record.to_dict()

        self.assertEqual(data["story_id"], "ST-001")
        self.assertEqual(data["reason"], "Test failure")
        self.assertTrue(data["recovery_attempted"])
        self.assertFalse(data["recovery_successful"])


class TestAgentCoordinator(unittest.TestCase):
    """Test AgentCoordinator class."""

    def setUp(self):
        """Set up test fixtures."""
        with patch.object(AgentCoordinator, "_check_redis", return_value=False):
            self.coordinator = AgentCoordinator(
                redis_host="localhost",
                redis_port=6380,
            )

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.coordinator.redis_host, "localhost")
        self.assertEqual(self.coordinator.redis_port, 6380)
        self.assertEqual(self.coordinator.max_agents, MAX_AGENTS)
        self.assertFalse(self.coordinator._redis_available)

    def test_utc_now(self):
        """Test UTC timestamp generation."""
        ts = self.coordinator._utc_now()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)
        self.assertTrue(ts.endswith("Z"))

    def test_agent_key(self):
        """Test agent key generation."""
        key = self.coordinator._agent_key("ST-001", "agent-1")
        self.assertEqual(key, "bmad:chiseai:swarm:agent:ST-001:agent-1")

    def test_heartbeat_key(self):
        """Test heartbeat key generation."""
        key = self.coordinator._heartbeat_key("ST-001", "agent-1")
        self.assertEqual(key, "bmad:chiseai:swarm:heartbeat:ST-001:agent-1")

    def test_failure_key(self):
        """Test failure key generation."""
        key = self.coordinator._failure_key("ST-001", "agent-1")
        self.assertEqual(key, "bmad:chiseai:swarm:failure:ST-001:agent-1")

    def test_register_agent(self):
        """Test registering an agent."""
        with patch.object(self.coordinator, "get_active_agents", return_value=[]):
            info = self.coordinator.register_agent(
                story_id="ST-001",
                agent_id="agent-1",
                branch="feature/test",
                worktree_path="/tmp/wt1",
                role=AgentRole.WORKER,
                scope_globs=["src/test/*"],
            )

        self.assertEqual(info.story_id, "ST-001")
        self.assertEqual(info.agent_id, "agent-1")
        self.assertEqual(info.role, AgentRole.WORKER)
        self.assertEqual(info.status, AgentStatus.STARTING)
        self.assertEqual(info.scope_globs, ["src/test/*"])

    def test_register_agent_max_reached(self):
        """Test registering agent when max reached."""
        # Create MAX_AGENTS active agents
        active_agents = [
            AgentInfo(
                story_id=f"ST-{i}",
                agent_id=f"agent-{i}",
                role=AgentRole.WORKER,
                status=AgentStatus.ACTIVE,
                branch=f"feature/test-{i}",
                worktree_path=f"/tmp/wt{i}",
                started_at="2026-02-26T10:00:00Z",
                last_heartbeat="2026-02-26T10:05:00Z",
            )
            for i in range(MAX_AGENTS)
        ]

        with patch.object(
            self.coordinator, "get_active_agents", return_value=active_agents
        ):
            with self.assertRaises(RuntimeError) as context:
                self.coordinator.register_agent(
                    story_id="ST-NEW",
                    agent_id="agent-new",
                    branch="feature/new",
                    worktree_path="/tmp/wt-new",
                )

        self.assertIn("Maximum agents", str(context.exception))

    def test_update_heartbeat(self):
        """Test updating heartbeat."""
        agent_data = json.dumps(
            {
                "story_id": "ST-001",
                "agent_id": "agent-1",
                "role": "worker",
                "status": "active",
                "branch": "feature/test",
                "worktree_path": "/tmp/wt1",
                "started_at": "2026-02-26T10:00:00Z",
                "last_heartbeat": "2026-02-26T10:00:00Z",
            }
        )

        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                side_effect=[
                    (0, "OK", ""),  # SET heartbeat
                    (0, agent_data, ""),  # GET agent info
                    (0, "OK", ""),  # SET agent info
                ],
            ):
                result = self.coordinator.update_heartbeat("ST-001", "agent-1")

        self.assertTrue(result)

    def test_update_heartbeat_no_redis(self):
        """Test updating heartbeat without Redis."""
        result = self.coordinator.update_heartbeat("ST-001", "agent-1")
        self.assertFalse(result)

    def test_update_agent_status(self):
        """Test updating agent status."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator, "_redis_cli", return_value=(0, "OK", "")
            ):
                with patch.object(
                    self.coordinator,
                    "get_agent_info",
                    return_value=AgentInfo(
                        story_id="ST-001",
                        agent_id="agent-1",
                        role=AgentRole.WORKER,
                        status=AgentStatus.STARTING,
                        branch="feature/test",
                        worktree_path="/tmp/wt1",
                        started_at="2026-02-26T10:00:00Z",
                        last_heartbeat="2026-02-26T10:00:00Z",
                    ),
                ):
                    info = self.coordinator.update_agent_status(
                        "ST-001", "agent-1", AgentStatus.WORKING
                    )

        self.assertIsNotNone(info)
        self.assertEqual(info.status, AgentStatus.WORKING)

    def test_update_agent_status_not_found(self):
        """Test updating status for non-existent agent."""
        with patch.object(self.coordinator, "get_agent_info", return_value=None):
            info = self.coordinator.update_agent_status(
                "ST-001", "agent-1", AgentStatus.WORKING
            )

        self.assertIsNone(info)

    def test_update_agent_status_completed(self):
        """Test updating agent status to completed."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator, "_redis_cli", return_value=(0, "OK", "")
            ):
                with patch.object(
                    self.coordinator,
                    "get_agent_info",
                    return_value=AgentInfo(
                        story_id="ST-001",
                        agent_id="agent-1",
                        role=AgentRole.WORKER,
                        status=AgentStatus.COMPLETING,
                        branch="feature/test",
                        worktree_path="/tmp/wt1",
                        started_at="2026-02-26T10:00:00Z",
                        last_heartbeat="2026-02-26T10:00:00Z",
                    ),
                ):
                    info = self.coordinator.update_agent_status(
                        "ST-001", "agent-1", AgentStatus.COMPLETED
                    )

        self.assertIsNotNone(info)
        self.assertEqual(info.status, AgentStatus.COMPLETED)
        self.assertIsNotNone(info.completed_at)

    def test_update_pr_info(self):
        """Test updating PR info."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator, "_redis_cli", return_value=(0, "OK", "")
            ):
                with patch.object(
                    self.coordinator,
                    "get_agent_info",
                    return_value=AgentInfo(
                        story_id="ST-001",
                        agent_id="agent-1",
                        role=AgentRole.WORKER,
                        status=AgentStatus.ACTIVE,
                        branch="feature/test",
                        worktree_path="/tmp/wt1",
                        started_at="2026-02-26T10:00:00Z",
                        last_heartbeat="2026-02-26T10:00:00Z",
                    ),
                ):
                    info = self.coordinator.update_pr_info(
                        "ST-001", "agent-1", "http://example.com/pr/1", 1
                    )

        self.assertIsNotNone(info)
        self.assertEqual(info.pr_url, "http://example.com/pr/1")
        self.assertEqual(info.pr_number, 1)

    def test_get_agent_info(self):
        """Test getting agent info."""
        agent_data = {
            "story_id": "ST-001",
            "agent_id": "agent-1",
            "role": "worker",
            "status": "active",
            "branch": "feature/test",
            "worktree_path": "/tmp/wt1",
            "started_at": "2026-02-26T10:00:00Z",
            "last_heartbeat": "2026-02-26T10:05:00Z",
        }

        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                return_value=(0, json.dumps(agent_data), ""),
            ):
                info = self.coordinator.get_agent_info("ST-001", "agent-1")

        self.assertIsNotNone(info)
        self.assertEqual(info.story_id, "ST-001")
        self.assertEqual(info.agent_id, "agent-1")

    def test_get_agent_info_not_found(self):
        """Test getting non-existent agent info."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(self.coordinator, "_redis_cli", return_value=(0, "", "")):
                info = self.coordinator.get_agent_info("ST-001", "agent-1")

        self.assertIsNone(info)

    def test_get_active_agents(self):
        """Test getting active agents."""
        agent_data = {
            "story_id": "ST-001",
            "agent_id": "agent-1",
            "role": "worker",
            "status": "active",
            "branch": "feature/test",
            "worktree_path": "/tmp/wt1",
            "started_at": "2026-02-26T10:00:00Z",
            "last_heartbeat": "2026-02-26T10:05:00Z",
        }

        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                side_effect=[
                    (0, "bmad:chiseai:swarm:agent:ST-001:agent-1", ""),  # KEYS
                    (0, json.dumps(agent_data), ""),  # GET
                ],
            ):
                agents = self.coordinator.get_active_agents()

        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].story_id, "ST-001")

    def test_get_active_agents_no_redis(self):
        """Test getting active agents without Redis."""
        agents = self.coordinator.get_active_agents()
        self.assertEqual(len(agents), 0)

    def test_get_all_agents(self):
        """Test getting all agents."""
        active_data = {
            "story_id": "ST-001",
            "agent_id": "agent-1",
            "role": "worker",
            "status": "active",
            "branch": "feature/test",
            "worktree_path": "/tmp/wt1",
            "started_at": "2026-02-26T10:00:00Z",
            "last_heartbeat": "2026-02-26T10:05:00Z",
        }
        completed_data = {
            "story_id": "ST-002",
            "agent_id": "agent-2",
            "role": "worker",
            "status": "completed",
            "branch": "feature/test2",
            "worktree_path": "/tmp/wt2",
            "started_at": "2026-02-26T09:00:00Z",
            "last_heartbeat": "2026-02-26T09:05:00Z",
            "completed_at": "2026-02-26T10:00:00Z",
        }

        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                side_effect=[
                    (0, "key1\nkey2", ""),  # KEYS
                    (0, json.dumps(active_data), ""),  # GET 1
                    (0, json.dumps(completed_data), ""),  # GET 2
                ],
            ):
                agents = self.coordinator.get_all_agents()

        self.assertEqual(len(agents), 2)

    def test_is_agent_stale(self):
        """Test checking if agent is stale."""
        # Use a recent timestamp that will always be within the stale threshold
        # Current time is 2026-02-26, so use a timestamp just a few minutes ago
        recent_heartbeat = (
            "2026-02-26T18:55:00Z"  # 5 minutes before current time (19:00)
        )

        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                return_value=(0, recent_heartbeat, ""),
            ):
                is_stale = self.coordinator.is_agent_stale("ST-001", "agent-1")

        self.assertFalse(is_stale)

    def test_is_agent_stale_true(self):
        """Test checking if agent is stale (true case)."""
        # Old heartbeat
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                return_value=(0, "2026-02-26T08:00:00Z", ""),
            ):
                is_stale = self.coordinator.is_agent_stale("ST-001", "agent-1")

        self.assertTrue(is_stale)

    def test_get_stale_agents(self):
        """Test getting stale agents."""
        stale_agent = AgentInfo(
            story_id="ST-001",
            agent_id="agent-1",
            role=AgentRole.WORKER,
            status=AgentStatus.ACTIVE,
            branch="feature/test",
            worktree_path="/tmp/wt1",
            started_at="2026-02-26T10:00:00Z",
            last_heartbeat="2026-02-26T08:00:00Z",  # Old
        )

        with patch.object(
            self.coordinator, "get_active_agents", return_value=[stale_agent]
        ):
            with patch.object(self.coordinator, "is_agent_stale", return_value=True):
                stale = self.coordinator.get_stale_agents()

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].story_id, "ST-001")

    def test_record_failure(self):
        """Test recording failure."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator, "_redis_cli", return_value=(0, "OK", "")
            ):
                with patch.object(
                    self.coordinator, "update_agent_status", return_value=None
                ):
                    record = self.coordinator.record_failure(
                        "ST-001", "agent-1", "Test failure", "Traceback..."
                    )

        self.assertEqual(record.story_id, "ST-001")
        self.assertEqual(record.agent_id, "agent-1")
        self.assertEqual(record.reason, "Test failure")
        self.assertEqual(record.stack_trace, "Traceback...")

    def test_attempt_recovery_success(self):
        """Test successful recovery attempt."""
        info = AgentInfo(
            story_id="ST-001",
            agent_id="agent-1",
            role=AgentRole.WORKER,
            status=AgentStatus.FAILED,
            branch="feature/test",
            worktree_path="/tmp/wt1",
            started_at="2026-02-26T10:00:00Z",
            last_heartbeat="2026-02-26T10:05:00Z",
        )

        failure_data = {
            "story_id": "ST-001",
            "agent_id": "agent-1",
            "failed_at": "2026-02-26T10:00:00Z",
            "reason": "Test failure",
            "recovery_attempted": False,
            "recovery_successful": False,
            "cleanup_completed": False,
        }

        with patch.object(self.coordinator, "get_agent_info", return_value=info):
            with patch.object(self.coordinator, "_redis_available", True):
                with patch.object(
                    self.coordinator,
                    "_redis_cli",
                    side_effect=[
                        (0, json.dumps(failure_data), ""),  # GET failure
                        (0, "OK", ""),  # SET failure (updated)
                    ],
                ):
                    with patch.object(
                        self.coordinator, "_cleanup_agent_resources", return_value=True
                    ):
                        with patch.object(
                            self.coordinator, "update_agent_status", return_value=None
                        ):
                            success, msg = self.coordinator.attempt_recovery(
                                "ST-001", "agent-1"
                            )

        self.assertTrue(success)
        self.assertIn("successful", msg)

    def test_attempt_recovery_not_found(self):
        """Test recovery when agent not found."""
        with patch.object(self.coordinator, "get_agent_info", return_value=None):
            success, msg = self.coordinator.attempt_recovery("ST-001", "agent-1")

        self.assertFalse(success)
        self.assertIn("not found", msg)

    def test_cleanup_agent_resources(self):
        """Test cleaning up agent resources."""
        info = AgentInfo(
            story_id="ST-001",
            agent_id="agent-1",
            role=AgentRole.WORKER,
            status=AgentStatus.FAILED,
            branch="feature/test",
            worktree_path="/tmp/wt1",
            started_at="2026-02-26T10:00:00Z",
            last_heartbeat="2026-02-26T10:05:00Z",
        )

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=MagicMock(returncode=0)):
                with patch.object(self.coordinator, "_redis_available", True):
                    with patch.object(
                        self.coordinator, "_redis_cli", return_value=(0, "1", "")
                    ):
                        success = self.coordinator._cleanup_agent_resources(info)

        self.assertTrue(success)

    def test_get_dashboard_data(self):
        """Test getting dashboard data."""
        active_agent = AgentInfo(
            story_id="ST-001",
            agent_id="agent-1",
            role=AgentRole.WORKER,
            status=AgentStatus.ACTIVE,
            branch="feature/test",
            worktree_path="/tmp/wt1",
            started_at="2026-02-26T10:00:00Z",
            last_heartbeat="2026-02-26T10:05:00Z",
            pr_url="http://example.com/pr/1",
            pr_number=1,
        )

        completed_agent = AgentInfo(
            story_id="ST-002",
            agent_id="agent-2",
            role=AgentRole.WORKER,
            status=AgentStatus.COMPLETED,
            branch="feature/test2",
            worktree_path="/tmp/wt2",
            started_at="2026-02-26T09:00:00Z",
            last_heartbeat="2026-02-26T09:05:00Z",
            completed_at="2026-02-26T10:00:00Z",
        )

        failed_agent = AgentInfo(
            story_id="ST-003",
            agent_id="agent-3",
            role=AgentRole.WORKER,
            status=AgentStatus.FAILED,
            branch="feature/test3",
            worktree_path="/tmp/wt3",
            started_at="2026-02-26T08:00:00Z",
            last_heartbeat="2026-02-26T08:05:00Z",
        )

        with patch.object(
            self.coordinator,
            "get_all_agents",
            return_value=[active_agent, completed_agent, failed_agent],
        ):
            data = self.coordinator.get_dashboard_data()

        self.assertEqual(data.total_agents, 3)
        self.assertEqual(data.active_agents, 1)
        self.assertEqual(data.completed_agents, 1)
        self.assertEqual(data.failed_agents, 1)
        self.assertEqual(len(data.prs), 1)

    def test_export_dashboard_json(self):
        """Test exporting dashboard data as JSON."""
        with patch.object(
            self.coordinator,
            "get_dashboard_data",
            return_value=DashboardData(
                timestamp="2026-02-26T10:00:00Z",
                total_agents=5,
                active_agents=3,
                completed_agents=1,
                failed_agents=1,
                agents=[],
                prs=[],
            ),
        ):
            json_str = self.coordinator.export_dashboard_json()

        data = json.loads(json_str)
        self.assertEqual(data["total_agents"], 5)
        self.assertEqual(data["active_agents"], 3)

    def test_check_ownership(self):
        """Test checking ownership."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                return_value=(0, "ST-001/agent-1/2026-02-26T10:00:00Z", ""),
            ):
                owns, owner = self.coordinator.check_ownership(
                    "ST-001", "agent-1", "scripts/swarm"
                )

        self.assertTrue(owns)
        self.assertIsNotNone(owner)

    def test_check_ownership_conflict(self):
        """Test checking ownership with conflict."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                return_value=(0, "ST-002/agent-2/2026-02-26T10:00:00Z", ""),
            ):
                owns, owner = self.coordinator.check_ownership(
                    "ST-001", "agent-1", "scripts/swarm"
                )

        self.assertFalse(owns)
        self.assertIsNotNone(owner)

    def test_claim_ownership(self):
        """Test claiming ownership."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator, "_redis_cli", return_value=(0, "OK", "")
            ):
                success = self.coordinator.claim_ownership(
                    "ST-001", "agent-1", ["scripts/swarm", "tests/test_swarm"]
                )

        self.assertTrue(success)

    def test_release_ownership(self):
        """Test releasing ownership."""
        with patch.object(self.coordinator, "_redis_available", True):
            with patch.object(
                self.coordinator,
                "_redis_cli",
                side_effect=[
                    (0, "ST-001/agent-1/2026-02-26T10:00:00Z", ""),  # HGET
                    (0, "1", ""),  # HDEL
                ],
            ):
                success = self.coordinator.release_ownership(
                    "ST-001", "agent-1", ["scripts/swarm"]
                )

        self.assertTrue(success)


class TestAgentCoordinatorRedis(unittest.TestCase):
    """Test AgentCoordinator Redis integration."""

    def setUp(self):
        """Set up test fixtures."""
        with patch.object(AgentCoordinator, "_check_redis", return_value=True):
            self.coordinator = AgentCoordinator()

    def test_redis_available(self):
        """Test Redis availability."""
        self.assertTrue(self.coordinator._redis_available)

    @patch("subprocess.run")
    def test_redis_cli(self, mock_run):
        """Test Redis CLI execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="PONG", stderr="")

        rc, stdout, stderr = self.coordinator._redis_cli("PING")

        self.assertEqual(rc, 0)
        self.assertEqual(stdout, "PONG")


if __name__ == "__main__":
    unittest.main()
