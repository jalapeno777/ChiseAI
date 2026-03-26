"""Tests for ICT ML Model Training Integration.

ST-ICT-028-B: ICT ML Model Training Integration
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from src.ml.training.ict_integration import (
    ICTFeatureLoader,
    ICTMetricType,
    ICTModelConfig,
    ICTModelTrainer,
    ICTModelType,
    ICTTrainingMetrics,
    ICTTrainingPipeline,
    ICTValidationResult,
    ICTValidator,
)


class TestICTModelConfig:
    """Tests for ICTModelConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ICTModelConfig()
        assert config.model_type == ICTModelType.ICT_CLASSIFIER
        assert config.learning_rate == 0.001
        assert config.batch_size == 32
        assert config.epochs == 100
        assert config.validation_split == 0.2
        assert config.min_samples == 100
        assert config.confidence_threshold == 0.6

    def test_custom_config(self):
        """Test custom configuration."""
        config = ICTModelConfig(
            model_type=ICTModelType.ICT_ENSEMBLE,
            learning_rate=0.01,
            batch_size=64,
            min_samples=200,
            feature_weights={"cvd_slope": 1.5, "fvg_bullish_count": 1.2},
        )
        assert config.model_type == ICTModelType.ICT_ENSEMBLE
        assert config.learning_rate == 0.01
        assert config.batch_size == 64
        assert config.min_samples == 200
        assert config.feature_weights["cvd_slope"] == 1.5

    def test_validation_min_samples(self):
        """Test min_samples validation."""
        with pytest.raises(ValueError, match="min_samples must be at least 50"):
            ICTModelConfig(min_samples=10)

    def test_validation_split(self):
        """Test validation_split validation."""
        with pytest.raises(
            ValueError, match="validation_split must be between 0 and 1"
        ):
            ICTModelConfig(validation_split=1.5)

        with pytest.raises(
            ValueError, match="validation_split must be between 0 and 1"
        ):
            ICTModelConfig(validation_split=-0.1)

    def test_confidence_threshold(self):
        """Test confidence_threshold validation."""
        with pytest.raises(
            ValueError, match="confidence_threshold must be between 0 and 1"
        ):
            ICTModelConfig(confidence_threshold=1.5)

    def test_dropout_rate(self):
        """Test dropout_rate validation."""
        with pytest.raises(ValueError, match="dropout_rate must be between 0 and 1"):
            ICTModelConfig(dropout_rate=1.5)

    def test_to_dict(self):
        """Test dictionary conversion."""
        config = ICTModelConfig(
            model_type=ICTModelType.ICT_REGRESSOR,
            learning_rate=0.005,
        )
        d = config.to_dict()
        assert d["model_type"] == "ict_regressor"
        assert d["learning_rate"] == 0.005
        assert "feature_weights" in d

    def test_to_hyperparameters(self):
        """Test conversion to base Hyperparameters."""
        config = ICTModelConfig(
            learning_rate=0.01,
            batch_size=64,
            epochs=50,
        )
        hyperparams = config.to_hyperparameters()
        assert hyperparams.learning_rate == 0.01
        assert hyperparams.batch_size == 64
        assert hyperparams.epochs == 50


class TestICTTrainingMetrics:
    """Tests for ICTTrainingMetrics."""

    def test_default_metrics(self):
        """Test default metrics."""
        metrics = ICTTrainingMetrics()
        assert metrics.direction_accuracy == 0.0
        assert metrics.confidence_calibration == 0.0
        assert metrics.validation_accuracy == 0.0

    def test_custom_metrics(self):
        """Test custom metrics."""
        metrics = ICTTrainingMetrics(
            direction_accuracy=0.75,
            confidence_calibration=0.08,
            fvg_hit_rate=0.65,
            validation_accuracy=0.72,
        )
        assert metrics.direction_accuracy == 0.75
        assert metrics.confidence_calibration == 0.08

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = ICTTrainingMetrics(direction_accuracy=0.72, loss=0.22)
        d = metrics.to_dict()
        assert "direction_accuracy" in d
        assert d["direction_accuracy"] == 0.72
        assert d["loss"] == 0.22

    def test_is_acceptable(self):
        """Test is_acceptable property."""
        good_metrics = ICTTrainingMetrics(
            direction_accuracy=0.60,
            confidence_calibration=0.10,
            validation_accuracy=0.55,
        )
        assert good_metrics.is_acceptable is True

        bad_metrics = ICTTrainingMetrics(
            direction_accuracy=0.50,
            confidence_calibration=0.20,
            validation_accuracy=0.45,
        )
        assert bad_metrics.is_acceptable is False

        # Edge case: exactly at threshold
        threshold_metrics = ICTTrainingMetrics(
            direction_accuracy=0.55,
            confidence_calibration=0.15,
            validation_accuracy=0.50,
        )
        assert threshold_metrics.is_acceptable is True


