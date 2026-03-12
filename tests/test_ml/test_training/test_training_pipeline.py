"""Unit tests for training_pipeline.py module.

Tests TrainingPipeline, TrainingDataLoader, ModelValidator, and related components.
For ST-TRAIN-001: Training Pipeline Core
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "/home/tacopants/projects/ChiseAI/src")

from ml.training.training_pipeline import (
    CheckpointInfo,
    DataQualityReport,
    DataSplit,
    ModelValidator,
    TrainingConfig,
    TrainingDataLoader,
    TrainingMetrics,
    TrainingMode,
    TrainingPipeline,
    TrainingStatus,
    ValidationReport,
    create_training_pipeline,
)


class TestTrainingMode:
    """Tests for TrainingMode enum."""

    def test_incremental_mode(self):
        """Test INCREMENTAL mode exists."""
        assert TrainingMode.INCREMENTAL is not None
        assert TrainingMode.INCREMENTAL.name == "INCREMENTAL"

    def test_full_mode(self):
        """Test FULL mode exists."""
        assert TrainingMode.FULL is not None
        assert TrainingMode.FULL.name == "FULL"


class TestTrainingStatus:
    """Tests for TrainingStatus enum."""

    def test_all_statuses_exist(self):
        """Test all required statuses exist."""
        statuses = [
            TrainingStatus.PENDING,
            TrainingStatus.VALIDATING,
            TrainingStatus.PREPARING,
            TrainingStatus.TRAINING,
            TrainingStatus.VALIDATING_MODEL,
            TrainingStatus.COMPLETED,
            TrainingStatus.FAILED,
            TrainingStatus.CANCELLED,
        ]
        for status in statuses:
            assert status is not None


class TestDataSplit:
    """Tests for DataSplit dataclass."""

    def test_default_creation(self):
        """Test creating DataSplit with defaults."""
        split = DataSplit()
        assert split.train == []
        assert split.validation == []
        assert split.test == []
        assert split.total_count == 0

    def test_with_data(self):
        """Test DataSplit with sample data."""
        train = [1, 2, 3, 4, 5, 6, 7]
        validation = [8, 9]
        test = [10, 11]
        split = DataSplit(train=train, validation=validation, test=test)
        assert split.total_count == 11

    def test_to_dict(self):
        """Test conversion to dictionary."""
        train = [1] * 70
        validation = [1] * 15
        test = [1] * 15
        split = DataSplit(train=train, validation=validation, test=test)
        result = split.to_dict()
        assert result["train_count"] == 70
        assert result["validation_count"] == 15
        assert result["test_count"] == 15
        assert result["total_count"] == 100
        assert result["split_ratio"] == "70/15/15"


class TestDataQualityReport:
    """Tests for DataQualityReport dataclass."""

    def test_default_creation(self):
        """Test creating report with defaults."""
        report = DataQualityReport()
        assert report.total_samples == 0
        assert report.valid_samples == 0
        assert report.quality_score == 0.0
        assert report.issues == []
        assert not report.is_acceptable

    def test_is_acceptable_true(self):
        """Test is_acceptable when quality >= 90%."""
        report = DataQualityReport(
            total_samples=100,
            valid_samples=95,
            quality_score=0.95,
        )
        assert report.is_acceptable

    def test_is_acceptable_false(self):
        """Test is_acceptable when quality < 90%."""
        report = DataQualityReport(
            total_samples=100,
            valid_samples=80,
            quality_score=0.80,
        )
        assert not report.is_acceptable

    def test_to_dict(self):
        """Test conversion to dictionary."""
        report = DataQualityReport(
            total_samples=100,
            valid_samples=95,
            quality_score=0.95,
            issues=["Some issue"],
        )
        result = report.to_dict()
        assert result["total_samples"] == 100
        assert result["valid_samples"] == 95
        assert result["quality_score"] == 0.95
        assert result["quality_pct"] == 95.0
        assert result["is_acceptable"] is True
        assert result["issues"] == ["Some issue"]


class TestTrainingMetrics:
    """Tests for TrainingMetrics dataclass."""

    def test_default_creation(self):
        """Test creating metrics with defaults."""
        metrics = TrainingMetrics()
        assert metrics.accuracy == 0.0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0
        assert metrics.loss == 0.0
        assert metrics.validation_accuracy == 0.0
        assert metrics.training_time_seconds == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = TrainingMetrics(
            accuracy=0.85,
            precision=0.84,
            recall=0.86,
            f1=0.85,
            loss=0.15,
            validation_accuracy=0.83,
            training_time_seconds=3600.0,
        )
        result = metrics.to_dict()
        assert result["accuracy"] == 0.85
        assert result["precision"] == 0.84
        assert result["recall"] == 0.86
        assert result["f1"] == 0.85
        assert result["loss"] == 0.15
        assert result["validation_accuracy"] == 0.83
        assert result["training_time_seconds"] == 3600.0


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_default_creation(self):
        """Test creating report with defaults."""
        report = ValidationReport()
        assert report.model_version == ""
        assert report.baseline_version == ""
        assert not report.passed
        assert report.threshold == -0.05

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = TrainingMetrics(accuracy=0.85)
        baseline = TrainingMetrics(accuracy=0.82)
        report = ValidationReport(
            model_version="1.0.0",
            baseline_version="0.9.0",
            test_metrics=metrics,
            baseline_metrics=baseline,
            passed=True,
            margin=0.03,
            recommendation="APPROVED",
        )
        result = report.to_dict()
        assert result["model_version"] == "1.0.0"
        assert result["baseline_version"] == "0.9.0"
        assert result["passed"] is True
        assert result["accuracy_margin"] == 0.03
        assert result["threshold"] == -0.05
        assert result["recommendation"] == "APPROVED"


class TestTrainingConfig:
    """Tests for TrainingConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = TrainingConfig()
        assert config.training_mode == TrainingMode.INCREMENTAL
        assert config.train_ratio == 0.70
        assert config.validation_ratio == 0.15
        assert config.test_ratio == 0.15
        assert config.incremental_days == 30
        assert config.incremental_sla_hours == 4.0
        assert config.full_sla_hours == 24.0
        assert config.checkpoint_interval_hours == 1.0
        assert config.quality_threshold == 0.90
        assert config.baseline_accuracy_margin == -0.05
        assert config.random_seed == 42
        assert config.max_memory_gb == 8.0

    def test_invalid_split_ratios(self):
        """Test that invalid split ratios raise error."""
        with pytest.raises(ValueError, match="Split ratios must sum to 1.0"):
            TrainingConfig(train_ratio=0.5, validation_ratio=0.3, test_ratio=0.3)

    def test_sla_hours_incremental(self):
        """Test SLA hours for incremental mode."""
        config = TrainingConfig(training_mode=TrainingMode.INCREMENTAL)
        assert config.sla_hours == 4.0

    def test_sla_hours_full(self):
        """Test SLA hours for full mode."""
        config = TrainingConfig(training_mode=TrainingMode.FULL)
        assert config.sla_hours == 24.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = TrainingConfig()
        result = config.to_dict()
        assert result["training_mode"] == "INCREMENTAL"
        assert result["train_ratio"] == 0.70
        assert result["validation_ratio"] == 0.15
        assert result["test_ratio"] == 0.15
        assert result["incremental_days"] == 30
        assert result["sla_hours"] == 4.0
        assert result["quality_threshold"] == 0.90
        assert result["random_seed"] == 42
        assert result["max_memory_gb"] == 8.0


