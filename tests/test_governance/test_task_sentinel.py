"""
Tests for Task Decomposition Sentinel (ST-GOV-003).

Test coverage for task size validation, feature flag integration,
and blocking logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from governance.sentinel import TaskSentinel, SentinelConfig
from governance.sentinel.task_sentinel import (
    TaskInfo,
    ValidationResult,
    FEATURE_FLAG_KEY,
)


class TestSentinelConfig:
    """Tests for SentinelConfig dataclass."""

    def test_default_config(self):
        """Verify default configuration values."""
        config = SentinelConfig()

        assert config.max_story_points == 5
        assert config.approval_timeout_hours == 24
        assert config.require_justification is True
        assert config.blocked_task_ttl_days == 7
        assert config.redis_prefix == "chise:governance:sentinel"

    def test_custom_config(self):
        """Verify custom configuration overrides."""
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
        """Verify task info is created correctly."""
        task = TaskInfo(
            task_id="ST-GOV-003",
            story_points=3,
            title="Implement Task Sentinel",
            description="Create skeleton for sentinel module",
            assignee="dev-agent",
            labels=["governance", "batch-1b"],
        )

        assert task.task_id == "ST-GOV-003"
        assert task.story_points == 3
        assert task.title == "Implement Task Sentinel"
        assert "governance" in task.labels

    def test_task_info_minimal(self):
        """Verify minimal task info works."""
        task = TaskInfo(
            task_id="ST-001",
            story_points=2,
            title="Small task",
        )

        assert task.task_id == "ST-001"
        assert task.description is None
        assert task.labels == []


class TestTaskSentinelInitialization:
    """Tests for TaskSentinel initialization."""

    def test_init_without_redis(self):
        """Verify sentinel works without Redis client."""
        sentinel = TaskSentinel()

        assert sentinel.redis_client is None
        assert sentinel.config.max_story_points == 5

    def test_init_with_redis(self):
        """Verify sentinel accepts Redis client."""
        mock_redis = Mock()
        sentinel = TaskSentinel(redis_client=mock_redis)

        assert sentinel.redis_client is mock_redis

    def test_init_with_custom_config(self):
        """Verify custom config is applied."""
        config = SentinelConfig(max_story_points=10)
        sentinel = TaskSentinel(config=config)

        assert sentinel.config.max_story_points == 10


class TestFeatureFlagIntegration:
    """Tests for feature flag integration."""

    def test_disabled_by_default_no_redis(self):
        """Sentinel should be disabled when no Redis client."""
        sentinel = TaskSentinel()
        assert sentinel.is_enabled() is False

    def test_disabled_when_flag_false(self):
        """Sentinel should be disabled when feature flag is false."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"false"

        sentinel = TaskSentinel(redis_client=mock_redis)
        assert sentinel.is_enabled() is False

    def test_enabled_when_flag_true(self):
        """Sentinel should be enabled when feature flag is true."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"true"

        sentinel = TaskSentinel(redis_client=mock_redis)
        assert sentinel.is_enabled() is True

    def test_disabled_on_redis_error(self):
        """Sentinel should be disabled if Redis fails."""
        mock_redis = Mock()
        mock_redis.get.side_effect = Exception("Redis connection error")

        sentinel = TaskSentinel(redis_client=mock_redis)
        assert sentinel.is_enabled() is False

    def test_feature_flag_key_correct(self):
        """Verify correct feature flag key is used."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"false"

        sentinel = TaskSentinel(redis_client=mock_redis)
        sentinel.is_enabled()

        mock_redis.get.assert_called_once_with(FEATURE_FLAG_KEY)

    def test_feature_flag_caching(self):
        """Verify feature flag state is cached."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"true"

        sentinel = TaskSentinel(redis_client=mock_redis)

        # Multiple calls should only query Redis once
        assert sentinel.is_enabled() is True
        assert sentinel.is_enabled() is True
        assert sentinel.is_enabled() is True

        mock_redis.get.assert_called_once()

    def test_clear_cache(self):
        """Verify cache clearing allows re-reading flag."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"true"

        sentinel = TaskSentinel(redis_client=mock_redis)
        sentinel.is_enabled()
        sentinel.clear_cache()
        sentinel.is_enabled()

        assert mock_redis.get.call_count == 2


