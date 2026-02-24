"""ML Optimization Scheduler for Auto-tuning.

This module provides automated scheduling for strategy optimization:
- Scheduled optimization jobs run reliably without manual trigger
- Configurable per-strategy schedules (daily/weekly/monthly)
- Adapts frequency to market volatility regime
- Persists optimization results with timestamps and parameter deltas
- Supports pause/resume without data loss
- Visible and editable via CLI and dashboard

Usage:
    from ml.scheduler import OptimizationScheduler, ScheduleConfig

    config = ScheduleConfig(frequency="weekly")
    scheduler = OptimizationScheduler(config)
    await scheduler.start()
    await scheduler.schedule_strategy(strategy_id, optimization_task)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ScheduleFrequency(Enum):
    """Optimization schedule frequencies."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    VOLATILITY_ADAPTIVE = "volatility_adaptive"
    MANUAL = "manual"


class JobStatus(Enum):
    """Status of a scheduled optimization job."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class VolatilityRegime(Enum):
    """Market volatility regimes for adaptive scheduling."""

    LOW = "low"  # < 1% daily volatility
    NORMAL = "normal"  # 1-3% daily volatility
    HIGH = "high"  # 3-5% daily volatility
    EXTREME = "extreme"  # > 5% daily volatility


@dataclass
class ScheduleConfig:
    """Configuration for optimization scheduling.

    Attributes:
        frequency: Base schedule frequency
        day_of_week: Day of week for weekly (0=Monday, 6=Sunday)
        day_of_month: Day of month for monthly (1-31)
        hour: Hour to run (0-23, default: 2 for 2 AM)
        minute: Minute to run (0-59, default: 0)
        timezone: Timezone for scheduling (default: UTC)
        adaptive_enabled: Whether to adapt to volatility
        high_volatility_boost: Increase frequency in high vol (default: True)
        low_volatility_skip: Decrease frequency in low vol (default: False)
        max_concurrent_jobs: Maximum concurrent optimizations (default: 3)
        job_timeout_hours: Timeout for individual jobs (default: 24)
        persistence_path: Path to store schedule state
    """

    frequency: ScheduleFrequency = ScheduleFrequency.WEEKLY
    day_of_week: int = 0  # Monday
    day_of_month: int = 1
    hour: int = 2  # 2 AM
    minute: int = 0
    timezone: str = "UTC"
    adaptive_enabled: bool = True
    high_volatility_boost: bool = True
    low_volatility_skip: bool = False
    max_concurrent_jobs: int = 3
    job_timeout_hours: float = 24.0
    persistence_path: str = "data/optimization_schedule.json"

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 <= self.day_of_week <= 6:
            raise ValueError("day_of_week must be 0-6")
        if not 1 <= self.day_of_month <= 31:
            raise ValueError("day_of_month must be 1-31")
        if not 0 <= self.hour <= 23:
            raise ValueError("hour must be 0-23")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be 0-59")


@dataclass
class ParameterDelta:
    """Change in parameter value between optimizations.

    Attributes:
        parameter_name: Name of the parameter
        old_value: Previous value
        new_value: New value
        absolute_change: Absolute difference
        percent_change: Percentage change
        significant: Whether change exceeds threshold
    """

    parameter_name: str
    old_value: Any
    new_value: Any
    absolute_change: float = 0.0
    percent_change: float = 0.0
    significant: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "parameter_name": self.parameter_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "absolute_change": self.absolute_change,
            "percent_change": self.percent_change,
            "significant": self.significant,
        }


@dataclass
class OptimizationRecord:
    """Record of a single optimization run.

    Attributes:
        record_id: Unique record identifier
        strategy_id: Strategy identifier
        job_id: Reference to scheduled job
        status: Job status
        started_at: Start timestamp
        completed_at: Completion timestamp
        previous_parameters: Parameters before optimization
        new_parameters: Parameters after optimization
        parameter_deltas: Changes in parameters
        previous_score: Score before optimization
        new_score: Score after optimization
        improvement_pct: Percentage improvement
        volatility_regime: Market regime during optimization
        error_message: Error details if failed
    """

    record_id: str
    strategy_id: str
    job_id: str
    status: JobStatus = JobStatus.SCHEDULED
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    previous_parameters: dict[str, Any] = field(default_factory=dict)
    new_parameters: dict[str, Any] = field(default_factory=dict)
    parameter_deltas: list[ParameterDelta] = field(default_factory=list)
    previous_score: float = 0.0
    new_score: float = 0.0
    improvement_pct: float = 0.0
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "strategy_id": self.strategy_id,
            "job_id": self.job_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "previous_parameters": self.previous_parameters,
            "new_parameters": self.new_parameters,
            "parameter_deltas": [d.to_dict() for d in self.parameter_deltas],
            "previous_score": self.previous_score,
            "new_score": self.new_score,
            "improvement_pct": self.improvement_pct,
            "volatility_regime": self.volatility_regime.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimizationRecord:
        """Create from dictionary."""
        record = cls(
            record_id=data["record_id"],
            strategy_id=data["strategy_id"],
            job_id=data["job_id"],
            status=JobStatus(data.get("status", "scheduled")),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            previous_parameters=data.get("previous_parameters", {}),
            new_parameters=data.get("new_parameters", {}),
            previous_score=data.get("previous_score", 0.0),
            new_score=data.get("new_score", 0.0),
            improvement_pct=data.get("improvement_pct", 0.0),
            volatility_regime=VolatilityRegime(data.get("volatility_regime", "normal")),
            error_message=data.get("error_message"),
        )

        # Parse parameter deltas
        record.parameter_deltas = [
            ParameterDelta(**d) for d in data.get("parameter_deltas", [])
        ]

        return record


@dataclass
class ScheduledJob:
    """A scheduled optimization job.

    Attributes:
        job_id: Unique job identifier
        strategy_id: Strategy identifier
        status: Current job status
        config: Schedule configuration
        next_run_at: Next scheduled run time
        last_run_at: Last run timestamp
        last_record_id: Reference to last optimization record
        run_count: Total number of runs
        success_count: Number of successful runs
        failure_count: Number of failed runs
        created_at: Creation timestamp
        paused_at: When job was paused (if paused)
    """

    job_id: str
    strategy_id: str
    status: JobStatus = JobStatus.SCHEDULED
    config: ScheduleConfig = field(default_factory=ScheduleConfig)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_record_id: str | None = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    paused_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "config": {
                "frequency": self.config.frequency.value,
                "day_of_week": self.config.day_of_week,
                "day_of_month": self.config.day_of_month,
                "hour": self.config.hour,
                "minute": self.config.minute,
                "timezone": self.config.timezone,
                "adaptive_enabled": self.config.adaptive_enabled,
            },
            "next_run_at": (self.next_run_at.isoformat() if self.next_run_at else None),
            "last_run_at": (self.last_run_at.isoformat() if self.last_run_at else None),
            "last_record_id": self.last_record_id,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_at": self.created_at.isoformat(),
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledJob:
        """Create from dictionary."""
        config_data = data.get("config", {})
        config = ScheduleConfig(
            frequency=ScheduleFrequency(config_data.get("frequency", "weekly")),
            day_of_week=config_data.get("day_of_week", 0),
            day_of_month=config_data.get("day_of_month", 1),
            hour=config_data.get("hour", 2),
            minute=config_data.get("minute", 0),
            timezone=config_data.get("timezone", "UTC"),
            adaptive_enabled=config_data.get("adaptive_enabled", True),
        )

        return cls(
            job_id=data["job_id"],
            strategy_id=data["strategy_id"],
            status=JobStatus(data.get("status", "scheduled")),
            config=config,
            next_run_at=(
                datetime.fromisoformat(data["next_run_at"])
                if data.get("next_run_at")
                else None
            ),
            last_run_at=(
                datetime.fromisoformat(data["last_run_at"])
                if data.get("last_run_at")
                else None
            ),
            last_record_id=data.get("last_record_id"),
            run_count=data.get("run_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.utcnow().isoformat())
            ),
            paused_at=(
                datetime.fromisoformat(data["paused_at"])
                if data.get("paused_at")
                else None
            ),
        )


class OptimizationTask(Protocol):
    """Protocol for optimization tasks."""

    async def __call__(
        self,
        strategy_id: str,
        previous_params: dict[str, Any],
    ) -> tuple[dict[str, Any], float, dict[str, float]]:
        """Execute optimization task.

        Args:
            strategy_id: Strategy identifier
            previous_params: Previous parameter values

        Returns:
            Tuple of (new_params, score, metrics)
        """
        ...


class VolatilityMonitor:
    """Monitor market volatility for adaptive scheduling."""

    def __init__(self) -> None:
        """Initialize volatility monitor."""
        self._current_regime = VolatilityRegime.NORMAL
        self._last_update: datetime | None = None

    async def get_current_regime(self) -> VolatilityRegime:
        """Get current volatility regime.

        Returns:
            Current volatility regime
        """
        # In a real implementation, this would query market data
        # For now, return cached or default value
        return self._current_regime

    def update_regime(self, regime: VolatilityRegime) -> None:
        """Update current volatility regime.

        Args:
            regime: New volatility regime
        """
        self._current_regime = regime
        self._last_update = datetime.utcnow()
        logger.info(f"Volatility regime updated to {regime.value}")

    def should_run_optimization(
        self,
        base_frequency: ScheduleFrequency,
        config: ScheduleConfig,
    ) -> bool:
        """Determine if optimization should run based on volatility.

        Args:
            base_frequency: Base schedule frequency
            config: Schedule configuration

        Returns:
            True if optimization should run
        """
        if not config.adaptive_enabled:
            return True

        if self._current_regime == VolatilityRegime.HIGH:
            return config.high_volatility_boost or True
        elif self._current_regime == VolatilityRegime.EXTREME:
            # Always run in extreme volatility
            return True
        elif self._current_regime == VolatilityRegime.LOW:
            return not config.low_volatility_skip

        return True


class OptimizationScheduler:
    """Scheduler for automated strategy optimization.

    This class manages scheduled optimization jobs with:
    - Configurable frequencies (daily/weekly/monthly/adaptive)
    - Volatility regime adaptation
    - Persistent state management
    - Pause/resume functionality

    Usage:
        scheduler = OptimizationScheduler()
        await scheduler.start()

        # Schedule a strategy
        job = await scheduler.schedule_strategy(
            strategy_id="my_strategy",
            config=ScheduleConfig(frequency="weekly"),
            optimization_task=my_optimization_task,
        )

        # Pause/resume
        await scheduler.pause_job(job.job_id)
        await scheduler.resume_job(job.job_id)
    """

    def __init__(
        self,
        config: ScheduleConfig | None = None,
        volatility_monitor: VolatilityMonitor | None = None,
    ):
        """Initialize scheduler.

        Args:
            config: Default schedule configuration
            volatility_monitor: Volatility monitor for adaptive scheduling
        """
        self.config = config or ScheduleConfig()
        self.volatility_monitor = volatility_monitor or VolatilityMonitor()

        self._jobs: dict[str, ScheduledJob] = {}
        self._records: dict[str, OptimizationRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._optimization_functions: dict[str, OptimizationTask] = {}

        self._running = False
        self._stop_event = asyncio.Event()
        self._scheduler_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Load persisted state
        self._load_state()

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._stop_event.clear()

        logger.info("Starting optimization scheduler")

        # Start main scheduler loop
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._running:
            return

        logger.info("Stopping optimization scheduler")
        self._running = False
        self._stop_event.set()

        # Cancel all running tasks
        for task in self._tasks.values():
            task.cancel()

        if self._scheduler_task:
            self._scheduler_task.cancel()

        # Wait for cleanup
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        # Save state
        self._save_state()

        logger.info("Optimization scheduler stopped")

    async def schedule_strategy(
        self,
        strategy_id: str,
        optimization_task: OptimizationTask | Callable,
        config: ScheduleConfig | None = None,
    ) -> ScheduledJob:
        """Schedule optimization for a strategy.

        Args:
            strategy_id: Strategy identifier
            optimization_task: Function to execute for optimization
            config: Schedule configuration (uses default if not provided)

        Returns:
            Scheduled job
        """
        async with self._lock:
            job_id = f"job_{strategy_id}_{datetime.utcnow().timestamp()}"
            job_config = config or self.config

            # Calculate next run time
            next_run = self._calculate_next_run(job_config)

            job = ScheduledJob(
                job_id=job_id,
                strategy_id=strategy_id,
                config=job_config,
                next_run_at=next_run,
            )

            self._jobs[job_id] = job
            self._optimization_functions[job_id] = optimization_task

            logger.info(
                f"Scheduled optimization for {strategy_id}: "
                f"next_run={next_run}, frequency={job_config.frequency.value}"
            )

            self._save_state()
            return job

    async def unschedule_strategy(self, job_id: str) -> bool:
        """Remove a scheduled optimization job.

        Args:
            job_id: Job identifier

        Returns:
            True if job was removed
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False

            # Cancel running task if any
            if job_id in self._tasks:
                self._tasks[job_id].cancel()
                del self._tasks[job_id]

            del self._jobs[job_id]
            if job_id in self._optimization_functions:
                del self._optimization_functions[job_id]

            logger.info(f"Unscheduled optimization job {job_id}")
            self._save_state()
            return True

    async def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job.

        Args:
            job_id: Job identifier

        Returns:
            True if job was paused
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False

            job = self._jobs[job_id]
            if job.status == JobStatus.RUNNING:
                logger.warning(f"Cannot pause running job {job_id}")
                return False

            job.status = JobStatus.PAUSED
            job.paused_at = datetime.utcnow()

            logger.info(f"Paused optimization job {job_id}")
            self._save_state()
            return True

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.

        Args:
            job_id: Job identifier

        Returns:
            True if job was resumed
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False

            job = self._jobs[job_id]
            if job.status != JobStatus.PAUSED:
                return False

            job.status = JobStatus.SCHEDULED
            job.paused_at = None

            # Recalculate next run
            job.next_run_at = self._calculate_next_run(job.config)

            logger.info(f"Resumed optimization job {job_id}")
            self._save_state()
            return True

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Get a scheduled job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Scheduled job or None
        """
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[ScheduledJob]:
        """Get all scheduled jobs.

        Returns:
            List of scheduled jobs
        """
        return list(self._jobs.values())

    def get_records(
        self,
        strategy_id: str | None = None,
        limit: int = 100,
    ) -> list[OptimizationRecord]:
        """Get optimization records.

        Args:
            strategy_id: Optional filter by strategy
            limit: Maximum number of records

        Returns:
            List of optimization records
        """
        records = list(self._records.values())

        if strategy_id:
            records = [r for r in records if r.strategy_id == strategy_id]

        # Sort by started_at descending
        records.sort(key=lambda r: r.started_at, reverse=True)

        return records[:limit]

    async def run_job_now(self, job_id: str) -> OptimizationRecord | None:
        """Manually trigger a job to run immediately.

        Args:
            job_id: Job identifier

        Returns:
            Optimization record or None
        """
        async with self._lock:
            if job_id not in self._jobs:
                return None

            job = self._jobs[job_id]
            task = self._optimization_functions.get(job_id)

            if not task:
                return None

            return await self._execute_job(job, task)

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running and not self._stop_event.is_set():
            try:
                await self._check_and_run_jobs()

                # Wait before next check
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=60.0,  # Check every minute
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(5.0)

    async def _check_and_run_jobs(self) -> None:
        """Check for jobs that need to run and execute them."""
        now = datetime.utcnow()

        async with self._lock:
            for job_id, job in self._jobs.items():
                # Skip non-scheduled jobs
                if job.status not in (JobStatus.SCHEDULED,):
                    continue

                # Skip if already running
                if job_id in self._tasks and not self._tasks[job_id].done():
                    continue

                # Check if it's time to run
                if job.next_run_at and now >= job.next_run_at:
                    # Check volatility adaptation
                    if not self.volatility_monitor.should_run_optimization(
                        job.config.frequency, job.config
                    ):
                        # Skip this run and reschedule
                        job.next_run_at = self._calculate_next_run(job.config)
                        continue

                    # Get optimization task
                    task = self._optimization_functions.get(job_id)
                    if task:
                        # Start job in background
                        self._tasks[job_id] = asyncio.create_task(
                            self._execute_job(job, task)
                        )

    async def _execute_job(
        self,
        job: ScheduledJob,
        task: OptimizationTask | Callable,
    ) -> OptimizationRecord:
        """Execute an optimization job.

        Args:
            job: Scheduled job
            task: Optimization task

        Returns:
            Optimization record
        """
        record_id = f"record_{job.job_id}_{datetime.utcnow().timestamp()}"

        # Get previous parameters if available
        previous_params = {}
        previous_score = 0.0
        if job.last_record_id and job.last_record_id in self._records:
            last_record = self._records[job.last_record_id]
            previous_params = last_record.new_parameters
            previous_score = last_record.new_score

        # Get current volatility regime
        volatility_regime = await self.volatility_monitor.get_current_regime()

        record = OptimizationRecord(
            record_id=record_id,
            strategy_id=job.strategy_id,
            job_id=job.job_id,
            status=JobStatus.RUNNING,
            previous_parameters=previous_params,
            previous_score=previous_score,
            volatility_regime=volatility_regime,
        )

        self._records[record_id] = record
        job.status = JobStatus.RUNNING
        job.last_run_at = datetime.utcnow()
        job.run_count += 1

        logger.info(f"Starting optimization job {job.job_id} for {job.strategy_id}")

        try:
            # Execute with timeout
            if asyncio.iscoroutinefunction(task):
                new_params, score, metrics = await asyncio.wait_for(
                    task(job.strategy_id, previous_params),
                    timeout=job.config.job_timeout_hours * 3600,
                )
            else:
                (
                    new_params,
                    score,
                    metrics,
                ) = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: task(job.strategy_id, previous_params)
                )

            # Update record
            record.status = JobStatus.COMPLETED
            record.new_parameters = new_params
            record.new_score = score
            record.completed_at = datetime.utcnow()

            # Calculate improvement
            if previous_score != 0:
                record.improvement_pct = (
                    (score - previous_score) / abs(previous_score) * 100
                )
            else:
                record.improvement_pct = 100.0 if score > 0 else 0.0

            # Calculate parameter deltas
            record.parameter_deltas = self._calculate_deltas(
                previous_params, new_params
            )

            job.success_count += 1

            logger.info(
                f"Optimization job {job.job_id} completed: "
                f"score={score:.4f}, improvement={record.improvement_pct:.1f}%"
            )

        except TimeoutError:
            record.status = JobStatus.FAILED
            record.error_message = f"Timeout after {job.config.job_timeout_hours} hours"
            job.failure_count += 1
            logger.error(f"Optimization job {job.job_id} timed out")

        except Exception as e:
            record.status = JobStatus.FAILED
            record.error_message = str(e)
            job.failure_count += 1
            logger.error(f"Optimization job {job.job_id} failed: {e}")

        # Update job status and schedule next run
        job.status = (
            JobStatus.SCHEDULED if job.status != JobStatus.PAUSED else JobStatus.PAUSED
        )
        job.next_run_at = self._calculate_next_run(job.config)
        job.last_record_id = record_id

        self._save_state()
        return record

    def _calculate_next_run(self, config: ScheduleConfig) -> datetime:
        """Calculate next run time based on schedule configuration.

        Args:
            config: Schedule configuration

        Returns:
            Next run datetime
        """
        now = datetime.utcnow()

        if config.frequency == ScheduleFrequency.DAILY:
            next_run = now.replace(
                hour=config.hour, minute=config.minute, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

        elif config.frequency == ScheduleFrequency.WEEKLY:
            days_ahead = config.day_of_week - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(
                hour=config.hour, minute=config.minute, second=0, microsecond=0
            )

        elif config.frequency == ScheduleFrequency.MONTHLY:
            if now.day < config.day_of_month:
                next_run = now.replace(day=config.day_of_month)
            else:
                # Next month
                if now.month == 12:
                    next_run = now.replace(
                        year=now.year + 1, month=1, day=config.day_of_month
                    )
                else:
                    next_run = now.replace(month=now.month + 1, day=config.day_of_month)
            next_run = next_run.replace(
                hour=config.hour, minute=config.minute, second=0, microsecond=0
            )

        elif config.frequency == ScheduleFrequency.VOLATILITY_ADAPTIVE:
            # Run daily but actual execution depends on volatility
            next_run = now.replace(
                hour=config.hour, minute=config.minute, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

        else:  # MANUAL
            # Set far in the future
            next_run = now + timedelta(days=365)

        return next_run

    def _calculate_deltas(
        self,
        old_params: dict[str, Any],
        new_params: dict[str, Any],
    ) -> list[ParameterDelta]:
        """Calculate parameter changes.

        Args:
            old_params: Previous parameters
            new_params: New parameters

        Returns:
            List of parameter deltas
        """
        deltas = []
        all_keys = set(old_params.keys()) | set(new_params.keys())

        for key in all_keys:
            old_val = old_params.get(key)
            new_val = new_params.get(key)

            if old_val != new_val:
                delta = ParameterDelta(
                    parameter_name=key,
                    old_value=old_val,
                    new_value=new_val,
                )

                # Calculate numeric changes if possible
                if isinstance(old_val, (int, float)) and isinstance(
                    new_val, (int, float)
                ):
                    delta.absolute_change = new_val - old_val
                    if old_val != 0:
                        delta.percent_change = (new_val - old_val) / abs(old_val) * 100
                    delta.significant = abs(delta.percent_change) > 10  # 10% threshold

                deltas.append(delta)

        return deltas

    def _save_state(self) -> None:
        """Persist scheduler state to disk."""
        try:
            state = {
                "jobs": {k: v.to_dict() for k, v in self._jobs.items()},
                "records": {k: v.to_dict() for k, v in self._records.items()},
                "saved_at": datetime.utcnow().isoformat(),
            }

            path = Path(self.config.persistence_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w") as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    def _load_state(self) -> None:
        """Load scheduler state from disk."""
        try:
            path = Path(self.config.persistence_path)
            if not path.exists():
                return

            with open(path) as f:
                state = json.load(f)

            # Load jobs
            for job_id, job_data in state.get("jobs", {}).items():
                self._jobs[job_id] = ScheduledJob.from_dict(job_data)

            # Load records
            for record_id, record_data in state.get("records", {}).items():
                self._records[record_id] = OptimizationRecord.from_dict(record_data)

            logger.info(
                f"Loaded scheduler state: {len(self._jobs)} jobs, "
                f"{len(self._records)} records"
            )

        except Exception as e:
            logger.error(f"Failed to load scheduler state: {e}")

    def get_schedule_summary(self) -> dict[str, Any]:
        """Get summary of scheduled jobs for CLI/dashboard.

        Returns:
            Dictionary with schedule summary
        """
        now = datetime.utcnow()

        return {
            "scheduler_running": self._running,
            "total_jobs": len(self._jobs),
            "jobs_by_status": {
                status.value: len(
                    [j for j in self._jobs.values() if j.status == status]
                )
                for status in JobStatus
            },
            "upcoming_runs": [
                {
                    "job_id": j.job_id,
                    "strategy_id": j.strategy_id,
                    "next_run": j.next_run_at.isoformat() if j.next_run_at else None,
                    "time_until": (
                        (j.next_run_at - now).total_seconds() // 60
                        if j.next_run_at and j.next_run_at > now
                        else None
                    ),
                }
                for j in sorted(
                    self._jobs.values(),
                    key=lambda x: x.next_run_at or datetime.max,
                )[:10]
            ],
            "recent_records": [
                {
                    "record_id": r.record_id,
                    "strategy_id": r.strategy_id,
                    "status": r.status.value,
                    "improvement_pct": r.improvement_pct,
                    "started_at": r.started_at.isoformat(),
                }
                for r in sorted(
                    self._records.values(),
                    key=lambda x: x.started_at,
                    reverse=True,
                )[:10]
            ],
        }