class TestCheckpointInfo:
    """Tests for CheckpointInfo dataclass."""

    def test_creation(self):
        """Test creating checkpoint info."""
        now = datetime.now(UTC)
        checkpoint = CheckpointInfo(
            checkpoint_id="ckpt_001",
            timestamp=now,
            epoch=10,
            metrics={"accuracy": 0.85},
            path="/path/to/checkpoint",
        )
        assert checkpoint.checkpoint_id == "ckpt_001"
        assert checkpoint.epoch == 10
        assert checkpoint.metrics["accuracy"] == 0.85

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        checkpoint = CheckpointInfo(
            checkpoint_id="ckpt_001",
            timestamp=now,
            epoch=10,
            metrics={"accuracy": 0.85},
        )
        result = checkpoint.to_dict()
        assert result["checkpoint_id"] == "ckpt_001"
        assert result["epoch"] == 10
        assert result["metrics"]["accuracy"] == 0.85


class TestTrainingDataLoader:
    """Tests for TrainingDataLoader class."""

    @pytest.fixture
    def mock_feature_extractor(self):
        """Create mock feature extractor."""
        return MagicMock()

    @pytest.fixture
    def mock_signal_storage(self):
        """Create mock signal storage."""
        return MagicMock()

    @pytest.fixture
    def mock_sample(self):
        """Create a mock training sample."""
        sample = MagicMock()
        sample.token = "BTC"
        sample.timeframe = "1h"
        sample.outcome = 1
        return sample

    def test_default_creation(self):
        """Test creating loader with defaults."""
        loader = TrainingDataLoader()
        assert loader.feature_extractor is None
        assert loader.signal_storage is None
        assert loader.config is not None

    def test_custom_creation(self, mock_feature_extractor, mock_signal_storage):
        """Test creating loader with custom components."""
        config = TrainingConfig()
        loader = TrainingDataLoader(
            feature_extractor=mock_feature_extractor,
            signal_storage=mock_signal_storage,
            config=config,
        )
        assert loader.feature_extractor == mock_feature_extractor
        assert loader.signal_storage == mock_signal_storage
        assert loader.config == config

    @pytest.mark.asyncio
    async def test_load_training_data_no_storage(self):
        """Test loading data without storage returns empty."""
        loader = TrainingDataLoader()
        split, report = await loader.load_training_data()
        assert split.total_count == 0
        assert report.total_samples == 0

    @pytest.mark.asyncio
    async def test_validate_quality_empty_samples(self):
        """Test quality validation with empty samples."""
        loader = TrainingDataLoader()
        report = loader._validate_quality([])
        assert report.total_samples == 0
        assert report.quality_score == 0.0
        assert "No samples available" in report.issues

    @pytest.mark.asyncio
    async def test_validate_quality_with_valid_samples(self, mock_sample):
        """Test quality validation with valid samples."""
        loader = TrainingDataLoader()
        samples = [mock_sample for _ in range(10)]
        report = loader._validate_quality(samples)
        assert report.total_samples == 10
        assert report.valid_samples == 10
        assert report.quality_score == 1.0
        assert report.is_acceptable

    @pytest.mark.asyncio
    async def test_validate_quality_with_invalid_samples(self):
        """Test quality validation with invalid samples."""
        loader = TrainingDataLoader()
        valid_sample = MagicMock()
        valid_sample.token = "BTC"
        valid_sample.timeframe = "1h"
        valid_sample.outcome = 1

        invalid_sample = MagicMock()
        invalid_sample.token = None
        invalid_sample.timeframe = None
        invalid_sample.outcome = None

        samples = [valid_sample, invalid_sample]
        report = loader._validate_quality(samples)
        assert report.total_samples == 2
        assert report.valid_samples == 1
        assert report.quality_score == 0.5
        assert not report.is_acceptable

    def test_split_data_empty(self):
        """Test data splitting with empty samples."""
        loader = TrainingDataLoader()
        split = loader._split_data([])
        assert split.total_count == 0

    def test_split_data_70_15_15(self):
        """Test 70/15/15 split ratio."""
        loader = TrainingDataLoader()
        samples = list(range(100))
        split = loader._split_data(samples)

        # Check ratios
        assert len(split.train) == 70
        assert len(split.validation) == 15
        assert len(split.test) == 15
        assert split.total_count == 100

    def test_split_data_reproducibility(self):
        """Test that split is reproducible with same seed."""
        config = TrainingConfig(random_seed=42)
        loader1 = TrainingDataLoader(config=config)
        loader2 = TrainingDataLoader(config=config)

        samples = list(range(100))
        split1 = loader1._split_data(samples)
        split2 = loader2._split_data(samples)

        assert split1.train == split2.train
        assert split1.validation == split2.validation
        assert split1.test == split2.test


