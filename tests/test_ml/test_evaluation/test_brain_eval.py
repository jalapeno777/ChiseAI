"""Tests for BrainEvalClient and EvaluationOrchestrator in brain_eval.py.

Tests client initialization, synthetic data generation, model evaluation,
batch evaluation, and model comparison/orchestration.
"""

import numpy as np
import pytest

from ml.evaluation.brain_eval import (
    BrainEvalClient,
    BrainEvalConfig,
    DataSourceType,
    EvalResult,
    EvaluationOrchestrator,
)
from ml.evaluation.metrics import EvaluationMetrics


class TestBrainEvalConfig:
    """Tests for BrainEvalConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BrainEvalConfig()
        assert config.data_source == DataSourceType.SYNTHETIC
        assert config.n_samples == 1000
        assert config.random_seed == 42
        assert len(config.metrics_to_compute) == 16

    def test_custom_config(self):
        """Test custom configuration."""
        config = BrainEvalConfig(
            data_source=DataSourceType.API,
            api_url="http://example.com",
            n_samples=500,
            random_seed=123,
        )
        assert config.data_source == DataSourceType.API
        assert config.api_url == "http://example.com"
        assert config.n_samples == 500

    def test_frozen_immutability(self):
        """Test that BrainEvalConfig is frozen."""
        config = BrainEvalConfig()
        with pytest.raises(AttributeError):
            config.n_samples = 9999


class TestEvalResult:
    """Tests for EvalResult dataclass."""

    def test_to_dict(self):
        """Test EvalResult serialization."""
        metrics = EvaluationMetrics(accuracy=0.75, f1=0.70)
        result = EvalResult(
            model_id="test_model",
            version_id="v1",
            metrics=metrics,
            sample_count=100,
            data_source=DataSourceType.SYNTHETIC,
        )
        d = result.to_dict()
        assert d["model_id"] == "test_model"
        assert d["version_id"] == "v1"
        assert d["data_source"] == "synthetic"
        assert d["sample_count"] == 100
        assert d["metrics"]["accuracy"] == 0.75

    def test_from_dict(self):
        """Test EvalResult deserialization."""
        metrics = EvaluationMetrics(accuracy=0.75, f1=0.70)
        result = EvalResult(
            model_id="test_model",
            version_id="v1",
            metrics=metrics,
            sample_count=100,
            data_source=DataSourceType.SYNTHETIC,
        )
        d = result.to_dict()
        restored = EvalResult.from_dict(d)
        assert restored.model_id == "test_model"
        assert restored.metrics.accuracy == 0.75
        assert restored.data_source == DataSourceType.SYNTHETIC

    def test_round_trip_serialization(self):
        """Test round-trip serialization preserves all fields."""
        metrics = EvaluationMetrics(
            accuracy=0.80,
            precision=0.75,
            recall=0.70,
            f1=0.72,
            sharpe_ratio=1.5,
        )
        result = EvalResult(
            model_id="grid_btc",
            version_id="v2",
            metrics=metrics,
            sample_count=1000,
            data_source=DataSourceType.SYNTHETIC,
            metadata={"key": "value"},
        )
        restored = EvalResult.from_dict(result.to_dict())
        assert restored.model_id == "grid_btc"
        assert restored.metrics.sharpe_ratio == 1.5
        assert restored.metadata == {"key": "value"}


class TestBrainEvalClientInit:
    """Tests for BrainEvalClient initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        client = BrainEvalClient()
        assert client._config.data_source == DataSourceType.SYNTHETIC
        assert client._config.n_samples == 1000

    def test_custom_config_initialization(self, synthetic_config):
        """Test initialization with custom config."""
        client = BrainEvalClient(config=synthetic_config)
        assert client._config.n_samples == 500
        assert client._config.random_seed == 42


