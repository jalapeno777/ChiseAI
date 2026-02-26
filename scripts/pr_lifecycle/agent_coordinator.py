#!/usr/bin/env python3
"""Agent coordinator for managing parallel agent execution.

This module provides agent registration, heartbeat monitoring, work assignment,
load balancing, and failure detection/recovery for the 10-agent parallel system.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(Enum):
    """Status of an agent in the swarm."""

    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    DEGRADED = "degraded"
    FAILED = "failed"
    OFFLINE = "offline"


class AgentPriority(Enum):
    """Priority levels for agent work assignment."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class AgentInfo:
    """Information about a registered agent."""

    agent_id: str
    story_id: str
    agent_type: str
    status: AgentStatus
    registered_at: float
    last_heartbeat: float
    capabilities: list[str] = field(default_factory=list)
    current_work: dict[str, Any] | None = None
    completed_work: list[dict[str, Any]] = field(default_factory=list)
    failure_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "story_id": self.story_id,
            "agent_type": self.agent_type,
            "status": self.status.value,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "capabilities": self.capabilities,
            "current_work": self.current_work,
            "completed_work": self.completed_work,
            "failure_count": self.failure_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInfo:
        return cls(
            agent_id=data["agent_id"],
            story_id=data["story_id"],
            agent_type=data["agent_type"],
            status=AgentStatus(data.get("status", "idle")),
            registered_at=data["registered_at"],
            last_heartbeat=data["last_heartbeat"],
            capabilities=data.get("capabilities", []),
            current_work=data.get("current_work"),
            completed_work=data.get("completed_work", []),
            failure_count=data.get("failure_count", 0),
            metadata=data.get("metadata", {}),
        )

    def is_healthy(self, heartbeat_timeout_seconds: float = 60.0) -> bool:
        """Check if the agent is healthy based on heartbeat."""
        if self.status in (AgentStatus.FAILED, AgentStatus.OFFLINE):
            return False
        time_since_heartbeat = time.time() - self.last_heartbeat
        return time_since_heartbeat < heartbeat_timeout_seconds


@dataclass
class WorkAssignment:
    """Represents a work assignment for an agent."""

    work_id: str
    story_id: str
    agent_id: str | None
    priority: AgentPriority
    scope_globs: list[str]
    description: str
    dependencies: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "story_id": self.story_id,
            "agent_id": self.agent_id,
            "priority": self.priority.value,
            "scope_globs": self.scope_globs,
            "description": self.description,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkAssignment:
        return cls(
            work_id=data["work_id"],
            story_id=data["story_id"],
            agent_id=data.get("agent_id"),
            priority=AgentPriority(data.get("priority", 2)),
            scope_globs=data.get("scope_globs", []),
            description=data["description"],
            dependencies=data.get("dependencies", []),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
        )


