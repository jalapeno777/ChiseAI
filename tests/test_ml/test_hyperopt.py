"""Tests for hyperparameter optimization module."""

from __future__ import annotations

import pytest

from ml.hyperopt import (
    GeneticOptimizer,
    HyperparameterOptimizer,
    OptimizationConfig,
    OptimizationMethod,
    OptimizationResult,
    OptimizationTrial,
    ParameterConstraint,
    ParameterType,
)


class TestParameterConstraint:
    """Tests for ParameterConstraint class."""

    def test_float_constraint_validation(self) -> None:
        """Test float parameter validation."""
        constraint = ParameterConstraint(
            name="learning_rate",
            param_type=ParameterType.FLOAT,
            min_value=0.001,
            max_value=0.1,
        )

        assert constraint.validate_value(0.01) is True
        assert constraint.validate_value(0.001) is True
        assert constraint.validate_value(0.1) is True
        assert constraint.validate_value(0.0001) is False  # Below min
        assert constraint.validate_value(0.2) is False  # Above max
        assert constraint.validate_value("invalid") is False  # Wrong type

    def test_integer_constraint_validation(self) -> None:
        """Test integer parameter validation."""
        constraint = ParameterConstraint(
            name="window_size",
            param_type=ParameterType.INTEGER,
            min_value=5,
            max_value=50,
        )

        assert constraint.validate_value(20) is True
        assert constraint.validate_value(5) is True
        assert constraint.validate_value(50) is True
        assert constraint.validate_value(4) is False  # Below min
        assert constraint.validate_value(51) is False  # Above max
        assert constraint.validate_value(20.5) is False  # Not integer

    def test_categorical_constraint_validation(self) -> None:
        """Test categorical parameter validation."""
        constraint = ParameterConstraint(
            name="strategy_type",
            param_type=ParameterType.CATEGORICAL,
            choices=["trend", "mean_reversion", "breakout"],
        )

        assert constraint.validate_value("trend") is True
        assert constraint.validate_value("mean_reversion") is True
        assert constraint.validate_value("invalid") is False

    def test_boolean_constraint_validation(self) -> None:
        """Test boolean parameter validation."""
        constraint = ParameterConstraint(
            name="use_stop_loss",
            param_type=ParameterType.BOOLEAN,
        )

        assert constraint.validate_value(True) is True
        assert constraint.validate_value(False) is True
        assert constraint.validate_value(1) is False
        assert constraint.validate_value("true") is False

    def test_random_sampling_float(self) -> None:
        """Test random sampling for float parameters."""
        constraint = ParameterConstraint(
            name="param",
            param_type=ParameterType.FLOAT,
            min_value=0.0,
            max_value=1.0,
        )

        samples = [constraint.sample_random() for _ in range(10)]

        for sample in samples:
            assert isinstance(sample, float)
            assert 0.0 <= sample <= 1.0

    def test_random_sampling_integer(self) -> None:
        """Test random sampling for integer parameters."""
        constraint = ParameterConstraint(
            name="param",
            param_type=ParameterType.INTEGER,
            min_value=1,
            max_value=10,
        )

        samples = [constraint.sample_random() for _ in range(10)]

        for sample in samples:
            assert isinstance(sample, int)
            assert 1 <= sample <= 10

    def test_random_sampling_categorical(self) -> None:
        """Test random sampling for categorical parameters."""
        constraint = ParameterConstraint(
            name="param",
            param_type=ParameterType.CATEGORICAL,
            choices=["a", "b", "c"],
        )

        samples = [constraint.sample_random() for _ in range(10)]

        for sample in samples:
            assert sample in ["a", "b", "c"]