class TestICTValidationResult:
    """Tests for ICTValidationResult."""

    @pytest.mark.asyncio
    async def test_passed_validation(self):
        """Test passed validation result."""
        validator = ICTValidator()
        metrics = ICTTrainingMetrics(
            direction_accuracy=0.70,
            confidence_calibration=0.05,
            validation_accuracy=0.68,
        )
        result = await validator.validate(None, metrics)
        assert result.passed is True
        assert (
            result.recommendation
            == "APPROVED: Model meets ICT signal quality thresholds"
        )
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_failed_validation(self):
        """Test failed validation result."""
        validator = ICTValidator()
        metrics = ICTTrainingMetrics(
            direction_accuracy=0.45,
            confidence_calibration=0.25,
            validation_accuracy=0.40,
        )
        result = await validator.validate(None, metrics)

        assert result.passed is False
        assert len(result.issues) == 3
        assert "REJECTED" in result.recommendation

    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = ICTTrainingMetrics(direction_accuracy=0.72)
        result = ICTValidationResult(passed=True, metrics=metrics)
        d = result.to_dict()
        assert d["passed"] is True
        assert "thresholds" in d
        assert "metrics" in d


class TestICTFeatureLoader:
    """Tests for ICTFeatureLoader."""

    def test_init_default(self):
        """Test default initialization."""
        loader = ICTFeatureLoader()
        assert loader._min_samples == 100

    def test_init_custom(self):
        """Test custom initialization."""
        loader = ICTFeatureLoader(min_samples=200)
        assert loader._min_samples == 200

    @pytest.mark.asyncio
    async def test_load_features_no_extractor(self):
        """Test load features with no extractor."""
        loader = ICTFeatureLoader()
        features = await loader.load_features()
        assert features == []

    @pytest.mark.asyncio
    async def test_features_to_training_data(self):
        """Test conversion to TrainingData."""
        from src.ml.features.ict_features import ICTFeatures, MarketRegime

        # Create mock features
        mock_features = [
            ICTFeatures(
                timestamp=datetime.now(UTC),
                token="BTC",
                timeframe="1h",
                cvd_slope=0.5,
                cvd_momentum=0.3,
                combined_ict_score=0.7,
                regime=MarketRegime.BULLISH,
            ),
            ICTFeatures(
                timestamp=datetime.now(UTC),
                token="ETH",
                timeframe="1h",
                cvd_slope=-0.3,
                cvd_momentum=-0.2,
                combined_ict_score=-0.5,
                regime=MarketRegime.BEARISH,
            ),
        ]

        loader = ICTFeatureLoader()
        data = loader.features_to_training_data(mock_features)

        assert data.sample_count == 2
        assert len(data.features) > 0
        assert "cvd_slope" in data.features
        assert data.label_column == "outcome"