class TestModelValidator:
    """Tests for ModelValidator class."""

    def test_default_creation(self):
        """Test creating validator with defaults."""
        validator = ModelValidator()
        assert validator.baseline_accuracy_margin == -0.05

    def test_custom_margin(self):
        """Test creating validator with custom margin."""
        validator = ModelValidator(baseline_accuracy_margin=-0.10)
        assert validator.baseline_accuracy_margin == -0.10

    @pytest.mark.asyncio
    async def test_validate_no_baseline(self):
        """Test validation without baseline model."""
        validator = ModelValidator()
        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=[1, 0, 1, 0])

        # Create test samples with outcomes
        samples = []
        for i in range(4):
            sample = MagicMock()
            sample.to_feature_dict.return_value = {"feature": i}
            sample.outcome = i % 2
            samples.append(sample)

        report = await validator.validate(
            model=mock_model,
            test_data=samples,
            model_version="1.0.0",
        )

        assert report.model_version == "1.0.0"
        assert report.passed  # Should pass with default baseline of 0.5

    @pytest.mark.asyncio
    async def test_validate_empty_test_data(self):
        """Test validation with empty test data."""
        validator = ModelValidator()
        report = await validator.validate(
            model=MagicMock(),
            test_data=[],
            model_version="1.0.0",
        )
        assert report.test_metrics.accuracy == 0.0

    def test_calculate_metrics(self):
        """Test metrics calculation."""
        validator = ModelValidator()
        predictions = [1, 1, 0, 0, 1, 0, 1, 0]
        actuals = [1, 0, 0, 1, 1, 0, 0, 1]

        metrics = validator._calculate_metrics(predictions, actuals)

        # TP=2 (predicted 1, actual 1 at indices 0, 4)
        # TN=2 (predicted 0, actual 0 at indices 2, 5)
        # FP=2 (predicted 1, actual 0 at indices 1, 6)
        # FN=2 (predicted 0, actual 1 at indices 3, 7)
        assert metrics.accuracy == 0.5
        assert metrics.precision == 0.5
        assert metrics.recall == 0.5
        assert metrics.f1 == 0.5


