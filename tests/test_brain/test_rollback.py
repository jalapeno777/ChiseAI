"""Tests for brain rollback module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from brain.rollback import (
    RollbackError,
    RollbackManager,
    RollbackResult,
    RollbackStatus,
    RollbackTimeoutError,
)


class TestRollbackResult:
    """Tests for RollbackResult class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
        )
        assert result.from_version == "1.1.0"
        assert result.to_version == "1.0.0"
        assert result.status == RollbackStatus.COMPLETED

    def test_duration_remaining(self) -> None:
        """Test duration remaining calculation."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            duration_seconds=100.0,
            target_duration_seconds=300.0,
        )
        assert result.duration_remaining_seconds == 200.0

    def test_duration_remaining_exceeded(self) -> None:
        """Test duration remaining when target exceeded."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            duration_seconds=400.0,
            target_duration_seconds=300.0,
        )
        assert result.duration_remaining_seconds == 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            duration_seconds=60.0,
            target_met=True,
            steps_completed=["step1", "step2"],
        )
        data = result.to_dict()
        assert data["from_version"] == "1.1.0"
        assert data["status"] == "completed"
        assert data["target_met"] is True
        assert data["steps_completed"] == ["step1", "step2"]

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "from_version": "1.1.0",
            "to_version": "1.0.0",
            "status": "completed",
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:01:00Z",
            "duration_seconds": 60.0,
            "target_duration_seconds": 300.0,
            "target_met": True,
            "steps_completed": ["step1", "step2"],
            "steps_failed": [],
        }
        result = RollbackResult.from_dict(data)
        assert result.from_version == "1.1.0"
        assert result.status == RollbackStatus.COMPLETED
        assert result.target_met is True


class TestRollbackManager:
    """Tests for RollbackManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for rollback storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_creation(self, temp_dir: str) -> None:
        """Test basic creation."""
        manager = RollbackManager(temp_dir)
        assert manager.target_duration_seconds == 300.0  # 5 minutes

    def test_custom_target_duration(self, temp_dir: str) -> None:
        """Test custom target duration."""
        manager = RollbackManager(temp_dir, target_duration_seconds=180.0)
        assert manager.target_duration_seconds == 180.0

    def test_rollback(self, temp_dir: str) -> None:
        """Test rollback operation."""
        manager = RollbackManager(temp_dir)
        result = manager.rollback("1.1.0", "1.0.0")

        assert result.from_version == "1.1.0"
        assert result.to_version == "1.0.0"
        assert result.status == RollbackStatus.COMPLETED
        assert result.duration_seconds > 0
        assert result.target_met is True  # Should complete within 5 minutes
        assert len(result.steps_completed) > 0

    def test_rollback_persistence(self, temp_dir: str) -> None:
        """Test that rollback is persisted."""
        manager1 = RollbackManager(temp_dir)
        manager1.rollback("1.1.0", "1.0.0")

        # Create new manager pointing to same directory
        manager2 = RollbackManager(temp_dir)
        history = manager2.list_rollbacks()

        assert len(history) == 1
        assert history[0].from_version == "1.1.0"

    def test_get_rollback_result(self, temp_dir: str) -> None:
        """Test retrieving rollback result."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")

        result = manager.get_rollback_result("1.1.0", "1.0.0")
        assert result is not None
        assert result.from_version == "1.1.0"
        assert result.to_version == "1.0.0"

    def test_get_rollback_result_not_found(self, temp_dir: str) -> None:
        """Test retrieving non-existent rollback."""
        manager = RollbackManager(temp_dir)
        result = manager.get_rollback_result("1.1.0", "1.0.0")
        assert result is None

    def test_can_rollback_to(self, temp_dir: str) -> None:
        """Test checking if rollback is possible."""
        manager = RollbackManager(temp_dir)
        can_rollback, reason = manager.can_rollback_to("1.0.0")

        assert can_rollback is True
        assert "1.0.0" in reason

    def test_get_previous_version(self, temp_dir: str) -> None:
        """Test getting previous version."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")

        prev = manager.get_previous_version("1.1.0")
        assert prev == "1.0.0"

    def test_get_previous_version_not_found(self, temp_dir: str) -> None:
        """Test getting previous version when not found."""
        manager = RollbackManager(temp_dir)
        prev = manager.get_previous_version("1.1.0")
        assert prev is None

    def test_list_rollbacks(self, temp_dir: str) -> None:
        """Test listing rollbacks."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")
        manager.rollback("1.2.0", "1.1.0")

        rollbacks = manager.list_rollbacks()
        assert len(rollbacks) == 2
        # Should be sorted by started_at descending
        assert rollbacks[0].from_version == "1.2.0"
        assert rollbacks[1].from_version == "1.1.0"

    def test_list_rollbacks_by_status(self, temp_dir: str) -> None:
        """Test listing rollbacks filtered by status."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")

        completed = manager.list_rollbacks(status=RollbackStatus.COMPLETED)
        assert len(completed) == 1

        failed = manager.list_rollbacks(status=RollbackStatus.FAILED)
        assert len(failed) == 0

    def test_get_rollback_statistics(self, temp_dir: str) -> None:
        """Test rollback statistics."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")

        stats = manager.get_rollback_statistics()
        assert stats["total_rollbacks"] == 1
        assert stats["successful_rollbacks"] == 1
        assert stats["failed_rollbacks"] == 0
        assert stats["target_met_percentage"] == 100.0

    def test_get_rollback_statistics_empty(self, temp_dir: str) -> None:
        """Test statistics with no rollbacks."""
        manager = RollbackManager(temp_dir)
        stats = manager.get_rollback_statistics()

        assert stats["total_rollbacks"] == 0
        assert stats["average_duration_seconds"] == 0.0

    def test_emergency_rollback(self, temp_dir: str) -> None:
        """Test emergency rollback."""
        manager = RollbackManager(temp_dir)
        manager.rollback("1.1.0", "1.0.0")  # First establish history

        result = manager.emergency_rollback("1.1.0")
        assert result.from_version == "1.1.0"
        assert result.to_version == "1.0.0"
        assert result.metadata.get("emergency") is True

    def test_emergency_rollback_no_history(self, temp_dir: str) -> None:
        """Test emergency rollback without history."""
        manager = RollbackManager(temp_dir)

        with pytest.raises(RollbackError):
            manager.emergency_rollback("1.1.0")

    def test_rollback_target_met(self, temp_dir: str) -> None:
        """Test that rollback completes within target time."""
        manager = RollbackManager(temp_dir, target_duration_seconds=300.0)
        result = manager.rollback("1.1.0", "1.0.0")

        # AC: Rollback to previous version completes in <5 minutes
        assert result.duration_seconds < 300.0
        assert result.target_met is True

    def test_rollback_steps(self, temp_dir: str) -> None:
        """Test that all rollback steps are executed."""
        manager = RollbackManager(temp_dir)
        result = manager.rollback("1.1.0", "1.0.0")

        expected_steps = [
            "validate_target_version",
            "stop_current_brain",
            "backup_current_state",
            "load_previous_version",
            "verify_loaded_version",
            "activate_previous_version",
            "verify_activation",
            "notify_listeners",
        ]

        for step in expected_steps:
            assert step in result.steps_completed, f"Step {step} not completed"

        assert len(result.steps_failed) == 0