class TestICTModelTrainer:
    """Tests for ICTModelTrainer."""

    def test_init_default(self):
        """Test default initialization."""
        trainer = ICTModelTrainer()
        assert trainer._config.model_type == ICTModelType.ICT_CLASSIFIER

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ICTModelConfig(model_type=ICTModelType.ICT_ENSEMBLE)
        trainer = ICTModelTrainer(config=config)
        assert trainer._config.model_type == ICTModelType.ICT_ENSEMBLE

    @pytest.mark.asyncio
    async def test_train_insufficient_samples(self):
        """Test training with insufficient samples."""
        from src.ml.training.pipeline_integration import TrainingData

        config = ICTModelConfig(min_samples=100)
        trainer = ICTModelTrainer(config=config)

        data = TrainingData(samples=[], sample_count=0)
        success, metrics, model = await trainer.train(data)

        assert success is False
        assert metrics.direction_accuracy == 0.0
        assert model is None

    @pytest.mark.asyncio
    async def test_train_classifier(self):
        """Test classifier training."""
        from src.ml.training.pipeline_integration import TrainingData

        config = ICTModelConfig(model_type=ICTModelType.ICT_CLASSIFIER)
        trainer = ICTModelTrainer(config=config)

        # Create mock data
        samples = [{"feature": i, "outcome": i % 2} for i in range(100)]
        data = TrainingData(samples=samples, sample_count=100)

        success, metrics, model = await trainer.train(data)

        assert success is True
        assert metrics.direction_accuracy > 0
        assert model is not None
        assert model["type"] == "classifier"

    @pytest.mark.asyncio
    async def test_train_regressor(self):
        """Test regressor training."""
        from src.ml.training.pipeline_integration import TrainingData

        config = ICTModelConfig(model_type=ICTModelType.ICT_REGRESSOR)
        trainer = ICTModelTrainer(config=config)

        samples = [{"feature": i} for i in range(100)]
        data = TrainingData(samples=samples, sample_count=100)

        success, metrics, model = await trainer.train(data)

        assert success is True
        assert model["type"] == "regressor"

    @pytest.mark.asyncio
    async def test_train_ensemble(self):
        """Test ensemble training."""
        from src.ml.training.pipeline_integration import TrainingData

        config = ICTModelConfig(model_type=ICTModelType.ICT_ENSEMBLE)
        trainer = ICTModelTrainer(config=config)

        samples = [{"feature": i} for i in range(100)]
        data = TrainingData(samples=samples, sample_count=100)

        success, metrics, model = await trainer.train(data)

        assert success is True
        assert model["type"] == "ensemble"
        # Ensemble should have highest accuracy
        assert metrics.direction_accuracy >= 0.70


class TestICTValidator:
    """Tests for ICTValidator."""

    def test_init_default(self):
        """Test default initialization."""
        validator = ICTValidator()
        assert validator._threshold_direction_accuracy == 0.55
        assert validator._threshold_confidence_calibration == 0.15
        assert validator._threshold_validation_accuracy == 0.50

    def test_init_custom_thresholds(self):
        """Test custom thresholds."""
        validator = ICTValidator(
            threshold_direction_accuracy=0.60,
            threshold_confidence_calibration=0.10,
        )
        assert validator._threshold_direction_accuracy == 0.60
        assert validator._threshold_confidence_calibration == 0.10

    @pytest.mark.asyncio
    async def test_validate_passes(self):
        """Test validation passes."""
        validator = ICTValidator()

        metrics = ICTTrainingMetrics(
            direction_accuracy=0.72,
            confidence_calibration=0.08,
            validation_accuracy=0.70,
        )

        result = await validator.validate(None, metrics)

        assert result.passed is True
        assert len(result.issues) == 0
        assert "APPROVED" in result.recommendation

    @pytest.mark.asyncio
    async def test_validate_fails_direction_accuracy(self):
        """Test validation fails on direction accuracy."""
        validator = ICTValidator()

        metrics = ICTTrainingMetrics(
            direction_accuracy=0.50,
            confidence_calibration=0.05,
            validation_accuracy=0.70,
        )

        result = await validator.validate(None, metrics)

        assert result.passed is False
        assert any("Direction accuracy" in issue for issue in result.issues)

    @pytest.mark.asyncio
    async def test_validate_fails_calibration(self):
        """Test validation fails on calibration."""
        validator = ICTValidator()

        metrics = ICTTrainingMetrics(
            direction_accuracy=0.70,
            confidence_calibration=0.25,
            validation_accuracy=0.70,
        )

        result = await validator.validate(None, metrics)

        assert result.passed is False
        assert any("calibration" in issue.lower() for issue in result.issues)

    @pytest.mark.asyncio
    async def test_validate_multiple_failures(self):
        """Test validation with multiple failures."""
        validator = ICTValidator()

        metrics = ICTTrainingMetrics(
            direction_accuracy=0.45,
            confidence_calibration=0.30,
            validation_accuracy=0.40,
        )

        result = await validator.validate(None, metrics)

        assert result.passed is False
        assert len(result.issues) == 3


