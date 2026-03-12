"""Tests for training metrics collection.

This module tests the TrainingMetricsCollector class and related functionality
for tracking training runs, metrics, and statistics.

Acceptance Criteria:
- Training run tracking with start/complete/failure
- Duration tracking by mode (full vs incremental)
- Success/failure rate calculation
- Data quality score tracking
- Model performance metrics logging
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from ml.monitoring.training_metrics import (
    TrainingMetricsCollector,
    TrainingMode,
    TrainingRunMetrics,
    TrainingStatus,
    TrainingSummary,
)

logger = logging.getLogger(__name__)


class TestTrainingRunMetrics:
    """Tests for TrainingRunMetrics dataclass."""

    def test_training_run_metrics_creation(self):
        """Test creating training run metrics."""
        metrics = TrainingRunMetrics(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode=TrainingMode.FULL,
            status=TrainingStatus.SUCCESS,
            started_at=datetime.now(timezone.utc),
        )

        assert metrics.run_id == "train_001"
        assert metrics.model_name == "signal_predictor"
        assert metrics.training_mode == TrainingMode.FULL
        assert metrics.status == TrainingStatus.SUCCESS
        assert metrics.model_metrics == {}

    def test_training_run_metrics_to_dict(self):
        """Test converting training run metrics to dictionary."""
        started = datetime.now(timezone.utc)
        metrics = TrainingRunMetrics(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode=TrainingMode.INCREMENTAL,
            status=TrainingStatus.SUCCESS,
            started_at=started,
            duration_seconds=3600.0,
            data_quality_score=85.0,
            sample_count=10000,
            model_metrics={"accuracy": 0.65, "f1": 0.62},
        )

        result = metrics.to_dict()

        assert result["run_id"] == "train_001"
        assert result["model_name"] == "signal_predictor"
        assert result["training_mode"] == "incremental"
        assert result["status"] == "success"
        assert result["duration_seconds"] == 3600.0
        assert result["data_quality_score"] == 85.0
        assert result["sample_count"] == 10000
        assert result["model_metrics"] == {"accuracy": 0.65, "f1": 0.62}


class TestTrainingMetricsCollector:
    """Tests for TrainingMetricsCollector."""

    def test_initialization(self):
        """Test collector initialization."""
        collector = TrainingMetricsCollector()

        assert collector.get_active_runs() == []
        assert collector.get_run_history() == []

    def test_record_training_start(self):
        """Test recording training start."""
        collector = TrainingMetricsCollector()

        metrics = collector.record_training_start(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode="full",
            sample_count=10000,
            validation_split=0.2,
        )

        assert metrics.run_id == "train_001"
        assert metrics.model_name == "signal_predictor"
        assert metrics.training_mode == TrainingMode.FULL
        assert metrics.sample_count == 10000
        assert metrics.validation_split == 0.2

        # Should be in active runs
        active = collector.get_active_runs()
        assert len(active) == 1
        assert active[0].run_id == "train_001"

    def test_record_training_start_with_enum(self):
        """Test recording training start with enum mode."""
        collector = TrainingMetricsCollector()

        metrics = collector.record_training_start(
            run_id="train_002",
            model_name="signal_predictor",
            training_mode=TrainingMode.INCREMENTAL,
        )

        assert metrics.training_mode == TrainingMode.INCREMENTAL

    def test_record_training_complete_success(self):
        """Test recording successful training completion."""
        collector = TrainingMetricsCollector()

        collector.record_training_start(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode="full",
        )

        result = collector.record_training_complete(
            run_id="train_001",
            success=True,
            metrics={"accuracy": 0.65, "f1": 0.62},
            data_quality_score=85.0,
            sample_count=10000,
        )

        assert result is not None
        assert result.status == TrainingStatus.SUCCESS
        assert result.model_metrics == {"accuracy": 0.65, "f1": 0.62}
        assert result.data_quality_score == 85.0
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

        # Should not be in active runs
        assert len(collector.get_active_runs()) == 0

        # Should be in history
        history = collector.get_run_history()
        assert len(history) == 1
        assert history[0].run_id == "train_001"

    def test_record_training_complete_failure(self):
        """Test recording failed training completion."""
        collector = TrainingMetricsCollector()

        collector.record_training_start(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode="full",
        )

        result = collector.record_training_complete(
            run_id="train_001",
            success=False,
            error_message="Out of memory",
        )

        assert result is not None
        assert result.status == TrainingStatus.FAILURE
        assert result.error_message == "Out of memory"

    def test_record_training_complete_not_found(self):
        """Test recording completion for non-existent run."""
        collector = TrainingMetricsCollector()

        result = collector.record_training_complete(
            run_id="non_existent",
            success=True,
        )

        assert result is None

    def test_record_training_failure(self):
        """Test recording training failure with specific status."""
        collector = TrainingMetricsCollector()

        collector.record_training_start(
            run_id="train_001",
            model_name="signal_predictor",
            training_mode="full",
        )

        result = collector.record_training_failure(
            run_id="train_001",
            error_type="validation_failed",
            error_message="Validation gate failed",
            status=TrainingStatus.VALIDATION_FAILED,
        )

        assert result is not None
        assert result.status == TrainingStatus.VALIDATION_FAILED
        assert result.error_message == "Validation gate failed"

    def test_get_run_history_filtering(self):
        """Test run history filtering."""
        collector = TrainingMetricsCollector()

        # Create runs for different models
        collector.record_training_start("train_001", "model_a", "full")
        collector.record_training_complete("train_001", True)

        collector.record_training_start("train_002", "model_b", "incremental")
        collector.record_training_complete("train_002", True)

        collector.record_training_start("train_003", "model_a", "full")
        collector.record_training_failure("train_003", "timeout", "Timeout")

        # Filter by model name
        history_a = collector.get_run_history(model_name="model_a")
        assert len(history_a) == 2
        assert all(r.model_name == "model_a" for r in history_a)

        # Filter by status
        history_success = collector.get_run_history(status=TrainingStatus.SUCCESS)
        assert len(history_success) == 2

        history_failed = collector.get_run_history(status=TrainingStatus.FAILURE)
        assert len(history_failed) == 1

        # Filter by mode
        history_full = collector.get_run_history(training_mode=TrainingMode.FULL)
        assert len(history_full) == 2

    def test_get_summary(self):
        """Test training summary calculation."""
        collector = TrainingMetricsCollector()

        # Create successful runs
        for i in range(3):
            collector.record_training_start(f"train_{i}", "model_a", "full")
            collector.record_training_complete(
                f"train_{i}",
                True,
                data_quality_score=80.0 + i * 5,
                sample_count=10000,
            )

        # Create failed run
        collector.record_training_start("train_fail", "model_a", "full")
        collector.record_training_complete("train_fail", False, data_quality_score=70.0)

        summary = collector.get_summary(days=7)

        assert summary.total_runs == 4
        assert summary.successful_runs == 3
        assert summary.failed_runs == 1
        assert summary.success_rate == 75.0
        # Average of 80, 85, 90, 70 = 81.25
        assert summary.avg_data_quality_score == 81.25

        # Check breakdown by mode
        assert "full" in summary.by_mode
        assert summary.by_mode["full"]["total"] == 4

        # Check breakdown by model
        assert "model_a" in summary.by_model
        assert summary.by_model["model_a"]["total"] == 4

    def test_get_summary_empty(self):
        """Test summary with no runs."""
        collector = TrainingMetricsCollector()

        summary = collector.get_summary(days=7)

        assert summary.total_runs == 0
        assert summary.successful_runs == 0
        assert summary.success_rate == 0.0

    def test_get_duration_by_mode(self):
        """Test duration statistics by mode."""
        collector = TrainingMetricsCollector()

        # Create full training runs with different durations
        for i in range(5):
            collector.record_training_start(f"train_full_{i}", "model", "full")
            result = collector.record_training_complete(f"train_full_{i}", True)
            # Manually set duration for testing
            if result:
                result.duration_seconds = 3600.0 + i * 600  # 1h to 1h50m

        # Create incremental training runs
        for i in range(3):
            collector.record_training_start(f"train_inc_{i}", "model", "incremental")
            result = collector.record_training_complete(f"train_inc_{i}", True)
            if result:
                result.duration_seconds = 600.0 + i * 60  # 10m to 12m

        durations = collector.get_duration_by_mode(days=7)

        assert "full" in durations
        assert "incremental" in durations

        assert durations["full"]["count"] == 5
        assert durations["incremental"]["count"] == 3

    def test_clear_history(self):
        """Test clearing history."""
        collector = TrainingMetricsCollector()

        collector.record_training_start("train_001", "model", "full")
        collector.record_training_complete("train_001", True)

        assert len(collector.get_run_history()) == 1

        collector.clear_history()

        assert len(collector.get_run_history()) == 0
        assert len(collector.get_active_runs()) == 0

    def test_history_limit(self):
        """Test that history is limited."""
        collector = TrainingMetricsCollector()
        collector._max_history = 5

        # Create more runs than max_history
        for i in range(10):
            collector.record_training_start(f"train_{i}", "model", "full")
            collector.record_training_complete(f"train_{i}", True)

        history = collector.get_run_history()
        assert len(history) == 5


class TestTrainingSummary:
    """Tests for TrainingSummary dataclass."""

    def test_summary_to_dict(self):
        """Test converting summary to dictionary."""
        summary = TrainingSummary(
            period_days=7,
            total_runs=10,
            successful_runs=8,
            failed_runs=2,
            success_rate=80.0,
            avg_duration_seconds=3600.0,
            avg_data_quality_score=85.0,
            by_mode={
                "full": {"total": 6, "successful": 5, "failed": 1, "success_rate": 83.3}
            },
            by_model={
                "model_a": {
                    "total": 10,
                    "successful": 8,
                    "failed": 2,
                    "success_rate": 80.0,
                }
            },
        )

        result = summary.to_dict()

        assert result["period_days"] == 7
        assert result["total_runs"] == 10
        assert result["success_rate"] == 80.0
        assert result["by_mode"]["full"]["success_rate"] == 83.3


class TestTrainingEnums:
    """Tests for training enums."""

    def test_training_mode_values(self):
        """Test training mode enum values."""
        assert TrainingMode.FULL.value == "full"
        assert TrainingMode.INCREMENTAL.value == "incremental"

    def test_training_status_values(self):
        """Test training status enum values."""
        assert TrainingStatus.SUCCESS.value == "success"
        assert TrainingStatus.FAILURE.value == "failure"
        assert TrainingStatus.VALIDATION_FAILED.value == "validation_failed"
        assert TrainingStatus.NO_DATA.value == "no_data"
        assert TrainingStatus.TIMEOUT.value == "timeout"
        assert TrainingStatus.CANCELLED.value == "cancelled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
