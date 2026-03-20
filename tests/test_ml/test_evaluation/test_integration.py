"""Integration tests for ML evaluation module.

Tests the full evaluation pipeline from data generation to reporting.
"""

from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "src")

from ml.evaluation.brain_eval import (
    BrainEvalClient,
    BrainEvalConfig,
    DataSourceType,
    EvalResult,
    EvaluationOrchestrator,
)
from ml.evaluation.metrics import EvaluationMetrics, compute_all_metrics
from ml.evaluation.reporting import (
    BenchmarkComparison,
    RegressionSeverity,
    RegressionThresholds,
    compare_to_benchmark,
    generate_comparison_report,
)


class TestFullEvaluationPipeline:
    """Tests for the complete evaluation pipeline."""

    def test_full_evaluation_pipeline(self):
        """End-to-end: generate data -> evaluate -> compare -> report.

        This test exercises the entire evaluation workflow from synthetic
        data generation through metric computation, benchmark comparison,
        and report generation.
        """
        # 1. Create BrainEval client with synthetic data
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=500,
            random_seed=42,
        )
        client = BrainEvalClient(config)

        # 2. Generate synthetic data
        data = client.generate_synthetic_data()
        assert "y_true" in data
        assert "y_pred" in data
        assert "y_proba" in data
        assert "returns" in data
        assert "trades" in data
        assert len(data["y_true"]) == 500

        # 3. Compute all metrics
        metrics = compute_all_metrics(
            y_true=data["y_true"],
            y_pred=data["y_pred"],
            y_proba=data["y_proba"],
            returns=data["returns"],
            trades=data["trades"],
            benchmark_returns=data["benchmark_returns"],
        )

        # Verify all 16 metrics are computed
        assert isinstance(metrics.accuracy, float)
        assert isinstance(metrics.precision, float)
        assert isinstance(metrics.recall, float)
        assert isinstance(metrics.f1, float)
        assert isinstance(metrics.auc_roc, float)
        assert isinstance(metrics.log_loss, float)
        assert isinstance(metrics.calibration_error, float)
        assert isinstance(metrics.brier_score, float)
        assert isinstance(metrics.sharpe_ratio, float)
        assert isinstance(metrics.max_drawdown, float)
        assert isinstance(metrics.win_rate, float)
        assert isinstance(metrics.profit_factor, float)
        assert isinstance(metrics.expectancy, float)
        assert isinstance(metrics.kelly_fraction, float)
        assert isinstance(metrics.information_ratio, float)
        assert isinstance(metrics.sortino_ratio, float)

        # 4. Create baseline metrics for comparison
        baseline_metrics = {
            "accuracy": 0.75,
            "precision": 0.70,
            "recall": 0.80,
            "f1": 0.75,
            "sharpe_ratio": 1.0,
            "win_rate": 0.50,
        }

        current_metrics = {
            "accuracy": metrics.accuracy,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
            "sharpe_ratio": metrics.sharpe_ratio,
            "win_rate": metrics.win_rate,
        }

        # 5. Compare to benchmark
        comparison = compare_to_benchmark(
            current_metrics=current_metrics,
            baseline_metrics=baseline_metrics,
            model_id="test_model_v1",
        )

        assert isinstance(comparison, BenchmarkComparison)
        assert comparison.model_id == "test_model_v1"
        assert len(comparison.regressions) == len(baseline_metrics)

        # 6. Generate report
        report = generate_comparison_report(comparison)
        assert "Benchmark Comparison Report" in report
        assert "test_model_v1" in report
        assert "Overall Severity" in report

    def test_batch_evaluation_with_comparison(self):
        """Evaluate 3 models, compare best vs worst.

        This test validates batch evaluation and model comparison
        functionality of the client and orchestrator.
        """
        # Setup
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=300,
            random_seed=123,
        )
        client = BrainEvalClient(config)
        orchestrator = EvaluationOrchestrator(client)

        # Evaluate 3 model versions using client's batch_evaluate
        model_versions = [
            ("grid_btc", "v1"),
            ("grid_btc", "v2"),
            ("grid_btc", "v3"),
        ]

        results = client.batch_evaluate(model_versions)
        assert len(results) == 3

        # Get best model by F1 using orchestrator
        best_model = orchestrator.get_best_model(results, metric="f1")
        assert best_model is not None
        assert best_model.model_id == "grid_btc"

        # Get best by Sharpe ratio
        best_sharpe = orchestrator.get_best_model(results, metric="sharpe_ratio")
        assert best_sharpe is not None

        # Compare first and last model using orchestrator
        comparison = orchestrator.compare_models(
            ("grid_btc", "v1"),
            ("grid_btc", "v3"),
        )
        assert "model_a" in comparison
        assert "model_b" in comparison
        assert "deltas" in comparison
        assert "better_model" in comparison
        assert comparison["better_model"] in ["a", "b", "tie"]

        # Verify deltas contain all 16 metrics
        assert len(comparison["deltas"]) == 16

    def test_regression_detection_in_pipeline(self):
        """Create baseline + degraded model, detect regression.

        This test creates a scenario where a newer model version
        performs worse than baseline and verifies regression detection.
        """
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=400,
            random_seed=456,
        )
        client = BrainEvalClient(config)

        # Create baseline evaluation (good performance)
        baseline_data = client.generate_synthetic_data(n_samples=400, random_seed=100)
        baseline_metrics = compute_all_metrics(
            y_true=baseline_data["y_true"],
            y_pred=baseline_data["y_pred"],
            y_proba=baseline_data["y_proba"],
            returns=baseline_data["returns"],
            trades=baseline_data["trades"],
            benchmark_returns=baseline_data["benchmark_returns"],
        )

        # Create degraded model (introduce noise to predictions)
        degraded_data = client.generate_synthetic_data(n_samples=400, random_seed=100)
        # Add more noise to predictions
        noise_mask = np.random.random(400) < 0.4  # 40% noise
        degraded_data["y_pred"] = degraded_data["y_pred"].copy()
        degraded_data["y_pred"][noise_mask] = 1 - degraded_data["y_pred"][noise_mask]

        degraded_metrics = compute_all_metrics(
            y_true=degraded_data["y_true"],
            y_pred=degraded_data["y_pred"],
            y_proba=degraded_data["y_proba"],
            returns=degraded_data["returns"],
            trades=degraded_data["trades"],
            benchmark_returns=degraded_data["benchmark_returns"],
        )

        # Convert to dicts for comparison
        baseline_dict = {
            "accuracy": baseline_metrics.accuracy,
            "precision": baseline_metrics.precision,
            "recall": baseline_metrics.recall,
            "f1": baseline_metrics.f1,
            "auc_roc": baseline_metrics.auc_roc,
        }

        degraded_dict = {
            "accuracy": degraded_metrics.accuracy,
            "precision": degraded_metrics.precision,
            "recall": degraded_metrics.recall,
            "f1": degraded_metrics.f1,
            "auc_roc": degraded_metrics.auc_roc,
        }

        # Detect regression with custom thresholds
        thresholds = RegressionThresholds(
            low_threshold=0.02,
            medium_threshold=0.05,
            high_threshold=0.10,
            critical_threshold=0.20,
        )

        comparison = compare_to_benchmark(
            current_metrics=degraded_dict,
            baseline_metrics=baseline_dict,
            thresholds=thresholds,
            model_id="degraded_model",
        )

        # Verify regression was detected
        regressions = [r for r in comparison.regressions if r.is_regression]
        assert len(regressions) > 0, "Expected to detect regressions in degraded model"

        # Check that accuracy regression is detected (higher noise = lower accuracy)
        accuracy_regression = next(
            (r for r in regressions if r.metric_name == "accuracy"), None
        )
        if accuracy_regression:
            assert accuracy_regression.delta < 0  # Should be negative (worse)
            assert accuracy_regression.severity != RegressionSeverity.NONE

    def test_evaluation_metrics_serialization(self):
        """Full roundtrip: EvalResult -> JSON -> dict -> EvalResult.

        Tests that evaluation results can be serialized to JSON and
        deserialized back without data loss.
        """
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=200,
            random_seed=789,
        )
        client = BrainEvalClient(config)

        # Create evaluation result
        original_result = client.evaluate_model(
            model_id="serialization_test",
            version_id="v1.0",
        )

        # Serialize to dict
        result_dict = original_result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["model_id"] == "serialization_test"
        assert result_dict["version_id"] == "v1.0"
        assert "metrics" in result_dict
        assert "timestamp" in result_dict

        # Convert to JSON string
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)

        # Parse back from JSON
        parsed_dict = json.loads(json_str)

        # Reconstruct EvalResult
        restored_result = EvalResult.from_dict(parsed_dict)

        # Verify all fields match
        assert restored_result.model_id == original_result.model_id
        assert restored_result.version_id == original_result.version_id
        assert restored_result.sample_count == original_result.sample_count
        assert restored_result.data_source == original_result.data_source

        # Verify all metrics match
        assert (
            abs(restored_result.metrics.accuracy - original_result.metrics.accuracy)
            < 1e-10
        )
        assert (
            abs(restored_result.metrics.precision - original_result.metrics.precision)
            < 1e-10
        )
        assert (
            abs(restored_result.metrics.recall - original_result.metrics.recall) < 1e-10
        )
        assert abs(restored_result.metrics.f1 - original_result.metrics.f1) < 1e-10
        assert (
            abs(
                restored_result.metrics.sharpe_ratio
                - original_result.metrics.sharpe_ratio
            )
            < 1e-10
        )

    def test_benchmark_comparison_serialization(self):
        """Full roundtrip: BenchmarkComparison -> JSON -> dict -> BenchmarkComparison.

        Tests that benchmark comparison results can be serialized to JSON
        and deserialized back without data loss.
        """
        # Create benchmark comparison
        baseline = {
            "accuracy": 0.85,
            "precision": 0.82,
            "recall": 0.88,
            "f1": 0.85,
            "sharpe_ratio": 1.5,
            "log_loss": 0.35,
        }

        current = {
            "accuracy": 0.82,  # Regression
            "precision": 0.80,  # Regression
            "recall": 0.90,  # Improvement
            "f1": 0.84,  # Slight regression
            "sharpe_ratio": 1.3,  # Regression
            "log_loss": 0.40,  # Regression (higher is worse)
        }

        thresholds = RegressionThresholds(
            low_threshold=0.02,
            medium_threshold=0.05,
            high_threshold=0.10,
            critical_threshold=0.20,
        )

        original_comparison = compare_to_benchmark(
            current_metrics=current,
            baseline_metrics=baseline,
            thresholds=thresholds,
            model_id="comparison_test",
        )

        # Serialize to dict
        comp_dict = original_comparison.to_dict()
        assert isinstance(comp_dict, dict)
        assert comp_dict["model_id"] == "comparison_test"
        assert "regressions" in comp_dict
        assert "overall_severity" in comp_dict

        # Convert to JSON string
        json_str = json.dumps(comp_dict)

        # Parse back from JSON
        parsed_dict = json.loads(json_str)

        # Reconstruct BenchmarkComparison
        restored_comparison = BenchmarkComparison.from_dict(parsed_dict)

        # Verify all fields match
        assert restored_comparison.model_id == original_comparison.model_id
        assert (
            restored_comparison.overall_severity == original_comparison.overall_severity
        )
        assert len(restored_comparison.regressions) == len(
            original_comparison.regressions
        )

        # Verify each regression matches
        for orig_reg, rest_reg in zip(
            original_comparison.regressions,
            restored_comparison.regressions,
            strict=True,
        ):
            assert orig_reg.metric_name == rest_reg.metric_name
            assert abs(orig_reg.baseline_value - rest_reg.baseline_value) < 1e-10
            assert abs(orig_reg.current_value - rest_reg.current_value) < 1e-10
            assert abs(orig_reg.delta - rest_reg.delta) < 1e-10
            assert orig_reg.severity == rest_reg.severity
            assert orig_reg.is_regression == rest_reg.is_regression

    def test_end_to_end_with_registry_simulation(self):
        """Use evaluate_from_registry() in full pipeline.

        Tests the registry-based evaluation workflow that would be used
        in production with the model registry.
        """
        # Create orchestrator
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=600,
            random_seed=999,
        )
        client = BrainEvalClient(config)
        orchestrator = EvaluationOrchestrator(client)

        # Evaluate from registry (simulated)
        result = orchestrator.run_evaluation(
            model_id="production_model",
            version_id="v2.1.0",
        )

        # Verify result
        assert result.model_id == "production_model"
        assert result.version_id == "v2.1.0"
        assert result.sample_count == 600
        assert result.data_source == DataSourceType.SYNTHETIC

        # Verify metrics are computed
        assert 0.0 <= result.metrics.accuracy <= 1.0
        assert 0.0 <= result.metrics.precision <= 1.0
        assert 0.0 <= result.metrics.recall <= 1.0
        assert 0.0 <= result.metrics.f1 <= 1.0
        assert 0.0 <= result.metrics.auc_roc <= 1.0
        assert result.metrics.log_loss >= 0.0
        assert 0.0 <= result.metrics.calibration_error <= 1.0
        assert 0.0 <= result.metrics.brier_score <= 1.0
        assert 0.0 <= result.metrics.max_drawdown <= 1.0
        assert 0.0 <= result.metrics.win_rate <= 1.0
        assert 0.0 <= result.metrics.kelly_fraction <= 1.0

        # Create comparison with previous version
        previous_metrics = {
            "accuracy": 0.78,
            "f1": 0.76,
            "sharpe_ratio": 1.2,
        }

        current_metrics = {
            "accuracy": result.metrics.accuracy,
            "f1": result.metrics.f1,
            "sharpe_ratio": result.metrics.sharpe_ratio,
        }

        comparison = compare_to_benchmark(
            current_metrics=current_metrics,
            baseline_metrics=previous_metrics,
            model_id="production_model_v2.1.0",
        )

        # Generate report
        report = generate_comparison_report(comparison)

        # Verify report structure
        assert "production_model_v2.1.0" in report
        assert "accuracy" in report.lower()
        assert "f1" in report.lower()


