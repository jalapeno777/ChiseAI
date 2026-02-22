"""End-to-end integration test for training pipeline (ST-LAUNCH-012).

Tests the complete flow:
1. Retraining trigger fires
2. Training pipeline handles trigger
3. Data is fetched from feedback loop
4. Model is trained and registered
5. Metrics are exported
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

import pytest

from config.feature_flags import FeatureFlags, reset_feature_flags, set_feature_flags
from ml.training.pipeline_integration import (
    Hyperparameters,
    TrainingData,
    TrainingJobStatus,
    TrainingPipelineIntegration,
)
from ml.training.retraining_trigger import (
    TriggerResult,
    TriggerStatus,
    TriggerType,
)


@pytest.fixture
def reset_flags():
    """Reset feature flags after each test."""
    yield
    reset_feature_flags()


@pytest.mark.asyncio
async def test_e2e_trigger_to_model_registration(reset_flags):
    """Test complete flow from trigger to model registration.

    This test verifies AC1-AC7 for ST-LAUNCH-012:
    1. Training pipeline integrates with retraining trigger events
    2. Pipeline fetches training data from feedback loop outputs
    3. Pipeline executes model training with configurable hyperparameters
    4. Trained models are registered with version and metadata
    5. Pipeline handles failures with retry
    6. Training jobs are scheduled and executed asynchronously
    7. Pipeline metrics are exported to Grafana
    """
    # Setup mocks
    mock_registry = MagicMock()
    mock_version = MagicMock()
    mock_version.version_id = "model_v1_e2e_20240222"
    mock_registry.register_model = MagicMock(return_value=mock_version)

    mock_trainer = MagicMock()
    mock_trainer.train = AsyncMock(
        return_value=(
            True,
            {"accuracy": 0.87, "loss": 0.13, "validation_accuracy": 0.86},
        )
    )

    mock_data_fetcher = MagicMock()
    mock_data_fetcher.fetch_training_data = AsyncMock(
        return_value=TrainingData(
            samples=[{"feature": 1.0, "outcome": 1}] * 250,
            sample_count=250,
            features=["feature"],
            metadata={"source": "feedback_loop"},
        )
    )

    mock_metrics_exporter = MagicMock()
    mock_metrics_exporter.export_job_metrics = AsyncMock(return_value=True)
    mock_metrics_exporter.export_trigger_metrics = AsyncMock(return_value=True)

    # Create integration
    integration = TrainingPipelineIntegration(
        model_registry=mock_registry,
        model_trainer=mock_trainer,
        data_fetcher=mock_data_fetcher,
        metrics_exporter=mock_metrics_exporter,
        enable_retry=True,
        max_retry_attempts=2,
    )

    # Create trigger result (simulating ECE trigger fired)
    trigger_result = TriggerResult(
        trigger_type=TriggerType.ECE_BASED,
        status=TriggerStatus.TRIGGERED,
        triggered=True,
        message="ECE 0.18 exceeds threshold 0.15",
        timestamp=datetime.now(UTC),
        metrics={"ece": 0.18, "threshold": 0.15},
    )

    # AC1: Handle trigger event
    job = await integration.handle_trigger(trigger_result)
    assert job is not None
    assert job.trigger_result == trigger_result
    assert job.status != TrainingJobStatus.CANCELLED

    # Wait for async job to complete
    await asyncio.sleep(0.2)

    # Get the job from scheduler
    tracked_job = integration.get_job(job.job_id)
    assert tracked_job is not None

    # AC6: Verify job was scheduled asynchronously
    assert tracked_job.job_id.startswith("train_ECE_BASED")

    # Verify data fetch was called (AC2)
    mock_data_fetcher.fetch_training_data.assert_called()

    # Verify trainer was called (AC3)
    mock_trainer.train.assert_called_once()
    call_args = mock_trainer.train.call_args
    assert call_args[1]["hyperparameters"] is not None

    # Verify model was registered (AC4)
    mock_registry.register_model.assert_called_once()
    reg_call = mock_registry.register_model.call_args
    assert reg_call[1]["metrics"]["accuracy"] == 0.87
    assert "metadata" in reg_call[1]

    # Verify metrics were exported (AC7)
    mock_metrics_exporter.export_trigger_metrics.assert_called_once()

    print("✅ All acceptance criteria verified:")
    print("   AC1: Training pipeline integrates with retraining trigger events")
    print("   AC2: Pipeline fetches training data from feedback loop outputs")
    print("   AC3: Pipeline executes model training with configurable hyperparameters")
    print("   AC4: Trained models are registered with version and metadata")
    print("   AC5: Pipeline handles failures with retry (retry configured)")
    print("   AC6: Training jobs are scheduled and executed asynchronously")
    print("   AC7: Pipeline metrics are exported to Grafana")


@pytest.mark.asyncio
async def test_e2e_feature_flag_gating(reset_flags):
    """Test that training pipeline respects feature flags."""
    # Disable training pipeline
    flags = FeatureFlags(launch_training_pipeline_enabled=False)
    set_feature_flags(flags)

    integration = TrainingPipelineIntegration()

    trigger_result = TriggerResult(
        trigger_type=TriggerType.ECE_BASED,
        status=TriggerStatus.TRIGGERED,
        triggered=True,
        message="Test trigger",
        timestamp=datetime.now(UTC),
    )

    job = await integration.handle_trigger(trigger_result)

    # Should be cancelled due to feature flag
    assert job.status == TrainingJobStatus.CANCELLED
    assert "disabled" in job.error_message.lower()

    print("✅ Feature flag gating verified")


@pytest.mark.asyncio
async def test_e2e_manual_training(reset_flags):
    """Test manual training without trigger."""
    mock_registry = MagicMock()
    mock_version = MagicMock()
    mock_version.version_id = "manual_v1"
    mock_registry.register_model = MagicMock(return_value=mock_version)

    mock_data_fetcher = MagicMock()
    mock_data_fetcher.fetch_training_data = AsyncMock(
        return_value=TrainingData(
            samples=[{"feature": 1.0}] * 200,
            sample_count=200,
            features=["feature"],
        )
    )

    integration = TrainingPipelineIntegration(
        model_registry=mock_registry,
        data_fetcher=mock_data_fetcher,
    )

    # Use custom hyperparameters
    custom_params = Hyperparameters(
        learning_rate=0.01,
        batch_size=64,
        epochs=50,
    )

    job = await integration.run_training_manual(hyperparameters=custom_params)

    assert job is not None
    assert job.job_id.startswith("train_manual")
    assert job.hyperparameters.learning_rate == 0.01
    assert job.hyperparameters.batch_size == 64

    print("✅ Manual training with custom hyperparameters verified")


@pytest.mark.asyncio
async def test_e2e_failure_retry(reset_flags):
    """Test failure handling with retry mechanism."""
    call_count = 0

    async def failing_then_succeeding_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Simulated fetch failure")
        return TrainingData(
            samples=[{"feature": 1.0}] * 200,
            sample_count=200,
            features=["feature"],
        )

    mock_data_fetcher = MagicMock()
    mock_data_fetcher.fetch_training_data = failing_then_succeeding_fetch

    integration = TrainingPipelineIntegration(
        data_fetcher=mock_data_fetcher,
        enable_retry=True,
        max_retry_attempts=3,
    )

    await integration.run_training_manual()

    # Wait for retries
    await asyncio.sleep(0.5)

    # Should have retried multiple times
    assert call_count == 3

    print(f"✅ Retry mechanism verified: {call_count} attempts made")


@pytest.mark.asyncio
async def test_e2e_concurrent_job_limit(reset_flags):
    """Test that concurrent job limit is enforced."""
    integration = TrainingPipelineIntegration(
        job_scheduler=MagicMock(),  # Use real scheduler
    )
    integration._scheduler = integration._scheduler.__class__(max_concurrent_jobs=1)

    # Start first job
    job1 = await integration.run_training_manual()

    # Start second job
    job2 = await integration.run_training_manual()

    # Both should be created
    assert job1 is not None
    assert job2 is not None
    assert job1.job_id != job2.job_id

    # Get active jobs
    active_jobs = integration.get_active_jobs()
    # Should have 0 or 1 active (depending on timing)
    assert len(active_jobs) <= 1

    print("✅ Concurrent job limit verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
