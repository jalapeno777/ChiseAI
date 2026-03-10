"""Smoke tests for brain rollback module.

Verifies basic functionality and imports for the rollback system.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime

import pytest

from brain.rollback import (
    RollbackError,
    RollbackManager,
    RollbackResult,
    RollbackStatus,
    RollbackTimeoutError,
)


class TestRollbackResultSmoke:
    """Smoke tests for RollbackResult class."""

    def test_result_creation(self) -> None:
        """Test creating a rollback result."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at=datetime.now(UTC).isoformat(),
        )

        assert result.from_version == "1.1.0"
        assert result.to_version == "1.0.0"
        assert result.status == RollbackStatus.COMPLETED

    def test_result_default_target_duration(self) -> None:
        """Test default target duration (5 minutes)."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at=datetime.now(UTC).isoformat(),
        )

        assert result.target_duration_seconds == 300.0  # 5 minutes

    def test_result_duration_remaining(self) -> None:
        """Test duration remaining calculation."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.IN_PROGRESS,
            started_at=datetime.now(UTC).isoformat(),
            duration_seconds=60.0,
            target_duration_seconds=300.0,
        )

        assert result.duration_remaining_seconds == 240.0

    def test_result_to_dict(self) -> None:
        """Test converting result to dict."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.COMPLETED,
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:02:00Z",
            duration_seconds=120.0,
            target_met=True,
        )

        data = result.to_dict()
        assert data["from_version"] == "1.1.0"
        assert data["to_version"] == "1.0.0"
        assert data["status"] == "completed"
        assert data["target_met"] is True

    def test_result_from_dict(self) -> None:
        """Test creating result from dict."""
        data = {
            "from_version": "2.0.0",
            "to_version": "1.5.0",
            "status": "failed",
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:01:00Z",
            "duration_seconds": 60.0,
            "target_duration_seconds": 300.0,
            "target_met": True,
            "steps_completed": ["step1", "step2"],
            "steps_failed": [],
            "error_message": None,
            "metadata": {"key": "value"},
        }

        result = RollbackResult.from_dict(data)
        assert result.from_version == "2.0.0"
        assert result.status == RollbackStatus.FAILED
        assert result.target_met is True
        assert len(result.steps_completed) == 2

    def test_result_with_steps(self) -> None:
        """Test result with completed and failed steps."""
        result = RollbackResult(
            from_version="1.1.0",
            to_version="1.0.0",
            status=RollbackStatus.FAILED,
            started_at=datetime.now(UTC).isoformat(),
            steps_completed=["step1", "step2"],
            steps_failed=["step3"],
            error_message="Step 3 failed",
        )

        assert len(result.steps_completed) == 2
        assert len(result.steps_failed) == 1
        assert result.error_message == "Step 3 failed"


class TestRollbackManagerSmoke:
    """Smoke tests for RollbackManager class."""

    def test_manager_initialization(self) -> None:
        """Test initializing rollback manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)
            assert manager.storage_path.exists()
            assert manager.target_duration_seconds == 300.0

    def test_manager_custom_target_duration(self) -> None:
        """Test manager with custom target duration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir, target_duration_seconds=600.0)
            assert manager.target_duration_seconds == 600.0

    def test_rollback_execution(self) -> None:
        """Test executing a rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            result = manager.rollback("1.1.0", "1.0.0")

            assert result.from_version == "1.1.0"
            assert result.to_version == "1.0.0"
            assert result.status == RollbackStatus.COMPLETED
            assert result.duration_seconds > 0

    def test_rollback_with_metadata(self) -> None:
        """Test rollback with metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            result = manager.rollback(
                "1.1.0",
                "1.0.0",
                metadata={"reason": "bug found", "triggered_by": "monitor"},
            )

            assert result.metadata["reason"] == "bug found"
            assert result.metadata["triggered_by"] == "monitor"

    def test_rollback_steps_completed(self) -> None:
        """Test that rollback steps are tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            result = manager.rollback("1.1.0", "1.0.0")

            assert len(result.steps_completed) > 0
            assert "validate_target_version" in result.steps_completed
            assert "activate_previous_version" in result.steps_completed

    def test_rollback_target_met(self) -> None:
        """Test that rollback target is met."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            result = manager.rollback("1.1.0", "1.0.0")

            assert result.target_met is True
            assert result.duration_seconds <= result.target_duration_seconds

    def test_can_rollback_to(self) -> None:
        """Test checking if rollback is possible."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            can_rollback, reason = manager.can_rollback_to("1.0.0")
            assert can_rollback is True
            assert "1.0.0" in reason

    def test_get_previous_version(self) -> None:
        """Test getting previous version from history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            # First, do a rollback to populate history
            manager.rollback("1.1.0", "1.0.0")

            previous = manager.get_previous_version("1.1.0")
            assert previous == "1.0.0"

    def test_get_previous_version_not_found(self) -> None:
        """Test getting previous version when not in history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            previous = manager.get_previous_version("9.9.9")
            assert previous is None

    def test_get_rollback_result(self) -> None:
        """Test retrieving rollback result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            # Execute rollback
            manager.rollback("1.1.0", "1.0.0")

            # Retrieve result
            result = manager.get_rollback_result("1.1.0", "1.0.0")
            assert result is not None
            assert result.from_version == "1.1.0"

    def test_get_rollback_result_not_found(self) -> None:
        """Test retrieving non-existent rollback result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            result = manager.get_rollback_result("9.9.9", "8.8.8")
            assert result is None

    def test_list_rollbacks(self) -> None:
        """Test listing rollback operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            manager.rollback("1.1.0", "1.0.0")
            manager.rollback("1.2.0", "1.1.0")

            rollbacks = manager.list_rollbacks()
            assert len(rollbacks) == 2

    def test_list_rollbacks_with_limit(self) -> None:
        """Test listing rollbacks with limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            manager.rollback("1.1.0", "1.0.0")
            manager.rollback("1.2.0", "1.1.0")
            manager.rollback("1.3.0", "1.2.0")

            rollbacks = manager.list_rollbacks(limit=2)
            assert len(rollbacks) == 2

    def test_list_rollbacks_by_status(self) -> None:
        """Test listing rollbacks filtered by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            manager.rollback("1.1.0", "1.0.0")

            completed = manager.list_rollbacks(status=RollbackStatus.COMPLETED)
            failed = manager.list_rollbacks(status=RollbackStatus.FAILED)

            assert len(completed) == 1
            assert len(failed) == 0

    def test_get_rollback_statistics(self) -> None:
        """Test getting rollback statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            # Empty stats
            stats = manager.get_rollback_statistics()
            assert stats["total_rollbacks"] == 0
            assert stats["successful_rollbacks"] == 0

            # Execute some rollbacks
            manager.rollback("1.1.0", "1.0.0")
            manager.rollback("1.2.0", "1.1.0")

            stats = manager.get_rollback_statistics()
            assert stats["total_rollbacks"] == 2
            assert stats["successful_rollbacks"] == 2
            assert stats["target_met_percentage"] == 100.0
            assert stats["average_duration_seconds"] > 0

    def test_emergency_rollback(self) -> None:
        """Test emergency rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            # First create history
            manager.rollback("1.1.0", "1.0.0")

            # Emergency rollback should find previous version
            result = manager.emergency_rollback("1.1.0")

            assert result.from_version == "1.1.0"
            assert result.to_version == "1.0.0"
            assert result.metadata.get("emergency") is True

    def test_emergency_rollback_no_previous(self) -> None:
        """Test emergency rollback when no previous version exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(tmpdir)

            with pytest.raises(RollbackError):
                manager.emergency_rollback("1.0.0")

    def test_persistence(self) -> None:
        """Test rollback history persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First manager instance
            manager1 = RollbackManager(tmpdir)
            manager1.rollback("1.1.0", "1.0.0")

            # Second manager instance - should load history
            manager2 = RollbackManager(tmpdir)
            rollbacks = manager2.list_rollbacks()

            assert len(rollbacks) == 1
            assert rollbacks[0].from_version == "1.1.0"


class TestRollbackStatusSmoke:
    """Smoke tests for RollbackStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert RollbackStatus.PENDING.value == "pending"
        assert RollbackStatus.IN_PROGRESS.value == "in_progress"
        assert RollbackStatus.COMPLETED.value == "completed"
        assert RollbackStatus.FAILED.value == "failed"
        assert RollbackStatus.TIMEOUT.value == "timeout"


class TestRollbackExceptionsSmoke:
    """Smoke tests for rollback exceptions."""

    def test_rollback_error_is_exception(self) -> None:
        """Test RollbackError is an Exception."""
        assert issubclass(RollbackError, Exception)

    def test_rollback_timeout_error(self) -> None:
        """Test RollbackTimeoutError is RollbackError."""
        assert issubclass(RollbackTimeoutError, RollbackError)

    def test_rollback_error_message(self) -> None:
        """Test rollback error message."""
        error = RollbackError("Test error message")
        assert str(error) == "Test error message"

    def test_rollback_timeout_error_message(self) -> None:
        """Test rollback timeout error message."""
        error = RollbackTimeoutError("Rollback timed out")
        assert str(error) == "Rollback timed out"
