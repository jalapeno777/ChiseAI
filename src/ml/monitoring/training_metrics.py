"""Training metrics collection and monitoring for ChiseAI.

Provides comprehensive metrics collection for training runs, including
duration tracking, success/failure rates, data quality scores, and model
performance metrics. Integrates with InfluxDB for time-series storage.

Example:
    >>> from ml.monitoring.training_metrics import TrainingMetricsCollector
    >>> collector = TrainingMetricsCollector()
    >>>
    >>> # Record a training run
    >>> collector.record_training_start(
    ...     run_id="train_001",
    ...     model_name="signal_predictor",
    ...     training_mode="incremental"
    ... )
    >>>
    >>> # After training completes
    >>> collector.record_training_complete(
    ...     run_id="train_001",
    ...     success=True,
    ...     metrics={"accuracy": 0.65, "f1": 0.62}
    ... )
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# InfluxDB availability flag - graceful degradation if not installed
INFLUXDB_AVAILABLE = False
try:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write.point import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    INFLUXDB_AVAILABLE = True
except ImportError:
    pass


class TrainingMode(Enum):
    """Training mode types."""

    FULL = "full"
    INCREMENTAL = "incremental"


class TrainingStatus(Enum):
    """Training run status."""

    SUCCESS = "success"
    FAILURE = "failure"
    VALIDATION_FAILED = "validation_failed"
    NO_DATA = "no_data"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TrainingRunMetrics:
    """Metrics for a single training run.

    Attributes:
        run_id: Unique identifier for the training run
        model_name: Name of the model being trained
        training_mode: Type of training (full/incremental)
        status: Final status of the training run
        started_at: When training started
        completed_at: When training completed
        duration_seconds: Total training duration
        data_quality_score: Data quality score (0-100)
        sample_count: Number of training samples
        validation_split: Fraction used for validation
        model_metrics: Model performance metrics
        error_message: Error message if failed
        data_freshness_hours: Age of training data in hours
        missing_features_pct: Percentage of missing features
    """

    run_id: str
    model_name: str
    training_mode: TrainingMode
    status: TrainingStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    data_quality_score: float | None = None
    sample_count: int | None = None
    validation_split: float | None = None
    model_metrics: dict[str, float] = field(default_factory=dict)
    error_message: str | None = None
    data_freshness_hours: float | None = None
    missing_features_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "training_mode": self.training_mode.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_seconds": self.duration_seconds,
            "data_quality_score": self.data_quality_score,
            "sample_count": self.sample_count,
            "validation_split": self.validation_split,
            "model_metrics": self.model_metrics,
            "error_message": self.error_message,
            "data_freshness_hours": self.data_freshness_hours,
            "missing_features_pct": self.missing_features_pct,
        }


@dataclass
class TrainingSummary:
    """Summary of training runs over a period.

    Attributes:
        period_days: Number of days in the summary period
        total_runs: Total number of training runs
        successful_runs: Number of successful runs
        failed_runs: Number of failed runs
        success_rate: Percentage of successful runs
        avg_duration_seconds: Average training duration
        avg_data_quality_score: Average data quality score
        by_mode: Breakdown by training mode
        by_model: Breakdown by model name
    """

    period_days: int
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    avg_data_quality_score: float = 0.0
    by_mode: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "period_days": self.period_days,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate": self.success_rate,
            "avg_duration_seconds": self.avg_duration_seconds,
            "avg_data_quality_score": self.avg_data_quality_score,
            "by_mode": self.by_mode,
            "by_model": self.by_model,
        }


class InfluxDBLogger(Protocol):
    """Protocol for logging training metrics to InfluxDB."""

    def log_training_run(self, metrics: TrainingRunMetrics) -> bool:
        """Log a training run."""
        ...

    def log_training_failure(
        self, run_id: str, model_name: str, error_type: str, error_message: str
    ) -> bool:
        """Log a training failure."""
        ...


class DefaultInfluxDBLogger:
    """Default InfluxDB logger for training metrics."""

    def __init__(
        self,
        url: str = "http://chiseai-influxdb:18087",
        token: str = "chiseai-token",
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        """Initialize InfluxDB logger.

        Args:
            url: InfluxDB URL
            token: Authentication token
            org: Organization name
            bucket: Bucket name
        """
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._client = None
        self._write_api = None
        self._available = INFLUXDB_AVAILABLE

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if not self._available:
            return None

        if self._client is None:
            try:
                self._client = InfluxDBClient(
                    url=self._url, token=self._token, org=self._org
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.warning(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def log_training_run(self, metrics: TrainingRunMetrics) -> bool:
        """Log a training run to InfluxDB.

        Args:
            metrics: Training run metrics

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                logger.debug("InfluxDB not available, skipping training run log")
                return False

        try:
            # Main training run point
            point = (
                Point("training_run")
                .tag("run_id", metrics.run_id)
                .tag("model_name", metrics.model_name)
                .tag("training_mode", metrics.training_mode.value)
                .tag("status", metrics.status.value)
                .field("duration_seconds", metrics.duration_seconds or 0.0)
                .field("data_quality_score", metrics.data_quality_score or 0.0)
                .field("sample_count", metrics.sample_count or 0)
                .field("success", 1 if metrics.status == TrainingStatus.SUCCESS else 0)
                .time(metrics.started_at)
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)

            # Log model performance metrics as separate points
            for metric_name, metric_value in metrics.model_metrics.items():
                metric_point = (
                    Point("training_model_metrics")
                    .tag("run_id", metrics.run_id)
                    .tag("model_name", metrics.model_name)
                    .tag("metric_name", metric_name)
                    .field("value", float(metric_value))
                    .time(metrics.started_at)
                )
                self._write_api.write(
                    bucket=self._bucket, org=self._org, record=metric_point
                )

            logger.debug(f"Logged training run: {metrics.run_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log training run to InfluxDB: {e}")
            return False

    def log_training_failure(
        self, run_id: str, model_name: str, error_type: str, error_message: str
    ) -> bool:
        """Log a training failure to InfluxDB.

        Args:
            run_id: Training run ID
            model_name: Model name
            error_type: Type of error
            error_message: Error message

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            point = (
                Point("training_failure")
                .tag("run_id", run_id)
                .tag("model_name", model_name)
                .tag("error_type", error_type)
                .field("error_message", error_message)
                .time(datetime.now(UTC))
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.info(f"Logged training failure: {run_id} - {error_type}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log training failure to InfluxDB: {e}")
            return False


class TrainingMetricsCollector:
    """Collector for training metrics.

    Tracks training runs, collects performance metrics, and logs to InfluxDB.
    Provides summary statistics for monitoring training health.

    Example:
        >>> collector = TrainingMetricsCollector()
        >>>
        >>> # Start tracking a training run
        >>> collector.record_training_start(
        ...     run_id="train_001",
        ...     model_name="signal_predictor",
        ...     training_mode="incremental"
        ... )
        >>>
        >>> # Complete the run
        >>> collector.record_training_complete(
        ...     run_id="train_001",
        ...     success=True,
        ...     metrics={"accuracy": 0.65, "f1": 0.62},
        ...     data_quality_score=85.0,
        ...     sample_count=10000
        ... )
        >>>
        >>> # Get summary
        >>> summary = collector.get_summary(days=7)
        >>> print(f"Success rate: {summary.success_rate:.1f}%")
    """

    def __init__(
        self,
        influx_logger: InfluxDBLogger | None = None,
    ):
        """Initialize training metrics collector.

        Args:
            influx_logger: Optional InfluxDB logger
        """
        self._influx_logger = influx_logger or DefaultInfluxDBLogger()
        self._active_runs: dict[str, TrainingRunMetrics] = {}
        self._completed_runs: list[TrainingRunMetrics] = []
        self._max_history = 1000

        logger.info("TrainingMetricsCollector initialized")

    def record_training_start(
        self,
        run_id: str,
        model_name: str,
        training_mode: str | TrainingMode = TrainingMode.FULL,
        sample_count: int | None = None,
        validation_split: float | None = None,
        data_freshness_hours: float | None = None,
        missing_features_pct: float | None = None,
    ) -> TrainingRunMetrics:
        """Record the start of a training run.

        Args:
            run_id: Unique identifier for this run
            model_name: Name of the model being trained
            training_mode: Type of training (full/incremental)
            sample_count: Number of training samples
            validation_split: Fraction used for validation
            data_freshness_hours: Age of training data in hours
            missing_features_pct: Percentage of missing features

        Returns:
            TrainingRunMetrics for the started run
        """
        if isinstance(training_mode, str):
            training_mode = TrainingMode(training_mode)

        metrics = TrainingRunMetrics(
            run_id=run_id,
            model_name=model_name,
            training_mode=training_mode,
            status=TrainingStatus.SUCCESS,  # Will be updated on completion
            started_at=datetime.now(UTC),
            sample_count=sample_count,
            validation_split=validation_split,
            data_freshness_hours=data_freshness_hours,
            missing_features_pct=missing_features_pct,
        )

        self._active_runs[run_id] = metrics

        logger.info(
            f"Training started: {run_id} for {model_name} ({training_mode.value} mode)"
        )

        return metrics

    def record_training_complete(
        self,
        run_id: str,
        success: bool,
        metrics: dict[str, float] | None = None,
        data_quality_score: float | None = None,
        sample_count: int | None = None,
        error_message: str | None = None,
    ) -> TrainingRunMetrics | None:
        """Record the completion of a training run.

        Args:
            run_id: Training run ID
            success: Whether training was successful
            metrics: Model performance metrics
            data_quality_score: Data quality score (0-100)
            sample_count: Final sample count
            error_message: Error message if failed

        Returns:
            Updated TrainingRunMetrics or None if run_id not found
        """
        run_metrics = self._active_runs.get(run_id)
        if not run_metrics:
            logger.warning(f"Training run not found: {run_id}")
            return None

        # Update metrics
        run_metrics.completed_at = datetime.now(UTC)
        run_metrics.duration_seconds = (
            run_metrics.completed_at - run_metrics.started_at
        ).total_seconds()
        run_metrics.status = (
            TrainingStatus.SUCCESS if success else TrainingStatus.FAILURE
        )
        run_metrics.model_metrics = metrics or {}
        run_metrics.data_quality_score = data_quality_score
        run_metrics.error_message = error_message

        if sample_count is not None:
            run_metrics.sample_count = sample_count

        # Move to completed runs
        del self._active_runs[run_id]
        self._completed_runs.append(run_metrics)

        # Trim history if needed
        if len(self._completed_runs) > self._max_history:
            self._completed_runs = self._completed_runs[-self._max_history :]

        # Log to InfluxDB
        self._influx_logger.log_training_run(run_metrics)

        if success:
            dq_str = (
                f"{data_quality_score:.1f}" if data_quality_score is not None else "N/A"
            )
            logger.info(
                f"Training completed successfully: {run_id} "
                f"(duration={run_metrics.duration_seconds:.1f}s, "
                f"data_quality={dq_str})"
            )
        else:
            logger.error(
                f"Training failed: {run_id} - {error_message} "
                f"(duration={run_metrics.duration_seconds:.1f}s)"
            )

        return run_metrics

    def record_training_failure(
        self,
        run_id: str,
        error_type: str,
        error_message: str,
        status: TrainingStatus = TrainingStatus.FAILURE,
    ) -> TrainingRunMetrics | None:
        """Record a training failure with specific status.

        Args:
            run_id: Training run ID
            error_type: Type of error (e.g., "validation_failed", "timeout")
            error_message: Error message
            status: Specific failure status

        Returns:
            Updated TrainingRunMetrics or None if run_id not found
        """
        run_metrics = self._active_runs.get(run_id)
        if not run_metrics:
            logger.warning(f"Training run not found: {run_id}")
            return None

        run_metrics.completed_at = datetime.now(UTC)
        run_metrics.duration_seconds = (
            run_metrics.completed_at - run_metrics.started_at
        ).total_seconds()
        run_metrics.status = status
        run_metrics.error_message = error_message

        # Move to completed runs
        del self._active_runs[run_id]
        self._completed_runs.append(run_metrics)

        # Log to InfluxDB
        self._influx_logger.log_training_run(run_metrics)
        self._influx_logger.log_training_failure(
            run_id, run_metrics.model_name, error_type, error_message
        )

        logger.error(
            f"Training {status.value}: {run_id} - {error_type}: {error_message}"
        )

        return run_metrics

    def get_active_runs(self) -> list[TrainingRunMetrics]:
        """Get all currently active training runs.

        Returns:
            List of active training runs
        """
        return list(self._active_runs.values())

    def get_run_history(
        self,
        model_name: str | None = None,
        training_mode: TrainingMode | None = None,
        status: TrainingStatus | None = None,
        limit: int = 100,
    ) -> list[TrainingRunMetrics]:
        """Get training run history with optional filtering.

        Args:
            model_name: Filter by model name
            training_mode: Filter by training mode
            status: Filter by status
            limit: Maximum number of runs to return

        Returns:
            List of training runs matching filters
        """
        runs = self._completed_runs

        if model_name:
            runs = [r for r in runs if r.model_name == model_name]

        if training_mode:
            runs = [r for r in runs if r.training_mode == training_mode]

        if status:
            runs = [r for r in runs if r.status == status]

        return runs[-limit:]

    def get_summary(self, days: int = 7) -> TrainingSummary:
        """Get training summary for a period.

        Args:
            days: Number of days to summarize

        Returns:
            TrainingSummary with statistics
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        recent_runs = [r for r in self._completed_runs if r.started_at >= cutoff]

        summary = TrainingSummary(period_days=days)

        if not recent_runs:
            return summary

        summary.total_runs = len(recent_runs)
        summary.successful_runs = sum(
            1 for r in recent_runs if r.status == TrainingStatus.SUCCESS
        )
        summary.failed_runs = summary.total_runs - summary.successful_runs
        summary.success_rate = (
            summary.successful_runs / summary.total_runs * 100
            if summary.total_runs > 0
            else 0.0
        )

        # Average duration
        durations = [r.duration_seconds for r in recent_runs if r.duration_seconds]
        summary.avg_duration_seconds = (
            sum(durations) / len(durations) if durations else 0.0
        )

        # Average data quality
        quality_scores = [
            r.data_quality_score
            for r in recent_runs
            if r.data_quality_score is not None
        ]
        summary.avg_data_quality_score = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )

        # Breakdown by mode
        by_mode: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "successful": 0, "failed": 0}
        )
        for run in recent_runs:
            mode = run.training_mode.value
            by_mode[mode]["total"] += 1
            if run.status == TrainingStatus.SUCCESS:
                by_mode[mode]["successful"] += 1
            else:
                by_mode[mode]["failed"] += 1

        for mode, stats in by_mode.items():
            stats["success_rate"] = (
                stats["successful"] / stats["total"] * 100
                if stats["total"] > 0
                else 0.0
            )

        summary.by_mode = dict(by_mode)

        # Breakdown by model
        by_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "successful": 0, "failed": 0}
        )
        for run in recent_runs:
            by_model[run.model_name]["total"] += 1
            if run.status == TrainingStatus.SUCCESS:
                by_model[run.model_name]["successful"] += 1
            else:
                by_model[run.model_name]["failed"] += 1

        for model, stats in by_model.items():
            stats["success_rate"] = (
                stats["successful"] / stats["total"] * 100
                if stats["total"] > 0
                else 0.0
            )

        summary.by_model = dict(by_model)

        return summary

    def get_duration_by_mode(self, days: int = 7) -> dict[str, dict[str, float]]:
        """Get training duration statistics by mode.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with duration stats per mode
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        recent_runs = [r for r in self._completed_runs if r.started_at >= cutoff]

        durations_by_mode: dict[str, list[float]] = defaultdict(list)

        for run in recent_runs:
            if run.duration_seconds:
                durations_by_mode[run.training_mode.value].append(run.duration_seconds)

        result = {}
        for mode, durations in durations_by_mode.items():
            if durations:
                sorted_durations = sorted(durations)
                result[mode] = {
                    "avg": sum(durations) / len(durations),
                    "min": min(durations),
                    "max": max(durations),
                    "p50": sorted_durations[len(sorted_durations) // 2],
                    "p95": sorted_durations[int(len(sorted_durations) * 0.95)],
                    "count": len(durations),
                }

        return result

    def clear_history(self) -> None:
        """Clear all training run history."""
        self._completed_runs.clear()
        self._active_runs.clear()
        logger.info("Training metrics history cleared")
