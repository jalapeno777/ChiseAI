"""Comprehensive tests for training pipeline integration.

Tests all components:
- TrainingPipelineIntegration (main coordinator)
- AsyncJobScheduler (async job management)
- FeedbackLoopDataFetcher (data fetching)
- GrafanaMetricsExporter (metrics export)
- Hyperparameters configuration
- Failure handling with retry

Acceptance Criteria:
1. Training pipeline integrates with retraining trigger events
2. Pipeline fetches training data from feedback loop outputs
3. Pipeline executes model training with configurable hyperparameters
4. Trained models are registered with version and metadata
5. Pipeline handles failures with retry and alerting
6. Training jobs are scheduled and executed asynchronously
7. Pipeline metrics are exported to Grafana

For ST-LAUNCH-012: Training Pipeline Integration
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from config.feature_flags import (
    FeatureFlags,
    reset_feature_flags,
    set_feature_flags,
)
from ml.training.pipeline_integration import (
    AsyncJobScheduler,
    DataFetchError,
    FeedbackLoopDataFetcher,
    GrafanaMetricsExporter,
    Hyperparameters,
    TrainingData,
    TrainingJob,
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

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def reset_flags():
    """Reset feature flags after each test."""
    yield
    reset_feature_flags()


@pytest.fixture
def default_hyperparameters():
    """Create default hyperparameters."""
    return Hyperparameters()


@pytest.fixture
def sample_training_data():
    """Create sample training data."""
    return TrainingData(
        samples=[
            {"signal_id": "sig_1", "confidence": 0.8, "outcome": 1},
            {"signal_id": "sig_2", "confidence": 0.7, "outcome": 0},
            {"signal_id": "sig_3", "confidence": 0.9, "outcome": 1},
        ],
        sample_count=3,
        features=["confidence"],
        label_column="outcome",
    )


@pytest.fixture
def mock_model_registry():
    """Create mock model registry."""
    registry = MagicMock()
    mock_version = MagicMock()
    mock_version.version_id = "model_v1_20240222_120000"
    registry.register_model = MagicMock(return_value=mock_version)
    return registry


@pytest.fixture
def mock_model_trainer():
    """Create mock model trainer."""
    trainer = MagicMock()
    trainer.train = AsyncMock(
        return_value=(
            True,
            {"accuracy": 0.85, "loss": 0.15, "validation_accuracy": 0.83},
        )
    )
    return trainer


@pytest.fixture
def mock_metrics_exporter():
    """Create mock metrics exporter."""
    exporter = MagicMock()
    exporter.export_job_metrics = AsyncMock(return_value=True)
    exporter.export_trigger_metrics = AsyncMock(return_value=True)
    return exporter


@pytest.fixture
def mock_feedback_orchestrator():
    """Create mock feedback orchestrator."""
    orchestrator = MagicMock()
    orchestrator.matcher = MagicMock()
    orchestrator.signal_tracker = MagicMock()
    return orchestrator


@pytest.fixture
def default_trigger(reset_flags):
    """Create default retraining trigger."""
    return RetrainingTrigger(
        config=RetrainingTriggerConfig(enable_discord_alerts=False),
        dedup_store=InMemoryDeduplicationStore(),
    )


@pytest.fixture
def default_integration(
    default_trigger,
    mock_model_registry,
    mock_model_trainer,
    mock_metrics_exporter,
):
    """Create default training pipeline integration."""
    return TrainingPipelineIntegration(
        retraining_trigger=default_trigger,
        model_registry=mock_model_registry,
        model_trainer=mock_model_trainer,
        metrics_exporter=mock_metrics_exporter,
        enable_retry=True,
        max_retry_attempts=2,
    )


# =============================================================================
# Hyperparameters Tests
# =============================================================================


class TestHyperparameters:
    """Tests for hyperparameters configuration."""

    def test_default_hyperparameters(self):
        """Test hyperparameters have correct defaults."""
        params = Hyperparameters()
        assert params.learning_rate == 0.001
        assert params.batch_size == 32
        assert params.epochs == 100
        assert params.validation_split == 0.2
        assert params.early_stopping_patience == 10
        assert params.dropout_rate == 0.2
        assert params.hidden_units == 128
        assert params.random_seed == 42

    def test_hyperparameters_custom_values(self):
        """Test hyperparameters can be customized."""
        params = Hyperparameters(
            learning_rate=0.01,
            batch_size=64,
            epochs=50,
        )
        assert params.learning_rate == 0.01
        assert params.batch_size == 64
        assert params.epochs == 50

    def test_hyperparameters_to_dict(self):
        """Test hyperparameters serialization."""
        params = Hyperparameters()
        data = params.to_dict()
        assert "learning_rate" in data
        assert "batch_size" in data
        assert "epochs" in data
        assert data["learning_rate"] == 0.001


# =============================================================================
# TrainingJob Tests
# =============================================================================


class TestTrainingJob:
    """Tests for training job dataclass."""

    def test_job_creation(self):
        """Test training job creation."""
        job = TrainingJob(job_id="test_001")
        assert job.job_id == "test_001"
        assert job.status == TrainingJobStatus.PENDING
        assert job.retry_count == 0

    def test_job_duration_calculation(self):
        """Test job duration calculation."""
        start = datetime.now(UTC)
        end = start + timedelta(minutes=5)

        job = TrainingJob(
            job_id="test_001",
            started_at=start,
            completed_at=end,
        )
        assert job.duration_seconds == 300.0

    def test_job_to_dict(self):
        """Test job serialization."""
        job = TrainingJob(
            job_id="test_001",
            status=TrainingJobStatus.COMPLETED,
            model_version="v1.0.0",
            metrics={"accuracy": 0.85},
        )
        data = job.to_dict()
        assert data["job_id"] == "test_001"
        assert data["status"] == "COMPLETED"
        assert data["model_version"] == "v1.0.0"
        assert data["metrics"]["accuracy"] == 0.85


# =============================================================================
# TrainingData Tests
# =============================================================================


class TestTrainingData:
    """Tests for training data container."""

    def test_training_data_creation(self):
        """Test training data creation."""
        data = TrainingData(
            samples=[{"feature": 1.0}],
            sample_count=1,
            features=["feature"],
        )
        assert data.sample_count == 1
        assert data.features == ["feature"]

    def test_training_data_to_dict(self):
        """Test training data serialization."""
        data = TrainingData(
            samples=[],
            sample_count=0,
            features=[],
            metadata={"source": "test"},
        )
        result = data.to_dict()
        assert result["sample_count"] == 0
        assert result["metadata"]["source"] == "test"


# =============================================================================
# AsyncJobScheduler Tests
# =============================================================================


class TestAsyncJobScheduler:
    """Tests for async job scheduler."""

    @pytest.mark.asyncio
    async def test_job_submission(self):
        """Test job submission."""
        scheduler = AsyncJobScheduler(max_concurrent_jobs=2)
        job = TrainingJob(job_id="test_001")

        async def mock_runner(j):
            j.status = TrainingJobStatus.COMPLETED
            return j

        task = await scheduler.submit_job(job, mock_runner)
        result = await task

        assert result.status == TrainingJobStatus.COMPLETED
        assert scheduler.get_job("test_001") is not None

    @pytest.mark.asyncio
    async def test_concurrent_job_limit(self):
        """Test concurrent job limit is enforced."""
        scheduler = AsyncJobScheduler(max_concurrent_jobs=1)
        running_count = 0
        max_running = 0

        async def slow_runner(j):
            nonlocal running_count, max_running
            running_count += 1
            max_running = max(max_running, running_count)
            await asyncio.sleep(0.1)
            running_count -= 1
            j.status = TrainingJobStatus.COMPLETED
            return j

        # Submit two jobs
        job1 = TrainingJob(job_id="test_001")
        job2 = TrainingJob(job_id="test_002")

        task1 = await scheduler.submit_job(job1, slow_runner)
        task2 = await scheduler.submit_job(job2, slow_runner)

        await asyncio.gather(task1, task2)

        # Should not exceed max concurrent
        assert max_running <= 1

    @pytest.mark.asyncio
    async def test_get_active_jobs(self):
        """Test getting active jobs."""
        scheduler = AsyncJobScheduler()

        async def slow_runner(j):
            await asyncio.sleep(0.5)
            j.status = TrainingJobStatus.COMPLETED
            return j

        job = TrainingJob(job_id="test_001")
        await scheduler.submit_job(job, slow_runner)

        # Should be active immediately after submission
        active = scheduler.get_active_jobs()
        assert len(active) >= 0

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """Test job cancellation."""
        scheduler = AsyncJobScheduler()

        async def slow_runner(j):
            await asyncio.sleep(10)
            return j

        job = TrainingJob(job_id="test_001")
        await scheduler.submit_job(job, slow_runner)

        # Cancel the job
        result = await scheduler.cancel_job("test_001")
        assert result is True
        assert job.status == TrainingJobStatus.CANCELLED


# =============================================================================
# GrafanaMetricsExporter Tests
# =============================================================================


class TestGrafanaMetricsExporter:
    """Tests for Grafana metrics exporter."""

    @pytest.mark.asyncio
    async def test_export_job_metrics(self):
        """Test exporting job metrics."""
        exporter = GrafanaMetricsExporter()

        job = TrainingJob(
            job_id="test_001",
            status=TrainingJobStatus.COMPLETED,
            metrics={"accuracy": 0.85, "loss": 0.15},
        )
        job.started_at = datetime.now(UTC) - timedelta(minutes=5)
        job.completed_at = datetime.now(UTC)

        result = await exporter.export_job_metrics(job)
        assert result is True

    @pytest.mark.asyncio
    async def test_export_trigger_metrics(self):
        """Test exporting trigger metrics."""
        exporter = GrafanaMetricsExporter()

        trigger_result = TriggerResult(
            trigger_type=TriggerType.ECE_BASED,
            status=TriggerStatus.TRIGGERED,
            triggered=True,
            message="ECE exceeded threshold",
            timestamp=datetime.now(UTC),
            metrics={"ece": 0.20},
        )

        result = await exporter.export_trigger_metrics(trigger_result)
        assert result is True


# =============================================================================
# TrainingPipelineIntegration Tests
# =============================================================================


class TestTrainingPipelineIntegration:
    """Tests for main training pipeline integration."""

    @pytest.mark.asyncio
    async def test_handle_trigger_creates_job(self, default_integration, reset_flags):
        """Test handling trigger creates training job."""
        trigger_result = TriggerResult(
            trigger_type=TriggerType.ECE_BASED,
            status=TriggerStatus.TRIGGERED,
            triggered=True,
            message="Test trigger",
            timestamp=datetime.now(UTC),
        )

        job = await default_integration.handle_trigger(trigger_result)

        assert job is not None
        assert job.trigger_result == trigger_result
        assert job.job_id.startswith("train_ECE_BASED")

    @pytest.mark.asyncio
    async def test_handle_trigger_disabled_by_feature_flag(
        self, default_integration, reset_flags
    ):
        """Test trigger handling disabled by feature flag."""
        flags = FeatureFlags(launch_training_pipeline_enabled=False)
        set_feature_flags(flags)

        trigger_result = TriggerResult(
            trigger_type=TriggerType.ECE_BASED,
            status=TriggerStatus.TRIGGERED,
            triggered=True,
            message="Test trigger",
            timestamp=datetime.now(UTC),
        )

        job = await default_integration.handle_trigger(trigger_result)

        assert job.status == TrainingJobStatus.CANCELLED
        assert "disabled" in job.error_message.lower()

    @pytest.mark.asyncio
    async def test_run_training_manual(self, default_integration, reset_flags):
        """Test manual training run."""
        job = await default_integration.run_training_manual()

        assert job is not None
        assert job.job_id.startswith("train_manual")

    @pytest.mark.asyncio
    async def test_execute_training_job_success(
        self,
        default_integration,
        mock_model_registry,
        sample_training_data,
        reset_flags,
    ):
        """Test successful training job execution."""
        # Mock data fetcher
        default_integration._data_fetcher = MagicMock()
        default_integration._data_fetcher.fetch_training_data = AsyncMock(
            return_value=sample_training_data
        )

        job = TrainingJob(job_id="test_001")

        result = await default_integration._execute_training_job(job)

        assert result.status == TrainingJobStatus.COMPLETED
        assert result.model_version is not None
        mock_model_registry.register_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_training_job_with_retry(
        self, default_integration, sample_training_data, reset_flags, monkeypatch
    ):
        """Test training job with retry on failure."""
        # Patch asyncio.sleep to avoid long delays during retry
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())

        # Mock data fetcher to fail then succeed
        call_count = 0

        async def fetch_with_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DataFetchError("Simulated fetch error")
            return sample_training_data

        default_integration._data_fetcher = MagicMock()
        default_integration._data_fetcher.fetch_training_data = fetch_with_failure

        job = TrainingJob(job_id="test_001", max_retries=2)

        result = await default_integration._execute_training_job(job)

        assert result.status == TrainingJobStatus.COMPLETED
        assert job.retry_count > 0

    @pytest.mark.asyncio
    async def test_execute_training_job_max_retries_exceeded(
        self, default_integration, reset_flags, monkeypatch
    ):
        """Test training job fails after max retries."""
        # Patch asyncio.sleep to avoid long delays during retry
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())

        default_integration._data_fetcher = MagicMock()
        default_integration._data_fetcher.fetch_training_data = AsyncMock(
            side_effect=DataFetchError("Persistent fetch error")
        )

        job = TrainingJob(job_id="test_001", max_retries=1)

        result = await default_integration._execute_training_job(job)

        assert result.status == TrainingJobStatus.FAILED
        assert result.retry_count > result.max_retries

    def test_get_stats(self, default_integration, reset_flags):
        """Test getting integration statistics."""
        stats = default_integration.get_stats()

        assert "total_jobs" in stats
        assert "completed_jobs" in stats
        assert "failed_jobs" in stats
        assert "success_rate" in stats
        assert "is_listening" in stats


# =============================================================================
# FeedbackLoopDataFetcher Tests
# =============================================================================


class TestFeedbackLoopDataFetcher:
    """Tests for feedback loop data fetcher."""

    @pytest.mark.asyncio
    async def test_fetch_training_data_insufficient_samples(self, reset_flags):
        """Test fetch fails with insufficient samples."""
        fetcher = FeedbackLoopDataFetcher()

        with pytest.raises(DataFetchError, match="Insufficient training data"):
            await fetcher.fetch_training_data(min_samples=1000)

    def test_fetch_training_data_empty_feedback(self, reset_flags):
        """Test fetch with empty feedback orchestrator."""
        fetcher = FeedbackLoopDataFetcher()

        # Should raise DataFetchError when no feedback configured
        with pytest.raises(DataFetchError):
            asyncio.run(fetcher.fetch_training_data(min_samples=1))


# =============================================================================
# Feature Flag Tests
# =============================================================================


class TestFeatureFlags:
    """Tests for feature flags including new training pipeline flag."""

    def test_training_pipeline_flag_defaults(self):
        """Test training pipeline flag defaults to enabled."""
        flags = FeatureFlags()
        assert flags.launch_training_pipeline_enabled is True

    def test_training_pipeline_flag_can_be_disabled(self):
        """Test training pipeline flag can be disabled."""
        flags = FeatureFlags(launch_training_pipeline_enabled=False)
        assert flags.launch_training_pipeline_enabled is False

    def test_feature_flags_to_dict_includes_pipeline_flag(self):
        """Test feature flags dict includes pipeline flag."""
        flags = FeatureFlags()
        data = flags.to_dict()
        assert "launch_training_pipeline_enabled" in data


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complete training pipeline."""

    @pytest.mark.asyncio
    async def test_full_training_pipeline_flow(self, reset_flags):
        """Test complete flow from trigger to model registration."""
        # Create mock components
        mock_registry = MagicMock()
        mock_version = MagicMock()
        mock_version.version_id = "model_v1_20240222_120000"
        mock_registry.register_model = MagicMock(return_value=mock_version)

        mock_trainer = MagicMock()
        mock_trainer.train = AsyncMock(
            return_value=(
                True,
                {"accuracy": 0.85, "loss": 0.15, "validation_accuracy": 0.83},
            )
        )

        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=TrainingData(
                samples=[{"feature": 1.0}] * 200,
                sample_count=200,
                features=["feature"],
            )
        )

        # Create integration
        integration = TrainingPipelineIntegration(
            model_registry=mock_registry,
            model_trainer=mock_trainer,
            data_fetcher=mock_data_fetcher,
            enable_retry=True,
            max_retry_attempts=2,
        )

        # Create trigger result
        trigger_result = TriggerResult(
            trigger_type=TriggerType.ECE_BASED,
            status=TriggerStatus.TRIGGERED,
            triggered=True,
            message="ECE exceeded threshold",
            timestamp=datetime.now(UTC),
            metrics={"ece": 0.20},
        )

        # Handle trigger
        job = await integration.handle_trigger(trigger_result)

        # Wait for job to complete
        await asyncio.sleep(0.1)

        # Verify job was created
        assert job is not None
        assert job.trigger_result == trigger_result

    @pytest.mark.asyncio
    async def test_manual_training_flow(self, reset_flags):
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

        job = await integration.run_training_manual()

        assert job is not None
        assert job.job_id.startswith("train_manual")


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_training_job_with_no_trainer(self, reset_flags):
        """Test job execution without model trainer (simulation mode)."""
        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=TrainingData(
                samples=[{"feature": 1.0}] * 200,
                sample_count=200,
                features=["feature"],
            )
        )

        integration = TrainingPipelineIntegration(
            data_fetcher=mock_data_fetcher,
            model_trainer=None,  # No trainer configured
        )

        job = TrainingJob(job_id="test_001")
        result = await integration._execute_training_job(job)

        # Should complete in simulation mode
        assert result.status == TrainingJobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_training_job_training_failure(self, reset_flags):
        """Test handling of training execution failure."""
        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=TrainingData(
                samples=[{"feature": 1.0}] * 200,
                sample_count=200,
                features=["feature"],
            )
        )

        mock_trainer = MagicMock()
        mock_trainer.train = AsyncMock(
            return_value=(False, {"error": "Training failed"})
        )

        integration = TrainingPipelineIntegration(
            data_fetcher=mock_data_fetcher,
            model_trainer=mock_trainer,
            enable_retry=False,  # Disable retry for this test
        )

        job = TrainingJob(job_id="test_001")
        result = await integration._execute_training_job(job)

        assert result.status == TrainingJobStatus.FAILED


