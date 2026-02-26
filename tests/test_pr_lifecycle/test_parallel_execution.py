"""Tests for parallel execution support.

This module tests the scope registry, agent coordinator, and parallel execution
coordinator functionality for the 10-agent parallel support system.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from scripts.pr_lifecycle.agent_coordinator import (
    AgentCoordinator,
    AgentInfo,
    AgentPriority,
    AgentStatus,
    WorkAssignment,
)
from scripts.pr_lifecycle.parallel_execution import (
    BatchItem,
    BatchStatus,
    DeadlockResolution,
    ExecutionBatch,
    ParallelExecutionCoordinator,
)
from scripts.pr_lifecycle.scope_registry import (
    ConflictType,
    ScopeConflict,
    ScopeRegistry,
    ScopeReservation,
)


class TestScopeRegistry:
    """Tests for the ScopeRegistry class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hgetall.return_value = {}
        mock.hget.return_value = None
        mock.hset.return_value = 1
        mock.hdel.return_value = 1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def registry(self, mock_redis):
        """Create a ScopeRegistry with mock Redis."""
        return ScopeRegistry(mock_redis)

    def test_path_slug_conversion(self, registry):
        """Test path to slug conversion."""
        assert registry._path_slug("src/test/") == "src:test"
        assert registry._path_slug("./src/test") == "src:test"
        assert registry._path_slug("src/test/file.py") == "src:test:file.py"

    def test_paths_overlap_exact(self, registry):
        """Test exact path overlap detection."""
        assert registry._paths_overlap("src/test", "src/test") is True

    def test_paths_overlap_subpath(self, registry):
        """Test subpath overlap detection."""
        assert registry._paths_overlap("src/test/file.py", "src/test") is True
        assert registry._paths_overlap("src/test", "src/test/file.py") is True

    def test_paths_overlap_no_overlap(self, registry):
        """Test non-overlapping paths."""
        assert registry._paths_overlap("src/test", "src/other") is False
        assert registry._paths_overlap("src/a", "dst/a") is False

    def test_paths_overlap_glob(self, registry):
        """Test glob pattern overlap detection."""
        assert registry._paths_overlap("src/*.py", "src/test.py") is True
        assert registry._paths_overlap("src/test.py", "src/*.py") is True

    def test_determine_conflict_type_exact(self, registry):
        """Test exact conflict type detection."""
        conflict = registry._determine_conflict_type("src/test", "src/test")
        assert conflict == ConflictType.EXACT_OVERLAP

    def test_determine_conflict_type_subscope(self, registry):
        """Test subscope conflict type detection."""
        conflict = registry._determine_conflict_type("src/test/file.py", "src/test")
        assert conflict == ConflictType.SUBSCOPE

    def test_determine_conflict_type_superscope(self, registry):
        """Test superscope conflict type detection."""
        conflict = registry._determine_conflict_type("src/test", "src/test/file.py")
        assert conflict == ConflictType.SUPERSCOPE

    def test_check_conflicts_no_conflict(self, registry, mock_redis):
        """Test conflict detection with no conflicts."""
        mock_redis.hgetall.return_value = {}
        conflicts = registry.check_conflicts(["src/test"], "ST-001", "agent-1")
        assert len(conflicts) == 0

    def test_check_conflicts_with_conflict(self, registry, mock_redis):
        """Test conflict detection with conflicts."""
        reservation = ScopeReservation(
            story_id="ST-002",
            agent="agent-2",
            scopes=["src/test"],
            reserved_at=time.time(),
            expires_at=time.time() + 3600,
        )
        mock_redis.hgetall.return_value = {
            "ST-002:agent-2": json.dumps(reservation.to_dict())
        }

        conflicts = registry.check_conflicts(["src/test"], "ST-001", "agent-1")
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.EXACT_OVERLAP
        assert conflicts[0].story_id == "ST-002"

    def test_reserve_scopes_success(self, registry, mock_redis):
        """Test successful scope reservation."""
        mock_redis.hgetall.return_value = {}
        success, conflicts = registry.reserve_scopes(["src/test"], "ST-001", "agent-1")
        assert success is True
        assert len(conflicts) == 0
        mock_redis.hset.assert_called_once()

    def test_reserve_scopes_conflict(self, registry, mock_redis):
        """Test scope reservation with conflict."""
        reservation = ScopeReservation(
            story_id="ST-002",
            agent="agent-2",
            scopes=["src/test"],
            reserved_at=time.time(),
            expires_at=time.time() + 3600,
        )
        mock_redis.hgetall.return_value = {
            "ST-002:agent-2": json.dumps(reservation.to_dict())
        }

        success, conflicts = registry.reserve_scopes(["src/test"], "ST-001", "agent-1")
        assert success is False
        assert len(conflicts) == 1

    def test_release_scopes(self, registry, mock_redis):
        """Test scope release."""
        result = registry.release_scopes("ST-001", "agent-1")
        assert result is True
        mock_redis.hdel.assert_called_once()

    def test_validate_scope_access_granted(self, registry, mock_redis):
        """Test scope access validation - access granted."""
        reservation = ScopeReservation(
            story_id="ST-001",
            agent="agent-1",
            scopes=["src/test"],
            reserved_at=time.time(),
            expires_at=time.time() + 3600,
        )
        mock_redis.hget.return_value = json.dumps(reservation.to_dict())

        has_access, reason = registry.validate_scope_access(
            "src/test/file.py", "ST-001", "agent-1"
        )
        assert has_access is True
        assert "granted" in reason.lower()

    def test_validate_scope_access_denied(self, registry, mock_redis):
        """Test scope access validation - access denied."""
        mock_redis.hget.return_value = None

        has_access, reason = registry.validate_scope_access(
            "src/test/file.py", "ST-001", "agent-1"
        )
        assert has_access is False
        assert "no scope reservation" in reason.lower()


