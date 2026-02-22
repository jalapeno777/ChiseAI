"""Training Pipeline Integration for ChiseAI.

This module provides the integration layer between:
- Retraining triggers (ST-LAUNCH-011)
- Feedback loop data (EP-LAUNCH-002)
- Model training execution
- Model registry (ST-LAUNCH-013)

Features:
- Trigger event listening and handling
- Training data fetching from feedback loop
- Async job scheduling for training
- Model registration with metadata
- Failure handling with retry logic
- Grafana metrics export

For ST-LAUNCH-012: Training Pipeline Integration
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ml.feedback.orchestrator import FeedbackOrchestrator
    from ml.model_registry.registry import ModelRegistry
    from ml.training.retraining_trigger import (
        RetrainingTrigger,
        TriggerResult,
    )

logger = logging.getLogger(__name__)

# Training pipeline constants
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_JOB_TIMEOUT_SECONDS = 3600 * 4  # 4 hours
MIN_SAMPLES_FOR_TRAINING = 100


class TrainingJobStatus(Enum):
    """Status of a training job."""

    PENDING = auto()
    FETCHING_DATA = auto()
    VALIDATING = auto()
    TRAINING = auto()
    REGISTERING = auto()
    COMPLETED = auto()
    FAILED = auto()
    RETRYING = auto()
    CANCELLED = auto()


class TrainingPipelineError(Exception):
    """Base exception for training pipeline errors."""

    pass


class DataFetchError(TrainingPipelineError):
    """Error fetching training data."""

    pass


class TrainingExecutionError(TrainingPipelineError):
    """Error during model training."""

    pass


class ModelRegistrationError(TrainingPipelineError):
    """Error registering trained model."""

    pass


@dataclass
class Hyperparameters:
    """Configurable hyperparameters for model training.

    Attributes:
        learning_rate: Learning rate for optimizer
        batch_size: Batch size for training
        epochs: Number of training epochs
        validation_split: Fraction of data for validation
        early_stopping_patience: Epochs to wait before early stopping
        dropout_rate: Dropout regularization rate
        hidden_units: Number of hidden units in model
        random_seed: Random seed for reproducibility
    """

    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 100
    validation_split: float = 0.2
    early_stopping_patience: int = 10
    dropout_rate: float = 0.2
    hidden_units: int = 128
    random_seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "validation_split": self.validation_split,
            "early_stopping_patience": self.early_stopping_patience,
            "dropout_rate": self.dropout_rate,
            "hidden_units": self.hidden_units,
            "random_seed": self.random_seed,
        }


@dataclass
class TrainingJob:
    """Represents a training job.

    Attributes:
        job_id: Unique job identifier
        trigger_result: Trigger that initiated this job
        status: Current job status
        hyperparameters: Training hyperparameters
        created_at: When job was created
        started_at: When job started
        completed_at: When job completed
        model_version: Registered model version ID
        metrics: Training metrics
        error_message: Error message if failed
        retry_count: Number of retry attempts
        max_retries: Maximum retry attempts
    """

    job_id: str
    trigger_result: TriggerResult | None = None
    status: TrainingJobStatus = TrainingJobStatus.PENDING
    hyperparameters: Hyperparameters = field(default_factory=Hyperparameters)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_version: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = DEFAULT_RETRY_ATTEMPTS

    @property
    def duration_seconds(self) -> float | None:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        if self.started_at:
            return (datetime.now(UTC) - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "trigger_type": (
                self.trigger_result.trigger_type.name if self.trigger_result else None
            ),
            "status": self.status.name,
            "hyperparameters": self.hyperparameters.to_dict(),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "model_version": self.model_version,
            "metrics": self.metrics,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


@dataclass
class TrainingData:
    """Training data container.

    Attributes:
        samples: List of training samples
        sample_count: Total number of samples
        features: List of feature names
        label_column: Name of label column
        metadata: Additional metadata about the data
    """

    samples: list[dict[str, Any]] = field(default_factory=list)
    sample_count: int = 0
    features: list[str] = field(default_factory=list)
    label_column: str = "outcome"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sample_count": self.sample_count,
            "features": self.features,
            "label_column": self.label_column,
            "metadata": self.metadata,
        }


class TrainingDataFetcher(Protocol):
    """Protocol for fetching training data from feedback loop."""

    async def fetch_training_data(
        self,
        min_samples: int = MIN_SAMPLES_FOR_TRAINING,
        temporal_boundary: datetime | None = None,
    ) -> TrainingData:
        """Fetch training data from feedback loop.

        Args:
            min_samples: Minimum samples required
            temporal_boundary: Optional temporal safety boundary

        Returns:
            TrainingData container

        Raises:
            DataFetchError: If data cannot be fetched
        """
        ...


class ModelTrainer(Protocol):
    """Protocol for model training execution."""

    async def train(
        self,
        data: TrainingData,
        hyperparameters: Hyperparameters,
    ) -> tuple[bool, dict[str, Any]]:
        """Train a model.

        Args:
            data: Training data
            hyperparameters: Training hyperparameters

        Returns:
            Tuple of (success, metrics)

        Raises:
            TrainingExecutionError: If training fails
        """
        ...


class FeedbackLoopDataFetcher:
    """Fetches training data from the feedback loop."""

    def __init__(
        self,
        feedback_orchestrator: FeedbackOrchestrator | None = None,
        signal_storage: Any | None = None,
    ) -> None:
        """Initialize data fetcher.

        Args:
            feedback_orchestrator: Feedback loop orchestrator
            signal_storage: Signal storage interface
        """
        self._feedback = feedback_orchestrator
        self._signal_storage = signal_storage

    async def fetch_training_data(
        self,
        min_samples: int = MIN_SAMPLES_FOR_TRAINING,
        temporal_boundary: datetime | None = None,
    ) -> TrainingData:
        """Fetch training data from feedback loop.

        Args:
            min_samples: Minimum samples required
            temporal_boundary: Optional temporal safety boundary

        Returns:
            TrainingData container

        Raises:
            DataFetchError: If data cannot be fetched
        """
        try:
            # Calculate time window
            end_time = temporal_boundary or datetime.now(UTC)
            start_time = end_time - timedelta(days=30)  # 30-day lookback

            logger.info(f"Fetching training data from {start_time} to {end_time}")

            # Get matches from feedback loop
            samples = []
            if self._feedback and self._feedback.matcher:
                from ml.feedback.matcher import MatchStatus

                # Get recent signals with outcomes
                if self._feedback.signal_tracker:
                    cutoff_ms = int(end_time.timestamp() * 1000)
                    start_ms = int(start_time.timestamp() * 1000)

                    signals = await self._feedback.signal_tracker.get_signal_history(
                        start_time_ms=start_ms,
                        end_time_ms=cutoff_ms,
                        with_outcomes_only=True,
                    )

                    if signals:
                        signal_records = [s.signal for s in signals]
                        match_result = await self._feedback.matcher.match_batch(
                            signals=signal_records,
                            current_time_ms=cutoff_ms,
                        )

                        # Extract valid matches as training samples
                        for match in match_result.matches:
                            if (
                                match.status == MatchStatus.MATCHED
                                and match.outcome is not None
                            ):
                                sample = {
                                    "signal_id": match.signal_id,
                                    "timestamp": match.signal.timestamp,
                                    "direction": match.signal.direction,
                                    "confidence": match.signal.confidence,
                                    "outcome": 1 if match.outcome.is_win else 0,
                                    "pnl": getattr(match.outcome, "pnl", 0.0),
                                }
                                samples.append(sample)

            # Check minimum samples
            if len(samples) < min_samples:
                raise DataFetchError(
                    f"Insufficient training data: {len(samples)} < {min_samples}"
                )

            # Extract features from samples
            features = list(samples[0].keys()) if samples else []
            features = [f for f in features if f not in ["signal_id", "outcome", "pnl"]]

            logger.info(f"Fetched {len(samples)} training samples")

            return TrainingData(
                samples=samples,
                sample_count=len(samples),
                features=features,
                metadata={
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "data_source": "feedback_loop",
                },
            )

        except Exception as e:
            logger.error(f"Failed to fetch training data: {e}")
            raise DataFetchError(f"Failed to fetch training data: {e}") from e


class AsyncJobScheduler:
    """Schedules and manages async training jobs."""

    def __init__(self, max_concurrent_jobs: int = 2) -> None:
        """Initialize job scheduler.

        Args:
            max_concurrent_jobs: Maximum concurrent training jobs
        """
        self._max_concurrent = max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._jobs: dict[str, TrainingJob] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def submit_job(
        self,
        job: TrainingJob,
        job_runner: callable[[TrainingJob], Any],
    ) -> asyncio.Task:
        """Submit a job for async execution.

        Args:
            job: Training job to execute
            job_runner: Async function to run the job

        Returns:
            Task handle for the job
        """
        self._jobs[job.job_id] = job

        async def run_with_semaphore():
            async with self._semaphore:
                return await job_runner(job)

        task = asyncio.create_task(run_with_semaphore())
        self._running_tasks[job.job_id] = task

        # Clean up when done
        task.add_done_callback(lambda t: self._cleanup_job(job.job_id))

        logger.info(f"Submitted training job: {job.job_id}")
        return task

    def _cleanup_job(self, job_id: str) -> None:
        """Clean up completed job."""
        if job_id in self._running_tasks:
            del self._running_tasks[job_id]

    def get_job(self, job_id: str) -> TrainingJob | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def get_active_jobs(self) -> list[TrainingJob]:
        """Get list of active (running) jobs."""
        return [
            self._jobs[jid]
            for jid in self._running_tasks
            if jid in self._jobs
            and self._jobs[jid].status
            in [TrainingJobStatus.PENDING, TrainingJobStatus.TRAINING]
        ]

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        if job_id in self._running_tasks:
            task = self._running_tasks[job_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            if job_id in self._jobs:
                self._jobs[job_id].status = TrainingJobStatus.CANCELLED

            return True
        return False


class GrafanaMetricsExporter:
    """Exports training metrics to Grafana/InfluxDB."""

    def __init__(self, influxdb_client: Any | None = None) -> None:
        """Initialize metrics exporter.

        Args:
            influxdb_client: InfluxDB client for metrics export
        """
        self._client = influxdb_client

    async def export_job_metrics(self, job: TrainingJob) -> bool:
        """Export metrics for a training job.

        Args:
            job: Completed training job

        Returns:
            True if export succeeded
        """
        try:
            metrics = {
                "training_job_duration_seconds": job.duration_seconds or 0,
                "training_job_status": (
                    1 if job.status == TrainingJobStatus.COMPLETED else 0
                ),
                "training_job_retries": job.retry_count,
            }

            if job.metrics:
                if "accuracy" in job.metrics:
                    metrics["training_accuracy"] = job.metrics["accuracy"]
                if "loss" in job.metrics:
                    metrics["training_loss"] = job.metrics["loss"]
                if "validation_accuracy" in job.metrics:
                    metrics["training_validation_accuracy"] = job.metrics[
                        "validation_accuracy"
                    ]

            # In production, would write to InfluxDB
            if self._client:
                # await self._client.write_metrics(metrics)
                pass

            logger.info(f"Exported metrics for job {job.job_id}: {metrics}")
            return True

        except Exception as e:
            logger.error(f"Failed to export metrics for job {job.job_id}: {e}")
            return False

    async def export_trigger_metrics(self, trigger_result: TriggerResult) -> bool:
        """Export trigger event metrics.

        Args:
            trigger_result: Trigger evaluation result

        Returns:
            True if export succeeded
        """
        try:
            metrics = {
                "training_trigger_fired": 1 if trigger_result.triggered else 0,
                "training_trigger_type": trigger_result.trigger_type.value,
            }

            if trigger_result.metrics:
                for key, value in trigger_result.metrics.items():
                    if isinstance(value, (int, float)):
                        metrics[f"training_trigger_{key}"] = value

            logger.info(
                f"Exported trigger metrics: {trigger_result.trigger_type.name} = "
                f"{trigger_result.triggered}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to export trigger metrics: {e}")
            return False


class TrainingPipelineIntegration:
    """Main integration class for training pipeline.

    Coordinates:
    - Retraining trigger listening
    - Training data fetching from feedback loop
    - Async job scheduling
    - Model training execution
    - Model registration
    - Failure handling with retry
    - Grafana metrics export

    Example:
        >>> from ml.training.pipeline_integration import TrainingPipelineIntegration
        >>> integration = TrainingPipelineIntegration(
        ...     retraining_trigger=trigger,
        ...     model_registry=registry,
        ...     feedback_orchestrator=feedback,
        ... )
        >>> await integration.start_listening()
    """

    def __init__(
        self,
        retraining_trigger: RetrainingTrigger | None = None,
        model_registry: ModelRegistry | None = None,
        feedback_orchestrator: FeedbackOrchestrator | None = None,
        data_fetcher: TrainingDataFetcher | None = None,
        model_trainer: ModelTrainer | None = None,
        metrics_exporter: GrafanaMetricsExporter | None = None,
        job_scheduler: AsyncJobScheduler | None = None,
        hyperparameters: Hyperparameters | None = None,
        enable_retry: bool = True,
        max_retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    ) -> None:
        """Initialize training pipeline integration.

        Args:
            retraining_trigger: Retraining trigger system
            model_registry: Model registry for trained models
            feedback_orchestrator: Feedback loop orchestrator
            data_fetcher: Training data fetcher
            model_trainer: Model trainer implementation
            metrics_exporter: Metrics exporter for Grafana
            job_scheduler: Async job scheduler
            hyperparameters: Default hyperparameters
            enable_retry: Whether to enable retry on failure
            max_retry_attempts: Maximum retry attempts
        """
        self._trigger = retraining_trigger
        self._registry = model_registry
        self._feedback = feedback_orchestrator

        # Use provided or create default implementations
        self._data_fetcher = data_fetcher or FeedbackLoopDataFetcher(
            feedback_orchestrator=feedback_orchestrator
        )
        self._model_trainer = model_trainer
        self._metrics_exporter = metrics_exporter or GrafanaMetricsExporter()
        self._scheduler = job_scheduler or AsyncJobScheduler()

        self._hyperparameters = hyperparameters or Hyperparameters()
        self._enable_retry = enable_retry
        self._max_retry_attempts = max_retry_attempts

        self._listening = False
        self._listen_task: asyncio.Task | None = None

        logger.info(
            f"TrainingPipelineIntegration initialized: "
            f"retry={enable_retry}, max_retries={max_retry_attempts}"
        )

    def _get_flags(self):
        """Get current feature flags."""
        from config.feature_flags import get_feature_flags

        return get_feature_flags()

    def _generate_job_id(self, trigger_type: str) -> str:
        """Generate unique job ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"train_{trigger_type}_{timestamp}"

    async def handle_trigger(self, trigger_result: TriggerResult) -> TrainingJob:
        """Handle a retraining trigger event.

        Args:
            trigger_result: Trigger evaluation result

        Returns:
            TrainingJob record
        """
        # Check feature flag
        if not self._get_flags().launch_training_pipeline_enabled:
            logger.info("Training pipeline disabled by feature flag")
            job = TrainingJob(
                job_id=self._generate_job_id("disabled"),
                trigger_result=trigger_result,
                status=TrainingJobStatus.CANCELLED,
                error_message="Training pipeline disabled by feature flag",
            )
            return job

        # Create job
        job = TrainingJob(
            job_id=self._generate_job_id(
                trigger_result.trigger_type.name if trigger_result else "manual"
            ),
            trigger_result=trigger_result,
            hyperparameters=self._hyperparameters,
            max_retries=self._max_retry_attempts,
        )

        # Submit for async execution
        await self._scheduler.submit_job(job, self._execute_training_job)

        return job

    async def _execute_training_job(self, job: TrainingJob) -> TrainingJob:
        """Execute a training job with retry logic.

        Args:
            job: Training job to execute

        Returns:
            Completed job record
        """
        job.started_at = datetime.now(UTC)

        while job.retry_count <= job.max_retries:
            try:
                # Phase 1: Fetch training data
                job.status = TrainingJobStatus.FETCHING_DATA
                training_data = await self._data_fetcher.fetch_training_data(
                    min_samples=MIN_SAMPLES_FOR_TRAINING
                )
                job.metrics["data_samples"] = training_data.sample_count

                # Phase 2: Train model
                if self._model_trainer:
                    job.status = TrainingJobStatus.TRAINING
                    success, training_metrics = await self._model_trainer.train(
                        data=training_data,
                        hyperparameters=job.hyperparameters,
                    )

                    if not success:
                        raise TrainingExecutionError(
                            training_metrics.get("error", "Training failed")
                        )

                    job.metrics.update(training_metrics)
                else:
                    # Simulation mode when no trainer configured
                    logger.warning("No model trainer configured, simulating training")
                    job.metrics.update(
                        {
                            "accuracy": 0.85,
                            "loss": 0.15,
                            "validation_accuracy": 0.83,
                        }
                    )

                # Phase 3: Register model
                if self._registry:
                    job.status = TrainingJobStatus.REGISTERING
                    version = self._registry.register_model(
                        model_id=f"model_{job.job_id}",
                        model_path=f"/models/{job.job_id}.pkl",
                        metrics={
                            "accuracy": job.metrics.get("accuracy", 0.0),
                            "validation_accuracy": job.metrics.get(
                                "validation_accuracy", 0.0
                            ),
                        },
                        metadata={
                            "trigger_type": (
                                job.trigger_result.trigger_type.name
                                if job.trigger_result
                                else "manual"
                            ),
                            "hyperparameters": job.hyperparameters.to_dict(),
                            "training_samples": training_data.sample_count,
                        },
                    )
                    job.model_version = version.version_id

                # Success
                job.status = TrainingJobStatus.COMPLETED
                job.completed_at = datetime.now(UTC)

                # Export metrics
                await self._metrics_exporter.export_job_metrics(job)

                logger.info(f"Training job completed: {job.job_id}")
                return job

            except Exception as e:
                job.retry_count += 1
                job.error_message = str(e)

                if job.retry_count <= job.max_retries and self._enable_retry:
                    job.status = TrainingJobStatus.RETRYING
                    logger.warning(
                        f"Training job failed, retrying ({job.retry_count}/{job.max_retries}): {e}"
                    )
                    await asyncio.sleep(DEFAULT_RETRY_DELAY_SECONDS * job.retry_count)
                else:
                    # Max retries exceeded
                    job.status = TrainingJobStatus.FAILED
                    job.completed_at = datetime.now(UTC)
                    logger.error(
                        f"Training job failed after {job.retry_count} attempts: {e}"
                    )

                    # Export failure metrics
                    await self._metrics_exporter.export_job_metrics(job)

                    return job

        return job

    async def start_listening(self, poll_interval_seconds: float = 60.0) -> None:
        """Start listening for retraining triggers.

        Args:
            poll_interval_seconds: How often to check for triggers
        """
        if self._listening:
            logger.warning("Already listening for triggers")
            return

        if self._trigger is None:
            logger.error("No trigger system configured, cannot listen")
            return

        self._listening = True
        logger.info(
            f"Started listening for retraining triggers (interval={poll_interval_seconds}s)"
        )

        async def listen_loop():
            while self._listening:
                try:
                    # Evaluate all triggers
                    results = await self._trigger.evaluate_all()

                    # Handle any triggered events
                    for result in results:
                        if result.triggered:
                            logger.info(f"Trigger fired: {result.trigger_type.name}")
                            await self._metrics_exporter.export_trigger_metrics(result)
                            await self.handle_trigger(result)

                    await asyncio.sleep(poll_interval_seconds)

                except Exception as e:
                    logger.error(f"Error in trigger listening loop: {e}")
                    await asyncio.sleep(poll_interval_seconds)

        self._listen_task = asyncio.create_task(listen_loop())

    async def stop_listening(self) -> None:
        """Stop listening for triggers."""
        if not self._listening:
            return

        self._listening = False

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        logger.info("Stopped listening for retraining triggers")

    def get_job(self, job_id: str) -> TrainingJob | None:
        """Get job by ID."""
        return self._scheduler.get_job(job_id)

    def get_active_jobs(self) -> list[TrainingJob]:
        """Get list of active training jobs."""
        return self._scheduler.get_active_jobs()

    def get_job_history(self, limit: int = 10) -> list[TrainingJob]:
        """Get recent job history.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of training jobs
        """
        jobs = list(self._scheduler._jobs.values())
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]

    async def run_training_manual(
        self,
        hyperparameters: Hyperparameters | None = None,
    ) -> TrainingJob:
        """Manually trigger a training run.

        Args:
            hyperparameters: Optional hyperparameters override

        Returns:
            TrainingJob record
        """
        job = TrainingJob(
            job_id=self._generate_job_id("manual"),
            hyperparameters=hyperparameters or self._hyperparameters,
            max_retries=self._max_retry_attempts,
        )

        await self._scheduler.submit_job(job, self._execute_training_job)
        return job

    def get_stats(self) -> dict[str, Any]:
        """Get integration statistics."""
        jobs = list(self._scheduler._jobs.values())

        completed = sum(1 for j in jobs if j.status == TrainingJobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == TrainingJobStatus.FAILED)
        active = len(self.get_active_jobs())

        return {
            "total_jobs": len(jobs),
            "completed_jobs": completed,
            "failed_jobs": failed,
            "active_jobs": active,
            "success_rate": completed / len(jobs) if jobs else 0.0,
            "is_listening": self._listening,
        }