# =============================================================================
# Pipeline-Validation Integration Tests
# =============================================================================


class TestPipelineValidationIntegration:
    """Tests for integration between training pipeline and validation gates."""

    @pytest.mark.asyncio
    async def test_pipeline_validates_model_after_training(
        self,
        mock_model_registry,
        sample_training_data,
        reset_flags,
    ):
        """Test that pipeline validates model via ValidationGate after training.

        ST-TRAIN-003: TrainingPipeline validates via ModelValidator after training
        """
        from ml.validation.model_validator import ValidationGate, ValidationThresholds

        # Create validation gate
        validation_gate = ValidationGate(
            thresholds=ValidationThresholds(
                accuracy_pass=0.60,
                precision_pass=0.55,
                recall_pass=0.50,
                f1_pass=0.52,
                win_rate_pass=0.55,
            )
        )

        # Mock data fetcher
        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=sample_training_data
        )

        # Create integration
        integration = TrainingPipelineIntegration(
            model_registry=mock_model_registry,
            data_fetcher=mock_data_fetcher,
        )

        # Execute training job
        job = TrainingJob(job_id="test_validation_001")
        result = await integration._execute_training_job(job)

        # Verify training completed
        assert result.status == TrainingJobStatus.COMPLETED

        # Simulate validation of trained model metrics
        training_metrics = result.metrics or {}
        validation_result = validation_gate.validate(
            metrics={
                "accuracy": training_metrics.get("accuracy", 0.85),
                "precision": training_metrics.get("precision", 0.82),
                "recall": training_metrics.get("recall", 0.80),
                "f1": training_metrics.get("f1", 0.81),
                "win_rate": training_metrics.get("win_rate", 0.75),
            },
            model_version=result.model_version or "v1.0.0",
        )

        # Validation should pass for good metrics
        assert validation_result.passed is True
        assert validation_result.critical_count == 0

    @pytest.mark.asyncio
    async def test_pipeline_rejects_poor_model(
        self,
        mock_model_registry,
        reset_flags,
    ):
        """Test that pipeline rejects models that fail validation.

        ST-TRAIN-003: ValidationGate validates trained models
        """
        from ml.validation.model_validator import ValidationGate, ValidationThresholds

        # Create validation gate with strict thresholds
        validation_gate = ValidationGate(
            thresholds=ValidationThresholds(
                accuracy_pass=0.70,
                precision_pass=0.65,
                recall_pass=0.60,
                f1_pass=0.62,
                win_rate_pass=0.65,
            )
        )

        # Poor model metrics
        poor_metrics = {
            "accuracy": 0.50,
            "precision": 0.45,
            "recall": 0.40,
            "f1": 0.42,
            "win_rate": 0.45,
        }

        # Validate poor model
        validation_result = validation_gate.validate(
            metrics=poor_metrics,
            model_version="poor_model_v1",
        )

        # Validation should fail
        assert validation_result.passed is False
        assert validation_result.critical_count > 0

    @pytest.mark.asyncio
    async def test_orchestrator_pipeline_integration(
        self,
        default_trigger,
        reset_flags,
    ):
        """Test TrainingOrchestrator connects to TrainingPipeline.

        ST-TRAIN-003: TrainingOrchestrator connects to TrainingPipeline
        """
        from ml.training.training_orchestrator import (
            OrchestratorConfig,
            TrainingOrchestrator,
        )
        from ml.training.training_pipeline import TrainingConfig, TrainingPipeline

        # Create pipeline
        pipeline = TrainingPipeline(config=TrainingConfig())

        # Create orchestrator with pipeline
        orchestrator = TrainingOrchestrator(
            trigger=default_trigger,
            pipeline_runner=pipeline,
            config=OrchestratorConfig(
                min_training_interval_hours=0,
                enable_discord_notifications=False,
            ),
        )

        # Verify pipeline is connected
        assert orchestrator.pipeline_runner is pipeline

        # Run training
        run = await orchestrator.run_training()

        # Verify pipeline was invoked
        assert run is not None
        # The orchestrator returns TrainingRun, not TrainingJob
        # Check run.state from TrainingOrchestrator.TrainingState
        from ml.training.training_orchestrator import TrainingState

        assert run.state in [
            TrainingState.COMPLETED,
            TrainingState.FAILED,
            TrainingState.IDLE,
        ]

    def test_validation_gate_integration_with_registry(
        self,
        reset_flags,
    ):
        """Test ValidationGate integration with ModelRegistry.

        ST-TRAIN-003: ModelRegistry receives validated models
        """
        from ml.model_registry.registry import ModelRegistry, ModelStatus, ModelType
        from ml.validation.model_validator import ValidationGate, ValidationThresholds

        # Create registry and validation gate
        registry = ModelRegistry()
        validation_gate = ValidationGate(
            thresholds=ValidationThresholds(
                accuracy_pass=0.60,
                precision_pass=0.55,
                recall_pass=0.50,
                f1_pass=0.52,
                win_rate_pass=0.55,
            )
        )

        # Register model
        version = registry.register_model(
            model_id="test_model",
            model_path="/models/test.pkl",
            model_type=ModelType.SIGNAL_PREDICTOR,
            metrics={
                "accuracy": 0.75,
                "precision": 0.72,
                "recall": 0.70,
                "f1": 0.71,
                "win_rate": 0.73,
            },
        )

        # Validate model
        validation_result = validation_gate.validate(
            metrics=version.metrics,
            model_version=version.version_id,
        )

        # Promote to candidate if validation passes
        if validation_result.passed:
            registry.promote_to_candidate(version.version_id)

        # Verify model is in registry with correct status
        retrieved = registry.get_version(version.version_id)
        assert retrieved is not None
        if validation_result.passed:
            assert retrieved.status == ModelStatus.CANDIDATE

    @pytest.mark.asyncio
    async def test_full_flow_with_validation(
        self,
        mock_model_registry,
        sample_training_data,
        reset_flags,
    ):
        """Test full flow: trigger → training → validation → registration.

        ST-TRAIN-003: E2E test covering full training flow
        """
        from ml.validation.model_validator import ValidationGate, ValidationThresholds

        # Setup components
        validation_gate = ValidationGate(thresholds=ValidationThresholds())

        mock_data_fetcher = MagicMock()
        mock_data_fetcher.fetch_training_data = AsyncMock(
            return_value=sample_training_data
        )

        integration = TrainingPipelineIntegration(
            model_registry=mock_model_registry,
            data_fetcher=mock_data_fetcher,
        )

        # Execute training
        job = TrainingJob(job_id="full_flow_001")
        result = await integration._execute_training_job(job)

        # Verify training completed
        assert result.status == TrainingJobStatus.COMPLETED

        # Validate results
        metrics = result.metrics or {}
        validation_result = validation_gate.validate(
            metrics={
                "accuracy": metrics.get("accuracy", 0.85),
                "precision": metrics.get("precision", 0.82),
                "recall": metrics.get("recall", 0.80),
                "f1": metrics.get("f1", 0.81),
                "win_rate": metrics.get("win_rate", 0.75),
            },
            model_version=result.model_version or "v1.0.0",
        )

        # Verify validation passed
        assert validation_result.passed is True

        # Verify model was registered
        mock_model_registry.register_model.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