class TestTaskSizeValidation:
    """Tests for task size validation logic."""

    @pytest.fixture
    def sentinel(self):
        """Create a sentinel for testing."""
        return TaskSentinel()

    def test_valid_small_task(self, sentinel):
        """Small tasks should be valid."""
        task = TaskInfo(
            task_id="ST-001",
            story_points=3,
            title="Small task",
        )

        result = sentinel.validate_task_size(task)

        assert result.is_valid is True
        assert result.requires_approval is False
        assert result.story_points == 3
        assert result.max_allowed == 5

    def test_valid_exactly_at_limit(self, sentinel):
        """Tasks exactly at limit should be valid."""
        task = TaskInfo(
            task_id="ST-002",
            story_points=5,
            title="Task at limit",
        )

        result = sentinel.validate_task_size(task)

        assert result.is_valid is True
        assert result.requires_approval is False

    def test_oversized_task_requires_approval(self, sentinel):
        """Oversized tasks should require approval."""
        task = TaskInfo(
            task_id="ST-003",
            story_points=8,
            title="Large task",
        )

        result = sentinel.validate_task_size(task)

        assert result.is_valid is False
        assert result.requires_approval is True
        assert result.story_points == 8
        assert "exceeds max story points" in result.message

    def test_validation_result_contains_task_id(self, sentinel):
        """Validation result should include task ID."""
        task = TaskInfo(
            task_id="ST-GOV-003",
            story_points=10,
            title="Oversized task",
        )

        result = sentinel.validate_task_size(task)

        assert result.task_id == "ST-GOV-003"

    def test_custom_max_story_points(self):
        """Custom max story points should be respected."""
        config = SentinelConfig(max_story_points=8)
        sentinel = TaskSentinel(config=config)

        task = TaskInfo(
            task_id="ST-004",
            story_points=7,
            title="Medium task",
        )

        result = sentinel.validate_task_size(task)
        assert result.is_valid is True
        assert result.max_allowed == 8


class TestBlockingLogic:
    """Tests for task blocking behavior."""

    def test_oversized_task_not_blocked_when_disabled(self):
        """Oversized tasks should not be blocked when sentinel disabled."""
        sentinel = TaskSentinel()  # No Redis = disabled

        task = TaskInfo(
            task_id="ST-005",
            story_points=20,
            title="Very large task",
        )

        result = sentinel.validate_task_size(task)

        # Validation should still return requires_approval
        # but blocking behavior depends on is_enabled()
        assert result.requires_approval is True
        assert sentinel.is_enabled() is False

    def test_requires_decomposition_stub(self):
        """Test requires_decomposition stub implementation."""
        sentinel = TaskSentinel()

        task = TaskInfo(
            task_id="ST-006",
            story_points=10,
            title="Task needing decomposition",
        )

        # Stub should return False when disabled
        result = sentinel.requires_decomposition(task)
        assert result is False

    def test_get_pending_approvals_stub(self):
        """Test get_pending_approvals stub implementation."""
        sentinel = TaskSentinel()

        approvals = sentinel.get_pending_approvals()

        # Stub should return empty list
        assert approvals == []

    def test_request_approval_stub(self):
        """Test request_approval stub implementation."""
        sentinel = TaskSentinel()

        task = TaskInfo(
            task_id="ST-007",
            story_points=8,
            title="Task requiring approval",
        )

        request_id = sentinel.request_approval(task, "Need to keep task intact")

        # Stub should return a request ID with format "apr-" + 8 hex chars = 12 chars
        assert request_id is not None
        assert len(request_id) == 12

    def test_request_approval_requires_justification(self):
        """Test that justification is required."""
        config = SentinelConfig(require_justification=True)
        sentinel = TaskSentinel(config=config)

        task = TaskInfo(
            task_id="ST-008",
            story_points=8,
            title="Task",
        )

        # Should raise when justification is empty
        with pytest.raises(ValueError, match="Justification required"):
            sentinel.request_approval(task, "")


class TestSentinelIntegrationScenarios:
    """Integration scenario tests."""

    def test_workflow_valid_task(self):
        """Test complete workflow for a valid task."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"true"
        sentinel = TaskSentinel(redis_client=mock_redis)

        task = TaskInfo(
            task_id="ST-100",
            story_points=3,
            title="Normal task",
        )

        result = sentinel.validate_task_size(task)

        assert sentinel.is_enabled() is True
        assert result.is_valid is True
        assert result.requires_approval is False

    def test_workflow_oversized_task_with_approval(self):
        """Test workflow for oversized task seeking approval."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"true"
        sentinel = TaskSentinel(redis_client=mock_redis)

        task = TaskInfo(
            task_id="ST-101",
            story_points=10,
            title="Large feature",
            description="Complex multi-component feature",
        )

        # Validate
        result = sentinel.validate_task_size(task)
        assert result.requires_approval is True

        # Request approval
        request_id = sentinel.request_approval(task, "Cross-cutting concern")
        assert request_id is not None

        # Approve
        approved = sentinel.approve_task(task.task_id, "tech-lead")
        assert approved is True


# Pytest markers for test organization
pytestmark = [
    pytest.mark.unit,
    pytest.mark.governance,
]
