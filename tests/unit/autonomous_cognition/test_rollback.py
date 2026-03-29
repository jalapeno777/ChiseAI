"""Tests for rollback.py - snapshot creation, restore, and compensation."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.autonomous_cognition.rollback import (
    ActionSnapshot,
    RollbackLogEntry,
    RollbackManager,
)

# --- Fixtures ---


@pytest.fixture
def mock_action():
    """Create a mock action object for testing."""
    action = MagicMock()
    action.action_type = "test_action"
    action.name = "TestAction"
    action.payload = {"key": "value", "count": 42}
    return action


@pytest.fixture
def rollback_manager():
    """Create a RollbackManager instance for testing."""
    return RollbackManager(enable_audit_logging=True, max_snapshots=100)


@pytest.fixture
def snapshot(rollback_manager, mock_action) -> ActionSnapshot:
    """Create a pre-existing snapshot for testing."""
    return asyncio.get_event_loop().run_until_complete(
        rollback_manager.create_snapshot(
            action=mock_action,
            action_id="test-action-001",
            state={"initial": "state"},
            compensation_action={"type": "undo", "data": "test"},
        )
    )


# --- Snapshot Creation Tests ---


class TestSnapshotCreation:
    """Tests for RollbackManager.create_snapshot."""

    @pytest.mark.asyncio
    async def test_create_snapshot_generates_unique_id(
        self, rollback_manager, mock_action
    ):
        """Snapshot should have a UUID that's different from others."""
        snap1 = await rollback_manager.create_snapshot(mock_action, "action-1")
        snap2 = await rollback_manager.create_snapshot(mock_action, "action-2")

        assert snap1.snapshot_id != snap2.snapshot_id
        assert len(snap1.snapshot_id) == 36  # UUID4 format

    @pytest.mark.asyncio
    async def test_create_snapshot_captures_action_metadata(
        self, rollback_manager, mock_action
    ):
        """Snapshot should capture action type, name, and action_id."""
        snap = await rollback_manager.create_snapshot(
            action=mock_action,
            action_id="my-action-id",
            state={"custom": "data"},
        )

        assert snap.action_id == "my-action-id"
        assert snap.action_type == "test_action"
        assert snap.action_name == "TestAction"
        assert snap.state["custom"] == "data"

    @pytest.mark.asyncio
    async def test_create_snapshot_extracts_payload_from_action(
        self, rollback_manager, mock_action
    ):
        """Snapshot should merge action.payload into state if available."""
        snap = await rollback_manager.create_snapshot(
            action=mock_action,
            action_id="payload-test",
        )

        # Payload from mock_action: {"key": "value", "count": 42}
        assert snap.state["key"] == "value"
        assert snap.state["count"] == 42

    @pytest.mark.asyncio
    async def test_create_snapshot_stores_compensation_action(
        self, rollback_manager, mock_action
    ):
        """Snapshot should store compensation action for later execution."""
        compensation = {"type": "reverse", "steps": ["step1", "step2"]}
        snap = await rollback_manager.create_snapshot(
            action=mock_action,
            action_id="comp-test",
            compensation_action=compensation,
        )

        assert snap.compensation_action == compensation
        assert snap.compensation_action["type"] == "reverse"

    @pytest.mark.asyncio
    async def test_create_snapshot_registers_in_chain(
        self, rollback_manager, mock_action
    ):
        """Multiple snapshots for same action_id should be chained."""
        snap1 = await rollback_manager.create_snapshot(mock_action, "chained-action")
        snap2 = await rollback_manager.create_snapshot(mock_action, "chained-action")

        chain = rollback_manager.get_rollback_chain("chained-action")
        assert len(chain) == 2
        assert chain[0].snapshot_id == snap1.snapshot_id
        assert chain[1].snapshot_id == snap2.snapshot_id


# --- Rollback Execution Tests ---


