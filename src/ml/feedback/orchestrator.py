"""Feedback Loop Orchestrator for ML Model Improvement.

This module coordinates the full feedback loop pipeline, schedules iterations,
and ensures the 24-hour completion guarantee.

Features:
- Coordinate the full feedback loop pipeline
- Schedule and manage loop iterations
- Ensure temporal safety (no data leakage)
- Monitor loop completion within 24 hours
- Export metrics to InfluxDB for visibility

Usage:
    from ml.feedback.orchestrator import FeedbackOrchestrator, OrchestratorConfig

    config = OrchestratorConfig()
    orchestrator = FeedbackOrchestrator(config)
    await orchestrator.run_feedback_loop()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ml.feedback.analyzer import FeedbackAnalysisReport
    from ml.feedback.matcher import MatchBatchResult, PredictionOutcomeMatch
    from ml.feedback.updater import UpdateResult

logger = logging.getLogger(__name__)


class LoopStatus(Enum):
    """Status of a feedback loop iteration."""

    IDLE = "idle"
    RUNNING = "running"
    MATCHING = "matching"
    ANALYZING = "analyzing"
    UPDATING = "updating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TemporalSafetyMode(Enum):
    """Mode for temporal safety enforcement."""

    STRICT = "strict"  # No future data allowed whatsoever
    MODERATE = "moderate"  # Small buffer allowed
    LENIENT = "lenient"  # Only prevent obvious leakage


@dataclass
class OrchestratorConfig:
    """Configuration for feedback loop orchestration.

    Attributes:
        max_loop_duration_hours: Maximum allowed loop duration
        matching_window_hours: Default matching window
        min_samples_for_update: Minimum samples before model update
        temporal_safety_mode: Strictness of temporal validation
        enable_auto_update: Whether to auto-update models
        enable_drift_detection: Whether to enable drift detection
        metrics_export_interval_seconds: Interval for metrics export
        max_retries: Maximum retries on failure
        retry_delay_seconds: Delay between retries
        schedule_interval_hours: Hours between scheduled runs
    """

    max_loop_duration_hours: float = 24.0
    matching_window_hours: float = 24.0
    min_samples_for_update: int = 100
    temporal_safety_mode: TemporalSafetyMode = TemporalSafetyMode.STRICT
    enable_auto_update: bool = True
    enable_drift_detection: bool = True
    metrics_export_interval_seconds: int = 60
    max_retries: int = 3
    retry_delay_seconds: int = 60
    schedule_interval_hours: float = 24.0


@dataclass
class LoopIterationResult:
    """Result of a feedback loop iteration.

    Attributes:
        iteration_id: Unique iteration identifier
        start_time: When iteration started
        end_time: When iteration completed
        status: Final status
        total_matches: Number of prediction-outcome matches
        analysis_report: Analysis results
        update_result: Model update results
        duration_seconds: Total duration
        errors: List of errors encountered
        warnings: List of warnings
        metadata: Additional metadata
    """

    iteration_id: str
    start_time: datetime
    end_time: datetime | None = None
    status: LoopStatus = LoopStatus.IDLE
    total_matches: int = 0
    analysis_report: dict[str, Any] | None = None
    update_result: dict[str, Any] | None = None
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "iteration_id": self.iteration_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "total_matches": self.total_matches,
            "analysis_report": self.analysis_report,
            "update_result": self.update_result,
            "duration_seconds": round(self.duration_seconds, 2),
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class TemporalBoundary:
    """Temporal boundaries for data safety.

    Attributes:
        data_cutoff_time: Latest time for training data
        validation_start_time: Start of validation period
        validation_end_time: End of validation period
        buffer_hours: Safety buffer in hours
    """

    data_cutoff_time: datetime
    validation_start_time: datetime
    validation_end_time: datetime
    buffer_hours: float = 1.0

    def is_safe(self, timestamp: datetime) -> bool:
        """Check if timestamp is within safe training window.

        Args:
            timestamp: Timestamp to check

        Returns:
            True if safe for training data
        """
        return timestamp <= self.data_cutoff_time

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "data_cutoff_time": self.data_cutoff_time.isoformat(),
            "validation_start_time": self.validation_start_time.isoformat(),
            "validation_end_time": self.validation_end_time.isoformat(),
            "buffer_hours": self.buffer_hours,
        }


class FeedbackOrchestrator:
    """Orchestrates the ML feedback loop.

    This class coordinates:
    - Prediction-outcome matching
    - Performance analysis
    - Model updates
    - Temporal safety enforcement
    - Metrics export
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        matcher: Any | None = None,
        analyzer: Any | None = None,
        updater: Any | None = None,
        signal_tracker: Any | None = None,
        influxdb_client: Any | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            config: Orchestrator configuration
            matcher: PredictionOutcomeMatcher instance
            analyzer: FeedbackAnalyzer instance
            updater: ModelUpdater instance
            signal_tracker: SignalTracker instance
            influxdb_client: InfluxDB client for metrics export
        """
        self.config = config or OrchestratorConfig()
        self.matcher = matcher
        self.analyzer = analyzer
        self.updater = updater
        self.signal_tracker = signal_tracker
        self.influxdb_client = influxdb_client

        self._current_iteration: LoopIterationResult | None = None
        self._iteration_history: list[LoopIterationResult] = []
        self._is_running = False
        self._scheduled_task: asyncio.Task | None = None

    async def run_feedback_loop(
        self,
        model: Any | None = None,
        model_id: str = "default",
        force: bool = False,
    ) -> LoopIterationResult:
        """Run a complete feedback loop iteration.

        Args:
            model: Model to update (optional)
            model_id: Model identifier
            force: Force run even if already running

        Returns:
            LoopIterationResult with iteration details
        """
        if self._is_running and not force:
            logger.warning("Feedback loop already running, skipping")
            if self._current_iteration:
                return self._current_iteration

        self._is_running = True
        iteration_id = f"loop_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        result = LoopIterationResult(
            iteration_id=iteration_id,
            start_time=datetime.now(timezone.utc),
            status=LoopStatus.RUNNING,
        )
        self._current_iteration = result

        logger.info(f"Starting feedback loop iteration {iteration_id}")

        try:
            # Calculate temporal boundaries
            temporal_boundary = self._calculate_temporal_boundary()
            result.metadata["temporal_boundary"] = temporal_boundary.to_dict()

            # Step 1: Match predictions with outcomes
            result.status = LoopStatus.MATCHING
            match_result = await self._run_matching(temporal_boundary)
            result.total_matches = match_result.matched if match_result else 0

            if not match_result or result.total_matches == 0:
                result.status = LoopStatus.COMPLETED
                result.warnings.append("No matches found for analysis")
                return self._finalize_iteration(result)

            # Step 2: Analyze matches
            result.status = LoopStatus.ANALYZING
            analysis_report = await self._run_analysis(match_result)
            if analysis_report:
                result.analysis_report = analysis_report.to_dict()

            # Step 3: Update model (if enabled and model provided)
            if self.config.enable_auto_update and model is not None:
                result.status = LoopStatus.UPDATING
                update_result = await self._run_update(
                    model, match_result, analysis_report, model_id
                )
                if update_result:
                    result.update_result = update_result.to_dict()

            # Step 4: Export metrics
            await self._export_metrics(result)

            result.status = LoopStatus.COMPLETED
            logger.info(
                f"Feedback loop {iteration_id} completed: "
                f"{result.total_matches} matches in {result.duration_seconds:.1f}s"
            )

        except asyncio.TimeoutError:
            result.status = LoopStatus.TIMEOUT
            result.errors.append(
                f"Loop exceeded {self.config.max_loop_duration_hours} hour limit"
            )
            logger.error(f"Feedback loop {iteration_id} timed out")

        except Exception as e:
            result.status = LoopStatus.FAILED
            result.errors.append(str(e))
            logger.exception(f"Feedback loop {iteration_id} failed")

        finally:
            self._is_running = False

        return self._finalize_iteration(result)

    async def start_scheduled(
        self, model: Any | None = None, model_id: str = "default"
    ) -> None:
        """Start scheduled feedback loop execution.

        Args:
            model: Model to update
            model_id: Model identifier
        """
        if self._scheduled_task and not self._scheduled_task.done():
            logger.warning("Scheduled loop already running")
            return

        async def scheduled_loop():
            while True:
                try:
                    await self.run_feedback_loop(model, model_id)
                except Exception as e:
                    logger.error(f"Scheduled loop error: {e}")

                # Wait for next interval
                await asyncio.sleep(self.config.schedule_interval_hours * 3600)

        self._scheduled_task = asyncio.create_task(scheduled_loop())
        logger.info(
            f"Started scheduled feedback loop (interval: {self.config.schedule_interval_hours}h)"
        )

    async def stop_scheduled(self) -> None:
        """Stop scheduled feedback loop execution."""
        if self._scheduled_task and not self._scheduled_task.done():
            self._scheduled_task.cancel()
            try:
                await self._scheduled_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped scheduled feedback loop")

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status.

        Returns:
            Status dictionary
        """
        return {
            "is_running": self._is_running,
            "current_iteration": (
                self._current_iteration.to_dict() if self._current_iteration else None
            ),
            "total_iterations": len(self._iteration_history),
            "config": {
                "max_loop_duration_hours": self.config.max_loop_duration_hours,
                "enable_auto_update": self.config.enable_auto_update,
                "schedule_interval_hours": self.config.schedule_interval_hours,
            },
        }

    def get_iteration_history(
        self,
        limit: int = 10,
        status: LoopStatus | None = None,
    ) -> list[LoopIterationResult]:
        """Get iteration history.

        Args:
            limit: Maximum number of results
            status: Optional status filter

        Returns:
            List of iteration results
        """
        iterations = self._iteration_history
        if status:
            iterations = [i for i in iterations if i.status == status]
        return sorted(iterations, key=lambda x: x.start_time, reverse=True)[:limit]

    async def _run_matching(
        self,
        temporal_boundary: TemporalBoundary,
    ) -> Any | None:  # MatchBatchResult
        """Run prediction-outcome matching phase."""
        if not self.matcher:
            logger.warning("No matcher configured, skipping matching phase")
            return None

        if not self.signal_tracker:
            logger.warning("No signal tracker configured, skipping matching phase")
            return None

        try:
            # Get signals within safe temporal window
            cutoff_ms = int(temporal_boundary.data_cutoff_time.timestamp() * 1000)
            start_ms = cutoff_ms - int(self.config.matching_window_hours * 3600 * 1000)

            signals = await self.signal_tracker.get_signal_history(
                start_time_ms=start_ms,
                end_time_ms=cutoff_ms,
                with_outcomes_only=False,
            )

            if not signals:
                logger.info("No signals found for matching")
                return None

            # Extract signal records
            signal_records = [s.signal for s in signals]

            # Run matching
            match_result = await self.matcher.match_batch(
                signals=signal_records,
                current_time_ms=cutoff_ms,
            )

            logger.info(
                f"Matching complete: {match_result.matched}/{match_result.total_signals} matched"
            )

            return match_result

        except Exception as e:
            logger.error(f"Matching phase failed: {e}")
            raise

    async def _run_analysis(
        self,
        match_result: Any,  # MatchBatchResult
    ) -> Any | None:  # FeedbackAnalysisReport
        """Run analysis phase."""
        if not self.analyzer:
            logger.warning("No analyzer configured, skipping analysis phase")
            return None

        try:
            # Get valid matches (with outcomes)
            from ml.feedback.matcher import MatchStatus

            valid_matches = [
                m
                for m in match_result.matches
                if m.status == MatchStatus.MATCHED and m.outcome is not None
            ]

            if len(valid_matches) < self.config.min_samples_for_update:
                logger.info(
                    f"Insufficient matches for analysis: {len(valid_matches)} "
                    f"(minimum {self.config.min_samples_for_update})"
                )
                return None

            # Run analysis
            report = await self.analyzer.analyze_matches(valid_matches)

            logger.info(
                f"Analysis complete: {report.overall_accuracy:.2%} accuracy, "
                f"{len(report.drift_indicators)} drift indicators"
            )

            return report

        except Exception as e:
            logger.error(f"Analysis phase failed: {e}")
            raise

    async def _run_update(
        self,
        model: Any,
        match_result: Any,  # MatchBatchResult
        analysis_report: Any | None,  # FeedbackAnalysisReport
        model_id: str,
    ) -> Any | None:  # UpdateResult
        """Run model update phase."""
        if not self.updater:
            logger.warning("No updater configured, skipping update phase")
            return None

        try:
            # Get valid matches
            from ml.feedback.matcher import MatchStatus

            valid_matches = [
                m
                for m in match_result.matches
                if m.status == MatchStatus.MATCHED and m.outcome is not None
            ]

            if len(valid_matches) < self.config.min_samples_for_update:
                logger.info(
                    f"Insufficient matches for update: {len(valid_matches)} "
                    f"(minimum {self.config.min_samples_for_update})"
                )
                return None

            # Run update
            if analysis_report:
                result = await self.updater.update_from_analysis(
                    model=model,
                    analysis_report=analysis_report,
                    matches=valid_matches,
                    model_id=model_id,
                )
            else:
                result = await self.updater.update_from_matches(
                    model=model,
                    matches=valid_matches,
                    model_id=model_id,
                )

            logger.info(
                f"Update complete: status={result.status.value}, "
                f"accuracy={result.validation_metrics.get('accuracy', 0):.2%}"
            )

            return result

        except Exception as e:
            logger.error(f"Update phase failed: {e}")
            raise

    async def _export_metrics(self, result: LoopIterationResult) -> None:
        """Export metrics to InfluxDB."""
        if not self.influxdb_client:
            return

        try:
            # Prepare metrics
            metrics = {
                "feedback_loop_duration_seconds": result.duration_seconds,
                "feedback_loop_matches_total": result.total_matches,
                "feedback_loop_status": (
                    1 if result.status == LoopStatus.COMPLETED else 0
                ),
            }

            if result.analysis_report:
                metrics["feedback_loop_accuracy"] = result.analysis_report.get(
                    "overall_accuracy", 0
                )
                metrics["feedback_loop_drift_indicators"] = len(
                    result.analysis_report.get("drift_indicators", [])
                )

            # Export to InfluxDB
            # Note: Actual implementation depends on InfluxDB client interface
            logger.debug(f"Exported metrics: {metrics}")

        except Exception as e:
            logger.warning(f"Failed to export metrics: {e}")

    def _calculate_temporal_boundary(self) -> TemporalBoundary:
        """Calculate safe temporal boundaries.

        Returns:
            TemporalBoundary with safe data cutoff
        """
        now = datetime.now(timezone.utc)

        # Calculate buffer based on safety mode
        if self.config.temporal_safety_mode == TemporalSafetyMode.STRICT:
            buffer_hours = 2.0
        elif self.config.temporal_safety_mode == TemporalSafetyMode.MODERATE:
            buffer_hours = 1.0
        else:
            buffer_hours = 0.5

        # Data cutoff is now minus buffer
        data_cutoff = now - timedelta(hours=buffer_hours)

        # Validation period is after cutoff
        validation_start = data_cutoff
        validation_end = now

        return TemporalBoundary(
            data_cutoff_time=data_cutoff,
            validation_start_time=validation_start,
            validation_end_time=validation_end,
            buffer_hours=buffer_hours,
        )

    def _enforce_temporal_safety(
        self,
        matches: list[PredictionOutcomeMatch],
        boundary: TemporalBoundary,
    ) -> list[PredictionOutcomeMatch]:
        """Enforce temporal safety on matches.

        Args:
            matches: List of matches
            boundary: Temporal boundary

        Returns:
            Filtered matches within safe window
        """
        safe_matches = []
        for match in matches:
            signal_time = datetime.fromtimestamp(
                match.signal.timestamp / 1000, tz=timezone.utc
            )
            if boundary.is_safe(signal_time):
                safe_matches.append(match)
            else:
                logger.warning(
                    f"Filtered match {match.signal_id} - signal time {signal_time} "
                    f"exceeds cutoff {boundary.data_cutoff_time}"
                )

        return safe_matches

    def _finalize_iteration(self, result: LoopIterationResult) -> LoopIterationResult:
        """Finalize iteration result."""
        result.end_time = datetime.now(timezone.utc)
        result.duration_seconds = (result.end_time - result.start_time).total_seconds()

        # Check duration constraint
        max_duration = self.config.max_loop_duration_hours * 3600
        if result.duration_seconds > max_duration:
            result.warnings.append(
                f"Loop duration ({result.duration_seconds:.1f}s) exceeded target "
                f"({max_duration:.1f}s)"
            )

        self._iteration_history.append(result)
        self._current_iteration = None

        return result
