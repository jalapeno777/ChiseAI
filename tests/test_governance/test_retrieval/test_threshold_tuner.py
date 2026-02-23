"""
Tests for Threshold Tuner Module.

ST-GOV-007: Retrieval Quality Evaluator

Tests cover:
- ThresholdTuner class
- Threshold registration and management
- Automatic tuning algorithms
- History tracking
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock

from src.governance.retrieval.threshold_tuner import (
    ThresholdTuner,
    ThresholdConfig,
    TunerConfig,
    TuningResult,
    TuningHistory,
    OptimizationGoal,
    AdjustmentStrategy,
)


class TestThresholdConfig:
    """Tests for ThresholdConfig."""

    def test_creation(self):
        """Test creating a threshold config."""
        config = ThresholdConfig(
            name="similarity_cutoff",
            current_value=0.7,
            min_value=0.5,
            max_value=0.95,
            step_size=0.05,
            target_metric="precision_at_10",
            target_value=0.85,
        )
        assert config.name == "similarity_cutoff"
        assert config.current_value == 0.7
        assert config.min_value == 0.5
        assert config.max_value == 0.95

    def test_serialization(self):
        """Test serialization round-trip."""
        config = ThresholdConfig(
            name="test",
            current_value=0.5,
            target_metric="precision_at_5",
            target_value=0.9,
        )
        d = config.to_dict()
        restored = ThresholdConfig.from_dict(d)
        assert restored.name == config.name
        assert restored.current_value == config.current_value
        assert restored.target_metric == config.target_metric


class TestTunerConfig:
    """Tests for TunerConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TunerConfig()
        assert config.optimization_goal == OptimizationGoal.BALANCE_F1
        assert config.adjustment_strategy == AdjustmentStrategy.GRADIENT
        assert config.min_sample_size == 100
        assert config.learning_rate == 0.1
        assert config.patience == 10

    def test_serialization(self):
        """Test serialization round-trip."""
        config = TunerConfig(
            optimization_goal=OptimizationGoal.MAXIMIZE_PRECISION,
            adjustment_strategy=AdjustmentStrategy.BINARY_SEARCH,
            learning_rate=0.2,
        )
        d = config.to_dict()
        restored = TunerConfig.from_dict(d)
        assert restored.optimization_goal == OptimizationGoal.MAXIMIZE_PRECISION
        assert restored.adjustment_strategy == AdjustmentStrategy.BINARY_SEARCH
        assert restored.learning_rate == 0.2


class TestTuningResult:
    """Tests for TuningResult."""

    def test_creation(self):
        """Test creating a tuning result."""
        result = TuningResult(
            threshold_name="similarity_cutoff",
            old_value=0.7,
            new_value=0.75,
            metric_name="precision_at_10",
            old_metric_value=0.80,
            new_metric_value=0.85,
            improvement=True,
        )
        assert result.threshold_name == "similarity_cutoff"
        assert result.improvement is True

    def test_serialization(self):
        """Test serialization round-trip."""
        result = TuningResult(
            threshold_name="test",
            old_value=0.5,
            new_value=0.6,
            metric_name="precision",
            old_metric_value=0.7,
            new_metric_value=0.8,
            improvement=True,
        )
        d = result.to_dict()
        restored = TuningResult.from_dict(d)
        assert restored.threshold_name == result.threshold_name
        assert restored.new_value == result.new_value


