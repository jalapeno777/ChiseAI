"""
Tests for Retrieval Metrics Exporter.

ST-GOV-007: Retrieval Quality Evaluator

Tests cover:
- RetrievalMetricsExporter class
- Metric collection
- Metric recording
- Summary generation
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock

from src.governance.retrieval.metrics import (
    RetrievalMetricsExporter,
    RETRIEVAL_PREFIX,
)


class TestRetrievalMetricsExporter:
    """Tests for RetrievalMetricsExporter class."""

    def test_init(self):
        """Test exporter initialization."""
        exporter = RetrievalMetricsExporter()
        assert exporter._redis_client is None
        assert exporter._influx_client is None

    def test_init_with_redis(self):
        """Test initialization with Redis client."""
        mock_redis = MagicMock()
        exporter = RetrievalMetricsExporter(redis_client=mock_redis)
        assert exporter._redis_client is not None

    def test_collect(self):
        """Test collecting metrics."""
        exporter = RetrievalMetricsExporter()

        # Set some values
        exporter._queries_evaluated = 100
        exporter._last_precision_at_5 = 0.85
        exporter._last_recall_at_10 = 0.80
        exporter._last_mrr = 0.75

        points = exporter.collect()

        assert len(points) > 0

        # Check that we have expected metrics
        metric_names = [p.name for p in points]
        assert "governance.retrieval.queries.evaluated" in metric_names
        assert "governance.retrieval.precision.at_5" in metric_names
        assert "governance.retrieval.recall.at_10" in metric_names
        assert "governance.retrieval.mrr" in metric_names

    def test_collect_includes_validation_gates(self):
        """Test that collection includes validation gate status."""
        exporter = RetrievalMetricsExporter()
        exporter._last_precision_at_5 = 0.90
        exporter._last_recall_at_10 = 0.85
        exporter._last_mrr = 0.80

        points = exporter.collect()

        gate_points = [p for p in points if "validation_gates" in p.name]
        assert len(gate_points) == 1
        assert gate_points[0].value == 1.0  # Gates passed

    def test_collect_includes_f1_score(self):
        """Test that collection includes F1 score."""
        exporter = RetrievalMetricsExporter()
        exporter._last_precision_at_5 = 0.90
        exporter._last_recall_at_10 = 0.80

        points = exporter.collect()

        f1_points = [p for p in points if "f1_score" in p.name]
        assert len(f1_points) == 1
        # F1 = 2 * (0.9 * 0.8) / (0.9 + 0.8) ≈ 0.847
        assert f1_points[0].value == pytest.approx(0.847, rel=0.01)

    def test_record_query_evaluated(self):
        """Test recording query evaluation."""
        exporter = RetrievalMetricsExporter()

        exporter.record_query_evaluated()
        exporter.record_query_evaluated()

        assert exporter._queries_evaluated == 2

    def test_record_query_evaluated_with_redis(self):
        """Test recording query evaluation with Redis."""
        mock_redis = MagicMock()
        exporter = RetrievalMetricsExporter(redis_client=mock_redis)

        exporter.record_query_evaluated()

        mock_redis.incr.assert_called()

    def test_record_metrics(self):
        """Test recording retrieval metrics."""
        exporter = RetrievalMetricsExporter()

        exporter.record_metrics(
            precision_at_5=0.85,
            precision_at_10=0.80,
            recall_at_5=0.75,
            recall_at_10=0.70,
            mrr=0.65,
        )

        assert exporter._last_precision_at_5 == 0.85
        assert exporter._last_precision_at_10 == 0.80
        assert exporter._last_recall_at_5 == 0.75
        assert exporter._last_recall_at_10 == 0.70
        assert exporter._last_mrr == 0.65

    def test_record_metrics_with_redis(self):
        """Test recording metrics with Redis."""
        mock_redis = MagicMock()
        exporter = RetrievalMetricsExporter(redis_client=mock_redis)

        exporter.record_metrics(
            precision_at_5=0.85,
            precision_at_10=0.80,
            recall_at_5=0.75,
            recall_at_10=0.70,
            mrr=0.65,
        )

        # Should have called set for each metric
        assert mock_redis.set.call_count == 5

    def test_record_human_validation(self):
        """Test recording human validation."""
        exporter = RetrievalMetricsExporter()

        exporter.record_human_validation()
        exporter.record_human_validation()

        assert exporter._human_validations == 2

    def test_record_ab_experiment_started(self):
        """Test recording A/B experiment start."""
        exporter = RetrievalMetricsExporter()

        exporter.record_ab_experiment_started()
        exporter.record_ab_experiment_started()

        assert exporter._ab_experiments_running == 2

    def test_record_ab_experiment_completed(self):
        """Test recording A/B experiment completion."""
        exporter = RetrievalMetricsExporter()

        exporter.record_ab_experiment_started()
        exporter.record_ab_experiment_started()
        exporter.record_ab_experiment_completed()

        assert exporter._ab_experiments_running == 1

    def test_record_ab_experiment_completed_no_underflow(self):
        """Test that experiment count doesn't go below zero."""
        exporter = RetrievalMetricsExporter()

        exporter.record_ab_experiment_completed()  # No experiments running
        assert exporter._ab_experiments_running == 0

    def test_record_threshold_adjustment(self):
        """Test recording threshold adjustment."""
        exporter = RetrievalMetricsExporter()

        exporter.record_threshold_adjustment()
        exporter.record_threshold_adjustment()

        assert exporter._threshold_adjustments == 2

    def test_get_summary(self):
        """Test getting metrics summary."""
        exporter = RetrievalMetricsExporter()
        exporter._queries_evaluated = 100
        exporter._last_precision_at_5 = 0.90
        exporter._last_recall_at_10 = 0.85
        exporter._last_mrr = 0.80
        exporter._human_validations = 10

        summary = exporter.get_summary()

        assert summary["queries_evaluated"] == 100
        assert summary["precision_at_5"] == 0.90
        assert summary["recall_at_10"] == 0.85
        assert summary["mrr"] == 0.80
        assert summary["human_validations"] == 10
        assert summary["validation_gates_passed"] is True

    def test_validation_gates_fail(self):
        """Test validation gates failing."""
        exporter = RetrievalMetricsExporter()
        exporter._last_precision_at_5 = 0.80  # Below 85%
        exporter._last_recall_at_10 = 0.85
        exporter._last_mrr = 0.80

        summary = exporter.get_summary()

        assert summary["validation_gates_passed"] is False

    def test_get_from_redis(self):
        """Test getting metrics from Redis."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"150"
        exporter = RetrievalMetricsExporter(redis_client=mock_redis)

        count = exporter._get_queries_evaluated()

        assert count == 150
        mock_redis.get.assert_called()

    def test_get_from_redis_error(self):
        """Test handling Redis errors gracefully."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")
        exporter = RetrievalMetricsExporter(redis_client=mock_redis)
        exporter._queries_evaluated = 50

        count = exporter._get_queries_evaluated()

        # Should fall back to in-memory value
        assert count == 50


