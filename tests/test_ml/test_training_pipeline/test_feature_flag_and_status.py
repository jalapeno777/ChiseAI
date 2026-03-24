"""Tests for training pipeline feature flag and Redis status keys.

Tests:
- Feature flag functionality
- Redis status key operations
- Pipeline status tracking integration

For ST-LAUNCH-012: Training Pipeline Integration
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from config.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    set_feature_flags,
)
from ml.training.pipeline_status import (
    PipelineStatus,
    PipelineStatusTracker,
    delete_pipeline_status,
    get_pipeline_status,
    get_pipeline_status_value,
    is_pipeline_active,
    set_pipeline_status,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def reset_flags():
    """Reset feature flags after each test."""
    yield
    reset_feature_flags()


@pytest.fixture
def mock_redis():
    """Mock Redis state functions."""
    mock_data = {}

    def mock_hset(name, key, value, expire_seconds=None):
        if name not in mock_data:
            mock_data[name] = {}
        mock_data[name][key] = value
        return True

    def mock_hgetall(name):
        return mock_data.get(name, {})

    def mock_hdel(name, key):
        if name in mock_data and key in mock_data[name]:
            del mock_data[name][key]
        return True

    with patch(
        "ml.training.pipeline_status._get_redis_helpers",
        return_value=(mock_hset, None, mock_hgetall, mock_hdel),
    ):
        yield mock_data


# =============================================================================
# Feature Flag Tests
# =============================================================================


class TestFeatureFlag:
    """Tests for launch_training_pipeline_enabled feature flag."""

    def test_feature_flag_defaults_to_enabled(self):
        """Test that the feature flag defaults to enabled."""
        flags = FeatureFlags()
        assert flags.launch_training_pipeline_enabled is True

    def test_feature_flag_can_be_disabled(self):
        """Test that the feature flag can be explicitly disabled."""
        flags = FeatureFlags(launch_training_pipeline_enabled=False)
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flag_from_env_enabled(self, monkeypatch):
        """Test that feature flag can be enabled via environment variable."""
        monkeypatch.setenv("LAUNCH_TRAINING_PIPELINE_ENABLED", "true")
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is True

    def test_feature_flag_from_env_disabled(self, monkeypatch):
        """Test that feature flag can be disabled via environment variable."""
        monkeypatch.setenv("LAUNCH_TRAINING_PIPELINE_ENABLED", "false")
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flag_from_env_zero(self, monkeypatch):
        """Test that feature flag treats '0' as disabled."""
        monkeypatch.setenv("LAUNCH_TRAINING_PIPELINE_ENABLED", "0")
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flag_from_env_no(self, monkeypatch):
        """Test that feature flag treats 'no' as disabled."""
        monkeypatch.setenv("LAUNCH_TRAINING_PIPELINE_ENABLED", "no")
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flag_from_env_off(self, monkeypatch):
        """Test that feature flag treats 'off' as disabled."""
        monkeypatch.setenv("LAUNCH_TRAINING_PIPELINE_ENABLED", "off")
        reset_feature_flags()
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flag_in_dict(self):
        """Test that feature flag is included in to_dict output."""
        flags = FeatureFlags()
        data = flags.to_dict()
        assert "launch_training_pipeline_enabled" in data
        assert data["launch_training_pipeline_enabled"] is True

    def test_global_feature_flags_singleton(self, reset_flags):
        """Test that global feature flags work as singleton."""
        flags1 = get_feature_flags()
        flags2 = get_feature_flags()
        assert flags1 is flags2

    def test_set_feature_flags_override(self, reset_flags):
        """Test that set_feature_flags can override global flags."""
        custom_flags = FeatureFlags(launch_training_pipeline_enabled=False)
        set_feature_flags(custom_flags)
        flags = get_feature_flags()
        assert flags.launch_training_pipeline_enabled is False


# =============================================================================
# PipelineStatus Enum Tests
# =============================================================================


class TestPipelineStatus:
    """Tests for PipelineStatus enum."""

    def test_status_values(self):
        """Test that status values are correct."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"

    def test_status_from_string(self):
        """Test creating status from string."""
        assert PipelineStatus("pending") == PipelineStatus.PENDING
        assert PipelineStatus("running") == PipelineStatus.RUNNING
        assert PipelineStatus("completed") == PipelineStatus.COMPLETED
        assert PipelineStatus("failed") == PipelineStatus.FAILED


# =============================================================================
# Redis Status Key Tests
# =============================================================================