class TestAgentCoordinator:
    """Tests for the AgentCoordinator class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hgetall.return_value = {}
        mock.hget.return_value = None
        mock.hset.return_value = 1
        mock.hdel.return_value = 1
        mock.zadd.return_value = 1
        mock.zrevrange.return_value = []
        mock.zrem.return_value = 1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def coordinator(self, mock_redis):
        """Create an AgentCoordinator with mock Redis."""
        return AgentCoordinator(mock_redis)

    def test_register_agent(self, coordinator, mock_redis):
        """Test agent registration."""
        agent = coordinator.register_agent(
            story_id="ST-001",
            agent_type="worker",
            capabilities=["python", "git"],
        )
        assert agent.story_id == "ST-001"
        assert agent.agent_type == "worker"
        assert agent.status == AgentStatus.IDLE
        assert "python" in agent.capabilities
        mock_redis.hset.assert_called_once()

    def test_register_agent_max_reached(self, coordinator, mock_redis):
        """Test agent registration when max agents reached."""
        # Create MAX_CONCURRENT_AGENTS agents
        agents = []
        for i in range(coordinator.MAX_CONCURRENT_AGENTS):
            agent_data = AgentInfo(
                agent_id=f"agent-{i}",
                story_id=f"ST-{i}",
                agent_type="worker",
                status=AgentStatus.IDLE,
                registered_at=time.time(),
                last_heartbeat=time.time(),
            )
            agents.append((f"agent-{i}", json.dumps(agent_data.to_dict())))

        mock_redis.hgetall.return_value = dict(agents)

        with pytest.raises(RuntimeError, match="Maximum concurrent agents"):
            coordinator.register_agent(story_id="ST-NEW", agent_type="worker")

    def test_heartbeat(self, coordinator, mock_redis):
        """Test agent heartbeat."""
        agent = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.IDLE,
            registered_at=time.time(),
            last_heartbeat=time.time() - 100,
        )
        mock_redis.hget.return_value = json.dumps(agent.to_dict())

        result = coordinator.heartbeat("agent-1", AgentStatus.BUSY)
        assert result is True
        mock_redis.hset.assert_called_once()

    def test_get_available_agents(self, coordinator, mock_redis):
        """Test getting available agents."""
        agent1 = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.IDLE,
            registered_at=time.time(),
            last_heartbeat=time.time(),
        )
        agent2 = AgentInfo(
            agent_id="agent-2",
            story_id="ST-002",
            agent_type="worker",
            status=AgentStatus.BUSY,
            registered_at=time.time(),
            last_heartbeat=time.time(),
            current_work={"work_id": "work-1"},
        )
        mock_redis.hgetall.return_value = {
            "agent-1": json.dumps(agent1.to_dict()),
            "agent-2": json.dumps(agent2.to_dict()),
        }

        available = coordinator.get_available_agents()
        assert len(available) == 1
        assert "agent-1" in available

    def test_submit_work(self, coordinator, mock_redis):
        """Test work submission."""
        work = coordinator.submit_work(
            story_id="ST-001",
            scope_globs=["src/test"],
            description="Test work",
            priority=AgentPriority.HIGH,
        )
        assert work.story_id == "ST-001"
        assert work.priority == AgentPriority.HIGH
        assert work.status == "pending"
        mock_redis.hset.assert_called_once()
        mock_redis.zadd.assert_called_once()

    def test_assign_work(self, coordinator, mock_redis):
        """Test work assignment."""
        work = WorkAssignment(
            work_id="work-1",
            story_id="ST-001",
            agent_id=None,
            priority=AgentPriority.NORMAL,
            scope_globs=["src/test"],
            description="Test work",
        )
        agent = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.IDLE,
            registered_at=time.time(),
            last_heartbeat=time.time(),
        )
        mock_redis.hget.side_effect = [
            json.dumps(work.to_dict()),  # First call for work
            json.dumps(agent.to_dict()),  # Second call for agent
        ]

        result = coordinator.assign_work("work-1", "agent-1")
        assert result is True

    def test_complete_work(self, coordinator, mock_redis):
        """Test work completion."""
        work = WorkAssignment(
            work_id="work-1",
            story_id="ST-001",
            agent_id="agent-1",
            priority=AgentPriority.NORMAL,
            scope_globs=["src/test"],
            description="Test work",
            status="in_progress",
        )
        agent = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.BUSY,
            registered_at=time.time(),
            last_heartbeat=time.time(),
            current_work=work.to_dict(),
        )
        mock_redis.hget.side_effect = [
            json.dumps(work.to_dict()),  # First call for work
            json.dumps(agent.to_dict()),  # Second call for agent
        ]

        result = coordinator.complete_work("work-1", result={"status": "ok"})
        assert result is True

    def test_check_for_failures(self, coordinator, mock_redis):
        """Test failure detection."""
        agent = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.BUSY,
            registered_at=time.time(),
            last_heartbeat=time.time() - 500,  # Old heartbeat
        )
        mock_redis.hgetall.return_value = {"agent-1": json.dumps(agent.to_dict())}

        failed = coordinator.check_for_failures()
        assert len(failed) == 1
        assert failed[0].agent_id == "agent-1"
        assert failed[0].status == AgentStatus.FAILED


class TestParallelExecutionCoordinator:
    """Tests for the ParallelExecutionCoordinator class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hgetall.return_value = {}
        mock.hget.return_value = None
        mock.hset.return_value = 1
        mock.hdel.return_value = 1
        mock.lpush.return_value = 1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def coordinator(self, mock_redis):
        """Create a ParallelExecutionCoordinator with mock Redis."""
        return ParallelExecutionCoordinator(mock_redis)

    def test_create_batch(self, coordinator, mock_redis):
        """Test batch creation."""
        batch = coordinator.create_batch(
            description="Test batch",
            max_parallel=5,
            deadlock_resolution=DeadlockResolution.ABORT_ALL,
        )
        assert batch.description == "Test batch"
        assert batch.max_parallel == 5
        assert batch.deadlock_resolution == DeadlockResolution.ABORT_ALL
        mock_redis.hset.assert_called_once()

    def test_add_item_to_batch(self, coordinator, mock_redis):
        """Test adding item to batch."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        item = coordinator.add_item_to_batch(
            batch_id="batch-1",
            story_id="ST-001",
            scope_globs=["src/test"],
            description="Test item",
            priority=AgentPriority.HIGH,
        )
        assert item is not None
        assert item.story_id == "ST-001"
        assert item.priority == AgentPriority.HIGH

    def test_detect_deadlock_no_cycle(self, coordinator, mock_redis):
        """Test deadlock detection with no cycle."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    dependencies=["item-1"],
                ),
            },
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        deadlock = coordinator.detect_deadlock("batch-1")
        assert deadlock is None

    def test_detect_deadlock_with_cycle(self, coordinator, mock_redis):
        """Test deadlock detection with cycle."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    dependencies=["item-2"],
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    dependencies=["item-1"],
                ),
            },
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        deadlock = coordinator.detect_deadlock("batch-1")
        assert deadlock is not None
        assert "item-1" in deadlock.items_involved
        assert "item-2" in deadlock.items_involved

    def test_resolve_deadlock_abort_youngest(self, coordinator, mock_redis):
        """Test deadlock resolution - abort youngest."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    dependencies=["item-2"],
                    created_at=time.time() - 100,
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    dependencies=["item-1"],
                    created_at=time.time(),
                ),
            },
            deadlock_resolution=DeadlockResolution.ABORT_YOUNGEST,
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        result = coordinator.resolve_deadlock("batch-1")
        assert result is True

    def test_validate_batch_valid(self, coordinator, mock_redis):
        """Test batch validation - valid batch."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                ),
            },
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        is_valid, errors = coordinator.validate_batch("batch-1")
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_batch_empty(self, coordinator, mock_redis):
        """Test batch validation - empty batch."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={},
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        is_valid, errors = coordinator.validate_batch("batch-1")
        assert is_valid is False
        assert any("no items" in e.lower() for e in errors)

    def test_validate_batch_deadlock(self, coordinator, mock_redis):
        """Test batch validation - deadlock detected."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    dependencies=["item-2"],
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    dependencies=["item-1"],
                ),
            },
        )
        mock_redis.hget.return_value = json.dumps(batch.to_dict())

        is_valid, errors = coordinator.validate_batch("batch-1")
        assert is_valid is False
        assert any("deadlock" in e.lower() for e in errors)

    def test_batch_get_ready_items(self):
        """Test getting ready items from batch."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    status="pending",
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    status="pending",
                    dependencies=["item-1"],
                ),
                "item-3": BatchItem(
                    item_id="item-3",
                    story_id="ST-003",
                    scope_globs=["src/c"],
                    description="Item 3",
                    status="completed",
                ),
                "item-4": BatchItem(
                    item_id="item-4",
                    story_id="ST-004",
                    scope_globs=["src/d"],
                    description="Item 4",
                    status="pending",
                    dependencies=["item-3"],
                ),
            },
        )

        ready = batch.get_ready_items()
        assert len(ready) == 2
        ready_ids = {item.item_id for item in ready}
        assert "item-1" in ready_ids
        assert "item-4" in ready_ids

    def test_batch_is_complete(self):
        """Test batch completion check."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    status="completed",
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    status="failed",
                ),
            },
        )

        assert batch.is_complete() is True

    def test_batch_is_not_complete(self):
        """Test batch not complete check."""
        batch = ExecutionBatch(
            batch_id="batch-1",
            description="Test batch",
            items={
                "item-1": BatchItem(
                    item_id="item-1",
                    story_id="ST-001",
                    scope_globs=["src/a"],
                    description="Item 1",
                    status="completed",
                ),
                "item-2": BatchItem(
                    item_id="item-2",
                    story_id="ST-002",
                    scope_globs=["src/b"],
                    description="Item 2",
                    status="pending",
                ),
            },
        )

        assert batch.is_complete() is False


class TestIntegration:
    """Integration tests for the parallel execution system."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.hgetall.return_value = {}
        mock.hget.return_value = None
        mock.hset.return_value = 1
        mock.hdel.return_value = 1
        mock.zadd.return_value = 1
        mock.zrevrange.return_value = []
        mock.zrem.return_value = 1
        mock.lpush.return_value = 1
        mock.expire.return_value = True
        return mock

    def test_full_workflow(self, mock_redis):
        """Test a full parallel execution workflow."""
        # Create coordinators
        scope_registry = ScopeRegistry(mock_redis)
        agent_coordinator = AgentCoordinator(mock_redis)
        parallel_coordinator = ParallelExecutionCoordinator(
            mock_redis, scope_registry, agent_coordinator
        )

        # Create batch
        batch = parallel_coordinator.create_batch(
            description="Integration test batch",
            max_parallel=3,
        )
        assert batch.batch_id is not None

        # Add items
        item1 = parallel_coordinator.add_item_to_batch(
            batch_id=batch.batch_id,
            story_id="ST-001",
            scope_globs=["src/module1/"],
            description="Work on module 1",
            priority=AgentPriority.HIGH,
        )
        item2 = parallel_coordinator.add_item_to_batch(
            batch_id=batch.batch_id,
            story_id="ST-002",
            scope_globs=["src/module2/"],
            description="Work on module 2",
            priority=AgentPriority.NORMAL,
        )
        assert item1 is not None
        assert item2 is not None

        # Validate batch
        is_valid, errors = parallel_coordinator.validate_batch(batch.batch_id)
        assert is_valid is True

        # Start batch
        result = parallel_coordinator.start_batch(batch.batch_id)
        assert result is True

    def test_scope_conflict_prevention(self, mock_redis):
        """Test that scope conflicts are properly prevented."""
        scope_registry = ScopeRegistry(mock_redis)

        # First reservation should succeed
        success1, _ = scope_registry.reserve_scopes(["src/test/"], "ST-001", "agent-1")
        assert success1 is True

        # Second reservation with overlapping scope should fail
        mock_redis.hgetall.return_value = {
            "ST-001:agent-1": json.dumps(
                ScopeReservation(
                    story_id="ST-001",
                    agent="agent-1",
                    scopes=["src/test/"],
                    reserved_at=time.time(),
                    expires_at=time.time() + 3600,
                ).to_dict()
            )
        }
        success2, conflicts = scope_registry.reserve_scopes(
            ["src/test/file.py"], "ST-002", "agent-2"
        )
        assert success2 is False
        assert len(conflicts) > 0

    def test_agent_failure_detection(self, mock_redis):
        """Test agent failure detection."""
        agent_coordinator = AgentCoordinator(mock_redis)

        # Register agent with old heartbeat
        agent = AgentInfo(
            agent_id="agent-1",
            story_id="ST-001",
            agent_type="worker",
            status=AgentStatus.BUSY,
            registered_at=time.time(),
            last_heartbeat=time.time() - 500,  # Very old
        )
        mock_redis.hgetall.return_value = {"agent-1": json.dumps(agent.to_dict())}

        # Check for failures
        failed = agent_coordinator.check_for_failures()
        assert len(failed) == 1
        assert failed[0].status == AgentStatus.FAILED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