class TestRollbackExecution:
    """Tests for RollbackManager.rollback."""

    @pytest.mark.asyncio
    async def test_rollback_returns_success_result(self, rollback_manager, snapshot):
        """Successful rollback should return success=True."""
        result = await rollback_manager.rollback(snapshot)

        assert result.success is True
        assert result.snapshot_id == snapshot.snapshot_id
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_rollback_by_snapshot_id_string(self, rollback_manager, snapshot):
        """Rollback should accept snapshot_id string in addition to object."""
        result = await rollback_manager.rollback(snapshot.snapshot_id)

        assert result.success is True
        assert result.snapshot_id == snapshot.snapshot_id

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_snapshot_returns_error(self, rollback_manager):
        """Rollback with unknown snapshot_id should fail gracefully."""
        result = await rollback_manager.rollback("nonexistent-id")

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_rollback_logs_to_audit(self, rollback_manager, snapshot):
        """Rollback should create an audit log entry."""
        await rollback_manager.rollback(snapshot)

        logs = rollback_manager.get_rollback_logs(snapshot.action_id)
        assert len(logs) == 1
        assert logs[0].success is True
        assert logs[0].snapshot_id == snapshot.snapshot_id

    @pytest.mark.asyncio
    async def test_rollback_chain_executes_in_reverse_order(
        self, rollback_manager, mock_action
    ):
        """rollback_chain should execute in LIFO order."""
        snap1 = await rollback_manager.create_snapshot(
            mock_action, "chain-test", state={"step": 1}
        )
        snap2 = await rollback_manager.create_snapshot(
            mock_action, "chain-test", state={"step": 2}
        )
        snap3 = await rollback_manager.create_snapshot(
            mock_action, "chain-test", state={"step": 3}
        )

        results = await rollback_manager.rollback_chain("chain-test")

        assert len(results) == 3
        # Should execute in reverse order of creation
        assert results[0].snapshot_id == snap3.snapshot_id
        assert results[1].snapshot_id == snap2.snapshot_id
        assert results[2].snapshot_id == snap1.snapshot_id

    @pytest.mark.asyncio
    async def test_rollback_chain_stops_on_failure(self, rollback_manager, mock_action):
        """Rollback chain should stop when a rollback fails."""
        snap1 = await rollback_manager.create_snapshot(mock_action, "fail-chain")
        snap2 = await rollback_manager.create_snapshot(mock_action, "fail-chain")

        # Register a handler that raises an exception
        async def failing_handler(state):
            raise RuntimeError("Intentional rollback failure")

        rollback_manager.register_compensation_handler("test_action", failing_handler)

        results = await rollback_manager.rollback_chain("fail-chain")

        # Chain should stop after first failure
        assert len(results) >= 1
        # At least one should have failed
        assert not any(r.success for r in results)


# --- Compensation Action Tests ---


class TestCompensationActions:
    """Tests for compensation action execution."""

    @pytest.mark.asyncio
    async def test_compensation_handler_sync_is_called(
        self, rollback_manager, snapshot
    ):
        """Sync compensation handlers should be invoked on rollback."""
        handler_called = []

        def sync_handler(state: dict[str, Any]) -> None:
            handler_called.append(state)

        rollback_manager.register_compensation_handler("test_action", sync_handler)
        await rollback_manager.rollback(snapshot)

        assert len(handler_called) == 1
        assert handler_called[0] == snapshot.state

    @pytest.mark.asyncio
    async def test_compensation_handler_async_is_called(
        self, rollback_manager, snapshot
    ):
        """Async compensation handlers should be awaited on rollback."""
        handler_called = []

        async def async_handler(state: dict[str, Any]) -> None:
            handler_called.append(state)

        rollback_manager.register_compensation_handler("test_action", async_handler)
        await rollback_manager.rollback(snapshot)

        assert len(handler_called) == 1
        assert handler_called[0] == snapshot.state

    @pytest.mark.asyncio
    async def test_compensation_handler_unregister(self, rollback_manager, snapshot):
        """Unregistering a handler should prevent it from being called."""
        handler = AsyncMock()
        rollback_manager.register_compensation_handler("test_action", handler)
        rollback_manager.unregister_compensation_handler("test_action")

        await rollback_manager.rollback(snapshot)

        handler.assert_not_called()


# --- Snapshot Cleanup Tests ---


class TestSnapshotCleanup:
    """Tests for snapshot expiration and cleanup."""

    @pytest.mark.asyncio
    async def test_auto_cleanup_when_max_snapshots_exceeded(self, mock_action):
        """Manager should auto-cleanup oldest snapshots when limit reached."""
        manager = RollbackManager(max_snapshots=5, auto_cleanup=True)

        # Create 10 snapshots
        for i in range(10):
            await manager.create_snapshot(mock_action, f"cleanup-{i}")

        # Should only have 5 left
        assert manager.get_stats()["total_snapshots"] == 5

    @pytest.mark.asyncio
    async def test_no_cleanup_when_auto_cleanup_disabled(self, mock_action):
        """Manager should not auto-cleanup when disabled."""
        manager = RollbackManager(max_snapshots=5, auto_cleanup=False)

        for i in range(10):
            await manager.create_snapshot(mock_action, f"nocleanup-{i}")

        assert manager.get_stats()["total_snapshots"] == 10

    @pytest.mark.asyncio
    async def test_clear_snapshots_for_specific_action(
        self, rollback_manager, mock_action
    ):
        """clear_snapshots with action_id should only clear that action."""
        await rollback_manager.create_snapshot(mock_action, "keep-me")
        await rollback_manager.create_snapshot(mock_action, "clear-me")

        cleared = rollback_manager.clear_snapshots("clear-me")

        assert cleared == 1
        assert len(rollback_manager.get_rollback_chain("keep-me")) == 1
        assert len(rollback_manager.get_rollback_chain("clear-me")) == 0

    @pytest.mark.asyncio
    async def test_clear_snapshots_all_when_no_action_id(
        self, rollback_manager, mock_action
    ):
        """clear_snapshots without action_id should clear all."""
        await rollback_manager.create_snapshot(mock_action, "action-1")
        await rollback_manager.create_snapshot(mock_action, "action-2")

        cleared = rollback_manager.clear_snapshots()

        assert cleared == 2
        assert rollback_manager.get_stats()["total_snapshots"] == 0


