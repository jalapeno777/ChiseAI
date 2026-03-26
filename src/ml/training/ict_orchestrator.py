"""ICT ML Pipeline Orchestration.

This module provides orchestration for ICT model training including:
- Scheduled periodic ICT model retraining
- Performance monitoring and retraining triggers
- Integration with existing scheduler
- Model promotion/demotion based on performance

ST-ICT-028-C: ICT ML Pipeline Orchestration
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.ml.training.ict_integration import (
        ICTTrainingMetrics,
        ICTTrainingPipeline,
    )

logger = logging.getLogger(__name__)


class OrchestrationStatus(Enum):
    """Status of ICT orchestration."""

    IDLE = auto()
    MONITORING = auto()
    TRAINING = auto()
    VALIDATING = auto()
    PROMOTING = auto()
    DEMOTING = auto()
    FAILED = auto()


class RetrainingReason(Enum):
    """Reason for triggering retraining."""

    SCHEDULED = "scheduled"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    THRESHOLD_BREACH = "threshold_breach"
    MANUAL = "manual"
    NEW_DATA_AVAILABLE = "new_data_available"


@dataclass
class PerformanceThresholds:
    """Thresholds for triggering retraining.

    Attributes:
        min_direction_accuracy: Minimum direction accuracy before demotion
        max_ece: Maximum ECE before demotion
        min_validation_accuracy: Minimum validation accuracy before demotion
        degradation_margin: Margin below champion accuracy to trigger demotion
        promotion_margin: Margin above challenger to trigger promotion
    """

    min_direction_accuracy: float = 0.50
    max_ece: float = 0.20
    min_validation_accuracy: float = 0.45
    degradation_margin: float = 0.05
    promotion_margin: float = 0.02

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "min_direction_accuracy": self.min_direction_accuracy,
            "max_ece": self.max_ece,
            "min_validation_accuracy": self.min_validation_accuracy,
            "degradation_margin": self.degradation_margin,
            "promotion_margin": self.promotion_margin,
        }


@dataclass
class ICTModelState:
    """State of an ICT model in the promotion pipeline.

    Attributes:
        model_version: Version identifier
        metrics: ICT training metrics
        status: Current status (champion/challenger/archived)
        trained_at: Training timestamp
        promoted_at: When promoted to champion
        archived_at: When archived
    """

    model_version: str
    metrics: ICTTrainingMetrics | None = None
    status: str = "challenger"
    trained_at: datetime = field(default_factory=datetime.now)
    promoted_at: datetime | None = None
    archived_at: datetime | None = None


@dataclass
class RetrainingEvent:
    """Record of a retraining event.

    Attributes:
        event_id: Unique event identifier
        reason: Reason for retraining
        previous_version: Previous model version
        new_version: New model version (if successful)
        success: Whether retraining succeeded
        metrics: Training metrics
        timestamp: When event occurred
        error_message: Error message if failed
    """

    event_id: str
    reason: RetrainingReason
    previous_version: str
    new_version: str | None = None
    success: bool = False
    metrics: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "reason": self.reason.value,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "success": self.success,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
        }


@dataclass
class ICTOrchestratorConfig:
    """Configuration for ICT orchestrator.

    Attributes:
        schedule_frequency: How often to check for retraining (daily/weekly)
        retraining_enabled: Whether automatic retraining is enabled
        promotion_enabled: Whether automatic promotion is enabled
        thresholds: Performance thresholds for demotion/promotion
        champion_grace_period_hours: Hours before champion can be demoted
        min_training_interval_hours: Minimum hours between training runs
        max_retraining_per_day: Maximum retraining runs per day
    """

    schedule_frequency: str = "daily"
    retraining_enabled: bool = True
    promotion_enabled: bool = True
    thresholds: PerformanceThresholds = field(default_factory=PerformanceThresholds)
    champion_grace_period_hours: int = 24
    min_training_interval_hours: int = 6
    max_retraining_per_day: int = 3

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.min_training_interval_hours < 1:
            raise ValueError("min_training_interval_hours must be at least 1")
        if self.max_retraining_per_day < 1:
            raise ValueError("max_retraining_per_day must be at least 1")


class ICTSchedulerAdapter:
    """Adapter for integrating with existing scheduler."""

    def __init__(
        self,
        schedule_frequency: str = "daily",
        hour: int = 2,
        minute: int = 0,
    ) -> None:
        """Initialize scheduler adapter.

        Args:
            schedule_frequency: Schedule frequency (daily/weekly)
            hour: Hour to run
            minute: Minute to run
        """
        self._frequency = schedule_frequency
        self._hour = hour
        self._minute = minute

    def get_schedule_config(self) -> dict[str, Any]:
        """Get schedule configuration for existing scheduler.

        Returns:
            Dictionary with schedule configuration
        """
        from src.ml.scheduler import ScheduleFrequency

        freq_map = {
            "daily": ScheduleFrequency.DAILY,
            "weekly": ScheduleFrequency.WEEKLY,
            "monthly": ScheduleFrequency.MONTHLY,
        }

        freq = freq_map.get(self._frequency, ScheduleFrequency.DAILY)

        return {
            "frequency": freq,
            "hour": self._hour,
            "minute": self._minute,
        }

    def should_run(
        self,
        last_run: datetime | None,
        current_time: datetime | None = None,
    ) -> bool:
        """Check if should run based on schedule.

        Args:
            last_run: Last run timestamp
            current_time: Current time (defaults to now)

        Returns:
            True if should run
        """
        now = current_time or datetime.now(UTC)

        if last_run is None:
            return True

        if self._frequency == "daily":
            # Run if last run was yesterday or earlier
            return (now - last_run).total_seconds() >= 86400  # 24 hours

        elif self._frequency == "weekly":
            # Run if last run was 7 days ago or earlier
            return (now - last_run).total_seconds() >= 604800  # 7 days

        return True


class PerformanceMonitor:
    """Monitors ICT model performance and triggers retraining."""

    def __init__(
        self,
        thresholds: PerformanceThresholds | None = None,
    ) -> None:
        """Initialize performance monitor.

        Args:
            thresholds: Performance thresholds
        """
        self._thresholds = thresholds or PerformanceThresholds()
        self._history: list[ICTModelState] = []

    def add_model_state(self, state: ICTModelState) -> None:
        """Add model state to history.

        Args:
            state: Model state to add
        """
        self._history.append(state)
        # Keep last 100 states
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def should_retrain(
        self,
        champion_metrics: ICTTrainingMetrics | None,
        retraining_history: list[RetrainingEvent],
    ) -> tuple[bool, RetrainingReason | None]:
        """Check if should trigger retraining.

        Args:
            champion_metrics: Current champion metrics
            retraining_history: Recent retraining events

        Returns:
            Tuple of (should_retrain, reason)
        """
        # Check retraining frequency
        if retraining_history:
            last_retrain = retraining_history[-1]
            if last_retrain.success:
                elapsed = datetime.now(UTC) - last_retrain.timestamp
                if elapsed.total_seconds() < 21600:  # 6 hours
                    return False, None

        # Check max retraining per day
        today = datetime.now(UTC).date()
        today_retrains = sum(
            1 for e in retraining_history if e.timestamp.date() == today and e.success
        )
        if today_retrains >= 3:
            return False, None

        # Check champion performance
        if champion_metrics is None:
            return True, RetrainingReason.NEW_DATA_AVAILABLE

        # Check if champion has degraded
        if champion_metrics.direction_accuracy < (
            self._thresholds.min_direction_accuracy
            + self._thresholds.degradation_margin
        ):
            return True, RetrainingReason.PERFORMANCE_DEGRADATION

        if champion_metrics.confidence_calibration > (self._thresholds.max_ece - 0.02):
            return True, RetrainingReason.PERFORMANCE_DEGRADATION

        return True, RetrainingReason.SCHEDULED

    def should_demote(
        self,
        champion_metrics: ICTTrainingMetrics,
        challenger_metrics: ICTTrainingMetrics,
    ) -> bool:
        """Check if should demote champion in favor of challenger.

        Args:
            champion_metrics: Current champion metrics
            challenger_metrics: Challenger metrics

        Returns:
            True if should demote
        """
        # Check if challenger significantly outperforms champion
        accuracy_diff = (
            challenger_metrics.direction_accuracy - champion_metrics.direction_accuracy
        )

        # Demote if challenger is better by margin
        if accuracy_diff >= self._thresholds.promotion_margin:
            # Also check ECE is acceptable
            if challenger_metrics.confidence_calibration < self._thresholds.max_ece:
                return True

        return False

    def should_promote(
        self,
        champion_metrics: ICTTrainingMetrics | None,
        challenger_metrics: ICTTrainingMetrics,
    ) -> bool:
        """Check if should promote challenger to champion.

        Args:
            champion_metrics: Current champion metrics (None if no champion)
            challenger_metrics: Challenger metrics

        Returns:
            True if should promote
        """
        # No champion - always promote
        if champion_metrics is None:
            return True

        # Check if challenger meets minimum thresholds
        if (
            challenger_metrics.direction_accuracy
            < self._thresholds.min_direction_accuracy
        ):
            return False

        if challenger_metrics.confidence_calibration > self._thresholds.max_ece:
            return False

        # Check if challenger significantly outperforms
        accuracy_diff = (
            challenger_metrics.direction_accuracy - champion_metrics.direction_accuracy
        )

        return accuracy_diff >= self._thresholds.promotion_margin

    def get_thresholds(self) -> PerformanceThresholds:
        """Get performance thresholds."""
        return self._thresholds


class ModelPromoter:
    """Handles model promotion and demotion."""

    def __init__(
        self,
        grace_period_hours: int = 24,
    ) -> None:
        """Initialize model promoter.

        Args:
            grace_period_hours: Hours before champion can be demoted
        """
        self._grace_period = timedelta(hours=grace_period_hours)
        self._champion: ICTModelState | None = None
        self._challenger: ICTModelState | None = None

    def set_champion(self, state: ICTModelState) -> None:
        """Set champion model.

        Args:
            state: Champion model state
        """
        state.status = "champion"
        self._champion = state
        logger.info(f"Champion set: {state.model_version}")

    def set_challenger(self, state: ICTModelState) -> None:
        """Set challenger model.

        Args:
            state: Challenger model state
        """
        state.status = "challenger"
        self._challenger = state
        logger.info(f"Challenger set: {state.model_version}")

    def promote(self) -> tuple[str | None, str | None]:
        """Promote challenger to champion.

        Returns:
            Tuple of (new_champion_version, old_champion_version)
        """
        if self._challenger is None:
            return None, None

        old_version = self._champion.model_version if self._champion else None

        # Archive old champion
        if self._champion:
            self._champion.status = "archived"
            self._champion.archived_at = datetime.now(UTC)

        # Promote challenger
        self._challenger.status = "champion"
        self._challenger.promoted_at = datetime.now(UTC)

        new_champion = self._challenger
        self._champion = new_champion
        self._challenger = None

        logger.info(f"Promoted {new_champion.model_version} to champion")
        return new_champion.model_version, old_version

    def can_demote(self) -> bool:
        """Check if champion can be demoted.

        Returns:
            True if grace period has passed
        """
        if self._champion is None:
            return True

        if self._champion.promoted_at is None:
            return True

        elapsed = datetime.now(UTC) - self._champion.promoted_at
        return elapsed >= self._grace_period

    def get_champion(self) -> ICTModelState | None:
        """Get current champion."""
        return self._champion

    def get_challenger(self) -> ICTModelState | None:
        """Get current challenger."""
        return self._challenger


class ICTOrchestrator:
    """Orchestrates ICT model training with scheduling and promotion.

    Features:
    - Scheduled periodic ICT model retraining
    - Performance monitoring and retraining triggers
    - Integration with existing scheduler
    - Model promotion/demotion based on performance

    Example:
        >>> from src.ml.training.ict_orchestrator import ICTOrchestrator, ICTOrchestratorConfig
        >>> config = ICTOrchestratorConfig(retraining_enabled=True)
        >>> orchestrator = ICTOrchestrator(config=config)
        >>> await orchestrator.start()
    """

    def __init__(
        self,
        config: ICTOrchestratorConfig | None = None,
        training_pipeline: ICTTrainingPipeline | None = None,
        schedule_adapter: ICTSchedulerAdapter | None = None,
        performance_monitor: PerformanceMonitor | None = None,
        model_promoter: ModelPromoter | None = None,
    ) -> None:
        """Initialize ICT orchestrator.

        Args:
            config: Orchestrator configuration
            training_pipeline: ICT training pipeline
            schedule_adapter: Scheduler adapter for periodic runs
            performance_monitor: Performance monitoring
            model_promoter: Model promotion/demotion handler
        """
        self._config = config or ICTOrchestratorConfig()
        self._pipeline = training_pipeline
        self._scheduler = schedule_adapter or ICTSchedulerAdapter(
            schedule_frequency=self._config.schedule_frequency
        )
        self._monitor = performance_monitor or PerformanceMonitor(
            thresholds=self._config.thresholds
        )
        self._promoter = model_promoter or ModelPromoter(
            grace_period_hours=self._config.champion_grace_period_hours
        )

        # State
        self._status = OrchestrationStatus.IDLE
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_training: datetime | None = None
        self._retraining_history: list[RetrainingEvent] = []
        self._lock = asyncio.Lock()

        logger.info(
            f"ICTOrchestrator initialized: "
            f"schedule={self._config.schedule_frequency}, "
            f"retraining={self._config.retraining_enabled}"
        )

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"ict_retrain_{timestamp}"

    async def trigger_retraining(
        self,
        reason: RetrainingReason = RetrainingReason.MANUAL,
    ) -> RetrainingEvent:
        """Trigger ICT model retraining.

        Args:
            reason: Reason for retraining

        Returns:
            RetrainingEvent with results
        """
        async with self._lock:
            self._status = OrchestrationStatus.TRAINING

            champion = self._promoter.get_champion()
            previous_version = champion.model_version if champion else "none"

            event = RetrainingEvent(
                event_id=self._generate_event_id(),
                reason=reason,
                previous_version=previous_version,
            )

            logger.info(f"Starting ICT retraining: reason={reason.value}")

            try:
                if self._pipeline is None:
                    # Simulate training
                    event.success = False
                    event.error_message = "No training pipeline configured"
                    return event

                # Run full training pipeline
                result = await self._pipeline.run_full_pipeline()

                if result["status"] == "completed":
                    event.success = True
                    event.new_version = result.get("model_version", "unknown")
                    event.metrics = result.get("metrics", {})

                    # Update champion/challenger state
                    from src.ml.training.ict_integration import ICTTrainingMetrics

                    metrics = ICTTrainingMetrics(**event.metrics)
                    new_state = ICTModelState(
                        model_version=event.new_version,
                        metrics=metrics,
                    )

                    # Check if should promote
                    if self._config.promotion_enabled:
                        champion = self._promoter.get_champion()
                        if self._monitor.should_promote(
                            champion.metrics if champion else None,
                            metrics,
                        ):
                            self._status = OrchestrationStatus.PROMOTING
                            new_ver, old_ver = self._promoter.promote()
                            event.new_version = new_ver or event.new_version
                            logger.info(f"Promoted {new_ver} to champion")

                    # Set as challenger
                    self._promoter.set_challenger(new_state)
                    self._monitor.add_model_state(new_state)

                    self._last_training = datetime.now(UTC)
                    self._status = OrchestrationStatus.IDLE

                else:
                    event.success = False
                    event.error_message = result.get("error", "Training failed")

            except Exception as e:
                logger.exception(f"Retraining failed: {e}")
                event.success = False
                event.error_message = str(e)
                self._status = OrchestrationStatus.FAILED

            self._retraining_history.append(event)
            return event

    async def evaluate_and_retrain(self) -> RetrainingEvent | None:
        """Evaluate performance and trigger retraining if needed.

        Returns:
            RetrainingEvent if triggered, None otherwise
        """
        champion = self._promoter.get_champion()

        should_retrain, reason = self._monitor.should_retrain(
            champion.metrics if champion else None,
            self._retraining_history,
        )

        if not should_retrain or not self._config.retraining_enabled:
            return None

        return await self.trigger_retraining(reason)

    async def check_promotion(self) -> tuple[str | None, str | None]:
        """Check if challenger should be promoted.

        Returns:
            Tuple of (new_champion_version, old_champion_version)
        """
        champion = self._promoter.get_champion()
        challenger = self._promoter.get_challenger()

        if challenger is None:
            return None, None

        if self._monitor.should_promote(
            champion.metrics if champion else None,
            challenger.metrics,
        ):
            self._status = OrchestrationStatus.PROMOTING
            new_ver, old_ver = self._promoter.promote()
            self._status = OrchestrationStatus.IDLE
            return new_ver, old_ver

        return None, None

    async def start(self, poll_interval_seconds: float = 3600.0) -> None:
        """Start ICT orchestration loop.

        Args:
            poll_interval_seconds: How often to check for retraining (default: 1 hour)
        """
        if self._running:
            logger.warning("ICT orchestrator already running")
            return

        self._running = True
        logger.info(
            f"Starting ICT orchestration loop (poll_interval={poll_interval_seconds}s)"
        )

        async def orchestration_loop():
            while self._running:
                try:
                    # Check if should run based on schedule
                    if self._scheduler.should_run(self._last_training):
                        await self.evaluate_and_retrain()

                    # Check promotion
                    await self.check_promotion()

                    await asyncio.sleep(poll_interval_seconds)

                except Exception as e:
                    logger.error(f"Orchestration loop error: {e}")
                    await asyncio.sleep(poll_interval_seconds)

        self._task = asyncio.create_task(orchestration_loop())

    async def stop(self) -> None:
        """Stop ICT orchestration."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        self._status = OrchestrationStatus.IDLE
        logger.info("ICT orchestrator stopped")

    def get_status(self) -> OrchestrationStatus:
        """Get current orchestration status."""
        return self._status

    def get_champion(self) -> ICTModelState | None:
        """Get current champion model."""
        return self._promoter.get_champion()

    def get_challenger(self) -> ICTModelState | None:
        """Get current challenger model."""
        return self._promoter.get_challenger()

    def get_retraining_history(self, limit: int = 10) -> list[RetrainingEvent]:
        """Get retraining history.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of retraining events
        """
        return self._retraining_history[-limit:]

    def get_config(self) -> ICTOrchestratorConfig:
        """Get orchestrator configuration."""
        return self._config

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics.

        Returns:
            Dictionary with statistics
        """
        champion = self._promoter.get_champion()
        challenger = self._promoter.get_challenger()

        total_retrains = len(self._retraining_history)
        successful_retrains = sum(1 for e in self._retraining_history if e.success)
        failed_retrains = total_retrains - successful_retrains

        return {
            "status": self._status.name,
            "is_running": self._running,
            "champion_version": champion.model_version if champion else None,
            "champion_metrics": (
                champion.metrics.to_dict() if champion and champion.metrics else None
            ),
            "challenger_version": challenger.model_version if challenger else None,
            "challenger_metrics": (
                challenger.metrics.to_dict()
                if challenger and challenger.metrics
                else None
            ),
            "total_retrains": total_retrains,
            "successful_retrains": successful_retrains,
            "failed_retrains": failed_retrains,
            "last_training": (
                self._last_training.isoformat() if self._last_training else None
            ),
            "retraining_enabled": self._config.retraining_enabled,
            "promotion_enabled": self._config.promotion_enabled,
        }