class TestBrainEvalClientSyntheticData:
    """Tests for synthetic data generation."""

    def test_generate_synthetic_data_structure(self, brain_eval_client):
        """Test that synthetic data has correct structure."""
        data = brain_eval_client.generate_synthetic_data()
        assert "y_true" in data
        assert "y_pred" in data
        assert "y_proba" in data
        assert "returns" in data
        assert "trades" in data
        assert "benchmark_returns" in data

    def test_generate_synthetic_data_types(self, brain_eval_client):
        """Test that synthetic data has correct types."""
        data = brain_eval_client.generate_synthetic_data()
        assert isinstance(data["y_true"], np.ndarray)
        assert isinstance(data["y_pred"], np.ndarray)
        assert isinstance(data["y_proba"], np.ndarray)
        assert isinstance(data["returns"], np.ndarray)
        assert isinstance(data["trades"], np.ndarray)
        assert isinstance(data["benchmark_returns"], np.ndarray)

    def test_generate_synthetic_data_shapes(self, brain_eval_client):
        """Test that synthetic data arrays have correct shapes."""
        data = brain_eval_client.generate_synthetic_data()
        n = brain_eval_client._config.n_samples
        assert len(data["y_true"]) == n
        assert len(data["y_pred"]) == n
        assert len(data["y_proba"]) == n
        assert len(data["returns"]) == n
        assert len(data["trades"]) == n
        assert len(data["benchmark_returns"]) == n

    def test_generate_synthetic_data_custom_params(self, brain_eval_client):
        """Test generation with custom n_samples and random_seed."""
        data = brain_eval_client.generate_synthetic_data(n_samples=100, random_seed=99)
        assert len(data["y_true"]) == 100

    def test_generate_synthetic_data_reproducibility(self, brain_eval_client):
        """Test that same seed produces same data."""
        data1 = brain_eval_client.generate_synthetic_data(random_seed=42)
        data2 = brain_eval_client.generate_synthetic_data(random_seed=42)
        np.testing.assert_array_equal(data1["y_true"], data2["y_true"])
        np.testing.assert_array_equal(data1["y_pred"], data2["y_pred"])

    def test_generate_synthetic_data_binary_labels(self, brain_eval_client):
        """Test that y_true and y_pred are binary."""
        data = brain_eval_client.generate_synthetic_data()
        assert set(np.unique(data["y_true"])).issubset({0, 1})
        assert set(np.unique(data["y_pred"])).issubset({0, 1})

    def test_generate_synthetic_data_probabilities_in_range(self, brain_eval_client):
        """Test that probabilities are in valid range."""
        data = brain_eval_client.generate_synthetic_data()
        assert np.all(data["y_proba"] >= 0.0)
        assert np.all(data["y_proba"] <= 1.0)


class TestBrainEvalClientEvaluate:
    """Tests for model evaluation."""

    def test_evaluate_model_returns_eval_result(self, brain_eval_client):
        """Test that evaluate_model returns an EvalResult."""
        result = brain_eval_client.evaluate_model("model_v1", "version_1")
        assert isinstance(result, EvalResult)

    def test_evaluate_model_metadata(self, brain_eval_client):
        """Test evaluation result has correct metadata."""
        result = brain_eval_client.evaluate_model("model_v1", "version_1")
        assert result.model_id == "model_v1"
        assert result.version_id == "version_1"
        assert result.sample_count == brain_eval_client._config.n_samples
        assert result.data_source == DataSourceType.SYNTHETIC

    def test_evaluate_model_metrics_computed(self, brain_eval_client):
        """Test that evaluation computes all metrics."""
        result = brain_eval_client.evaluate_model("model_v1", "version_1")
        metrics = result.metrics
        assert 0.0 <= metrics.accuracy <= 1.0
        assert 0.0 <= metrics.precision <= 1.0
        assert 0.0 <= metrics.recall <= 1.0
        assert 0.0 <= metrics.f1 <= 1.0

    def test_evaluate_model_with_provided_data(
        self, brain_eval_client, sample_evaluation_data
    ):
        """Test evaluation with explicitly provided data."""
        result = brain_eval_client.evaluate_model(
            "model_v1",
            "version_1",
            data=sample_evaluation_data,
        )
        assert isinstance(result, EvalResult)
        assert result.sample_count == len(sample_evaluation_data["y_true"])

    def test_evaluate_from_registry(self, brain_eval_client):
        """Test evaluation from registry (uses synthetic data)."""
        result = brain_eval_client.evaluate_from_registry("model_v1", "version_1")
        assert isinstance(result, EvalResult)
        assert result.model_id == "model_v1"