class TestPipelineStatusKeys:
    """Tests for Redis pipeline status key operations."""

    def test_set_pipeline_status(self, mock_redis):
        """Test setting pipeline status."""
        result = set_pipeline_status("test-pipeline", PipelineStatus.RUNNING)
        assert result is True
        assert "bmad:chiseai:training:test-pipeline:status" in mock_redis

    def test_set_pipeline_status_with_metadata(self, mock_redis):
        """Test setting pipeline status with metadata."""
        metadata = {"key": "value", "number": 42}
        set_pipeline_status("test-pipeline", PipelineStatus.RUNNING, metadata=metadata)

        key = "bmad:chiseai:training:test-pipeline:status"
        assert key in mock_redis
        assert "metadata" in mock_redis[key]

    def test_get_pipeline_status(self, mock_redis):
        """Test getting pipeline status."""
        # Set status first
        set_pipeline_status("test-pipeline", PipelineStatus.RUNNING)

        # Get status
        status = get_pipeline_status("test-pipeline")
        assert status is not None
        assert status["status"] == "running"

    def test_get_pipeline_status_not_found(self, mock_redis):
        """Test getting non-existent pipeline status."""
        status = get_pipeline_status("non-existent-pipeline")
        assert status is None

    def test_get_pipeline_status_value(self, mock_redis):
        """Test getting just the status value."""
        set_pipeline_status("test-pipeline", PipelineStatus.COMPLETED)

        value = get_pipeline_status_value("test-pipeline")
        assert value == "completed"

    def test_delete_pipeline_status(self, mock_redis):
        """Test deleting pipeline status."""
        # Set and verify
        set_pipeline_status("test-pipeline", PipelineStatus.RUNNING)
        assert "bmad:chiseai:training:test-pipeline:status" in mock_redis

        # Delete
        result = delete_pipeline_status("test-pipeline")
        assert result is True

    def test_is_pipeline_active_pending(self, mock_redis):
        """Test checking if pending pipeline is active."""
        set_pipeline_status("test-pipeline", PipelineStatus.PENDING)
        assert is_pipeline_active("test-pipeline") is True

    def test_is_pipeline_active_running(self, mock_redis):
        """Test checking if running pipeline is active."""
        set_pipeline_status("test-pipeline", PipelineStatus.RUNNING)
        assert is_pipeline_active("test-pipeline") is True

    def test_is_pipeline_active_completed(self, mock_redis):
        """Test checking if completed pipeline is not active."""
        set_pipeline_status("test-pipeline", PipelineStatus.COMPLETED)
        assert is_pipeline_active("test-pipeline") is False

    def test_is_pipeline_active_failed(self, mock_redis):
        """Test checking if failed pipeline is not active."""
        set_pipeline_status("test-pipeline", PipelineStatus.FAILED)
        assert is_pipeline_active("test-pipeline") is False

    def test_is_pipeline_active_not_found(self, mock_redis):
        """Test checking if non-existent pipeline is not active."""
        assert is_pipeline_active("non-existent-pipeline") is False


# =============================================================================
# PipelineStatusTracker Context Manager Tests
# =============================================================================


class TestPipelineStatusTracker:
    """Tests for PipelineStatusTracker context manager."""

    def test_tracker_sets_running_on_enter(self, mock_redis):
        """Test that tracker sets status to running on enter."""
        with PipelineStatusTracker("test-pipeline"):
            status = get_pipeline_status_value("test-pipeline")
            assert status == "running"

    def test_tracker_sets_completed_on_success(self, mock_redis):
        """Test that tracker sets status to completed on successful exit."""
        with PipelineStatusTracker("test-pipeline"):
            pass

        status = get_pipeline_status_value("test-pipeline")
        assert status == "completed"

    def test_tracker_sets_failed_on_exception(self, mock_redis):
        """Test that tracker sets status to failed on exception."""
        with pytest.raises(ValueError):
            with PipelineStatusTracker("test-pipeline"):
                raise ValueError("Test error")

        status = get_pipeline_status_value("test-pipeline")
        assert status == "failed"

    def test_tracker_includes_error_metadata(self, mock_redis):
        """Test that tracker includes error info in metadata on failure."""
        with pytest.raises(ValueError):
            with PipelineStatusTracker("test-pipeline"):
                raise ValueError("Test error message")

        status_info = get_pipeline_status("test-pipeline")
        assert status_info is not None
        assert "metadata" in status_info

    def test_tracker_with_custom_metadata(self, mock_redis):
        """Test tracker with custom metadata."""
        custom_metadata = {"version": "1.0.0", "model": "test-model"}

        with PipelineStatusTracker("test-pipeline", metadata=custom_metadata):
            pass

        status_info = get_pipeline_status("test-pipeline")
        assert status_info is not None