class TestTrainingPipeline:
    """Tests for TrainingPipeline class."""

    @pytest.fixture
    def mock_data_loader(self):
        """Create mock data loader."""
        loader = AsyncMock()
        return loader

    @pytest.fixture
    def mock_model_registry(self):
        """Create mock model registry."""
        registry = MagicMock()
        return registry

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def mock_discord_notifier(self):
        """Create mock Discord notifier."""
        notifier = AsyncMock()
        return notifier

    def test_default_creation(self):
        """Test creating pipeline with defaults."""
        pipeline = TrainingPipeline()
        assert pipeline.model_registry is None
        assert pipeline.data_loader is not None
        assert pipeline.config is not None
        assert pipeline.get_status() == TrainingStatus.PENDING

    def test_custom_creation(
        self,
        mock_data_loader,
        mock_model_registry,
        mock_redis_client,
        mock_discord_notifier,
    ):
        """Test creating pipeline with custom components."""
        config = TrainingConfig()
        pipeline = TrainingPipeline(
            model_registry=mock_model_registry,
            data_loader=mock_data_loader,
            config=config,
            redis_client=mock_redis_client,
            discord_notifier=mock_discord_notifier,
        )
        assert pipeline.model_registry == mock_model_registry
        assert pipeline.data_loader == mock_data_loader
        assert pipeline.config == config
        assert pipeline.redis_client == mock_redis_client
        assert pipeline.discord_notifier == mock_discord_notifier

    def test_redis_keys(self):
        """Test Redis key constants."""
        assert TrainingPipeline.REDIS_STATUS_KEY == "launch:training:pipeline:status"
        assert (
            TrainingPipeline.REDIS_LAST_RUN_KEY == "launch:training:pipeline:last_run"
        )
        assert TrainingPipeline.REDIS_MODE_KEY == "launch:training:pipeline:mode"
        assert TrainingPipeline.REDIS_METRICS_KEY == "launch:training:pipeline:metrics"

    @pytest.mark.asyncio
    async def test_run_training_data_quality_failure(self):
        """Test training fails when data quality is insufficient."""
        mock_loader = AsyncMock()
        mock_loader.load_training_data.return_value = (
            DataSplit(),
            DataQualityReport(
                total_samples=100,
                valid_samples=80,
                quality_score=0.80,
                issues=["Low quality"],
            ),
        )

        pipeline = TrainingPipeline(data_loader=mock_loader)
        result = await pipeline.run_training()

        assert result["status"] == "failed"
        assert "Data quality below threshold" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_version_incremental(self):
        """Test version generation for incremental training."""
        config = TrainingConfig(training_mode=TrainingMode.INCREMENTAL)
        pipeline = TrainingPipeline(config=config)

        version = pipeline._generate_version()
        assert version == "0.1.0"  # Default starting version

    @pytest.mark.asyncio
    async def test_generate_version_full(self):
        """Test version generation for full training."""
        config = TrainingConfig(training_mode=TrainingMode.FULL)
        pipeline = TrainingPipeline(config=config)

        version = pipeline._generate_version()
        assert version == "0.1.0"  # Default starting version

    def test_compute_data_hash(self):
        """Test data hash computation."""
        pipeline = TrainingPipeline()
        split = DataSplit(train=[1] * 70, validation=[1] * 15, test=[1] * 15)
        hash1 = pipeline._compute_data_hash(split)
        hash2 = pipeline._compute_data_hash(split)
        assert hash1 == hash2  # Should be deterministic
        assert len(hash1) == 16

    @pytest.mark.asyncio
    async def test_save_checkpoint(self):
        """Test checkpoint saving."""
        pipeline = TrainingPipeline()
        checkpoint = await pipeline._save_checkpoint(
            epoch=5,
            metrics={"accuracy": 0.85},
        )
        assert checkpoint.epoch == 5
        assert checkpoint.metrics["accuracy"] == 0.85
        assert len(pipeline.get_checkpoints()) == 1

    @pytest.mark.asyncio
    async def test_update_status(self):
        """Test status updates."""
        mock_redis = AsyncMock()
        pipeline = TrainingPipeline(redis_client=mock_redis)

        await pipeline._update_status(TrainingStatus.TRAINING)
        assert pipeline.get_status() == TrainingStatus.TRAINING

    @pytest.mark.asyncio
    async def test_notify_success(self):
        """Test success notification."""
        mock_notifier = AsyncMock()
        pipeline = TrainingPipeline(discord_notifier=mock_notifier)

        result = {
            "mode": "INCREMENTAL",
            "model_version": "1.0.0",
            "elapsed_seconds": 3600,
        }
        await pipeline._notify_success(result)

        mock_notifier.send.assert_called_once()
        call_args = mock_notifier.send.call_args[0][0]
        assert "Training completed successfully" in call_args
        assert "1.0.0" in call_args

    @pytest.mark.asyncio
    async def test_notify_failure(self):
        """Test failure notification."""
        mock_notifier = AsyncMock()
        pipeline = TrainingPipeline(discord_notifier=mock_notifier)

        result = {
            "mode": "INCREMENTAL",
            "error": "Training timeout",
        }
        await pipeline._notify_failure(result)

        mock_notifier.send.assert_called_once()
        call_args = mock_notifier.send.call_args[0][0]
        assert "Training failed" in call_args
        assert "Training timeout" in call_args


