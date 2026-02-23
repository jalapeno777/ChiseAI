"""Tests for Task Sentinel module (ST-GOV-003)."""

import pytest
from unittest.mock import MagicMock, patch

from src.governance.sentinel.task_sentinel import (
    TaskSentinel,
    SentinelConfig,
    TaskInfo,
    ValidationResult,
)


class TestSentinelConfig:
    """Tests for SentinelConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SentinelConfig()
        assert config.max_story_points == 5
        assert config.approval_timeout_hours == 24
        assert config.require_justification is True
        assert config.blocked_task_ttl_days == 7
        assert config.redis_prefix == "chise:governance:sentinel"
        assert config.enable_dependency_check is True
        assert config.enable_conflict_detection is True
        assert config.latency_target_ms == 200

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SentinelConfig(
            max_story_points=8,
            approval_timeout_hours=48,
            require_justification=False,
        )
        assert config.max_story_points == 8
        assert config.approval_timeout_hours == 48
        assert config.require_justification is False


class TestTaskInfo:
    """Tests for TaskInfo dataclass."""

    def test_task_info_creation(self):
        """Test creating a TaskInfo instance."""
        task = TaskInfo(
            task_id="ST-001",
            story_points=3,
            title="Test task",
        )
        assert task.task_id == "ST-001"
        assert task.story_points == 3
        assert task.title == "Test task"
        assert task.labels == []
        assert task.scope_globs == []
        assert task.dependencies == []

    def test_task_info_with_all_fields(self):
        """Test TaskInfo with all optional fields."""
        task = TaskInfo(
            task_id="ST-002",
            story_points=5,
            title="Full task",
            description="Complete task description",
            assignee="agent-1",
            labels=["backend", "api"],
            scope_globs=["src/api/**/*.py"],
            dependencies=["ST-001"],
        )
        assert task.description == "Complete task description"
        assert task.assignee == "agent-1"
        assert task.labels == ["backend", "api"]
        assert task.scope_globs == ["src/api/**/*.py"]
        assert task.dependencies == ["ST-001"]


class TestTaskSentinel:
    """Tests for TaskSentinel class."""

    def test_sentinel_initialization(self):
        """Test sentinel initialization without Redis."""
        sentinel = TaskSentinel()
        assert sentinel.redis_client is None
        assert sentinel.config.max_story_points == 5

    def test_sentinel_with_custom_config(self):
        """Test sentinel with custom configuration."""
        config = SentinelConfig(max_story_points=10)
        sentinel = TaskSentinel(config=config)
        assert sentinel.config.max_story_points == 10

    def test_is_enabled_without_redis(self):
        """Test is_enabled returns False without Redis."""
        sentinel = TaskSentinel()
        assert sentinel.is_enabled() is False

    def test_is_enabled_with_redis_flag_true(self):
        """Test is_enabled returns True when Redis flag is set."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"true"
        sentinel = TaskSentinel(redis_client=mock_redis)
        assert sentinel.is_enabled() is True

    def test_is_enabled_with_redis_flag_false(self):
        """Test is_enabled returns False when Redis flag is not set."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        sentinel = TaskSentinel(redis_client=mock_redis)
        assert sentinel.is_enabled() is False

    def test_validate_task_size_within_limit(self):
        """Test validation of task within size limit."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-001", story_points=3, title="Small task")
        result = sentinel.validate_task_size(task)

        assert result.is_valid is True
        assert result.requires_approval is False
        assert result.story_points == 3
        assert result.max_allowed == 5

    def test_validate_task_size_exceeds_limit(self):
        """Test validation of task exceeding size limit."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-002", story_points=8, title="Large task")
        result = sentinel.validate_task_size(task)

        assert result.is_valid is False
        assert result.requires_approval is True
        assert result.story_points == 8
        assert "exceeds max story points" in result.message

    def test_validate_task_size_at_limit(self):
        """Test validation of task exactly at size limit."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-003", story_points=5, title="At limit task")
        result = sentinel.validate_task_size(task)

        assert result.is_valid is True
        assert result.requires_approval is False

    def test_validate_task_comprehensive(self):
        """Test comprehensive task validation."""
        sentinel = TaskSentinel()
        task = TaskInfo(
            task_id="ST-004",
            story_points=3,
            title="Valid task",
            scope_globs=["src/api/routes.py"],
        )
        result = sentinel.validate_task(task)

        assert result.is_valid is True
        assert result.requires_approval is False
        assert result.validation_latency_ms > 0

    def test_validate_task_with_oversized(self):
        """Test comprehensive validation of oversized task."""
        sentinel = TaskSentinel()
        task = TaskInfo(
            task_id="ST-005",
            story_points=8,
            title="Oversized task",
            scope_globs=["src/**/*.py"],
        )
        result = sentinel.validate_task(task)

        assert result.is_valid is False
        assert result.requires_approval is True
        assert "exceeds max story points" in result.message

    def test_requires_decomposition(self):
        """Test decomposition requirement check."""
        sentinel = TaskSentinel()

        small_task = TaskInfo(task_id="ST-006", story_points=3, title="Small")
        large_task = TaskInfo(task_id="ST-007", story_points=8, title="Large")

        assert sentinel.requires_decomposition(small_task) is False
        assert (
            sentinel.requires_decomposition(large_task) is False
        )  # Disabled without Redis

    def test_request_approval_with_justification(self):
        """Test approval request with justification."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-008", story_points=8, title="Needs approval")

        request_id = sentinel.request_approval(
            task, "Complex feature requiring coordination"
        )
        assert request_id.startswith("apr-")

    def test_request_approval_without_justification(self):
        """Test approval request fails without justification."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-009", story_points=8, title="Needs approval")

        with pytest.raises(ValueError, match="Justification required"):
            sentinel.request_approval(task, "")

    def test_approve_task(self):
        """Test task approval."""
        sentinel = TaskSentinel()
        result = sentinel.approve_task("ST-010", "human-1")
        assert result is True

    def test_is_task_approved_without_redis(self):
        """Test is_task_approved returns False without Redis."""
        sentinel = TaskSentinel()
        assert sentinel.is_task_approved("ST-011") is False

    def test_is_task_approved_with_redis(self):
        """Test is_task_approved with Redis."""
        mock_redis = MagicMock()
        mock_redis.sismember.return_value = 1
        sentinel = TaskSentinel(redis_client=mock_redis)

        assert sentinel.is_task_approved("ST-012") is True
        mock_redis.sismember.assert_called_once()

    def test_check_parallel_safety_no_conflicts(self):
        """Test parallel safety check with no conflicts."""
        sentinel = TaskSentinel()
        tasks = [
            TaskInfo(
                task_id="ST-013",
                story_points=3,
                title="Task A",
                scope_globs=["src/a/**/*.py"],
            ),
            TaskInfo(
                task_id="ST-014",
                story_points=3,
                title="Task B",
                scope_globs=["src/b/**/*.py"],
            ),
        ]

        is_safe, result = sentinel.check_parallel_safety(tasks)
        assert is_safe is True
        assert result.has_conflicts is False

    def test_check_parallel_safety_with_conflicts(self):
        """Test parallel safety check with conflicts."""
        sentinel = TaskSentinel()
        tasks = [
            TaskInfo(
                task_id="ST-015",
                story_points=3,
                title="Task A",
                scope_globs=["src/api/**/*.py"],
            ),
            TaskInfo(
                task_id="ST-016",
                story_points=3,
                title="Task B",
                scope_globs=["src/api/routes.py"],
            ),
        ]

        is_safe, result = sentinel.check_parallel_safety(tasks)
        # These scopes overlap, so there should be conflicts
        assert result.has_conflicts is True

    def test_get_execution_order(self):
        """Test getting execution order."""
        sentinel = TaskSentinel()
        tasks = [
            TaskInfo(
                task_id="ST-017",
                story_points=3,
                title="Task A",
                scope_globs=["src/a/**/*.py"],
            ),
            TaskInfo(
                task_id="ST-018",
                story_points=3,
                title="Task B",
                scope_globs=["src/b/**/*.py"],
            ),
        ]

        order = sentinel.get_execution_order(tasks)
        assert len(order) == 2
        assert "ST-017" in order
        assert "ST-018" in order

    def test_clear_cache(self):
        """Test clearing cache."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"true"
        sentinel = TaskSentinel(redis_client=mock_redis)

        # Enable the cache
        sentinel.is_enabled()
        assert sentinel._enabled is True

        # Clear cache
        sentinel.clear_cache()
        assert sentinel._enabled is None

    def test_get_pending_approvals_without_redis(self):
        """Test getting pending approvals without Redis."""
        sentinel = TaskSentinel()
        approvals = sentinel.get_pending_approvals()
        assert approvals == []

    def test_get_pending_approvals_with_redis(self):
        """Test getting pending approvals with Redis."""
        import json

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"true"
        mock_redis.lrange.return_value = [
            b'{"request_id": "apr-123", "task_id": "ST-019"}'
        ]
        sentinel = TaskSentinel(redis_client=mock_redis)

        sentinel.is_enabled()  # Enable it
        approvals = sentinel.get_pending_approvals()
        assert len(approvals) == 1
        assert approvals[0]["task_id"] == "ST-019"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test creating a ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            requires_approval=False,
            story_points=3,
            max_allowed=5,
            message="Task is valid",
            task_id="ST-001",
        )
        assert result.is_valid is True
        assert result.requires_approval is False
        assert result.story_points == 3
        assert result.max_allowed == 5
        assert result.message == "Task is valid"
        assert result.task_id == "ST-001"

    def test_validation_result_with_conflicts(self):
        """Test ValidationResult with ownership conflicts."""
        result = ValidationResult(
            is_valid=False,
            requires_approval=False,
            story_points=3,
            max_allowed=5,
            message="Ownership conflict",
            ownership_conflicts=[{"scope": "src/api", "owner": "ST-OTHER/agent"}],
        )
        assert len(result.ownership_conflicts) == 1


class TestLatencyTracking:
    """Tests for latency tracking in validation."""

    def test_latency_is_tracked(self):
        """Test that validation latency is tracked."""
        sentinel = TaskSentinel()
        task = TaskInfo(task_id="ST-LAT", story_points=3, title="Latency test")
        result = sentinel.validate_task(task)

        assert result.validation_latency_ms > 0
        assert result.validation_latency_ms < 1000  # Should be fast

    def test_latency_target_warning(self):
        """Test latency warning when exceeding target."""
        sentinel = TaskSentinel(config=SentinelConfig(latency_target_ms=0))
        task = TaskInfo(task_id="ST-SLOW", story_points=3, title="Slow test")

        # This should log a warning but not fail
        result = sentinel.validate_task(task)
        assert result.validation_latency_ms >= 0