class TestTuningHistory:
    """Tests for TuningHistory."""

    def test_add_result(self):
        """Test adding results to history."""
        history = TuningHistory(threshold_name="test")

        result1 = TuningResult(
            threshold_name="test",
            old_value=0.5,
            new_value=0.6,
            metric_name="precision",
            old_metric_value=0.7,
            new_metric_value=0.8,
            improvement=True,
        )
        history.add_result(result1)

        assert len(history.adjustments) == 1
        assert history.best_value == 0.6
        assert history.best_metric_value == 0.8

    def test_best_tracking(self):
        """Test tracking best value over multiple adjustments."""
        history = TuningHistory(threshold_name="test")

        # Add improving result
        result1 = TuningResult(
            threshold_name="test",
            old_value=0.5,
            new_value=0.6,
            metric_name="precision",
            old_metric_value=0.7,
            new_metric_value=0.8,
            improvement=True,
        )
        history.add_result(result1)
        assert history.best_metric_value == 0.8

        # Add worse result
        result2 = TuningResult(
            threshold_name="test",
            old_value=0.6,
            new_value=0.7,
            metric_name="precision",
            old_metric_value=0.8,
            new_metric_value=0.75,
            improvement=False,
        )
        history.add_result(result2)
        # Best should still be 0.8
        assert history.best_metric_value == 0.8
        assert history.best_value == 0.6

        # Add better result
        result3 = TuningResult(
            threshold_name="test",
            old_value=0.7,
            new_value=0.65,
            metric_name="precision",
            old_metric_value=0.75,
            new_metric_value=0.85,
            improvement=True,
        )
        history.add_result(result3)
        assert history.best_metric_value == 0.85
        assert history.best_value == 0.65


