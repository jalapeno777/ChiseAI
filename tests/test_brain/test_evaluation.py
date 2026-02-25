"""Tests for brain evaluation module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brain.evaluation import (
    BrainEvaluator,
    EvaluationMetrics,
    EvaluationResult,
    EvaluationStatus,
)


class TestEvaluationMetrics:
    """Tests for EvaluationMetrics class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            precision=0.90,
            recall=0.85,
            f1_score=0.875,
        )
        assert metrics.accuracy == 0.95
        assert metrics.precision == 0.90
        assert metrics.recall == 0.85

    def test_invalid_range(self) -> None:
        """Test that invalid metric ranges are rejected."""
        with pytest.raises(ValueError):
            EvaluationMetrics(accuracy=1.5)  # > 1.0

        with pytest.raises(ValueError):
            EvaluationMetrics(precision=-0.1)  # < 0.0

    def test_to_dict(self) -> None:
        """Test serialization."""
        metrics = EvaluationMetrics(
            accuracy=0.95,
            custom_metrics={"custom": 0.8},
        )
        data = metrics.to_dict()
        assert data["accuracy"] == 0.95
        assert data["custom_metrics"] == {"custom": 0.8}

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "accuracy": 0.95,
            "precision": 0.90,
            "recall": 0.85,
            "f1_score": 0.875,
            "paper_carryover_rate": 0.75,
            "custom_metrics": {"custom": 0.8},
        }
        metrics = EvaluationMetrics.from_dict(data)
        assert metrics.accuracy == 0.95
        assert metrics.paper_carryover_rate == 0.75
        assert metrics.custom_metrics == {"custom": 0.8}