class TestOptimizationConfig:
    """Tests for OptimizationConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = OptimizationConfig()

        assert config.method == OptimizationMethod.BAYESIAN
        assert config.max_iterations == 100
        assert config.convergence_threshold == 0.05
        assert config.max_time_hours == 24.0
        assert config.population_size == 50
        assert config.mutation_rate == 0.1
        assert config.crossover_rate == 0.8

    def test_invalid_max_iterations_raises(self) -> None:
        """Test that invalid max_iterations raises ValueError."""
        with pytest.raises(ValueError, match="max_iterations must be at least 10"):
            OptimizationConfig(max_iterations=5)

    def test_invalid_convergence_threshold_raises(self) -> None:
        """Test that invalid convergence_threshold raises ValueError."""
        with pytest.raises(ValueError, match="convergence_threshold must be between"):
            OptimizationConfig(convergence_threshold=1.5)


class TestOptimizationTrial:
    """Tests for OptimizationTrial class."""

    def test_trial_creation(self) -> None:
        """Test trial creation."""
        trial = OptimizationTrial(
            trial_id="test_trial_1",
            iteration=0,
            parameters={"param1": 0.5, "param2": 10},
            score=1.5,
            metrics={"sharpe": 1.5, "drawdown": 10.0},
            duration_seconds=60.0,
        )

        assert trial.trial_id == "test_trial_1"
        assert trial.iteration == 0
        assert trial.score == 1.5
        assert trial.duration_seconds == 60.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        trial = OptimizationTrial(
            trial_id="test_trial",
            iteration=1,
            parameters={"x": 0.5},
            score=1.0,
        )

        data = trial.to_dict()

        assert data["trial_id"] == "test_trial"
        assert data["iteration"] == 1
        assert data["score"] == 1.0
        assert data["parameters"] == {"x": 0.5}


class TestOptimizationResult:
    """Tests for OptimizationResult class."""

    def test_result_creation(self) -> None:
        """Test result creation."""
        result = OptimizationResult(
            strategy_id="test_strategy",
            method=OptimizationMethod.GENETIC,
            best_parameters={"param1": 0.5},
            best_score=1.5,
            improvement_pct=25.0,
            convergence_reached=True,
            variance_across_runs=0.03,
        )

        assert result.strategy_id == "test_strategy"
        assert result.method == OptimizationMethod.GENETIC
        assert result.best_score == 1.5
        assert result.improvement_pct == 25.0
        assert result.convergence_reached is True

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = OptimizationResult(
            strategy_id="test",
            method=OptimizationMethod.BAYESIAN,
            best_score=1.2,
        )

        data = result.to_dict()

        assert data["strategy_id"] == "test"
        assert data["method"] == "bayesian"
        assert data["best_score"] == 1.2
        assert "trials" in data


class TestGeneticOptimizer:
    """Tests for GeneticOptimizer class."""

    def test_optimizer_creation(self) -> None:
        """Test optimizer creation."""
        config = OptimizationConfig(method=OptimizationMethod.GENETIC)
        optimizer = GeneticOptimizer(config)

        assert optimizer.config == config

    def test_simple_optimization(self) -> None:
        """Test simple optimization run."""
        config = OptimizationConfig(
            method=OptimizationMethod.GENETIC,
            max_iterations=10,
            population_size=10,
        )
        optimizer = GeneticOptimizer(config)

        # Simple objective: maximize x where x is between 0 and 10
        def objective(params):
            x = params.get("x", 0)
            return x, {"x": x}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
        ]

        result = optimizer.optimize(objective, constraints, "test_strategy")

        assert result.strategy_id == "test_strategy"
        assert result.method == OptimizationMethod.GENETIC
        assert len(result.trials) > 0
        # Should find a value close to 10
        assert result.best_score > 7.0

    def test_convergence_detection(self) -> None:
        """Test convergence detection."""
        config = OptimizationConfig(
            method=OptimizationMethod.GENETIC,
            max_iterations=20,
            convergence_threshold=0.1,
        )
        optimizer = GeneticOptimizer(config)

        # Add some trials with low variance
        for i in range(15):
            trial = OptimizationTrial(
                trial_id=f"trial_{i}",
                iteration=i,
                parameters={"x": 5.0},
                score=5.0 + (i * 0.01),  # Very small variance
            )
            optimizer._trials.append(trial)

        converged, variance = optimizer._check_convergence(window_size=10)

        assert converged is True
        assert variance < config.convergence_threshold


class TestHyperparameterOptimizer:
    """Tests for HyperparameterOptimizer class."""

    def test_optimizer_creation(self) -> None:
        """Test optimizer creation."""
        config = OptimizationConfig()
        optimizer = HyperparameterOptimizer(config)

        assert optimizer.config == config

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        optimizer = HyperparameterOptimizer()

        constraints = [
            ParameterConstraint(
                name="param1",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=1.0,
            ),
            ParameterConstraint(
                name="param2",
                param_type=ParameterType.INTEGER,
                min_value=1,
                max_value=10,
            ),
        ]

        params = {"param1": 0.5, "param2": 5}
        results = optimizer.validate_parameters(params, constraints)

        assert results["param1"] is True
        assert results["param2"] is True

    def test_parameter_validation_failure(self) -> None:
        """Test parameter validation with invalid values."""
        optimizer = HyperparameterOptimizer()

        constraints = [
            ParameterConstraint(
                name="param1",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=1.0,
            ),
        ]

        params = {"param1": 1.5}  # Out of range
        results = optimizer.validate_parameters(params, constraints)

        assert results["param1"] is False

    def test_optimization_with_baseline(self) -> None:
        """Test optimization with baseline comparison."""
        config = OptimizationConfig(
            max_iterations=10,
            improvement_threshold=0.05,  # 5%
        )
        optimizer = HyperparameterOptimizer(config)

        def objective(params):
            x = params.get("x", 0)
            return x * 2, {"score": x * 2}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
        ]

        baseline = {"sharpe_ratio": 5.0}
        result = optimizer.optimize(objective, constraints, "test", baseline)

        assert result.baseline_score == 5.0
        # Should show improvement
        assert result.improvement_pct != 0


class TestOptimizationMethods:
    """Tests for different optimization methods."""

    def test_genetic_method(self) -> None:
        """Test genetic algorithm optimization."""
        config = OptimizationConfig(
            method=OptimizationMethod.GENETIC,
            max_iterations=10,
            population_size=10,
        )
        optimizer = HyperparameterOptimizer(config)

        def objective(params):
            return params.get("x", 0), {}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
        ]

        result = optimizer.optimize(objective, constraints, "test")
        assert result.method == OptimizationMethod.GENETIC

    def test_bayesian_method(self) -> None:
        """Test Bayesian optimization."""
        config = OptimizationConfig(
            method=OptimizationMethod.BAYESIAN,
            max_iterations=15,
        )
        optimizer = HyperparameterOptimizer(config)

        def objective(params):
            return params.get("x", 0), {}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
        ]

        result = optimizer.optimize(objective, constraints, "test")
        # May fall back to random if optuna not installed
        assert result.method in (OptimizationMethod.BAYESIAN, OptimizationMethod.RANDOM)


class TestOptimizationIntegration:
    """Integration tests for optimization workflow."""

    def test_full_optimization_workflow(self) -> None:
        """Test complete optimization workflow."""
        config = OptimizationConfig(
            method=OptimizationMethod.GENETIC,
            max_iterations=15,
            population_size=20,
            convergence_threshold=0.1,
        )
        optimizer = HyperparameterOptimizer(config)

        # Multi-parameter optimization
        def objective(params):
            x = params.get("x", 0)
            y = params.get("y", 0)
            # Maximize x * y where x in [0, 10], y in [1, 5]
            score = x * y
            return score, {"x": x, "y": y, "product": score}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
            ParameterConstraint(
                name="y",
                param_type=ParameterType.INTEGER,
                min_value=1,
                max_value=5,
            ),
        ]

        result = optimizer.optimize(objective, constraints, "multi_param_strategy")

        assert result.strategy_id == "multi_param_strategy"
        assert len(result.trials) > 0
        assert "x" in result.best_parameters
        assert "y" in result.best_parameters
        # Best should be close to x=10, y=5 => score=50
        assert result.best_score > 30.0

    def test_optimization_history(self) -> None:
        """Test retrieving optimization history."""
        config = OptimizationConfig(max_iterations=15)
        optimizer = HyperparameterOptimizer(config)

        def objective(params):
            return params.get("x", 0), {}

        constraints = [
            ParameterConstraint(
                name="x",
                param_type=ParameterType.FLOAT,
                min_value=0.0,
                max_value=10.0,
            ),
        ]

        optimizer.optimize(objective, constraints, "test")
        history = optimizer.get_optimization_history()

        assert len(history) > 0
        assert all(isinstance(t, OptimizationTrial) for t in history)