class TestICTTrainingPipeline:
    """Tests for ICTTrainingPipeline."""

    def test_init_default(self):
        """Test default initialization."""
        pipeline = ICTTrainingPipeline()
        assert pipeline._config.model_type == ICTModelType.ICT_CLASSIFIER
        assert pipeline._current_model is None
        assert pipeline._current_version == ""

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ICTModelConfig(model_type=ICTModelType.ICT_REGRESSOR)
        pipeline = ICTTrainingPipeline(ict_config=config)
        assert pipeline._config.model_type == ICTModelType.ICT_REGRESSOR

    @pytest.mark.asyncio
    async def test_load_ict_features_empty(self):
        """Test loading features with no extractor."""
        pipeline = ICTTrainingPipeline()
        data = await pipeline.load_ict_features()
        assert data.sample_count == 0

    @pytest.mark.asyncio
    async def test_train_model_no_data(self):
        """Test training with no data."""
        from src.ml.training.pipeline_integration import TrainingData

        pipeline = ICTTrainingPipeline()
        data = TrainingData(samples=[], sample_count=0)

        success, metrics, model = await pipeline.train_model(data)

        assert success is False

    @pytest.mark.asyncio
    async def test_validate_model(self):
        """Test model validation."""
        pipeline = ICTTrainingPipeline()

        metrics = ICTTrainingMetrics(
            direction_accuracy=0.72,
            confidence_calibration=0.08,
            validation_accuracy=0.70,
        )

        result = await pipeline.validate_model(None, metrics)

        assert result.passed is True

    def test_generate_version(self):
        """Test version generation."""
        pipeline = ICTTrainingPipeline()
        version = pipeline._generate_version()
        assert version == "0.1.0"

    def test_get_current_model(self):
        """Test getting current model."""
        pipeline = ICTTrainingPipeline()
        assert pipeline.get_current_model() is None

    def test_get_current_version(self):
        """Test getting current version."""
        pipeline = ICTTrainingPipeline()
        assert pipeline.get_current_version() == ""

    def test_get_last_training_time(self):
        """Test getting last training time."""
        pipeline = ICTTrainingPipeline()
        assert pipeline.get_last_training_time() is None

    @pytest.mark.asyncio
    async def test_run_full_pipeline_no_features(self):
        """Test full pipeline with no features."""
        pipeline = ICTTrainingPipeline()

        result = await pipeline.run_full_pipeline()

        assert result["status"] == "failed"
        assert "No ICT features loaded" in result["error"]


class TestICTModelType:
    """Tests for ICTModelType enum."""

    def test_model_types(self):
        """Test all model types exist."""
        assert ICTModelType.ICT_CLASSIFIER.value == "ict_classifier"
        assert ICTModelType.ICT_REGRESSOR.value == "ict_regressor"
        assert ICTModelType.ICT_ENSEMBLE.value == "ict_ensemble"


class TestICTMetricType:
    """Tests for ICTMetricType enum."""

    def test_metric_types(self):
        """Test all metric types exist."""
        assert ICTMetricType.DIRECTION_ACCURACY.value == "direction_accuracy"
        assert ICTMetricType.CONFIDENCE_CALIBRATION.value == "confidence_calibration"
        assert ICTMetricType.FVG_HIT_RATE.value == "fvg_hit_rate"
        assert ICTMetricType.OB_HIT_RATE.value == "ob_hit_rate"