class TestBrainEvalClientBatchEvaluate:
    """Tests for batch evaluation."""

    def test_batch_evaluate(self, brain_eval_client):
        """Test batch evaluation of multiple models."""
        model_versions = [
            ("model_a", "v1"),
            ("model_b", "v2"),
            ("model_c", "v3"),
        ]
        results = brain_eval_client.batch_evaluate(model_versions)
        assert len(results) == 3
        assert all(isinstance(r, EvalResult) for r in results)
        assert results[0].model_id == "model_a"
        assert results[1].model_id == "model_b"
        assert results[2].model_id == "model_c"

    def test_batch_evaluate_empty(self, brain_eval_client):
        """Test batch evaluation with empty list."""
        results = brain_eval_client.batch_evaluate([])
        assert results == []


class TestEvaluationOrchestrator:
    """Tests for EvaluationOrchestrator."""

    @pytest.fixture
    def orchestrator(self, brain_eval_client):
        """Create an EvaluationOrchestrator."""
        return EvaluationOrchestrator(client=brain_eval_client)

    def test_initialization(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator._client is not None

    def test_run_evaluation(self, orchestrator):
        """Test running single evaluation."""
        result = orchestrator.run_evaluation("grid_btc", "v1")
        assert isinstance(result, EvalResult)
        assert result.model_id == "grid_btc"
        assert result.version_id == "v1"

    def test_compare_models(self, orchestrator):
        """Test comparing two models."""
        comparison = orchestrator.compare_models(
            ("model_a", "v1"),
            ("model_b", "v2"),
        )
        assert "model_a" in comparison
        assert "model_b" in comparison
        assert "deltas" in comparison
        assert "better_model" in comparison
        assert comparison["better_model"] in ("a", "b", "tie")

    def test_compare_models_deltas_structure(self, orchestrator):
        """Test comparison deltas contain all expected metrics."""
        comparison = orchestrator.compare_models(
            ("model_a", "v1"),
            ("model_b", "v2"),
        )
        expected_metrics = [
            "accuracy",
            "precision",
            "recall",
            "f1",
            "auc_roc",
            "log_loss",
            "calibration_error",
            "brier_score",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "expectancy",
            "kelly_fraction",
            "information_ratio",
            "sortino_ratio",
        ]
        for metric in expected_metrics:
            assert metric in comparison["deltas"]

    def test_compare_models_winning_metrics(self, orchestrator):
        """Test comparison identifies winning metrics."""
        comparison = orchestrator.compare_models(
            ("model_a", "v1"),
            ("model_b", "v2"),
        )
        assert isinstance(comparison["winning_metrics"], list)

    def test_get_best_model(self, orchestrator):
        """Test selecting best model from evaluations."""
        results = [
            orchestrator.run_evaluation("model_a", "v1"),
            orchestrator.run_evaluation("model_b", "v2"),
        ]
        best = orchestrator.get_best_model(results, metric="f1")
        assert isinstance(best, EvalResult)

    def test_get_best_model_empty(self, orchestrator):
        """Test get_best_model returns None for empty list."""
        assert orchestrator.get_best_model([]) is None

    def test_get_best_model_single(self, orchestrator):
        """Test get_best_model returns the only model."""
        result = orchestrator.run_evaluation("model_a", "v1")
        best = orchestrator.get_best_model([result])
        assert best.model_id == "model_a"

    def test_get_best_model_unknown_metric(self, orchestrator):
        """Test get_best_model falls back to f1 for unknown metric."""
        result = orchestrator.run_evaluation("model_a", "v1")
        best = orchestrator.get_best_model([result], metric="unknown_metric")
        assert best is not None