class TestCreateTrainingPipeline:
    """Tests for create_training_pipeline factory function."""

    def test_factory_creates_pipeline(self):
        """Test factory creates pipeline correctly."""
        pipeline = create_training_pipeline()
        assert isinstance(pipeline, TrainingPipeline)
        assert pipeline.data_loader is not None

    def test_factory_with_components(self):
        """Test factory with all components."""
        mock_registry = MagicMock()
        mock_extractor = MagicMock()
        mock_storage = MagicMock()
        config = TrainingConfig()

        pipeline = create_training_pipeline(
            model_registry=mock_registry,
            feature_extractor=mock_extractor,
            signal_storage=mock_storage,
            config=config,
        )

        assert pipeline.model_registry == mock_registry
        assert pipeline.data_loader.feature_extractor == mock_extractor
        assert pipeline.data_loader.signal_storage == mock_storage


class TestAcceptanceCriteria:
    """Tests verifying ST-TRAIN-001 acceptance criteria."""

    def test_ac_1_data_split_ratios(self):
        """AC1: Verify 70/15/15 data split ratios."""
        config = TrainingConfig()
        assert config.train_ratio == 0.70
        assert config.validation_ratio == 0.15
        assert config.test_ratio == 0.15

        # Verify sum to 1.0
        total = config.train_ratio + config.validation_ratio + config.test_ratio
        assert abs(total - 1.0) < 0.01

    def test_ac_2_training_modes(self):
        """AC2: Verify training modes exist with correct parameters."""
        # Incremental mode
        incremental_config = TrainingConfig(training_mode=TrainingMode.INCREMENTAL)
        assert incremental_config.incremental_days == 30
        assert incremental_config.incremental_sla_hours == 4.0

        # Full mode
        full_config = TrainingConfig(training_mode=TrainingMode.FULL)
        assert full_config.full_sla_hours == 24.0

    def test_ac_3_sla_enforcement(self):
        """AC3: Verify SLA enforcement configuration."""
        incremental_config = TrainingConfig(training_mode=TrainingMode.INCREMENTAL)
        assert incremental_config.sla_hours == 4.0  # <4h SLA

        full_config = TrainingConfig(training_mode=TrainingMode.FULL)
        assert full_config.sla_hours == 24.0  # <24h SLA

    def test_ac_4_model_registry_integration(self):
        """AC4: Verify model registry integration exists."""
        mock_registry = MagicMock()
        pipeline = TrainingPipeline(model_registry=mock_registry)
        assert pipeline.model_registry is not None

    def test_ac_5_checkpointing_support(self):
        """AC5: Verify checkpointing support exists."""
        pipeline = TrainingPipeline()
        assert hasattr(pipeline, "_save_checkpoint")
        assert hasattr(pipeline, "get_checkpoints")

    def test_ac_6_data_quality_threshold(self):
        """AC6: Verify data quality threshold is 90%."""
        config = TrainingConfig()
        assert config.quality_threshold == 0.90

        report = DataQualityReport(quality_score=0.90)
        assert report.is_acceptable

        report_low = DataQualityReport(quality_score=0.89)
        assert not report_low.is_acceptable

    def test_ac_7_semantic_versioning(self):
        """AC7: Verify semantic versioning support."""
        pipeline = TrainingPipeline()
        version = pipeline._generate_version()
        # Should be in MAJOR.MINOR.PATCH format
        parts = version.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_ac_8_redis_status_tracking(self):
        """AC8: Verify Redis status tracking keys exist."""
        assert hasattr(TrainingPipeline, "REDIS_STATUS_KEY")
        assert hasattr(TrainingPipeline, "REDIS_LAST_RUN_KEY")
        assert hasattr(TrainingPipeline, "REDIS_MODE_KEY")
        assert hasattr(TrainingPipeline, "REDIS_METRICS_KEY")

    def test_ac_9_discord_notifications(self):
        """AC9: Verify Discord notification support."""
        mock_notifier = MagicMock()
        pipeline = TrainingPipeline(discord_notifier=mock_notifier)
        assert pipeline.discord_notifier is not None
        assert hasattr(pipeline, "_notify_success")
        assert hasattr(pipeline, "_notify_failure")