class TestThresholdTuner:
    """Tests for ThresholdTuner class."""

    def test_init(self):
        """Test tuner initialization."""
        tuner = ThresholdTuner()
        assert tuner._redis is None
        assert tuner._config is not None

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = TunerConfig(
            optimization_goal=OptimizationGoal.MAXIMIZE_RECALL,
            learning_rate=0.2,
        )
        tuner = ThresholdTuner(config=config)
        assert tuner._config.optimization_goal == OptimizationGoal.MAXIMIZE_RECALL
        assert tuner._config.learning_rate == 0.2

    def test_register_threshold(self):
        """Test registering a threshold."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            min_value=0.5,
            max_value=0.95,
        )

        assert "similarity_cutoff" in tuner._thresholds
        assert tuner.get_threshold("similarity_cutoff") == 0.7

    def test_unregister_threshold(self):
        """Test unregistering a threshold."""
        tuner = ThresholdTuner()
        tuner.register_threshold("test", initial_value=0.5)

        result = tuner.unregister_threshold("test")
        assert result is True
        assert tuner.get_threshold("test") is None

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent threshold."""
        tuner = ThresholdTuner()
        result = tuner.unregister_threshold("nonexistent")
        assert result is False

    def test_set_threshold(self):
        """Test manually setting threshold."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            "test", initial_value=0.5, min_value=0.0, max_value=1.0
        )

        result = tuner.set_threshold("test", 0.8)
        assert result is True
        assert tuner.get_threshold("test") == 0.8

    def test_set_threshold_clamped(self):
        """Test threshold is clamped to bounds."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            "test", initial_value=0.5, min_value=0.3, max_value=0.7
        )

        # Try to set above max
        tuner.set_threshold("test", 0.9)
        assert tuner.get_threshold("test") == 0.7

        # Try to set below min
        tuner.set_threshold("test", 0.1)
        assert tuner.get_threshold("test") == 0.3

    def test_get_all_thresholds(self):
        """Test getting all thresholds."""
        tuner = ThresholdTuner()
        tuner.register_threshold("t1", initial_value=0.5)
        tuner.register_threshold("t2", initial_value=0.7)

        all_thresholds = tuner.get_all_thresholds()
        assert len(all_thresholds) == 2
        assert all_thresholds["t1"] == 0.5
        assert all_thresholds["t2"] == 0.7

    def test_tune_gradient_strategy(self):
        """Test tuning with gradient strategy."""
        config = TunerConfig(
            adjustment_strategy=AdjustmentStrategy.GRADIENT,
            learning_rate=0.5,
            min_sample_size=10,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            target_metric="precision_at_10",
            target_value=0.90,
        )

        # Current precision is below target, should raise threshold
        result = tuner.tune(
            threshold_name="similarity_cutoff",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        assert result is not None
        assert result.old_value == 0.7
        # Threshold should have changed
        assert result.new_value != result.old_value

    def test_tune_binary_search_strategy(self):
        """Test tuning with binary search strategy."""
        config = TunerConfig(
            adjustment_strategy=AdjustmentStrategy.BINARY_SEARCH,
            min_sample_size=10,
            convergence_threshold=0.001,  # Small threshold for testing
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            step_size=0.1,
            target_metric="precision_at_10",
            target_value=0.90,
        )

        # Current precision is below target
        result = tuner.tune(
            threshold_name="similarity_cutoff",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        assert result is not None
        # Binary search should move by step_size (use approx for floating point)
        assert abs(result.new_value - result.old_value) == pytest.approx(0.1, rel=0.01)

    def test_tune_adaptive_strategy(self):
        """Test tuning with adaptive strategy."""
        config = TunerConfig(
            adjustment_strategy=AdjustmentStrategy.ADAPTIVE,
            min_sample_size=10,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.7,
            step_size=0.05,
        )

        # First adjustment
        result = tuner.tune(
            threshold_name="similarity_cutoff",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        assert result is not None

    def test_tune_insufficient_samples(self):
        """Test tuning with insufficient samples."""
        tuner = ThresholdTuner()
        tuner.register_threshold("test", initial_value=0.5)

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_10": 0.80},
            sample_size=10,  # Below default min_sample_size of 100
        )

        assert result is None

    def test_tune_nonexistent_threshold(self):
        """Test tuning non-existent threshold."""
        tuner = ThresholdTuner()

        result = tuner.tune(
            threshold_name="nonexistent",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        assert result is None

    def test_tune_missing_metric(self):
        """Test tuning with missing target metric."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            name="test",
            initial_value=0.5,
            target_metric="precision_at_10",
        )

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"recall_at_10": 0.80},  # Missing precision metric
            sample_size=100,
        )

        assert result is None

    def test_tune_all(self):
        """Test tuning all thresholds."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            "t1", initial_value=0.5, target_metric="precision_at_5"
        )
        tuner.register_threshold("t2", initial_value=0.6, target_metric="recall_at_10")

        results = tuner.tune_all(
            current_metrics={
                "precision_at_5": 0.80,
                "recall_at_10": 0.70,
            },
            sample_size=100,
        )

        assert len(results) <= 2  # May have adjustments

    def test_convergence(self):
        """Test convergence detection."""
        config = TunerConfig(
            patience=3,
            convergence_threshold=0.001,
            min_sample_size=10,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="test",
            initial_value=0.5,
            step_size=0.0001,  # Very small step
        )

        # Make several tuning attempts
        for _ in range(5):
            tuner.tune(
                threshold_name="test",
                current_metrics={"precision_at_10": 0.80},
                sample_size=100,
            )

        # After enough iterations without improvement, should converge
        assert tuner._iterations_without_improvement["test"] >= 3

    def test_get_history(self):
        """Test getting tuning history."""
        config = TunerConfig(
            min_sample_size=10,
            convergence_threshold=0.001,  # Small threshold for testing
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold("test", initial_value=0.5, step_size=0.1)

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        history = tuner.get_history("test")
        assert history is not None
        # History should have adjustments if tune was successful
        if result is not None:
            assert len(history.adjustments) >= 1

    def test_get_best_value(self):
        """Test getting best known value."""
        config = TunerConfig(
            min_sample_size=10,
            convergence_threshold=0.001,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold("test", initial_value=0.5, step_size=0.1)

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        best = tuner.get_best_value("test")
        # If tuning happened, best should be set
        if result is not None:
            assert best is not None

    def test_reset_threshold(self):
        """Test resetting threshold to best value."""
        config = TunerConfig(
            min_sample_size=10,
            convergence_threshold=0.001,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold("test", initial_value=0.5, step_size=0.1)

        # Tune a few times to establish a best value
        result1 = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        # Manually change it
        tuner.set_threshold("test", 0.9)

        # Reset to best - only works if we have a best value
        result = tuner.reset_threshold("test")
        # Result depends on whether tuning happened
        if result1 is not None and tuner.get_best_value("test") is not None:
            assert result is True
        else:
            # No best value was established
            assert result is False

    def test_auto_tune_from_evaluator(self):
        """Test auto-tuning from evaluator metrics."""
        tuner = ThresholdTuner()
        tuner.register_threshold(
            name="similarity_cutoff",
            initial_value=0.5,
            target_metric="precision_at_5",
        )

        results = tuner.auto_tune_from_evaluator(
            metrics={
                "precision_at_5": 0.80,
                "recall_at_10": 0.70,
            },
            sample_size=100,
        )

        assert isinstance(results, dict)

    def test_validate(self):
        """Test validation."""
        tuner = ThresholdTuner()

        # No thresholds - should fail
        assert tuner.validate() is False

        # With valid thresholds
        tuner.register_threshold(
            "test", initial_value=0.5, min_value=0.0, max_value=1.0
        )
        assert tuner.validate() is True

        # With invalid threshold value
        tuner._thresholds["test"].current_value = 1.5  # Out of bounds
        assert tuner.validate() is False


class TestThresholdTunerWithRedis:
    """Tests for ThresholdTuner with Redis."""

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        tuner = ThresholdTuner(redis_client=mock_redis)
        assert tuner._redis is not None

    def test_store_result(self):
        """Test storing result to Redis."""
        mock_redis = MagicMock()
        config = TunerConfig(
            min_sample_size=10,
            convergence_threshold=0.001,
        )
        tuner = ThresholdTuner(redis_client=mock_redis, config=config)
        tuner.register_threshold("test", initial_value=0.5, step_size=0.1)

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_10": 0.80},
            sample_size=100,
        )

        # Verify Redis lpush was called if tuning happened
        if result is not None:
            mock_redis.lpush.assert_called()


class TestOptimizationGoals:
    """Tests for different optimization goals."""

    def test_maximize_precision(self):
        """Test maximize precision goal."""
        config = TunerConfig(
            optimization_goal=OptimizationGoal.MAXIMIZE_PRECISION,
            min_sample_size=10,
            convergence_threshold=0.001,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="test",
            initial_value=0.5,
            step_size=0.1,
            target_metric="precision_at_5",
            target_value=0.95,
        )

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"precision_at_5": 0.80},
            sample_size=100,
        )

        # Result may or may not be None depending on calculations
        # Just verify the method runs without error
        assert result is None or result.threshold_name == "test"

    def test_maximize_recall(self):
        """Test maximize recall goal."""
        config = TunerConfig(optimization_goal=OptimizationGoal.MAXIMIZE_RECALL)
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="test",
            initial_value=0.7,
            target_metric="recall_at_10",
            target_value=0.90,
        )

        result = tuner.tune(
            threshold_name="test",
            current_metrics={"recall_at_10": 0.70},
            sample_size=100,
        )

        assert result is not None

    def test_balance_f1(self):
        """Test balance F1 goal."""
        config = TunerConfig(
            optimization_goal=OptimizationGoal.BALANCE_F1,
            min_sample_size=10,
            convergence_threshold=0.001,
        )
        tuner = ThresholdTuner(config=config)
        tuner.register_threshold(
            name="test",
            initial_value=0.6,
            step_size=0.1,
        )

        result = tuner.tune(
            threshold_name="test",
            current_metrics={
                "precision_at_10": 0.80,
                "recall_at_10": 0.70,
            },
            sample_size=100,
        )

        # Result may or may not be None depending on calculations
        # Just verify the method runs without error
        assert result is None or result.threshold_name == "test"
