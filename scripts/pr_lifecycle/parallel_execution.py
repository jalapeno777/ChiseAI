#!/usr/bin/env python3
"""Parallel execution coordinator for multi-agent work.

This module provides batch coordination, dependency resolution, priority queue
management, and deadlock detection for the 10-agent parallel execution system.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scripts.pr_lifecycle.agent_coordinator import (
    AgentCoordinator,
    AgentPriority,
    get_agent_coordinator,
)
from scripts.pr_lifecycle.scope_registry import (
    ScopeRegistry,
    get_scope_registry,
)


class BatchStatus(Enum):
    """Status of a parallel execution batch."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class DeadlockResolution(Enum):
    """Strategies for resolving deadlocks."""

    ABORT_ALL = "abort_all"
    ABORT_YOUNGEST = "abort_youngest"
    ABORT_LOWEST_PRIORITY = "abort_lowest_priority"
    SEQUENTIAL_FALLBACK = "sequential_fallback"


@dataclass
class BatchItem:
    """Represents a single item in a parallel batch."""

    item_id: str
    story_id: str
    scope_globs: list[str]
    description: str
    agent_id: str | None = None
    priority: AgentPriority = field(default=AgentPriority.NORMAL)
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "story_id": self.story_id,
            "agent_id": self.agent_id,
            "scope_globs": self.scope_globs,
            "description": self.description,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchItem:
        return cls(
            item_id=data["item_id"],
            story_id=data["story_id"],
            agent_id=data.get("agent_id"),
            scope_globs=data.get("scope_globs", []),
            description=data["description"],
            priority=AgentPriority(data.get("priority", 2)),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class ExecutionBatch:
    """Represents a batch of parallel execution items."""

    batch_id: str
    description: str
    items: dict[str, BatchItem] = field(default_factory=dict)
    status: BatchStatus = BatchStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    max_parallel: int = 10
    deadlock_resolution: DeadlockResolution = DeadlockResolution.ABORT_YOUNGEST
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "description": self.description,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "max_parallel": self.max_parallel,
            "deadlock_resolution": self.deadlock_resolution.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionBatch:
        batch = cls(
            batch_id=data["batch_id"],
            description=data["description"],
            status=BatchStatus(data.get("status", "pending")),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            max_parallel=data.get("max_parallel", 10),
            deadlock_resolution=DeadlockResolution(
                data.get("deadlock_resolution", "abort_youngest")
            ),
            metadata=data.get("metadata", {}),
        )
        batch.items = {
            k: BatchItem.from_dict(v) for k, v in data.get("items", {}).items()
        }
        return batch

    def get_ready_items(self) -> list[BatchItem]:
        """Get items that are ready to execute (dependencies met)."""
        ready = []
        for item in self.items.values():
            if item.status != "pending":
                continue

            # Check if all dependencies are completed
            deps_met = all(
                self.items.get(dep_id) is not None
                and self.items[dep_id].status == "completed"
                for dep_id in item.dependencies
            )

            if deps_met:
                ready.append(item)

        # Sort by priority (highest first)
        ready.sort(key=lambda x: x.priority.value, reverse=True)
        return ready

    def get_active_items(self) -> list[BatchItem]:
        """Get items that are currently active."""
        return [item for item in self.items.values() if item.status == "in_progress"]

    def get_completed_items(self) -> list[BatchItem]:
        """Get items that have completed."""
        return [item for item in self.items.values() if item.status == "completed"]

    def get_failed_items(self) -> list[BatchItem]:
        """Get items that have failed."""
        return [item for item in self.items.values() if item.status == "failed"]

    def is_complete(self) -> bool:
        """Check if all items are complete (completed or failed)."""
        return all(
            item.status in ("completed", "failed") for item in self.items.values()
        )


@dataclass
class DeadlockInfo:
    """Information about a detected deadlock."""

    cycle: list[str]
    items_involved: list[str]
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "items_involved": self.items_involved,
            "detected_at": self.detected_at,
        }