# --- Concurrent Snapshot Handling Tests ---


class TestConcurrentSnapshotHandling:
    """Tests for concurrent access to snapshot management."""

    @pytest.mark.asyncio
    async def test_concurrent_snapshot_creation(self, rollback_manager, mock_action):
        """Multiple concurrent snapshot creations should all succeed."""
        tasks = [
            rollback_manager.create_snapshot(mock_action, f"concurrent-{i}")
            for i in range(20)
        ]
        snapshots = await asyncio.gather(*tasks)

        assert len(snapshots) == 20
        # All should have unique IDs
        ids = [s.snapshot_id for s in snapshots]
        assert len(set(ids)) == 20

    @pytest.mark.asyncio
    async def test_concurrent_rollbacks_on_different_snapshots(
        self, rollback_manager, mock_action
    ):
        """Concurrent rollbacks on different snapshots should all succeed."""
        snap1 = await rollback_manager.create_snapshot(
            mock_action, "concurrent-rollback-1"
        )
        snap2 = await rollback_manager.create_snapshot(
            mock_action, "concurrent-rollback-2"
        )

        results = await asyncio.gather(
            rollback_manager.rollback(snap1),
            rollback_manager.rollback(snap2),
        )

        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_chain_rollbacks_independent(
        self, rollback_manager, mock_action
    ):
        """Concurrent rollback_chain calls for different actions should be independent."""
        await rollback_manager.create_snapshot(mock_action, "chain-a")
        await rollback_manager.create_snapshot(mock_action, "chain-a")

        await rollback_manager.create_snapshot(mock_action, "chain-b")
        await rollback_manager.create_snapshot(mock_action, "chain-b")

        results_a, results_b = await asyncio.gather(
            rollback_manager.rollback_chain("chain-a"),
            rollback_manager.rollback_chain("chain-b"),
        )

        assert len(results_a) == 2
        assert len(results_b) == 2


# --- Stats and Query Tests ---


class TestStatsAndQueries:
    """Tests for stats and query methods."""

    def test_get_stats_empty_manager(self, rollback_manager):
        """Empty manager should return correct initial stats."""
        stats = rollback_manager.get_stats()

        assert stats["total_snapshots"] == 0
        assert stats["total_rollback_chains"] == 0
        assert stats["total_rollbacks"] == 0
        assert stats["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_get_stats_after_operations(self, rollback_manager, snapshot):
        """Stats should reflect actual operation counts."""
        await rollback_manager.rollback(snapshot)
        await rollback_manager.rollback(snapshot)

        stats = rollback_manager.get_stats()
        assert stats["total_rollbacks"] == 2
        assert stats["successful_rollbacks"] == 2
        assert stats["failed_rollbacks"] == 0
        assert stats["success_rate"] == 1.0

    def test_get_snapshot_returns_none_for_unknown_id(self, rollback_manager):
        """get_snapshot should return None for nonexistent ID."""
        result = rollback_manager.get_snapshot("does-not-exist")
        assert result is None

    def test_get_rollback_logs_with_filters(self, rollback_manager, snapshot):
        """get_rollback_logs should support filtering."""
        # Create a failed rollback
        rollback_manager._rollback_logs.append(
            RollbackLogEntry(
                timestamp=time.time(),
                snapshot_id="fake-id",
                action_id="filtered-action",
                success=False,
                execution_time_ms=10.0,
                error="test error",
            )
        )

        logs = rollback_manager.get_rollback_logs(action_id="filtered-action")
        assert len(logs) == 1

        success_only = rollback_manager.get_rollback_logs(success_only=True)
        assert len(success_only) == 0