class AgentCoordinator:
    """Coordinates multiple agents working in parallel."""

    REDIS_AGENTS_HASH = "bmad:chiseai:agents"
    REDIS_WORK_QUEUE = "bmad:chiseai:work_queue"
    REDIS_ACTIVE_WORK = "bmad:chiseai:active_work"
    REDIS_COMPLETED_WORK = "bmad:chiseai:completed_work"

    MAX_CONCURRENT_AGENTS = 10
    HEARTBEAT_TIMEOUT_SECONDS = 60.0
    DEFAULT_TTL_SECONDS = 432000  # 5 days

    def __init__(self, redis_client=None):
        """Initialize the agent coordinator.

        Args:
            redis_client: Optional Redis client. If not provided, will attempt
                to connect using environment variables.
        """
        self._redis = redis_client
        self._local_agents: dict[str, AgentInfo] = {}
        self._local_work: dict[str, WorkAssignment] = {}
        self._failure_handlers: list[Callable[[AgentInfo], None]] = []

    def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is not None:
            return self._redis

        try:
            import redis as redis_lib

            host = (
                os.getenv("CHISE_REDIS_HOST")
                or os.getenv("REDIS_HOST")
                or "host.docker.internal"
            )
            port = int(
                os.getenv("CHISE_REDIS_PORT") or os.getenv("REDIS_PORT") or "6380"
            )
            db = int(os.getenv("CHISE_REDIS_DB") or os.getenv("REDIS_DB") or "0")

            self._redis = redis_lib.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self._redis.ping()
            return self._redis
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to Redis: {exc}") from exc

    def register_agent(
        self,
        story_id: str,
        agent_type: str = "worker",
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInfo:
        """Register a new agent with the coordinator.

        Args:
            story_id: Story ID this agent is working on
            agent_type: Type of agent (worker, senior-dev, etc.)
            capabilities: List of capabilities this agent has
            metadata: Optional metadata

        Returns:
            AgentInfo for the registered agent

        Raises:
            RuntimeError: If max concurrent agents reached
        """
        redis_client = self._get_redis()

        # Check if we've reached max agents
        active_count = self._count_active_agents()
        if active_count >= self.MAX_CONCURRENT_AGENTS:
            raise RuntimeError(
                f"Maximum concurrent agents ({self.MAX_CONCURRENT_AGENTS}) reached"
            )

        # Generate unique agent ID
        agent_id = f"{agent_type}-{uuid.uuid4().hex[:8]}"
        now = time.time()

        agent_info = AgentInfo(
            agent_id=agent_id,
            story_id=story_id,
            agent_type=agent_type,
            status=AgentStatus.IDLE,
            registered_at=now,
            last_heartbeat=now,
            capabilities=capabilities or [],
            metadata=metadata or {},
        )

        # Store in Redis
        redis_client.hset(
            self.REDIS_AGENTS_HASH,
            agent_id,
            json.dumps(agent_info.to_dict()),
        )
        redis_client.expire(self.REDIS_AGENTS_HASH, self.DEFAULT_TTL_SECONDS)

        # Update local cache
        self._local_agents[agent_id] = agent_info

        return agent_info

    def _count_active_agents(self) -> int:
        """Count the number of active (non-failed/offline) agents."""
        agents = self.get_all_agents()
        return sum(
            1
            for agent in agents.values()
            if agent.status not in (AgentStatus.FAILED, AgentStatus.OFFLINE)
        )

    def heartbeat(self, agent_id: str, status: AgentStatus | None = None) -> bool:
        """Update the heartbeat for an agent.

        Args:
            agent_id: ID of the agent
            status: Optional new status to set

        Returns:
            True if heartbeat was updated, False if agent not found
        """
        redis_client = self._get_redis()

        value = redis_client.hget(self.REDIS_AGENTS_HASH, agent_id)
        if not value:
            return False

        try:
            agent_info = AgentInfo.from_dict(json.loads(value))
        except (json.JSONDecodeError, KeyError):
            return False

        agent_info.last_heartbeat = time.time()
        if status is not None:
            agent_info.status = status

        redis_client.hset(
            self.REDIS_AGENTS_HASH, agent_id, json.dumps(agent_info.to_dict())
        )

        # Update local cache
        self._local_agents[agent_id] = agent_info

        return True

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> bool:
        """Update the status of an agent.

        Args:
            agent_id: ID of the agent
            status: New status

        Returns:
            True if status was updated, False if agent not found
        """
        return self.heartbeat(agent_id, status)

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get information about a specific agent.

        Args:
            agent_id: ID of the agent

        Returns:
            AgentInfo if found, None otherwise
        """
        # Check local cache first
        if agent_id in self._local_agents:
            return self._local_agents[agent_id]

        # Check Redis
        redis_client = self._get_redis()
        value = redis_client.hget(self.REDIS_AGENTS_HASH, agent_id)
        if not value:
            return None

        try:
            agent_info = AgentInfo.from_dict(json.loads(value))
            self._local_agents[agent_id] = agent_info
            return agent_info
        except (json.JSONDecodeError, KeyError):
            return None

    def get_all_agents(self) -> dict[str, AgentInfo]:
        """Get all registered agents.

        Returns:
            Dictionary mapping agent IDs to AgentInfo objects
        """
        redis_client = self._get_redis()
        all_data = redis_client.hgetall(self.REDIS_AGENTS_HASH)

        agents = {}
        for agent_id, value in all_data.items():
            try:
                agent_info = AgentInfo.from_dict(json.loads(value))
                agents[agent_id] = agent_info
            except (json.JSONDecodeError, KeyError):
                continue

        # Update local cache
        self._local_agents = agents
        return agents

    def get_healthy_agents(self) -> dict[str, AgentInfo]:
        """Get all healthy (active and responsive) agents.

        Returns:
            Dictionary mapping agent IDs to healthy AgentInfo objects
        """
        all_agents = self.get_all_agents()
        return {
            agent_id: agent
            for agent_id, agent in all_agents.items()
            if agent.is_healthy(self.HEARTBEAT_TIMEOUT_SECONDS)
        }

    def get_available_agents(self) -> dict[str, AgentInfo]:
        """Get agents that are available for work assignment.

        Returns:
            Dictionary mapping agent IDs to available AgentInfo objects
        """
        healthy = self.get_healthy_agents()
        return {
            agent_id: agent
            for agent_id, agent in healthy.items()
            if agent.status in (AgentStatus.IDLE, AgentStatus.ACTIVE)
            and agent.current_work is None
        }

    def submit_work(
        self,
        story_id: str,
        scope_globs: list[str],
        description: str,
        priority: AgentPriority = AgentPriority.NORMAL,
        dependencies: list[str] | None = None,
    ) -> WorkAssignment:
        """Submit work to the queue.

        Args:
            story_id: Story ID for the work
            scope_globs: List of scope globs for the work
            description: Description of the work
            priority: Priority level
            dependencies: List of work IDs that must complete first

        Returns:
            WorkAssignment object
        """
        work_id = f"work-{uuid.uuid4().hex[:8]}"
        assignment = WorkAssignment(
            work_id=work_id,
            story_id=story_id,
            agent_id=None,
            priority=priority,
            scope_globs=scope_globs,
            description=description,
            dependencies=dependencies or [],
        )

        redis_client = self._get_redis()

        # Store work
        redis_client.hset(
            self.REDIS_WORK_QUEUE, work_id, json.dumps(assignment.to_dict())
        )
        redis_client.expire(self.REDIS_WORK_QUEUE, self.DEFAULT_TTL_SECONDS)

        # Add to priority queue (sorted set)
        redis_client.zadd(
            f"{self.REDIS_WORK_QUEUE}:priority", {work_id: priority.value}
        )

        # Update local cache
        self._local_work[work_id] = assignment

        return assignment

    def assign_work(self, work_id: str, agent_id: str) -> bool:
        """Assign work to a specific agent.

        Args:
            work_id: ID of the work
            agent_id: ID of the agent

        Returns:
            True if work was assigned, False otherwise
        """
        redis_client = self._get_redis()

        # Get work
        work_value = redis_client.hget(self.REDIS_WORK_QUEUE, work_id)
        if not work_value:
            return False

        try:
            work = WorkAssignment.from_dict(json.loads(work_value))
        except (json.JSONDecodeError, KeyError):
            return False

        # Check dependencies
        for dep_id in work.dependencies:
            dep_value = redis_client.hget(self.REDIS_COMPLETED_WORK, dep_id)
            if not dep_value:
                # Dependency not completed
                return False

        # Get agent
        agent = self.get_agent(agent_id)
        if not agent or agent.current_work is not None:
            return False

        # Assign work
        work.agent_id = agent_id
        work.status = "in_progress"
        work.started_at = time.time()

        # Update work
        redis_client.hset(self.REDIS_ACTIVE_WORK, work_id, json.dumps(work.to_dict()))
        redis_client.expire(self.REDIS_ACTIVE_WORK, self.DEFAULT_TTL_SECONDS)
        redis_client.hdel(self.REDIS_WORK_QUEUE, work_id)
        redis_client.zrem(f"{self.REDIS_WORK_QUEUE}:priority", work_id)

        # Update agent
        agent.current_work = work.to_dict()
        agent.status = AgentStatus.BUSY
        redis_client.hset(self.REDIS_AGENTS_HASH, agent_id, json.dumps(agent.to_dict()))

        # Update local cache
        self._local_work[work_id] = work
        self._local_agents[agent_id] = agent

        return True

    def complete_work(
        self,
        work_id: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Mark work as completed.

        Args:
            work_id: ID of the work
            result: Optional result data
            error: Optional error message

        Returns:
            True if work was marked complete, False otherwise
        """
        redis_client = self._get_redis()

        # Get work from active
        work_value = redis_client.hget(self.REDIS_ACTIVE_WORK, work_id)
        if not work_value:
            return False

        try:
            work = WorkAssignment.from_dict(json.loads(work_value))
        except (json.JSONDecodeError, KeyError):
            return False

        # Update work
        work.status = "completed" if error is None else "failed"
        work.completed_at = time.time()
        work.result = result
        work.error = error

        # Move to completed
        redis_client.hset(
            self.REDIS_COMPLETED_WORK, work_id, json.dumps(work.to_dict())
        )
        redis_client.expire(self.REDIS_COMPLETED_WORK, self.DEFAULT_TTL_SECONDS)
        redis_client.hdel(self.REDIS_ACTIVE_WORK, work_id)

        # Update agent
        if work.agent_id:
            agent = self.get_agent(work.agent_id)
            if agent:
                agent.current_work = None
                agent.completed_work.append(work.to_dict())
                agent.status = (
                    AgentStatus.IDLE if error is None else AgentStatus.DEGRADED
                )
                if error:
                    agent.failure_count += 1
                redis_client.hset(
                    self.REDIS_AGENTS_HASH,
                    work.agent_id,
                    json.dumps(agent.to_dict()),
                )
                self._local_agents[work.agent_id] = agent

        # Update local cache
        self._local_work[work_id] = work

        return True

    def get_pending_work(self) -> list[WorkAssignment]:
        """Get all pending work assignments.

        Returns:
            List of pending WorkAssignment objects, sorted by priority
        """
        redis_client = self._get_redis()

        # Get work IDs sorted by priority (highest first)
        work_ids = redis_client.zrevrange(f"{self.REDIS_WORK_QUEUE}:priority", 0, -1)

        work_list = []
        for work_id in work_ids:
            work_value = redis_client.hget(self.REDIS_WORK_QUEUE, work_id)
            if work_value:
                try:
                    work = WorkAssignment.from_dict(json.loads(work_value))
                    work_list.append(work)
                except (json.JSONDecodeError, KeyError):
                    continue

        return work_list

    def get_active_work(self) -> dict[str, WorkAssignment]:
        """Get all active (in-progress) work assignments.

        Returns:
            Dictionary mapping work IDs to WorkAssignment objects
        """
        redis_client = self._get_redis()
        all_data = redis_client.hgetall(self.REDIS_ACTIVE_WORK)

        work_dict = {}
        for work_id, value in all_data.items():
            try:
                work = WorkAssignment.from_dict(json.loads(value))
                work_dict[work_id] = work
            except (json.JSONDecodeError, KeyError):
                continue

        return work_dict

    def check_for_failures(self) -> list[AgentInfo]:
        """Check for agents that have failed (missed heartbeats).

        Returns:
            List of failed AgentInfo objects
        """
        all_agents = self.get_all_agents()
        failed_agents = []

        for agent_id, agent in all_agents.items():
            if not agent.is_healthy(self.HEARTBEAT_TIMEOUT_SECONDS):
                if agent.status != AgentStatus.FAILED:
                    # Mark as failed
                    agent.status = AgentStatus.FAILED
                    redis_client = self._get_redis()
                    redis_client.hset(
                        self.REDIS_AGENTS_HASH,
                        agent_id,
                        json.dumps(agent.to_dict()),
                    )
                    self._local_agents[agent_id] = agent
                    failed_agents.append(agent)

                    # Trigger failure handlers
                    for handler in self._failure_handlers:
                        with suppress(Exception):
                            handler(agent)

        return failed_agents

    def register_failure_handler(self, handler: Callable[[AgentInfo], None]) -> None:
        """Register a handler to be called when an agent fails.

        Args:
            handler: Callback function that receives the failed AgentInfo
        """
        self._failure_handlers.append(handler)

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent.

        Args:
            agent_id: ID of the agent to unregister

        Returns:
            True if agent was unregistered, False if not found
        """
        redis_client = self._get_redis()

        result = redis_client.hdel(self.REDIS_AGENTS_HASH, agent_id)

        if agent_id in self._local_agents:
            del self._local_agents[agent_id]

        return result > 0

    def get_queue_stats(self) -> dict[str, Any]:
        """Get statistics about the work queue.

        Returns:
            Dictionary with queue statistics
        """
        redis_client = self._get_redis()

        pending = len(redis_client.hkeys(self.REDIS_WORK_QUEUE))
        active = len(redis_client.hkeys(self.REDIS_ACTIVE_WORK))
        completed = len(redis_client.hkeys(self.REDIS_COMPLETED_WORK))
        agents = len(redis_client.hkeys(self.REDIS_AGENTS_HASH))
        healthy = len(self.get_healthy_agents())
        available = len(self.get_available_agents())

        return {
            "pending_work": pending,
            "active_work": active,
            "completed_work": completed,
            "total_agents": agents,
            "healthy_agents": healthy,
            "available_agents": available,
            "max_concurrent_agents": self.MAX_CONCURRENT_AGENTS,
        }


# Singleton instance for module-level access
_coordinator_instance: AgentCoordinator | None = None


def get_agent_coordinator(redis_client=None) -> AgentCoordinator:
    """Get or create the global agent coordinator instance."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = AgentCoordinator(redis_client)
    return _coordinator_instance
