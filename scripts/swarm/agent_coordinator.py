#!/usr/bin/env python3
"""
Agent Coordinator for ChiseAI Agent Swarm Parallel Coordination.

Coordinates up to 10 simultaneous agents with:
- Agent registration and heartbeat tracking
- Dashboard data export (active agents, their PRs, status)
- Graceful failure handling and cleanup
- Integration with existing ownership system

Story: ST-AUTO-007
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key patterns
AGENT_PREFIX = "bmad:chiseai:swarm:agent:"
HEARTBEAT_PREFIX = "bmad:chiseai:swarm:heartbeat:"
DASHBOARD_PREFIX = "bmad:chiseai:swarm:dashboard:"
FAILURE_LOG_PREFIX = "bmad:chiseai:swarm:failure:"

# Constants
MAX_AGENTS = 10
DEFAULT_TTL = 432000  # 5 days
HEARTBEAT_INTERVAL_SECONDS = 60
STALE_THRESHOLD_MINUTES = 30


class AgentStatus(Enum):
    """Status values for agent lifecycle."""

    PENDING = "pending"
    STARTING = "starting"
    ACTIVE = "active"
    WORKING = "working"
    COMPLETING = "completing"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AgentRole(Enum):
    """Roles for agents in the swarm."""

    WORKER = "worker"
    COORDINATOR = "coordinator"
    MERGER = "merger"
    VALIDATOR = "validator"


@dataclass
class AgentInfo:
    """Information about an agent in the swarm."""

    story_id: str
    agent_id: str
    role: AgentRole
    status: AgentStatus
    branch: str
    worktree_path: str
    started_at: str
    last_heartbeat: str
    completed_at: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    scope_globs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "completed_at": self.completed_at,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "scope_globs": self.scope_globs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInfo:
        """Create AgentInfo from dictionary."""
        return cls(
            story_id=data["story_id"],
            agent_id=data["agent_id"],
            role=AgentRole(data.get("role", "worker")),
            status=AgentStatus(data.get("status", "pending")),
            branch=data["branch"],
            worktree_path=data["worktree_path"],
            started_at=data["started_at"],
            last_heartbeat=data["last_heartbeat"],
            completed_at=data.get("completed_at"),
            pr_url=data.get("pr_url"),
            pr_number=data.get("pr_number"),
            scope_globs=data.get("scope_globs", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DashboardData:
    """Data for the agent coordination dashboard."""

    timestamp: str
    total_agents: int
    active_agents: int
    completed_agents: int
    failed_agents: int
    agents: list[AgentInfo]
    prs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "total_agents": self.total_agents,
            "active_agents": self.active_agents,
            "completed_agents": self.completed_agents,
            "failed_agents": self.failed_agents,
            "agents": [a.to_dict() for a in self.agents],
            "prs": self.prs,
        }


@dataclass
class FailureRecord:
    """Record of an agent failure."""

    story_id: str
    agent_id: str
    failed_at: str
    reason: str
    stack_trace: str | None = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    cleanup_completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "agent_id": self.agent_id,
            "failed_at": self.failed_at,
            "reason": self.reason,
            "stack_trace": self.stack_trace,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "cleanup_completed": self.cleanup_completed,
        }


class AgentCoordinator:
    """Coordinates agents in the swarm with heartbeat tracking and dashboard."""

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int = 6380,
        redis_db: int = 0,
        max_agents: int = MAX_AGENTS,
    ):
        """Initialize agent coordinator.

        Args:
            redis_host: Redis host for coordination
            redis_port: Redis port
            redis_db: Redis database number
            max_agents: Maximum number of simultaneous agents
        """
        self.redis_host = (
            redis_host
            or os.getenv("CHISE_REDIS_HOST")
            or os.getenv("REDIS_HOST")
            or "host.docker.internal"
        )
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.max_agents = max_agents
        self._redis_available = self._check_redis()

    def _check_redis(self) -> bool:
        """Check if Redis is available."""
        try:
            result = subprocess.run(  # nosec B607
                [
                    "redis-cli",
                    "-h",
                    self.redis_host,
                    "-p",
                    str(self.redis_port),
                    "-n",
                    str(self.redis_db),
                    "PING",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == "PONG"
        except Exception:
            return False

    def _redis_cli(self, *args: str) -> tuple[int, str, str]:
        """Execute a redis-cli command."""
        cmd = [
            "redis-cli",
            "-h",
            self.redis_host,
            "-p",
            str(self.redis_port),
            "-n",
            str(self.redis_db),
            *args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _utc_now(self) -> str:
        """Get current UTC timestamp."""
        return (
            dt.datetime.now(dt.UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _agent_key(self, story_id: str, agent_id: str) -> str:
        """Generate Redis key for agent info."""
        return f"{AGENT_PREFIX}{story_id}:{agent_id}"

    def _heartbeat_key(self, story_id: str, agent_id: str) -> str:
        """Generate Redis key for agent heartbeat."""
        return f"{HEARTBEAT_PREFIX}{story_id}:{agent_id}"

    def _failure_key(self, story_id: str, agent_id: str) -> str:
        """Generate Redis key for failure record."""
        return f"{FAILURE_LOG_PREFIX}{story_id}:{agent_id}"

    def register_agent(
        self,
        story_id: str,
        agent_id: str,
        branch: str,
        worktree_path: str,
        role: AgentRole = AgentRole.WORKER,
        scope_globs: list[str] | None = None,
    ) -> AgentInfo:
        """Register a new agent in the swarm.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            branch: Branch name
            worktree_path: Path to agent's worktree
            role: Agent role
            scope_globs: Scope globs for this agent

        Returns:
            AgentInfo object

        Raises:
            RuntimeError: If max agents reached
        """
        # Check agent limit
        active_count = len(self.get_active_agents())
        if active_count >= self.max_agents:
            raise RuntimeError(
                f"Maximum agents ({self.max_agents}) reached. "
                "Cannot register new agent."
            )

        now = self._utc_now()
        info = AgentInfo(
            story_id=story_id,
            agent_id=agent_id,
            role=role,
            status=AgentStatus.STARTING,
            branch=branch,
            worktree_path=worktree_path,
            started_at=now,
            last_heartbeat=now,
            scope_globs=scope_globs or [],
        )

        # Store in Redis
        if self._redis_available:
            agent_key = self._agent_key(story_id, agent_id)
            self._redis_cli(
                "SET", agent_key, json.dumps(info.to_dict()), "EX", str(DEFAULT_TTL)
            )

            # Initialize heartbeat
            heartbeat_key = self._heartbeat_key(story_id, agent_id)
            self._redis_cli(
                "SET", heartbeat_key, now, "EX", str(HEARTBEAT_INTERVAL_SECONDS * 2)
            )

        logger.info(f"Registered agent {story_id}/{agent_id} with role {role.value}")
        return info

    def update_heartbeat(self, story_id: str, agent_id: str) -> bool:
        """Update heartbeat for an agent.

        Args:
            story_id: Story ID
            agent_id: Agent identifier

        Returns:
            True if heartbeat was updated
        """
        if not self._redis_available:
            return False

        now = self._utc_now()

        # Update heartbeat timestamp
        heartbeat_key = self._heartbeat_key(story_id, agent_id)
        rc, _, _ = self._redis_cli(
            "SET", heartbeat_key, now, "EX", str(HEARTBEAT_INTERVAL_SECONDS * 2)
        )

        # Update agent info
        agent_key = self._agent_key(story_id, agent_id)
        rc2, data, _ = self._redis_cli("GET", agent_key)
        if rc2 == 0 and data:
            try:
                info = AgentInfo.from_dict(json.loads(data))
                info.last_heartbeat = now
                self._redis_cli(
                    "SET", agent_key, json.dumps(info.to_dict()), "EX", str(DEFAULT_TTL)
                )
                return rc == 0
            except json.JSONDecodeError:
                pass

        return False

    def update_agent_status(
        self,
        story_id: str,
        agent_id: str,
        status: AgentStatus,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInfo | None:
        """Update agent status.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            status: New status
            metadata: Optional metadata to update

        Returns:
            Updated AgentInfo or None if not found
        """
        info = self.get_agent_info(story_id, agent_id)
        if not info:
            return None

        info.status = status
        info.last_heartbeat = self._utc_now()

        if status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TIMEOUT):
            info.completed_at = self._utc_now()

        if metadata:
            info.metadata.update(metadata)

        # Store in Redis
        if self._redis_available:
            agent_key = self._agent_key(story_id, agent_id)
            self._redis_cli(
                "SET", agent_key, json.dumps(info.to_dict()), "EX", str(DEFAULT_TTL)
            )

        logger.info(f"Updated {story_id}/{agent_id} status to {status.value}")
        return info

    def update_pr_info(
        self,
        story_id: str,
        agent_id: str,
        pr_url: str,
        pr_number: int,
    ) -> AgentInfo | None:
        """Update PR information for an agent.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            pr_url: PR URL
            pr_number: PR number

        Returns:
            Updated AgentInfo or None if not found
        """
        info = self.get_agent_info(story_id, agent_id)
        if not info:
            return None

        info.pr_url = pr_url
        info.pr_number = pr_number
        info.last_heartbeat = self._utc_now()

        # Store in Redis
        if self._redis_available:
            agent_key = self._agent_key(story_id, agent_id)
            self._redis_cli(
                "SET", agent_key, json.dumps(info.to_dict()), "EX", str(DEFAULT_TTL)
            )

        logger.info(f"Updated PR info for {story_id}/{agent_id}: {pr_url}")
        return info

    def get_agent_info(self, story_id: str, agent_id: str) -> AgentInfo | None:
        """Get agent info from Redis."""
        if not self._redis_available:
            return None

        agent_key = self._agent_key(story_id, agent_id)
        rc, stdout, _ = self._redis_cli("GET", agent_key)
        if rc == 0 and stdout:
            try:
                return AgentInfo.from_dict(json.loads(stdout))
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def get_active_agents(self) -> list[AgentInfo]:
        """Get all active agents."""
        if not self._redis_available:
            return []

        rc, stdout, _ = self._redis_cli("KEYS", f"{AGENT_PREFIX}*")
        if rc != 0 or not stdout:
            return []

        agents = []
        for key in stdout.split("\n"):
            if key:
                rc2, data, _ = self._redis_cli("GET", key)
                if rc2 == 0 and data:
                    try:
                        info = AgentInfo.from_dict(json.loads(data))
                        if info.status not in (
                            AgentStatus.COMPLETED,
                            AgentStatus.FAILED,
                            AgentStatus.TIMEOUT,
                        ):
                            agents.append(info)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return agents

    def get_all_agents(self) -> list[AgentInfo]:
        """Get all agents (active and completed)."""
        if not self._redis_available:
            return []

        rc, stdout, _ = self._redis_cli("KEYS", f"{AGENT_PREFIX}*")
        if rc != 0 or not stdout:
            return []

        agents = []
        for key in stdout.split("\n"):
            if key:
                rc2, data, _ = self._redis_cli("GET", key)
                if rc2 == 0 and data:
                    try:
                        info = AgentInfo.from_dict(json.loads(data))
                        agents.append(info)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return agents

    def is_agent_stale(self, story_id: str, agent_id: str) -> bool:
        """Check if an agent's heartbeat is stale.

        Args:
            story_id: Story ID
            agent_id: Agent identifier

        Returns:
            True if heartbeat is stale
        """
        if not self._redis_available:
            return False

        heartbeat_key = self._heartbeat_key(story_id, agent_id)
        rc, stdout, _ = self._redis_cli("GET", heartbeat_key)

        if rc != 0 or not stdout:
            return True

        try:
            last_beat = dt.datetime.fromisoformat(stdout.replace("Z", "+00:00"))
            threshold = dt.datetime.now(dt.UTC) - dt.timedelta(
                minutes=STALE_THRESHOLD_MINUTES
            )
            return last_beat < threshold
        except (ValueError, TypeError):
            return True

    def get_stale_agents(self) -> list[AgentInfo]:
        """Get all agents with stale heartbeats."""
        active_agents = self.get_active_agents()
        stale = []

        for agent in active_agents:
            if self.is_agent_stale(agent.story_id, agent.agent_id):
                stale.append(agent)

        return stale

    def record_failure(
        self,
        story_id: str,
        agent_id: str,
        reason: str,
        stack_trace: str | None = None,
    ) -> FailureRecord:
        """Record an agent failure.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            reason: Failure reason
            stack_trace: Optional stack trace

        Returns:
            FailureRecord
        """
        record = FailureRecord(
            story_id=story_id,
            agent_id=agent_id,
            failed_at=self._utc_now(),
            reason=reason,
            stack_trace=stack_trace,
        )

        # Store in Redis
        if self._redis_available:
            failure_key = self._failure_key(story_id, agent_id)
            self._redis_cli(
                "SET", failure_key, json.dumps(record.to_dict()), "EX", str(DEFAULT_TTL)
            )

        # Update agent status
        self.update_agent_status(story_id, agent_id, AgentStatus.FAILED)

        logger.error(f"Recorded failure for {story_id}/{agent_id}: {reason}")
        return record

    def attempt_recovery(
        self,
        story_id: str,
        agent_id: str,
    ) -> tuple[bool, str]:
        """Attempt to recover from an agent failure.

        Args:
            story_id: Story ID
            agent_id: Agent identifier

        Returns:
            Tuple of (success, message)
        """
        info = self.get_agent_info(story_id, agent_id)
        if not info:
            return False, "Agent not found"

        # Get failure record
        failure_key = self._failure_key(story_id, agent_id)
        rc, data, _ = self._redis_cli("GET", failure_key)

        if rc != 0 or not data:
            return False, "No failure record found"

        try:
            record = FailureRecord(**json.loads(data))
        except (json.JSONDecodeError, TypeError):
            return False, "Invalid failure record"

        # Mark recovery attempted
        record.recovery_attempted = True

        # Attempt cleanup
        cleanup_success = self._cleanup_agent_resources(info)
        record.cleanup_completed = cleanup_success

        if cleanup_success:
            record.recovery_successful = True
            self.update_agent_status(story_id, agent_id, AgentStatus.CLEANUP)

        # Update failure record
        if self._redis_available:
            self._redis_cli(
                "SET", failure_key, json.dumps(record.to_dict()), "EX", str(DEFAULT_TTL)
            )

        if cleanup_success:
            return True, "Recovery successful - resources cleaned up"
        else:
            return False, "Recovery failed - cleanup incomplete"

    def _cleanup_agent_resources(self, info: AgentInfo) -> bool:
        """Clean up resources for an agent.

        Args:
            info: AgentInfo

        Returns:
            True if cleanup successful
        """
        success = True

        # Clean up worktree if it exists
        if os.path.exists(info.worktree_path):
            try:
                # Remove worktree using git
                result = subprocess.run(  # nosec B607
                    ["git", "worktree", "remove", info.worktree_path, "--force"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    logger.warning(
                        f"Failed to remove worktree {info.worktree_path}: {result.stderr}"
                    )
                    success = False
            except Exception as e:
                logger.warning(f"Exception removing worktree {info.worktree_path}: {e}")
                success = False

        # Clean up Redis keys
        if self._redis_available:
            self._redis_cli("DEL", self._agent_key(info.story_id, info.agent_id))
            self._redis_cli("DEL", self._heartbeat_key(info.story_id, info.agent_id))

        return success

    def get_dashboard_data(self) -> DashboardData:
        """Get data for the agent coordination dashboard.

        Returns:
            DashboardData
        """
        all_agents = self.get_all_agents()
        active_agents = [
            a
            for a in all_agents
            if a.status
            not in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TIMEOUT)
        ]
        completed_agents = [a for a in all_agents if a.status == AgentStatus.COMPLETED]
        failed_agents = [a for a in all_agents if a.status == AgentStatus.FAILED]

        # Collect PR information
        prs = []
        for agent in all_agents:
            if agent.pr_url:
                prs.append(
                    {
                        "story_id": agent.story_id,
                        "agent_id": agent.agent_id,
                        "pr_url": agent.pr_url,
                        "pr_number": agent.pr_number,
                        "branch": agent.branch,
                        "status": agent.status.value,
                    }
                )

        return DashboardData(
            timestamp=self._utc_now(),
            total_agents=len(all_agents),
            active_agents=len(active_agents),
            completed_agents=len(completed_agents),
            failed_agents=len(failed_agents),
            agents=active_agents,
            prs=prs,
        )

    def export_dashboard_json(self, output_path: str | None = None) -> str:
        """Export dashboard data as JSON.

        Args:
            output_path: Optional output file path

        Returns:
            JSON string
        """
        data = self.get_dashboard_data()
        json_str = json.dumps(data.to_dict(), indent=2)

        if output_path:
            with open(output_path, "w") as f:
                f.write(json_str)
            logger.info(f"Dashboard data exported to {output_path}")

        return json_str

    def check_ownership(
        self, story_id: str, agent_id: str, scope: str
    ) -> tuple[bool, str | None]:
        """Check if an agent owns a scope.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            scope: Scope to check

        Returns:
            Tuple of (owns_scope, current_owner)
        """
        if not self._redis_available:
            return True, None

        # Convert scope to slug
        slug = scope.strip("/").replace("/", ":").lower()

        rc, stdout, _ = self._redis_cli("HGET", "bmad:chiseai:ownership", slug)
        if rc != 0 or not stdout:
            return True, None

        expected_prefix = f"{story_id}/{agent_id}/"
        if stdout.startswith(expected_prefix):
            return True, stdout
        else:
            return False, stdout

    def claim_ownership(
        self,
        story_id: str,
        agent_id: str,
        scopes: list[str],
        ttl_seconds: int = DEFAULT_TTL,
    ) -> bool:
        """Claim ownership of scopes for an agent.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            scopes: List of scopes to claim
            ttl_seconds: TTL for ownership

        Returns:
            True if all scopes claimed successfully
        """
        if not self._redis_available:
            return True

        now = self._utc_now()
        owner = f"{story_id}/{agent_id}/{now}"

        for scope in scopes:
            slug = scope.strip("/").replace("/", ":").lower()
            self._redis_cli("HSET", "bmad:chiseai:ownership", slug, owner)

        self._redis_cli("EXPIRE", "bmad:chiseai:ownership", str(ttl_seconds))

        logger.info(f"Claimed ownership for {story_id}/{agent_id}: {scopes}")
        return True

    def release_ownership(
        self, story_id: str, agent_id: str, scopes: list[str]
    ) -> bool:
        """Release ownership of scopes.

        Args:
            story_id: Story ID
            agent_id: Agent identifier
            scopes: List of scopes to release

        Returns:
            True if all scopes released successfully
        """
        if not self._redis_available:
            return True

        for scope in scopes:
            slug = scope.strip("/").replace("/", ":").lower()

            # Check current owner
            rc, stdout, _ = self._redis_cli("HGET", "bmad:chiseai:ownership", slug)
            if rc == 0 and stdout:
                expected_prefix = f"{story_id}/{agent_id}/"
                if stdout.startswith(expected_prefix):
                    self._redis_cli("HDEL", "bmad:chiseai:ownership", slug)

        logger.info(f"Released ownership for {story_id}/{agent_id}: {scopes}")
        return True


def main():
    """CLI entry point for agent coordinator."""
    import argparse

    parser = argparse.ArgumentParser(description="ChiseAI Agent Coordinator")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Register command
    register_parser = subparsers.add_parser("register", help="Register a new agent")
    register_parser.add_argument("--story-id", required=True, help="Story ID")
    register_parser.add_argument("--agent-id", required=True, help="Agent identifier")
    register_parser.add_argument("--branch", required=True, help="Branch name")
    register_parser.add_argument("--worktree", required=True, help="Worktree path")
    register_parser.add_argument(
        "--role",
        default="worker",
        choices=[r.value for r in AgentRole],
        help="Agent role",
    )
    register_parser.add_argument("--scopes", nargs="*", default=[], help="Scope globs")

    # Heartbeat command
    heartbeat_parser = subparsers.add_parser("heartbeat", help="Update agent heartbeat")
    heartbeat_parser.add_argument("--story-id", required=True, help="Story ID")
    heartbeat_parser.add_argument("--agent-id", required=True, help="Agent identifier")

    # Status command
    status_parser = subparsers.add_parser("status", help="Update agent status")
    status_parser.add_argument("--story-id", required=True, help="Story ID")
    status_parser.add_argument("--agent-id", required=True, help="Agent identifier")
    status_parser.add_argument(
        "--status",
        required=True,
        choices=[s.value for s in AgentStatus],
        help="New status",
    )

    # PR command
    pr_parser = subparsers.add_parser("pr", help="Update PR information")
    pr_parser.add_argument("--story-id", required=True, help="Story ID")
    pr_parser.add_argument("--agent-id", required=True, help="Agent identifier")
    pr_parser.add_argument("--url", required=True, help="PR URL")
    pr_parser.add_argument("--number", type=int, required=True, help="PR number")

    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Export dashboard data")
    dashboard_parser.add_argument("--output", help="Output file path")

    # List command
    list_parser = subparsers.add_parser("list", help="List agents")
    list_parser.add_argument(
        "--all", action="store_true", help="Include completed agents"
    )

    # Check-stale command
    subparsers.add_parser("check-stale", help="Check for stale agents")

    # Failure command
    failure_parser = subparsers.add_parser("failure", help="Record agent failure")
    failure_parser.add_argument("--story-id", required=True, help="Story ID")
    failure_parser.add_argument("--agent-id", required=True, help="Agent identifier")
    failure_parser.add_argument("--reason", required=True, help="Failure reason")
    failure_parser.add_argument("--stack-trace", help="Stack trace")

    # Recover command
    recover_parser = subparsers.add_parser("recover", help="Attempt agent recovery")
    recover_parser.add_argument("--story-id", required=True, help="Story ID")
    recover_parser.add_argument("--agent-id", required=True, help="Agent identifier")

    # Ownership command
    ownership_parser = subparsers.add_parser("ownership", help="Manage ownership")
    ownership_parser.add_argument(
        "--claim", action="store_true", help="Claim ownership"
    )
    ownership_parser.add_argument(
        "--release", action="store_true", help="Release ownership"
    )
    ownership_parser.add_argument(
        "--check", action="store_true", help="Check ownership"
    )
    ownership_parser.add_argument("--story-id", help="Story ID")
    ownership_parser.add_argument("--agent-id", help="Agent identifier")
    ownership_parser.add_argument("--scope", help="Scope to check/claim/release")
    ownership_parser.add_argument(
        "--scopes", nargs="*", default=[], help="Scopes for claim/release"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    coordinator = AgentCoordinator()

    try:
        if args.command == "register":
            info = coordinator.register_agent(
                story_id=args.story_id,
                agent_id=args.agent_id,
                branch=args.branch,
                worktree_path=args.worktree,
                role=AgentRole(args.role),
                scope_globs=args.scopes,
            )
            print(json.dumps(info.to_dict(), indent=2))

        elif args.command == "heartbeat":
            success = coordinator.update_heartbeat(args.story_id, args.agent_id)
            print(f"Heartbeat updated: {success}")

        elif args.command == "status":
            info = coordinator.update_agent_status(
                story_id=args.story_id,
                agent_id=args.agent_id,
                status=AgentStatus(args.status),
            )
            if info:
                print(json.dumps(info.to_dict(), indent=2))
            else:
                print(f"Agent {args.story_id}/{args.agent_id} not found")
                return 1

        elif args.command == "pr":
            info = coordinator.update_pr_info(
                story_id=args.story_id,
                agent_id=args.agent_id,
                pr_url=args.url,
                pr_number=args.number,
            )
            if info:
                print(json.dumps(info.to_dict(), indent=2))
            else:
                print(f"Agent {args.story_id}/{args.agent_id} not found")
                return 1

        elif args.command == "dashboard":
            json_str = coordinator.export_dashboard_json(args.output)
            if not args.output:
                print(json_str)

        elif args.command == "list":
            if args.all:
                agents = coordinator.get_all_agents()
            else:
                agents = coordinator.get_active_agents()

            print(f"{'Story ID':<20} {'Agent':<20} {'Status':<15} {'Branch':<40}")
            print("-" * 95)
            for agent in agents:
                print(
                    f"{agent.story_id:<20} {agent.agent_id:<20} {agent.status.value:<15} {agent.branch:<40}"
                )

        elif args.command == "check-stale":
            stale = coordinator.get_stale_agents()
            if stale:
                print(f"Found {len(stale)} stale agents:")
                for agent in stale:
                    print(f"  - {agent.story_id}/{agent.agent_id}")
            else:
                print("No stale agents found")

        elif args.command == "failure":
            record = coordinator.record_failure(
                story_id=args.story_id,
                agent_id=args.agent_id,
                reason=args.reason,
                stack_trace=args.stack_trace,
            )
            print(json.dumps(record.to_dict(), indent=2))

        elif args.command == "recover":
            success, msg = coordinator.attempt_recovery(args.story_id, args.agent_id)
            print(f"Recovery {'successful' if success else 'failed'}: {msg}")

        elif args.command == "ownership":
            if args.claim:
                scopes = args.scopes or ([args.scope] if args.scope else [])
                success = coordinator.claim_ownership(
                    args.story_id, args.agent_id, scopes
                )
                print(f"Ownership claimed: {success}")
            elif args.release:
                scopes = args.scopes or ([args.scope] if args.scope else [])
                success = coordinator.release_ownership(
                    args.story_id, args.agent_id, scopes
                )
                print(f"Ownership released: {success}")
            elif args.check:
                owns, owner = coordinator.check_ownership(
                    args.story_id, args.agent_id, args.scope
                )
                if owns:
                    print(f"Ownership confirmed for {args.scope}")
                else:
                    print(f"Ownership conflict: {args.scope} is owned by {owner}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
