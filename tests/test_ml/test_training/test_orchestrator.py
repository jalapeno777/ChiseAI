"""Unit tests for training_orchestrator.py module.

Tests TrainingOrchestrator and related components.
For ST-TRAIN-001: Training Pipeline Core
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from ml.training.training_orchestrator import (
    OrchestratorConfig,
    TrainingOrchestrator,
    TrainingRun,
    TrainingState,
    TrainingStatus,
)


class TestTrainingState:
    """Tests for TrainingState enum."""

    def test_all_states_exist(self):
        """Test all required states exist."""
        states = [
            TrainingState.IDLE,
            TrainingState.VALIDATING,
            TrainingState.PREPARING,
            TrainingState.TRAINING,
            TrainingState.COMPLETED,
            TrainingState.FAILED,
            TrainingState.CANCELLED,
        ]
        for state in states:
            assert state is not None


class TestTrainingStatus:
    """Tests for TrainingStatus enum."""

    def test_all_statuses_exist(self):
        """Test all required statuses exist."""
        statuses = [
            TrainingStatus.SUCCESS,
            TrainingStatus.VALIDATION_FAILED,
            TrainingStatus.NO_DATA,
            TrainingStatus.ALREADY_RUNNING,
            TrainingStatus.ERROR,
            TrainingStatus.CANCELLED,
        ]
        for status in statuses:
            assert status is not None


class TestTrainingRun:
    """Tests for TrainingRun dataclass."""

    def test_default_creation(self):
        """Test creating run with defaults."""
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.IDLE,
        )
        assert run.run_id == "test_001"
        assert run.trigger_type == "ECE"
        assert run.state == TrainingState.IDLE
        assert run.status is None
        assert run.started_at is None
        assert run.completed_at is None

    def test_duration_calculation(self):
        """Test duration calculation."""
        started = datetime.now(UTC) - timedelta(hours=1)
        completed = datetime.now(UTC)
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            started_at=started,
            completed_at=completed,
        )
        assert run.duration_seconds == pytest.approx(3600.0, abs=1.0)

    def test_duration_none_when_incomplete(self):
        """Test duration is None when not completed."""
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.TRAINING,
            started_at=datetime.now(UTC),
        )
        assert run.duration_seconds is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        started = datetime.now(UTC)
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            status=TrainingStatus.SUCCESS,
            started_at=started,
            model_version="1.0.0",
            metrics={"accuracy": 0.85},
        )
        result = run.to_dict()
        assert result["run_id"] == "test_001"
        assert result["trigger_type"] == "ECE"
        assert result["state"] == "COMPLETED"
        assert result["status"] == "SUCCESS"
        assert result["model_version"] == "1.0.0"
        assert result["metrics"]["accuracy"] == 0.85


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = OrchestratorConfig()
        assert config.min_training_interval_hours == 1
        assert config.max_training_duration_hours == 4
        assert config.enable_auto_trigger is True
        assert config.enable_discord_notifications is True
        assert config.training_channel_id is None
        assert config.validation_timeout_seconds == 60.0

    def test_custom_config(self):
        """Test creating config with custom values."""
        config = OrchestratorConfig(
            min_training_interval_hours=2,
            max_training_duration_hours=8,
            enable_auto_trigger=False,
            enable_discord_notifications=False,
            training_channel_id="123456",
            validation_timeout_seconds=120.0,
        )
        assert config.min_training_interval_hours == 2
        assert config.max_training_duration_hours == 8
        assert config.enable_auto_trigger is False
        assert config.enable_discord_notifications is False
        assert config.training_channel_id == "123456"
        assert config.validation_timeout_seconds == 120.0


class TestTrainingOrchestrator:
    """Tests for TrainingOrchestrator class."""

    @pytest.fixture
    def mock_trigger(self):
        """Create mock retraining trigger."""
        trigger = MagicMock()
        trigger.evaluate_all = AsyncMock()
        trigger.should_trigger_retraining = MagicMock(return_value=(False, []))
        trigger.validate_training_readiness = AsyncMock(
            return_value=(True, 95.0, "Validation passed")
        )
        return trigger

    @pytest.fixture
    def mock_pipeline_runner(self):
        """Create mock pipeline runner."""
        runner = AsyncMock()
        runner.run_training = AsyncMock(return_value=(True, {"accuracy": 0.85}))
        return runner

    @pytest.fixture
    def mock_data_provider(self):
        """Create mock data provider."""
        provider = AsyncMock()
        provider.get_training_data_summary = AsyncMock(
            return_value={
                "sample_count": 1000,
                "valid_samples": 950,
                "missing_features_pct": 2.0,
                "stale_data_pct": 1.0,
            }
        )
        provider.prepare_training_data = AsyncMock(return_value=(True, 950))
        return provider

    def test_default_creation(self):
        """Test creating orchestrator with defaults."""
        orchestrator = TrainingOrchestrator()
        assert orchestrator.trigger is None
        assert orchestrator.pipeline_runner is None
        assert orchestrator.data_provider is None
        assert orchestrator.config is not None
        assert orchestrator.get_current_run() is None

    def test_custom_creation(
        self,
        mock_trigger,
        mock_pipeline_runner,
        mock_data_provider,
    ):
        """Test creating orchestrator with custom components."""
        config = OrchestratorConfig()
        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            pipeline_runner=mock_pipeline_runner,
            data_provider=mock_data_provider,
            config=config,
        )
        assert orchestrator.trigger == mock_trigger
        assert orchestrator.pipeline_runner == mock_pipeline_runner
        assert orchestrator.data_provider == mock_data_provider
        assert orchestrator.config == config

    @pytest.mark.asyncio
    async def test_generate_run_id(self):
        """Test run ID generation."""
        orchestrator = TrainingOrchestrator()
        run_id = orchestrator._generate_run_id()
        assert run_id.startswith("training_")
        assert len(run_id) > 9  # "training_" + timestamp

    @pytest.mark.asyncio
    async def test_check_training_interval_no_history(self):
        """Test interval check with no history."""
        orchestrator = TrainingOrchestrator()
        result = await orchestrator._check_training_interval()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_training_interval_with_recent_run(self):
        """Test interval check with recent run."""
        config = OrchestratorConfig(min_training_interval_hours=1)
        orchestrator = TrainingOrchestrator(config=config)

        # Add a recent completed run
        recent_run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        orchestrator._run_history.append(recent_run)

        result = await orchestrator._check_training_interval()
        assert result is False  # Should not allow training yet

    @pytest.mark.asyncio
    async def test_check_training_interval_with_old_run(self):
        """Test interval check with old run."""
        config = OrchestratorConfig(min_training_interval_hours=1)
        orchestrator = TrainingOrchestrator(config=config)

        # Add an old completed run
        old_run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(hours=2),
        )
        orchestrator._run_history.append(old_run)

        result = await orchestrator._check_training_interval()
        assert result is True  # Should allow training now

    @pytest.mark.asyncio
    async def test_validate_data_success(self, mock_trigger, mock_data_provider):
        """Test successful data validation."""
        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            data_provider=mock_data_provider,
        )

        is_valid, quality_pct, message = await orchestrator._validate_data()

        assert is_valid is True
        assert quality_pct == 95.0
        assert "passed" in message

    @pytest.mark.asyncio
    async def test_validate_data_no_trigger(self, mock_data_provider):
        """Test validation without trigger."""
        orchestrator = TrainingOrchestrator(data_provider=mock_data_provider)

        is_valid, quality_pct, message = await orchestrator._validate_data()

        assert is_valid is False
        assert quality_pct == 0.0
        assert "No trigger system configured" in message

    @pytest.mark.asyncio
    async def test_validate_data_no_provider(self, mock_trigger):
        """Test validation without data provider."""
        orchestrator = TrainingOrchestrator(trigger=mock_trigger)

        is_valid, quality_pct, message = await orchestrator._validate_data()

        assert is_valid is False
        assert quality_pct == 0.0
        assert "No data provider configured" in message

    @pytest.mark.asyncio
    async def test_run_training_already_running(self):
        """Test training rejected when already running."""
        orchestrator = TrainingOrchestrator()

        # Set up a current running training
        orchestrator._current_run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.TRAINING,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.ALREADY_RUNNING
        assert "already in progress" in result.error_message

    @pytest.mark.asyncio
    async def test_run_training_interval_not_met(self):
        """Test training rejected when interval not met."""
        config = OrchestratorConfig(min_training_interval_hours=1)
        orchestrator = TrainingOrchestrator(config=config)

        # Add a recent completed run
        recent_run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        orchestrator._run_history.append(recent_run)

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.ERROR
        assert "interval not met" in result.error_message

    @pytest.mark.asyncio
    async def test_run_training_validation_failure(
        self,
        mock_trigger,
        mock_data_provider,
    ):
        """Test training with validation failure."""
        mock_trigger.validate_training_readiness = AsyncMock(
            return_value=(False, 80.0, "Quality too low")
        )

        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            data_provider=mock_data_provider,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.VALIDATION_FAILED
        assert "Quality too low" in result.error_message

    @pytest.mark.asyncio
    async def test_run_training_no_pipeline_runner(
        self, mock_trigger, mock_data_provider
    ):
        """Test training without pipeline runner."""
        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            data_provider=mock_data_provider,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.ERROR
        assert "No pipeline runner configured" in result.error_message

    @pytest.mark.asyncio
    async def test_run_training_success(
        self,
        mock_trigger,
        mock_pipeline_runner,
        mock_data_provider,
    ):
        """Test successful training run."""
        mock_pipeline_runner.run_training = AsyncMock(
            return_value=(True, {"accuracy": 0.85, "model_version": "1.0.0"})
        )

        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            pipeline_runner=mock_pipeline_runner,
            data_provider=mock_data_provider,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.SUCCESS
        assert result.model_version == "1.0.0"
        assert result.metrics["accuracy"] == 0.85

    @pytest.mark.asyncio
    async def test_run_training_failure(
        self,
        mock_trigger,
        mock_pipeline_runner,
        mock_data_provider,
    ):
        """Test failed training run."""
        mock_pipeline_runner.run_training = AsyncMock(
            return_value=(False, {"error": "Out of memory"})
        )

        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            pipeline_runner=mock_pipeline_runner,
            data_provider=mock_data_provider,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.ERROR
        assert "Out of memory" in result.error_message

    @pytest.mark.asyncio
    async def test_run_training_timeout(
        self,
        mock_trigger,
        mock_pipeline_runner,
        mock_data_provider,
    ):
        """Test training timeout."""
        mock_pipeline_runner.run_training = AsyncMock(side_effect=TimeoutError())

        config = OrchestratorConfig(max_training_duration_hours=1)
        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            pipeline_runner=mock_pipeline_runner,
            data_provider=mock_data_provider,
            config=config,
        )

        result = await orchestrator.run_training()

        assert result.status == TrainingStatus.ERROR
        assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_evaluate_triggers_and_train_no_trigger(self):
        """Test evaluate triggers with no trigger configured."""
        orchestrator = TrainingOrchestrator()
        result = await orchestrator.evaluate_triggers_and_train()
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_triggers_and_train_auto_disabled(self, mock_trigger):
        """Test evaluate triggers with auto-trigger disabled."""
        config = OrchestratorConfig(enable_auto_trigger=False)
        orchestrator = TrainingOrchestrator(
            trigger=mock_trigger,
            config=config,
        )
        result = await orchestrator.evaluate_triggers_and_train()
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_triggers_and_train_no_trigger_fired(self, mock_trigger):
        """Test evaluate triggers when no trigger fires."""
        mock_trigger.evaluate_all = AsyncMock(return_value=[])
        mock_trigger.should_trigger_retraining = MagicMock(return_value=(False, []))

        orchestrator = TrainingOrchestrator(trigger=mock_trigger)
        result = await orchestrator.evaluate_triggers_and_train()

        assert result is None

    def test_get_current_run(self):
        """Test getting current run."""
        orchestrator = TrainingOrchestrator()
        assert orchestrator.get_current_run() is None

        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.TRAINING,
        )
        orchestrator._current_run = run

        assert orchestrator.get_current_run() == run

    def test_get_run_history(self):
        """Test getting run history."""
        orchestrator = TrainingOrchestrator()

        # Add some runs
        for i in range(5):
            run = TrainingRun(
                run_id=f"test_{i:03d}",
                trigger_type="ECE",
                state=TrainingState.COMPLETED,
            )
            orchestrator._run_history.append(run)

        history = orchestrator.get_run_history(limit=3)
        assert len(history) == 3
        assert history[0].run_id == "test_002"
        assert history[2].run_id == "test_004"

    def test_get_stats(self):
        """Test getting orchestrator statistics."""
        orchestrator = TrainingOrchestrator()

        # Add some runs
        for i in range(5):
            run = TrainingRun(
                run_id=f"success_{i}",
                trigger_type="ECE",
                state=TrainingState.COMPLETED,
                status=TrainingStatus.SUCCESS,
            )
            orchestrator._run_history.append(run)

        for i in range(3):
            run = TrainingRun(
                run_id=f"failed_{i}",
                trigger_type="ECE",
                state=TrainingState.FAILED,
                status=TrainingStatus.ERROR,
            )
            orchestrator._run_history.append(run)

        stats = orchestrator.get_stats()

        assert stats["total_runs"] == 8
        assert stats["successful_runs"] == 5
        assert stats["failed_runs"] == 3
        assert stats["success_rate"] == 5 / 8
        assert stats["current_state"] == "idle"
        assert stats["is_monitoring"] is False


class TestAcceptanceCriteria:
    """Tests verifying ST-TRAIN-001 acceptance criteria for orchestrator."""

    def test_ac_1_trigger_integration(self):
        """AC1: Verify trigger-based training initiation exists."""
        mock_trigger = MagicMock()
        orchestrator = TrainingOrchestrator(trigger=mock_trigger)
        assert orchestrator.trigger is not None
        assert hasattr(orchestrator, "evaluate_triggers_and_train")

    def test_ac_2_pre_training_validation(self):
        """AC2: Verify pre-training validation exists."""
        orchestrator = TrainingOrchestrator()
        assert hasattr(orchestrator, "_validate_data")

    def test_ac_3_state_management(self):
        """AC3: Verify state management exists."""
        orchestrator = TrainingOrchestrator()
        assert hasattr(orchestrator, "get_current_run")
        assert hasattr(orchestrator, "get_run_history")
        assert hasattr(orchestrator, "get_stats")

        # Verify all states exist
        states = [
            TrainingState.IDLE,
            TrainingState.VALIDATING,
            TrainingState.PREPARING,
            TrainingState.TRAINING,
            TrainingState.COMPLETED,
            TrainingState.FAILED,
        ]
        for state in states:
            assert state is not None

    def test_ac_4_discord_notifications(self):
        """AC4: Verify Discord notification support exists."""
        config = OrchestratorConfig(enable_discord_notifications=True)
        orchestrator = TrainingOrchestrator(config=config)

        assert config.enable_discord_notifications is True
        assert hasattr(orchestrator, "_notify_training_start")
        assert hasattr(orchestrator, "_notify_training_complete")

    def test_ac_5_training_run_tracking(self):
        """AC5: Verify training run tracking exists."""
        run = TrainingRun(
            run_id="test_001",
            trigger_type="ECE",
            state=TrainingState.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        assert run.run_id is not None
        assert run.trigger_type is not None
        assert run.duration_seconds is not None

    def test_ac_6_configurable_timeouts(self):
        """AC6: Verify configurable timeouts exist."""
        config = OrchestratorConfig(
            max_training_duration_hours=4,
            validation_timeout_seconds=60.0,
        )
        assert config.max_training_duration_hours == 4
        assert config.validation_timeout_seconds == 60.0

    def test_ac_7_interval_control(self):
        """AC7: Verify training interval control exists."""
        config = OrchestratorConfig(min_training_interval_hours=1)
        orchestrator = TrainingOrchestrator(config=config)

        assert config.min_training_interval_hours == 1
        assert hasattr(orchestrator, "_check_training_interval")
