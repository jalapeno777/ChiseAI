"""Training orchestrator with retraining trigger integration.

Orchestrates model training workflows with automatic trigger handling.
Integrates with retraining triggers to initiate training when conditions are met.

Features:
- Trigger-based training initiation
- Pre-training validation
- Training state management
- Discord notifications
- Graceful error handling

For ST-LAUNCH-011: Model Retraining Trigger
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from discord_alerts.config import DiscordConfig
    from ml.training.retraining_trigger import RetrainingTrigger, TriggerResult

logger = logging.getLogger(__name__)


class TrainingState(Enum):
    """State of training orchestration."""

    IDLE = auto()
    VALIDATING = auto()
    PREPARING = auto()
    TRAINING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class TrainingStatus(Enum):
    """Status of a training run."""

    SUCCESS = auto()
    VALIDATION_FAILED = auto()
    NO_DATA = auto()
    ALREADY_RUNNING = auto()
    ERROR = auto()
    CANCELLED = auto()


@dataclass
class TrainingRun:
    """Record of a training run.

    Attributes:
        run_id: Unique identifier for this run
        trigger_type: Type of trigger that initiated training
        state: Current training state
        status: Final status
        started_at: When training started
        completed_at: When training completed (if applicable)
        model_version: Version of trained model
        metrics: Training metrics
        error_message: Error message if failed
    """

    run_id: str
    trigger_type: str
    state: TrainingState
    status: TrainingStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    model_version: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "trigger_type": self.trigger_type,
            "state": self.state.name,
            "status": self.status.name if self.status else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "model_version": self.model_version,
            "metrics": self.metrics,
            "error_message": self.error_message,
        }


@dataclass
class OrchestratorConfig:
    """Configuration for training orchestrator.

    Attributes:
        min_training_interval_hours: Minimum hours between training runs
        max_training_duration_hours: Maximum training duration before timeout
        enable_auto_trigger: Whether to auto-trigger on evaluation
        enable_discord_notifications: Whether to send Discord notifications
        training_channel_id: Discord channel ID for training notifications
        validation_timeout_seconds: Timeout for validation phase
    """

    min_training_interval_hours: int = 1
    max_training_duration_hours: int = 4
    enable_auto_trigger: bool = True
    enable_discord_notifications: bool = True
    training_channel_id: str | None = None
    validation_timeout_seconds: float = 60.0


class TrainingPipelineRunner(Protocol):
    """Protocol for running training pipeline."""

    async def run_training(
        self,
        sample_count: int | None = None,
        validation_split: float = 0.2,
    ) -> tuple[bool, dict[str, Any]]:
        """Run training pipeline.

        Args:
            sample_count: Number of samples to train on (None = all)
            validation_split: Fraction for validation

        Returns:
            Tuple of (success, metrics)
        """
        ...


class DataProvider(Protocol):
    """Protocol for providing training data."""

    async def get_training_data_summary(self) -> dict[str, Any]:
        """Get summary of available training data.

        Returns:
            Dictionary with:
                - sample_count: Total samples
                - valid_samples: Valid samples
                - missing_features_pct: Missing feature percentage
                - stale_data_pct: Stale data percentage
        """
        ...

    async def prepare_training_data(self) -> tuple[bool, int]:
        """Prepare data for training.

        Returns:
            Tuple of (success, sample_count)
        """
        ...


class TrainingOrchestrator:
    """Orchestrates model training with trigger integration.

    Coordinates:
    - Retraining trigger evaluation
    - Pre-training validation
    - Training execution
    - State management
    - Notifications
    """

    def __init__(
        self,
        trigger: RetrainingTrigger | None = None,
        pipeline_runner: TrainingPipelineRunner | None = None,
        data_provider: DataProvider | None = None,
        config: OrchestratorConfig | None = None,
        discord_config: DiscordConfig | None = None,
    ) -> None:
        """Initialize training orchestrator.

        Args:
            trigger: Retraining trigger system
            pipeline_runner: Training pipeline runner
            data_provider: Training data provider
            config: Orchestrator configuration
            discord_config: Discord configuration
        """
        self.trigger = trigger
        self.pipeline_runner = pipeline_runner
        self.data_provider = data_provider
        self.config = config or OrchestratorConfig()

        self._current_run: TrainingRun | None = None
        self._run_history: list[TrainingRun] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Discord notifier
        if self.config.enable_discord_notifications:
            from ml.training.retraining_trigger import DiscordNotifier

            self._discord = DiscordNotifier(discord_config)
        else:
            self._discord = None

        logger.info(
            "TrainingOrchestrator initialized: "
            f"auto_trigger={self.config.enable_auto_trigger}, "
            f"min_interval={self.config.min_training_interval_hours}h"
        )

    def _generate_run_id(self) -> str:
        """Generate unique run ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"training_{timestamp}"

    async def _check_training_interval(self) -> bool:
        """Check if enough time has passed since last training.

        Returns:
            True if training can proceed
        """
        if not self._run_history:
            return True

        last_run = self._run_history[-1]
        if last_run.completed_at is None:
            return True  # Last run didn't complete

        elapsed = datetime.now(UTC) - last_run.completed_at
        min_interval = timedelta(hours=self.config.min_training_interval_hours)

        return elapsed >= min_interval

    async def _validate_data(self) -> tuple[bool, float, str]:
        """Validate training data quality.

        Returns:
            Tuple of (is_valid, quality_pct, message)
        """
        if self.trigger is None:
            return False, 0.0, "No trigger system configured"

        if self.data_provider is None:
            return False, 0.0, "No data provider configured"

        try:
            # Get data summary
            summary = await self.data_provider.get_training_data_summary()

            # Validate through trigger system
            (
                is_valid,
                quality_pct,
                message,
            ) = await self.trigger.validate_training_readiness(
                sample_count=summary.get("sample_count", 0),
                valid_samples=summary.get("valid_samples", 0),
                missing_features_pct=summary.get("missing_features_pct", 0.0),
                stale_data_pct=summary.get("stale_data_pct", 0.0),
            )

            return is_valid, quality_pct, message

        except Exception as e:
            logger.error(f"Data validation failed: {e}")
            return False, 0.0, f"Validation error: {e}"

    async def _notify_training_start(
        self,
        run: TrainingRun,
        trigger_result: TriggerResult | None = None,
    ) -> bool:
        """Send training start notification.

        Args:
            run: Training run
            trigger_result: Optional trigger result

        Returns:
            True if notification sent
        """
        if self._discord is None:
            return False

        try:
            message = f"🚀 Training started: {run.run_id}"
            if trigger_result:
                message += f"\nTrigger: {trigger_result.trigger_type.name}"
                message += f"\nReason: {trigger_result.message}"

            logger.info(f"Discord notification: {message}")
            # In production, would send actual Discord message
            return True
        except Exception as e:
            logger.error(f"Failed to send start notification: {e}")
            return False

    async def _notify_training_complete(
        self,
        run: TrainingRun,
    ) -> bool:
        """Send training completion notification.

        Args:
            run: Training run

        Returns:
            True if notification sent
        """
        if self._discord is None:
            return False

        try:
            if run.status == TrainingStatus.SUCCESS:
                emoji = "✅"
                status_text = "SUCCESS"
            else:
                emoji = "❌"
                status_text = run.status.name if run.status else "UNKNOWN"

            message = f"{emoji} Training {status_text}: {run.run_id}"
            if run.duration_seconds:
                message += f"\nDuration: {run.duration_seconds / 60:.1f} minutes"
            if run.model_version:
                message += f"\nModel Version: {run.model_version}"
            if run.error_message:
                message += f"\nError: {run.error_message[:500]}"

            logger.info(f"Discord notification: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send completion notification: {e}")
            return False

    async def run_training(
        self,
        trigger_result: TriggerResult | None = None,
        force: bool = False,
    ) -> TrainingRun:
        """Execute training run.

        Args:
            trigger_result: Optional trigger that initiated training
            force: Force training even if interval not met

        Returns:
            TrainingRun record
        """
        async with self._lock:
            # Check if already running
            if self._current_run and self._current_run.state == TrainingState.TRAINING:
                logger.warning("Training already in progress")
                return TrainingRun(
                    run_id="rejected",
                    trigger_type=(
                        trigger_result.trigger_type.name if trigger_result else "manual"
                    ),
                    state=TrainingState.IDLE,
                    status=TrainingStatus.ALREADY_RUNNING,
                    error_message="Training already in progress",
                )

            # Check training interval
            if not force and not await self._check_training_interval():
                self._run_history[-1] if self._run_history else None
                error_msg = (
                    f"Training interval not met "
                    f"(min {self.config.min_training_interval_hours}h)"
                )
                logger.warning(error_msg)
                return TrainingRun(
                    run_id="rejected",
                    trigger_type=(
                        trigger_result.trigger_type.name if trigger_result else "manual"
                    ),
                    state=TrainingState.IDLE,
                    status=TrainingStatus.ERROR,
                    error_message=error_msg,
                )

            # Create run record
            run = TrainingRun(
                run_id=self._generate_run_id(),
                trigger_type=(
                    trigger_result.trigger_type.name if trigger_result else "manual"
                ),
                state=TrainingState.VALIDATING,
                started_at=datetime.now(UTC),
            )
            self._current_run = run

            logger.info(f"Starting training run: {run.run_id}")

            try:
                # Phase 1: Data Validation
                run.state = TrainingState.VALIDATING
                is_valid, quality_pct, message = await self._validate_data()

                if not is_valid:
                    run.state = TrainingState.FAILED
                    run.status = TrainingStatus.VALIDATION_FAILED
                    run.error_message = f"Validation failed: {message}"
                    run.completed_at = datetime.now(UTC)
                    self._run_history.append(run)
                    await self._notify_training_complete(run)
                    logger.warning(f"Training validation failed: {message}")
                    return run

                logger.info(f"Data validation passed: {message}")

                # Phase 2: Data Preparation
                run.state = TrainingState.PREPARING
                if self.data_provider:
                    (
                        prep_success,
                        sample_count,
                    ) = await self.data_provider.prepare_training_data()
                    if not prep_success:
                        run.state = TrainingState.FAILED
                        run.status = TrainingStatus.NO_DATA
                        run.error_message = "Failed to prepare training data"
                        run.completed_at = datetime.now(UTC)
                        self._run_history.append(run)
                        await self._notify_training_complete(run)
                        return run
                    run.metrics["sample_count"] = sample_count

                # Notify start
                await self._notify_training_start(run, trigger_result)

                # Phase 3: Training
                run.state = TrainingState.TRAINING

                if self.pipeline_runner is None:
                    run.state = TrainingState.FAILED
                    run.status = TrainingStatus.ERROR
                    run.error_message = "No pipeline runner configured"
                    run.completed_at = datetime.now(UTC)
                    self._run_history.append(run)
                    await self._notify_training_complete(run)
                    return run

                # Run training with timeout
                max_duration = timedelta(hours=self.config.max_training_duration_hours)

                try:
                    success, training_metrics = await asyncio.wait_for(
                        self.pipeline_runner.run_training(
                            sample_count=run.metrics.get("sample_count"),
                        ),
                        timeout=max_duration.total_seconds(),
                    )

                    run.metrics.update(training_metrics)

                    if success:
                        run.state = TrainingState.COMPLETED
                        run.status = TrainingStatus.SUCCESS
                        run.model_version = training_metrics.get("model_version")
                        logger.info(f"Training completed successfully: {run.run_id}")
                    else:
                        run.state = TrainingState.FAILED
                        run.status = TrainingStatus.ERROR
                        run.error_message = training_metrics.get(
                            "error", "Training failed"
                        )
                        logger.error(f"Training failed: {run.error_message}")

                except TimeoutError:
                    run.state = TrainingState.FAILED
                    run.status = TrainingStatus.ERROR
                    run.error_message = (
                        "Training timeout after "
                        f"{self.config.max_training_duration_hours}h"
                    )
                    logger.error(run.error_message)

                run.completed_at = datetime.now(UTC)
                self._run_history.append(run)
                await self._notify_training_complete(run)

                return run

            except Exception as e:
                logger.exception(f"Training run failed: {e}")
                run.state = TrainingState.FAILED
                run.status = TrainingStatus.ERROR
                run.error_message = str(e)
                run.completed_at = datetime.now(UTC)
                self._run_history.append(run)
                await self._notify_training_complete(run)
                return run

    async def evaluate_triggers_and_train(self) -> TrainingRun | None:
        """Evaluate triggers and run training if triggered.

        Returns:
            TrainingRun if training was triggered, None otherwise
        """
        if self.trigger is None:
            logger.warning("No trigger system configured")
            return None

        if not self.config.enable_auto_trigger:
            logger.info("Auto-trigger disabled")
            return None

        # Evaluate all triggers
        results = await self.trigger.evaluate_all()

        # Check if any triggered
        should_trigger, triggering = self.trigger.should_trigger_retraining(results)

        if not should_trigger:
            logger.debug("No triggers fired")
            return None

        # Use first triggering result
        trigger_result = triggering[0]
        logger.info(f"Trigger fired: {trigger_result.trigger_type.name}")

        # Run training
        return await self.run_training(trigger_result=trigger_result)

    async def start_monitoring(self, interval_seconds: float = 300.0) -> None:
        """Start continuous trigger monitoring and auto-training.

        Args:
            interval_seconds: Evaluation interval in seconds (default: 5 minutes)
        """
        if self._running:
            logger.warning("Orchestrator monitoring already running")
            return

        if self.trigger is None:
            logger.error("Cannot start monitoring without trigger system")
            return

        self._running = True
        logger.info(f"Starting orchestrator monitoring (interval={interval_seconds}s)")

        async def monitor_loop():
            while self._running:
                try:
                    await self.evaluate_triggers_and_train()
                    await asyncio.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Error in orchestrator monitoring loop: {e}")
                    await asyncio.sleep(interval_seconds)

        self._task = asyncio.create_task(monitor_loop())

    async def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("Orchestrator monitoring stopped")

    def get_current_run(self) -> TrainingRun | None:
        """Get current training run.

        Returns:
            Current TrainingRun or None
        """
        return self._current_run

    def get_run_history(self, limit: int = 10) -> list[TrainingRun]:
        """Get training run history.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of TrainingRun records
        """
        return self._run_history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics.

        Returns:
            Dictionary with statistics
        """
        total_runs = len(self._run_history)
        successful_runs = sum(
            1 for r in self._run_history if r.status == TrainingStatus.SUCCESS
        )
        failed_runs = sum(
            1
            for r in self._run_history
            if r.status in (TrainingStatus.ERROR, TrainingStatus.VALIDATION_FAILED)
        )

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": successful_runs / total_runs if total_runs > 0 else 0.0,
            "current_state": (
                self._current_run.state.name if self._current_run else "idle"
            ),
            "is_monitoring": self._running,
        }