# =============================================================================
# Integration Tests with Pipeline Integration
# =============================================================================


class TestPipelineIntegrationWithStatus:
    """Tests for integration between pipeline and status tracking."""

    @pytest.mark.asyncio
    async def test_manual_training_updates_status(self, mock_redis, reset_flags):
        """Test that manual training updates Redis status."""
        import asyncio
        from unittest.mock import AsyncMock

        from ml.training.pipeline_integration import (
            TrainingPipelineIntegration,
        )

        # Create integration with mocked components
        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=MagicMock(
                sample_count=200,
                samples=[{"feature": 1.0}] * 200,
                features=["feature"],
            )
        )

        integration = TrainingPipelineIntegration(
            data_fetcher=mock_data_fetcher,
            model_trainer=None,  # Simulation mode
            enable_retry=False,  # Disable retry for faster test
        )

        # Run manual training
        job = await integration.run_training_manual()

        # Wait for job to complete with timeout
        task = integration._scheduler._running_tasks.get(job.job_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        # Check status was tracked
        status_info = get_pipeline_status(job.job_id)
        assert status_info is not None

    def test_feature_flag_check_in_handle_trigger(self, reset_flags):
        """Test that handle_trigger checks feature flag."""
        from ml.training.pipeline_integration import (
            TrainingJobStatus,
            TrainingPipelineIntegration,
        )
        from ml.training.retraining_trigger import (
            InMemoryDeduplicationStore,
            RetrainingTrigger,
            RetrainingTriggerConfig,
            TriggerResult,
            TriggerStatus,
            TriggerType,
        )

        # Disable feature flag
        flags = FeatureFlags(launch_training_pipeline_enabled=False)
        set_feature_flags(flags)

        # Create trigger and integration
        trigger = RetrainingTrigger(
            config=RetrainingTriggerConfig(enable_discord_alerts=False),
            dedup_store=InMemoryDeduplicationStore(),
        )

        integration = TrainingPipelineIntegration(retraining_trigger=trigger)

        # Create trigger result
        trigger_result = TriggerResult(
            trigger_type=TriggerType.ECE_BASED,
            status=TriggerStatus.TRIGGERED,
            triggered=True,
            message="Test trigger",
            timestamp=datetime.now(UTC),
        )

        # Handle trigger (async)
        import asyncio

        job = asyncio.run(integration.handle_trigger(trigger_result))

        # Verify job was cancelled due to feature flag
        assert job.status == TrainingJobStatus.CANCELLED
        assert "disabled" in job.error_message.lower()


# =============================================================================
# Redis Key Pattern Tests
# =============================================================================


class TestRedisKeyPatterns:
    """Tests for Redis key patterns."""

    def test_key_prefix_format(self):
        """Test that key prefix follows expected format."""
        from ml.training.pipeline_status import REDIS_KEY_PREFIX, _get_redis_key

        assert REDIS_KEY_PREFIX == "bmad:chiseai:training"

        key = _get_redis_key("my-pipeline")
        assert key == "bmad:chiseai:training:my-pipeline:status"

    def test_key_with_special_characters(self):
        """Test key generation with special characters in pipeline ID."""
        from ml.training.pipeline_status import _get_redis_key

        key = _get_redis_key("pipeline_123-test.v1")
        assert key == "bmad:chiseai:training:pipeline_123-test.v1:status"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in status operations."""

    def test_set_pipeline_status_handles_redis_error(self):
        """Test that set_pipeline_status handles Redis errors gracefully."""
        with patch(
            "ml.training.pipeline_status._get_redis_helpers",
            return_value=(None, None, None, None),
        ):
            result = set_pipeline_status("test-pipeline", PipelineStatus.RUNNING)
            assert result is False

    def test_get_pipeline_status_handles_redis_error(self):
        """Test that get_pipeline_status handles Redis errors gracefully."""
        with patch(
            "ml.training.pipeline_status._get_redis_helpers",
            return_value=(None, None, None, None),
        ):
            result = get_pipeline_status("test-pipeline")
            assert result is None

    def test_delete_pipeline_status_handles_redis_error(self):
        """Test that delete_pipeline_status handles Redis errors gracefully."""
        with patch(
            "ml.training.pipeline_status._get_redis_helpers",
            return_value=(None, None, None, None),
        ):
            result = delete_pipeline_status("test-pipeline")
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