class TestEvaluationResult:
    """Tests for EvaluationResult class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        metrics = EvaluationMetrics(accuracy=0.95)
        result = EvaluationResult(
            version="1.0.0",
            status=EvaluationStatus.PASSED,
            metrics=metrics,
            started_at="2024-01-01T00:00:00Z",
        )
        assert result.version == "1.0.0"
        assert result.status == EvaluationStatus.PASSED

    def test_pass_rate(self) -> None:
        """Test pass rate calculation."""
        metrics = EvaluationMetrics()
        result = EvaluationResult(
            version="1.0.0",
            status=EvaluationStatus.PASSED,
            metrics=metrics,
            started_at="2024-01-01T00:00:00Z",
            test_cases_run=100,
            test_cases_passed=95,
        )
        assert result.pass_rate == 0.95
        assert result.test_cases_failed == 5

    def test_to_dict(self) -> None:
        """Test serialization."""
        metrics = EvaluationMetrics(accuracy=0.95)
        result = EvaluationResult(
            version="1.0.0",
            status=EvaluationStatus.PASSED,
            metrics=metrics,
            started_at="2024-01-01T00:00:00Z",
            test_cases_run=100,
            test_cases_passed=95,
        )
        data = result.to_dict()
        assert data["version"] == "1.0.0"
        assert data["status"] == "passed"
        assert data["metrics"]["accuracy"] == 0.95

    def test_from_dict(self) -> None:
        """Test deserialization."""
        data = {
            "version": "1.0.0",
            "status": "passed",
            "metrics": {"accuracy": 0.95},
            "started_at": "2024-01-01T00:00:00Z",
            "test_cases_run": 100,
            "test_cases_passed": 95,
        }
        result = EvaluationResult.from_dict(data)
        assert result.version == "1.0.0"
        assert result.status == EvaluationStatus.PASSED
        assert result.metrics.accuracy == 0.95


class TestBrainEvaluator:
    """Tests for BrainEvaluator class."""

    def test_creation(self) -> None:
        """Test basic creation."""
        evaluator = BrainEvaluator()
        assert evaluator.redis_client is None
        assert evaluator.influxdb_client is None

    def test_default_thresholds(self) -> None:
        """Test default thresholds are set."""
        evaluator = BrainEvaluator()
        assert "accuracy" in evaluator.thresholds
        assert "f1_score" in evaluator.thresholds
        assert evaluator.thresholds["accuracy"] == 0.80

    def test_custom_thresholds(self) -> None:
        """Test custom thresholds."""
        evaluator = BrainEvaluator(thresholds={"accuracy": 0.90})
        assert evaluator.thresholds["accuracy"] == 0.90
        assert evaluator.thresholds["f1_score"] == 0.80  # Default preserved

    def test_evaluate_version_with_expected_outputs(self) -> None:
        """Test version evaluation with expected outputs for real metrics."""
        evaluator = BrainEvaluator()
        # Test case: 2 TP, 1 FP, 1 TN, 0 FN
        # Accuracy = 3/4 = 0.75, Precision = 2/3 ≈ 0.6667, Recall = 2/2 = 1.0
        test_data = [
            {"output": True},  # TP (matches expected True)
            {"output": True},  # TP (matches expected True)
            {"output": True},  # FP (expected False)
            {"output": False},  # TN (matches expected False)
        ]
        expected_outputs = [
            {"expected": True},
            {"expected": True},
            {"expected": False},
            {"expected": False},
        ]

        result = evaluator.evaluate_version("1.0.0", test_data, expected_outputs)

        assert result.version == "1.0.0"
        assert result.status == EvaluationStatus.FAILED  # Below 0.80 thresholds
        assert result.metrics.accuracy == 0.75
        assert result.metrics.precision == pytest.approx(0.6667, rel=1e-3)
        assert result.metrics.recall == 1.0
        assert result.metrics.f1_score == pytest.approx(0.8, rel=1e-3)
        assert result.test_cases_run == 4
        assert (
            result.test_cases_passed == 3
        )  # Exact matches (3 True==True, 1 False==False)

    def test_evaluate_version_no_expected_outputs(self) -> None:
        """Test evaluation without expected outputs returns zero metrics."""
        evaluator = BrainEvaluator()
        test_data = [{"input": "test1"}, {"input": "test2"}]

        result = evaluator.evaluate_version("1.0.0", test_data)

        assert result.version == "1.0.0"
        assert result.metrics.accuracy == 0.0
        assert result.metrics.precision == 0.0
        assert result.metrics.recall == 0.0
        assert result.test_cases_run == 2

    def test_evaluate_version_empty_data(self) -> None:
        """Test evaluation with empty data."""
        evaluator = BrainEvaluator()
        result = evaluator.evaluate_version("1.0.0", [])

        assert result.test_cases_run == 0
        assert result.pass_rate == 0.0

    def test_evaluate_version_deterministic(self) -> None:
        """Test that same inputs produce same outputs (determinism)."""
        evaluator = BrainEvaluator()
        test_data = [
            {"output": True},
            {"output": False},
            {"output": True},
        ]
        expected_outputs = [
            {"expected": True},
            {"expected": False},
            {"expected": True},
        ]

        result1 = evaluator.evaluate_version("1.0.0", test_data, expected_outputs)
        result2 = evaluator.evaluate_version("1.0.0", test_data, expected_outputs)

        assert result1.metrics.accuracy == result2.metrics.accuracy
        assert result1.metrics.precision == result2.metrics.precision
        assert result1.metrics.recall == result2.metrics.recall
        assert result1.metrics.f1_score == result2.metrics.f1_score

    def test_compute_confusion_matrix(self) -> None:
        """Test confusion matrix computation."""
        evaluator = BrainEvaluator()
        test_data = [
            {"output": True},  # TP
            {"output": True},  # FP
            {"output": False},  # TN
            {"output": False},  # FN
        ]
        expected_outputs = [
            {"expected": True},
            {"expected": False},
            {"expected": False},
            {"expected": True},
        ]

        tp, fp, tn, fn = evaluator._compute_confusion_matrix(
            test_data, expected_outputs
        )

        assert tp == 1
        assert fp == 1
        assert tn == 1
        assert fn == 1

    def test_compute_metrics_from_confusion_matrix(self) -> None:
        """Test metric computation from confusion matrix."""
        evaluator = BrainEvaluator()

        # Perfect classifier: 10 TP, 0 FP, 10 TN, 0 FN
        metrics = evaluator._compute_metrics_from_confusion_matrix(10, 0, 10, 0)
        assert metrics.accuracy == 1.0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.false_positive_rate == 0.0

        # Worst classifier: 0 TP, 10 FP, 0 TN, 10 FN
        metrics = evaluator._compute_metrics_from_confusion_matrix(0, 10, 0, 10)
        assert metrics.accuracy == 0.0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1_score == 0.0
        assert metrics.false_positive_rate == 1.0

    def test_compute_metrics_edge_cases(self) -> None:
        """Test edge cases in metric computation."""
        evaluator = BrainEvaluator()

        # Division by zero cases
        metrics = evaluator._compute_metrics_from_confusion_matrix(0, 0, 10, 0)
        assert metrics.precision == 0.0  # No positive predictions
        assert metrics.recall == 0.0  # TP + FN = 0

        metrics = evaluator._compute_metrics_from_confusion_matrix(0, 0, 0, 10)
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0

        # Empty confusion matrix
        metrics = evaluator._compute_metrics_from_confusion_matrix(0, 0, 0, 0)
        assert metrics.accuracy == 0.0

    def test_evaluate_version_mismatched_lengths(self) -> None:
        """Test evaluation with mismatched test data and expected outputs."""
        evaluator = BrainEvaluator()
        test_data = [{"output": True}, {"output": False}]
        expected_outputs = [{"expected": True}]

        # Error is caught and stored in result, not raised
        result = evaluator.evaluate_version("1.0.0", test_data, expected_outputs)
        assert result.status == EvaluationStatus.ERROR
        assert result.error_message is not None
        assert "does not match" in result.error_message

    def test_no_random_module_usage(self) -> None:
        """Verify that evaluation.py does not import or use random module."""
        import ast
        import inspect

        from brain import evaluation

        source = inspect.getsourcefile(evaluation)
        assert source is not None

        with open(source) as f:
            tree = ast.parse(f.read())

        # Check for 'import random' or 'from random import ...'
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert (
                        alias.name != "random"
                    ), "random module import found in evaluation.py"
            elif isinstance(node, ast.ImportFrom):
                assert (
                    node.module != "random"
                ), "random module import found in evaluation.py"

    def test_is_evaluation_passed(self) -> None:
        """Test checking if evaluation passed."""
        # Create mock Redis client
        mock_redis = MagicMock()
        result_data = EvaluationResult(
            version="1.0.0",
            status=EvaluationStatus.PASSED,
            metrics=EvaluationMetrics(),
            started_at="2024-01-01T00:00:00Z",
        )
        mock_redis.get.return_value = json.dumps(result_data.to_dict())

        evaluator = BrainEvaluator(redis_client=mock_redis)
        assert evaluator.is_evaluation_passed("1.0.0") is True

        # Test failed evaluation
        result_data.status = EvaluationStatus.FAILED
        mock_redis.get.return_value = json.dumps(result_data.to_dict())
        assert evaluator.is_evaluation_passed("1.0.0") is False

    def test_is_evaluation_passed_no_data(self) -> None:
        """Test checking pass status when no data exists."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        evaluator = BrainEvaluator(redis_client=mock_redis)
        assert evaluator.is_evaluation_passed("1.0.0") is False

    def test_list_evaluations(self) -> None:
        """Test listing evaluations."""
        mock_redis = MagicMock()

        # Mock scan to return keys
        result1 = EvaluationResult(
            version="1.0.0",
            status=EvaluationStatus.PASSED,
            metrics=EvaluationMetrics(),
            started_at="2024-01-01T00:00:00Z",
        )
        result2 = EvaluationResult(
            version="1.1.0",
            status=EvaluationStatus.PASSED,
            metrics=EvaluationMetrics(),
            started_at="2024-01-02T00:00:00Z",
        )

        mock_redis.scan.side_effect = [
            (0, ["brain:evaluation:1.0.0", "brain:evaluation:1.1.0"]),
        ]
        mock_redis.get.side_effect = [
            json.dumps(result1.to_dict()),
            json.dumps(result2.to_dict()),
        ]

        evaluator = BrainEvaluator(redis_client=mock_redis)
        results = evaluator.list_evaluations()

        assert len(results) == 2
        # Should be sorted by started_at descending
        assert results[0].version == "1.1.0"
        assert results[1].version == "1.0.0"

    def test_list_evaluations_no_redis(self) -> None:
        """Test listing evaluations without Redis."""
        evaluator = BrainEvaluator()
        results = evaluator.list_evaluations()
        assert results == []