class TestMetricPointStructure:
    """Tests for metric point structure."""

    def test_metric_types(self):
        """Test that metrics have correct types."""
        from src.governance.metrics.base_exporter import MetricType

        exporter = RetrievalMetricsExporter()
        points = exporter.collect()

        # Queries evaluated should be a counter
        queries_point = next(
            (p for p in points if p.name == "governance.retrieval.queries.evaluated"),
            None,
        )
        assert queries_point is not None
        assert queries_point.metric_type == MetricType.COUNTER

        # Precision should be a gauge
        precision_point = next((p for p in points if "precision.at_5" in p.name), None)
        assert precision_point is not None
        assert precision_point.metric_type == MetricType.GAUGE

    def test_metric_tags(self):
        """Test that metrics have correct tags."""
        exporter = RetrievalMetricsExporter()
        points = exporter.collect()

        for point in points:
            assert "feature" in point.tags
            assert point.tags["feature"] == "retrieval"

    def test_metric_timestamps(self):
        """Test that metrics have timestamps."""
        exporter = RetrievalMetricsExporter()
        points = exporter.collect()

        for point in points:
            assert point.timestamp is not None
            assert isinstance(point.timestamp, datetime)


class TestValidationGates:
    """Tests for validation gate checking."""

    def test_all_gates_pass(self):
        """Test when all validation gates pass."""
        exporter = RetrievalMetricsExporter()

        result = exporter._check_validation_gates(
            precision_at_5=0.90,
            recall_at_10=0.85,
            mrr=0.80,
        )

        assert result is True

    def test_precision_gate_fail(self):
        """Test when precision gate fails."""
        exporter = RetrievalMetricsExporter()

        result = exporter._check_validation_gates(
            precision_at_5=0.80,  # Below 85%
            recall_at_10=0.85,
            mrr=0.80,
        )

        assert result is False

    def test_recall_gate_fail(self):
        """Test when recall gate fails."""
        exporter = RetrievalMetricsExporter()

        result = exporter._check_validation_gates(
            precision_at_5=0.90,
            recall_at_10=0.75,  # Below 80%
            mrr=0.80,
        )

        assert result is False

    def test_mrr_gate_fail(self):
        """Test when MRR gate fails."""
        exporter = RetrievalMetricsExporter()

        result = exporter._check_validation_gates(
            precision_at_5=0.90,
            recall_at_10=0.85,
            mrr=0.70,  # Below 0.75
        )

        assert result is False

    def test_boundary_values(self):
        """Test boundary values for validation gates."""
        exporter = RetrievalMetricsExporter()

        # Exactly at boundaries should pass
        result = exporter._check_validation_gates(
            precision_at_5=0.85,  # Exactly 85%
            recall_at_10=0.80,  # Exactly 80%
            mrr=0.75,  # Exactly 0.75
        )
        assert result is True

        # Just below boundaries should fail
        result = exporter._check_validation_gates(
            precision_at_5=0.849,
            recall_at_10=0.799,
            mrr=0.749,
        )
        assert result is False