class ParallelExecutionCoordinator:
    """Coordinates parallel execution of multiple work items."""

    REDIS_BATCH_HASH = "bmad:chiseai:execution_batches"
    REDIS_DEADLOCK_LOG = "bmad:chiseai:deadlock_log"
    DEFAULT_TTL_SECONDS = 432000  # 5 days

    def __init__(
        self,
        redis_client=None,
        scope_registry: ScopeRegistry | None = None,
        agent_coordinator: AgentCoordinator | None = None,
    ):
        """Initialize the parallel execution coordinator.

        Args:
            redis_client: Optional Redis client
            scope_registry: Optional ScopeRegistry instance
            agent_coordinator: Optional AgentCoordinator instance
        """
        self._redis = redis_client
        self._scope_registry = scope_registry
        self._agent_coordinator = agent_coordinator
        self._local_batches: dict[str, ExecutionBatch] = {}

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

    def _get_scope_registry(self) -> ScopeRegistry:
        """Get or create scope registry."""
        if self._scope_registry is None:
            self._scope_registry = get_scope_registry(self._get_redis())
        return self._scope_registry

    def _get_agent_coordinator(self) -> AgentCoordinator:
        """Get or create agent coordinator."""
        if self._agent_coordinator is None:
            self._agent_coordinator = get_agent_coordinator(self._get_redis())
        return self._agent_coordinator

    def create_batch(
        self,
        description: str,
        max_parallel: int = 10,
        deadlock_resolution: DeadlockResolution = DeadlockResolution.ABORT_YOUNGEST,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionBatch:
        """Create a new execution batch.

        Args:
            description: Description of the batch
            max_parallel: Maximum number of parallel items
            deadlock_resolution: Strategy for resolving deadlocks
            metadata: Optional metadata

        Returns:
            ExecutionBatch object
        """
        import uuid

        batch_id = f"batch-{uuid.uuid4().hex[:8]}"
        batch = ExecutionBatch(
            batch_id=batch_id,
            description=description,
            max_parallel=max_parallel,
            deadlock_resolution=deadlock_resolution,
            metadata=metadata or {},
        )

        # Store in Redis
        redis_client = self._get_redis()
        redis_client.hset(self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict()))
        redis_client.expire(self.REDIS_BATCH_HASH, self.DEFAULT_TTL_SECONDS)

        # Update local cache
        self._local_batches[batch_id] = batch

        return batch

    def add_item_to_batch(
        self,
        batch_id: str,
        story_id: str,
        scope_globs: list[str],
        description: str,
        priority: AgentPriority = AgentPriority.NORMAL,
        dependencies: list[str] | None = None,
    ) -> BatchItem | None:
        """Add an item to a batch.

        Args:
            batch_id: ID of the batch
            story_id: Story ID for the item
            scope_globs: List of scope globs
            description: Description of the work
            priority: Priority level
            dependencies: List of item IDs that must complete first

        Returns:
            BatchItem if added successfully, None if batch not found
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return None

        import uuid

        item_id = f"item-{uuid.uuid4().hex[:8]}"
        item = BatchItem(
            item_id=item_id,
            story_id=story_id,
            scope_globs=scope_globs,
            description=description,
            priority=priority,
            dependencies=dependencies or [],
        )

        batch.items[item_id] = item

        # Update in Redis
        redis_client = self._get_redis()
        redis_client.hset(self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict()))

        # Update local cache
        self._local_batches[batch_id] = batch

        return item

    def get_batch(self, batch_id: str) -> ExecutionBatch | None:
        """Get a batch by ID.

        Args:
            batch_id: ID of the batch

        Returns:
            ExecutionBatch if found, None otherwise
        """
        # Check local cache first
        if batch_id in self._local_batches:
            return self._local_batches[batch_id]

        # Check Redis
        redis_client = self._get_redis()
        value = redis_client.hget(self.REDIS_BATCH_HASH, batch_id)
        if not value:
            return None

        try:
            batch = ExecutionBatch.from_dict(json.loads(value))
            self._local_batches[batch_id] = batch
            return batch
        except (json.JSONDecodeError, KeyError):
            return None

    def get_all_batches(self) -> dict[str, ExecutionBatch]:
        """Get all batches.

        Returns:
            Dictionary mapping batch IDs to ExecutionBatch objects
        """
        redis_client = self._get_redis()
        all_data = redis_client.hgetall(self.REDIS_BATCH_HASH)

        batches = {}
        for batch_id, value in all_data.items():
            try:
                batch = ExecutionBatch.from_dict(json.loads(value))
                batches[batch_id] = batch
            except (json.JSONDecodeError, KeyError):
                continue

        self._local_batches = batches
        return batches

    def detect_deadlock(self, batch_id: str) -> DeadlockInfo | None:
        """Detect circular dependencies (deadlocks) in a batch.

        Args:
            batch_id: ID of the batch to check

        Returns:
            DeadlockInfo if deadlock detected, None otherwise
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return None

        # Build dependency graph
        graph: dict[str, list[str]] = {}
        for item_id, item in batch.items.items():
            graph[item_id] = item.dependencies

        # Find cycles using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycle: list[str] = []

        def dfs(node: str, path: list[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle.extend(path[cycle_start:] + [neighbor])
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if dfs(node, []):
                    # Log the deadlock
                    deadlock_info = DeadlockInfo(
                        cycle=cycle,
                        items_involved=list(set(cycle)),
                    )
                    self._log_deadlock(batch_id, deadlock_info)
                    return deadlock_info

        return None

    def _log_deadlock(self, batch_id: str, deadlock_info: DeadlockInfo) -> None:
        """Log a detected deadlock."""
        redis_client = self._get_redis()
        log_entry = {
            "batch_id": batch_id,
            "deadlock": deadlock_info.to_dict(),
            "logged_at": time.time(),
        }
        redis_client.lpush(self.REDIS_DEADLOCK_LOG, json.dumps(log_entry))
        redis_client.expire(self.REDIS_DEADLOCK_LOG, self.DEFAULT_TTL_SECONDS)

    def resolve_deadlock(
        self, batch_id: str, strategy: DeadlockResolution | None = None
    ) -> bool:
        """Resolve a deadlock in a batch.

        Args:
            batch_id: ID of the batch
            strategy: Resolution strategy (uses batch default if None)

        Returns:
            True if deadlock was resolved, False otherwise
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return False

        deadlock_info = self.detect_deadlock(batch_id)
        if not deadlock_info:
            return True  # No deadlock to resolve

        strategy = strategy or batch.deadlock_resolution

        if strategy == DeadlockResolution.ABORT_ALL:
            # Mark all items in cycle as failed
            for item_id in deadlock_info.items_involved:
                if item_id in batch.items:
                    batch.items[item_id].status = "failed"
                    batch.items[item_id].error = "Aborted due to deadlock resolution"

        elif strategy == DeadlockResolution.ABORT_YOUNGEST:
            # Find and abort the youngest item in the cycle
            youngest = None
            youngest_time = float("inf")
            for item_id in deadlock_info.items_involved:
                if item_id in batch.items:
                    item = batch.items[item_id]
                    if item.created_at > youngest_time:
                        youngest_time = item.created_at
                        youngest = item_id

            if youngest and youngest in batch.items:
                batch.items[youngest].status = "failed"
                batch.items[youngest].error = "Aborted due to deadlock (youngest)"

        elif strategy == DeadlockResolution.ABORT_LOWEST_PRIORITY:
            # Find and abort the lowest priority item
            lowest = None
            lowest_priority = float("inf")
            for item_id in deadlock_info.items_involved:
                if item_id in batch.items:
                    item = batch.items[item_id]
                    if item.priority.value < lowest_priority:
                        lowest_priority = item.priority.value
                        lowest = item_id

            if lowest and lowest in batch.items:
                batch.items[lowest].status = "failed"
                batch.items[lowest].error = "Aborted due to deadlock (lowest priority)"

        elif strategy == DeadlockResolution.SEQUENTIAL_FALLBACK:
            # Convert to sequential execution by removing all but one dependency
            for item_id in deadlock_info.items_involved:
                if item_id in batch.items:
                    item = batch.items[item_id]
                    if len(item.dependencies) > 1:
                        # Keep only the first dependency
                        item.dependencies = item.dependencies[:1]

        # Update batch in Redis
        redis_client = self._get_redis()
        redis_client.hset(self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict()))
        self._local_batches[batch_id] = batch

        return True

    def validate_batch(self, batch_id: str) -> tuple[bool, list[str]]:
        """Validate a batch before execution.

        Args:
            batch_id: ID of the batch

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return False, ["Batch not found"]

        errors = []

        # Check for empty batch
        if not batch.items:
            errors.append("Batch has no items")

        # Check for deadlock
        deadlock = self.detect_deadlock(batch_id)
        if deadlock:
            errors.append(f"Deadlock detected: {' -> '.join(deadlock.cycle)}")

        # Check for scope conflicts
        scope_registry = self._get_scope_registry()
        for item_id, item in batch.items.items():
            conflicts = scope_registry.check_conflicts(
                item.scope_globs, item.story_id, "batch-validator"
            )
            for conflict in conflicts:
                if conflict.story_id != item.story_id:
                    errors.append(
                        f"Item {item_id} has scope conflict with "
                        f"{conflict.story_id}/{conflict.agent}: {conflict.my_scope}"
                    )

        # Check for invalid dependencies
        for item_id, item in batch.items.items():
            for dep_id in item.dependencies:
                if dep_id not in batch.items:
                    errors.append(f"Item {item_id} has unknown dependency: {dep_id}")

        return len(errors) == 0, errors

    def start_batch(self, batch_id: str) -> bool:
        """Start executing a batch.

        Args:
            batch_id: ID of the batch

        Returns:
            True if batch was started, False otherwise
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return False

        # Validate first
        is_valid, errors = self.validate_batch(batch_id)
        if not is_valid:
            return False

        batch.status = BatchStatus.RUNNING
        batch.started_at = time.time()

        # Update in Redis
        redis_client = self._get_redis()
        redis_client.hset(self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict()))
        self._local_batches[batch_id] = batch

        return True

    def execute_batch_step(self, batch_id: str) -> dict[str, Any]:
        """Execute one step of a batch (assign ready items to agents).

        Args:
            batch_id: ID of the batch

        Returns:
            Dictionary with execution results
        """
        batch = self.get_batch(batch_id)
        if not batch or batch.status != BatchStatus.RUNNING:
            return {"success": False, "error": "Batch not running"}

        agent_coordinator = self._get_agent_coordinator()
        scope_registry = self._get_scope_registry()

        results = {
            "assigned": [],
            "failed": [],
            "skipped": [],
        }

        # Get ready items
        ready_items = batch.get_ready_items()
        active_count = len(batch.get_active_items())
        available_slots = batch.max_parallel - active_count

        for item in ready_items[:available_slots]:
            # Reserve scopes
            success, conflicts = scope_registry.reserve_scopes(
                item.scope_globs, item.story_id, f"batch-{batch_id}"
            )
            if not success:
                results["skipped"].append(
                    {
                        "item_id": item.item_id,
                        "reason": "scope_conflict",
                        "conflicts": [c.to_dict() for c in conflicts],
                    }
                )
                continue

            # Find available agent
            available_agents = agent_coordinator.get_available_agents()
            if not available_agents:
                # Release scopes and skip
                scope_registry.release_scopes(item.story_id, f"batch-{batch_id}")
                results["skipped"].append(
                    {"item_id": item.item_id, "reason": "no_available_agents"}
                )
                continue

            # Assign to first available agent
            agent_id = list(available_agents.keys())[0]

            # Submit work to agent coordinator
            work = agent_coordinator.submit_work(
                story_id=item.story_id,
                scope_globs=item.scope_globs,
                description=item.description,
                priority=item.priority,
                dependencies=item.dependencies,
            )

            # Assign to agent
            if agent_coordinator.assign_work(work.work_id, agent_id):
                item.agent_id = agent_id
                item.status = "in_progress"
                item.started_at = time.time()
                results["assigned"].append(
                    {"item_id": item.item_id, "agent_id": agent_id}
                )
            else:
                scope_registry.release_scopes(item.story_id, f"batch-{batch_id}")
                results["failed"].append(
                    {"item_id": item.item_id, "reason": "assignment_failed"}
                )

        # Update batch in Redis
        redis_client = self._get_redis()
        redis_client.hset(self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict()))
        self._local_batches[batch_id] = batch

        return results

    def update_batch_status(self, batch_id: str) -> BatchStatus:
        """Update the status of a batch based on item statuses.

        Args:
            batch_id: ID of the batch

        Returns:
            Updated batch status
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return BatchStatus.FAILED

        if batch.is_complete():
            batch.completed_at = time.time()
            failed_count = len(batch.get_failed_items())
            completed_count = len(batch.get_completed_items())

            if failed_count == 0:
                batch.status = BatchStatus.COMPLETED
            elif completed_count == 0:
                batch.status = BatchStatus.FAILED
            else:
                batch.status = BatchStatus.PARTIAL

            # Update in Redis
            redis_client = self._get_redis()
            redis_client.hset(
                self.REDIS_BATCH_HASH, batch_id, json.dumps(batch.to_dict())
            )
            self._local_batches[batch_id] = batch

        return batch.status

    def get_batch_summary(self, batch_id: str) -> dict[str, Any] | None:
        """Get a summary of batch execution status.

        Args:
            batch_id: ID of the batch

        Returns:
            Summary dictionary or None if batch not found
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return None

        return {
            "batch_id": batch.batch_id,
            "description": batch.description,
            "status": batch.status.value,
            "total_items": len(batch.items),
            "pending": len([i for i in batch.items.values() if i.status == "pending"]),
            "in_progress": len(
                [i for i in batch.items.values() if i.status == "in_progress"]
            ),
            "completed": len(batch.get_completed_items()),
            "failed": len(batch.get_failed_items()),
            "progress_percentage": (
                len(batch.get_completed_items()) / len(batch.items) * 100
                if batch.items
                else 0
            ),
        }


# Singleton instance for module-level access
_coordinator_instance: ParallelExecutionCoordinator | None = None


def get_parallel_execution_coordinator(
    redis_client=None,
    scope_registry: ScopeRegistry | None = None,
    agent_coordinator: AgentCoordinator | None = None,
) -> ParallelExecutionCoordinator:
    """Get or create the global parallel execution coordinator instance."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = ParallelExecutionCoordinator(
            redis_client, scope_registry, agent_coordinator
        )
    return _coordinator_instance