class TestIntegrationEdgeCases:
    """Edge case tests for integration scenarios."""

    def test_empty_data_handling(self):
        """Test pipeline handles empty data gracefully."""
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=0,
            random_seed=42,
        )
        client = BrainEvalClient(config)

        # Generate empty data
        data = client.generate_synthetic_data(n_samples=0)
        assert len(data["y_true"]) == 0

        # Compute metrics on empty data
        metrics = compute_all_metrics(
            y_true=data["y_true"],
            y_pred=data["y_pred"],
            y_proba=data["y_proba"],
            returns=data["returns"],
            trades=data["trades"],
            benchmark_returns=data["benchmark_returns"],
        )

        # Should return zeros for empty data
        assert metrics.accuracy == 0.0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0

    def test_single_sample_evaluation(self):
        """Test pipeline with single sample."""
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=1,
            random_seed=42,
        )
        client = BrainEvalClient(config)

        result = client.evaluate_model("single_sample_model", "v1")

        assert result.sample_count == 1
        assert isinstance(result.metrics, EvaluationMetrics)

    def test_perfect_model_scenario(self):
        """Test pipeline with perfect predictions."""
        # Create perfect predictions
        y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
        y_pred = y_true.copy()  # Perfect predictions
        y_proba = y_true.astype(float)  # Perfect probabilities

        returns = np.array(
            [0.01, -0.005, 0.02, -0.003, 0.015, -0.002, 0.018, -0.004, 0.012, -0.001]
        )
        trades = np.array([100, -30, 150, -20, 120, -15, 180, -25, 110, -10])

        metrics = compute_all_metrics(
            y_true=y_true,
            y_pred=y_pred,
            y_proba=y_proba,
            returns=returns,
            trades=trades,
            benchmark_returns=np.zeros_like(returns),
        )

        # Perfect classification metrics
        assert metrics.accuracy == 1.0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0

    def test_worst_model_scenario(self):
        """Test pipeline with worst predictions."""
        # Create worst predictions (all wrong)
        y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
        y_pred = 1 - y_true  # All predictions wrong
        y_proba = 1 - y_true.astype(float)  # Wrong probabilities

        returns = np.array(
            [0.01, -0.005, 0.02, -0.003, 0.015, -0.002, 0.018, -0.004, 0.012, -0.001]
        )
        trades = np.array(
            [-100, 30, -150, 20, -120, 15, -180, 25, -110, 10]
        )  # All losses

        metrics = compute_all_metrics(
            y_true=y_true,
            y_pred=y_pred,
            y_proba=y_proba,
            returns=returns,
            trades=trades,
            benchmark_returns=np.zeros_like(returns),
        )

        # Worst classification metrics
        assert metrics.accuracy == 0.0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0

    def test_large_batch_evaluation(self):
        """Test pipeline with large batch of models."""
        config = BrainEvalConfig(
            data_source=DataSourceType.SYNTHETIC,
            n_samples=100,
            random_seed=42,
        )
        client = BrainEvalClient(config)

        # Evaluate 10 models
        model_versions = [(f"model_{i}", f"v{i}") for i in range(10)]
        results = client.batch_evaluate(model_versions)

        assert len(results) == 10

        # All results should have valid metrics
        for result in results:
            assert isinstance(result.metrics, EvaluationMetrics)
            assert 0.0 <= result.metrics.accuracy <= 1.0
