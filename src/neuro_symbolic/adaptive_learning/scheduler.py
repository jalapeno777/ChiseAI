"""Learning Scheduler for adaptive learning.

Schedules retraining based on performance degradation and manages
trigger conditions for model updates.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from src.neuro_symbolic.learning.base import (
    AdaptationResult,
    LearningConfig,
    PerformanceMetrics,
    TriggerCondition,
)


class ScheduleStatus(Enum):
    """Status of a scheduled task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """A scheduled learning task."""

    task_id: str
    trigger: TriggerCondition
    scheduled_time: datetime
    status: ScheduleStatus = ScheduleStatus.PENDING
    priority: int = 0  # Higher = more important
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: AdaptationResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "trigger": self.trigger.value,
            "scheduled_time": self.scheduled_time.isoformat(),
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "result": self.result.to_dict() if self.result else None,
            "metadata": self.metadata,
        }


@dataclass
class TriggerRule:
    """Rule for triggering model updates."""

    name: str
    condition: TriggerCondition
    threshold: float
    enabled: bool = True
    cooldown_minutes: int = 60
    last_triggered: datetime | None = None
    priority: int = 0

    def should_trigger(
        self,
        current_value: float,
        reference_value: float,
    ) -> bool:
        """Check if rule should trigger.

        Args:
            current_value: Current metric value
            reference_value: Reference/baseline value

        Returns:
            True if rule should trigger
        """
        if not self.enabled:
            return False

        # Check cooldown
        if self.last_triggered:
            cooldown_end = self.last_triggered + timedelta(
                minutes=self.cooldown_minutes
            )
            if datetime.now() < cooldown_end:
                return False

        # Check condition
        if self.condition == TriggerCondition.PERFORMANCE_DEGRADATION:
            degradation = reference_value - current_value
            return degradation > self.threshold
        elif self.condition == TriggerCondition.THRESHOLD_BREACH:
            return current_value < self.threshold
        elif self.condition == TriggerCondition.DATA_DRIFT:
            return abs(current_value - reference_value) > self.threshold

        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "enabled": self.enabled,
            "cooldown_minutes": self.cooldown_minutes,
            "last_triggered": (
                self.last_triggered.isoformat() if self.last_triggered else None
            ),
            "priority": self.priority,
        }


@dataclass
class SchedulerStats:
    """Statistics for the scheduler."""

    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    last_run: datetime | None = None
    next_scheduled: datetime | None = None
    avg_task_duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "cancelled_tasks": self.cancelled_tasks,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_scheduled": (
                self.next_scheduled.isoformat() if self.next_scheduled else None
            ),
            "avg_task_duration": self.avg_task_duration,
        }


@dataclass
class SchedulerConfig:
    """Configuration for LearningScheduler."""

    default_interval_hours: int = 24
    max_concurrent_tasks: int = 1
    task_timeout_minutes: int = 60
    retry_on_failure: bool = True
    max_retries: int = 3
    enable_auto_scheduling: bool = True
    degradation_window: int = 100  # Number of samples to check
    min_improvement_for_update: float = 0.01
    emergency_threshold: float = 0.3  # Severe degradation


class LearningScheduler:
    """Schedules and manages learning tasks.

    Monitors performance, triggers updates based on conditions,
    and manages task execution.
    """

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        learning_config: LearningConfig | None = None,
    ):
        """Initialize the scheduler.

        Args:
            config: Scheduler configuration
            learning_config: Learning system configuration
        """
        self.config = config or SchedulerConfig()
        self.learning_config = learning_config or LearningConfig()
        self._task_queue: list[ScheduledTask] = []
        self._completed_tasks: list[ScheduledTask] = []
        self._trigger_rules: dict[str, TriggerRule] = {}
        self._performance_history: list[PerformanceMetrics] = []
        self._baseline_metrics: PerformanceMetrics | None = None
        self._stats = SchedulerStats()
        self._adaptation_callback: Callable | None = None
        self._last_adaptation_time: datetime | None = None
        self._daily_adaptation_count: int = 0
        self._last_day_reset: datetime = datetime.now()

        # Initialize default trigger rules
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default trigger rules."""
        default_rules = [
            TriggerRule(
                name="performance_degradation",
                condition=TriggerCondition.PERFORMANCE_DEGRADATION,
                threshold=self.learning_config.degradation_threshold,
                cooldown_minutes=60,
            ),
            TriggerRule(
                name="severe_degradation",
                condition=TriggerCondition.PERFORMANCE_DEGRADATION,
                threshold=self.config.emergency_threshold,
                cooldown_minutes=30,
                priority=10,
            ),
            TriggerRule(
                name="scheduled_maintenance",
                condition=TriggerCondition.SCHEDULED,
                threshold=0.0,
                cooldown_minutes=1440,  # 24 hours
            ),
        ]

        for rule in default_rules:
            self._trigger_rules[rule.name] = rule

    def set_adaptation_callback(self, callback: Callable) -> None:
        """Set callback function to execute adaptations.

        Args:
            callback: Function to call when adaptation is triggered
        """
        self._adaptation_callback = callback

    def add_trigger_rule(self, rule: TriggerRule) -> None:
        """Add a new trigger rule.

        Args:
            rule: TriggerRule to add
        """
        self._trigger_rules[rule.name] = rule

    def remove_trigger_rule(self, rule_name: str) -> bool:
        """Remove a trigger rule.

        Args:
            rule_name: Name of rule to remove

        Returns:
            True if rule was removed
        """
        if rule_name in self._trigger_rules:
            del self._trigger_rules[rule_name]
            return True
        return False

    def record_performance(self, metrics: PerformanceMetrics) -> list[TriggerCondition]:
        """Record performance metrics and check for triggers.

        Args:
            metrics: Current performance metrics

        Returns:
            List of triggered conditions
        """
        self._performance_history.append(metrics)

        # Trim history if needed
        if len(self._performance_history) > self.config.degradation_window:
            self._performance_history = self._performance_history[
                -self.config.degradation_window :
            ]

        # Set baseline if not set
        if self._baseline_metrics is None:
            self._baseline_metrics = metrics
            return []

        # Check triggers
        triggered = []
        for rule in self._trigger_rules.values():
            if rule.should_trigger(
                current_value=metrics.accuracy,
                reference_value=self._baseline_metrics.accuracy,
            ):
                triggered.append(rule.condition)
                rule.last_triggered = datetime.now()

                # Schedule task
                self.schedule_task(
                    trigger=rule.condition,
                    priority=getattr(rule, "priority", 0),
                )

        return triggered

    def schedule_task(
        self,
        trigger: TriggerCondition,
        scheduled_time: datetime | None = None,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        """Schedule a new learning task.

        Args:
            trigger: What triggers this task
            scheduled_time: When to run (defaults to now)
            priority: Task priority (higher = more important)
            metadata: Additional task metadata

        Returns:
            Created ScheduledTask
        """
        scheduled_time = scheduled_time or datetime.now()
        task_id = (
            f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._task_queue)}"
        )

        task = ScheduledTask(
            task_id=task_id,
            trigger=trigger,
            scheduled_time=scheduled_time,
            priority=priority,
            metadata=metadata or {},
        )

        # Insert in priority order
        inserted = False
        for i, existing in enumerate(self._task_queue):
            if task.priority > existing.priority:
                self._task_queue.insert(i, task)
                inserted = True
                break

        if not inserted:
            self._task_queue.append(task)

        self._stats.total_tasks += 1
        self._stats.next_scheduled = (
            self._task_queue[0].scheduled_time if self._task_queue else None
        )

        return task

    def get_next_task(self) -> ScheduledTask | None:
        """Get the next task to execute.

        Returns:
            Next ScheduledTask or None if queue empty
        """
        if not self._task_queue:
            return None

        # Check if task is scheduled for now
        task = self._task_queue[0]
        if task.scheduled_time > datetime.now():
            return None

        return self._task_queue.pop(0)

    def execute_next_task(self) -> AdaptationResult | None:
        """Execute the next scheduled task.

        Returns:
            AdaptationResult if task was executed, None otherwise
        """
        task = self.get_next_task()
        if task is None:
            return None

        # Check daily limit
        self._check_daily_reset()
        if self._daily_adaptation_count >= self.learning_config.max_adaptations_per_day:
            task.status = ScheduleStatus.CANCELLED
            task.metadata["cancel_reason"] = "daily_limit_reached"
            self._completed_tasks.append(task)
            self._stats.cancelled_tasks += 1
            return None

        # Check cooldown
        if self._last_adaptation_time:
            cooldown_end = self._last_adaptation_time + timedelta(
                seconds=self.learning_config.adaptation_cooldown
            )
            if datetime.now() < cooldown_end:
                task.status = ScheduleStatus.CANCELLED
                task.metadata["cancel_reason"] = "cooldown_active"
                self._completed_tasks.append(task)
                self._stats.cancelled_tasks += 1
                return None

        # Execute task
        task.status = ScheduleStatus.RUNNING
        task.started_at = datetime.now()

        try:
            if self._adaptation_callback:
                result = self._adaptation_callback(task.trigger, task.metadata)
                task.result = result
                task.status = ScheduleStatus.COMPLETED
                self._stats.completed_tasks += 1
                self._daily_adaptation_count += 1
                self._last_adaptation_time = datetime.now()
            else:
                # No callback - create synthetic result
                result = AdaptationResult(
                    status="skipped",
                    trigger=task.trigger,
                    error_message="No adaptation callback registered",
                )
                task.result = result
                task.status = ScheduleStatus.COMPLETED

        except Exception as e:
            result = AdaptationResult(
                status="failed",
                trigger=task.trigger,
                error_message=str(e),
            )
            task.result = result
            task.status = ScheduleStatus.FAILED
            self._stats.failed_tasks += 1

            # Retry if configured
            if (
                self.config.retry_on_failure
                and task.metadata.get("retry_count", 0) < self.config.max_retries
            ):
                task.metadata["retry_count"] = task.metadata.get("retry_count", 0) + 1
                task.status = ScheduleStatus.PENDING
                task.scheduled_time = datetime.now() + timedelta(minutes=5)
                self._task_queue.append(task)

        task.completed_at = datetime.now()
        self._completed_tasks.append(task)
        self._stats.last_run = task.completed_at

        # Update average duration
        if task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds()
            n = self._stats.completed_tasks
            self._stats.avg_task_duration = (
                self._stats.avg_task_duration * (n - 1) + duration
            ) / n

        return task.result

    def _check_daily_reset(self) -> None:
        """Check and reset daily counters if needed."""
        now = datetime.now()
        if now.date() > self._last_day_reset.date():
            self._daily_adaptation_count = 0
            self._last_day_reset = now

    def schedule_recurring(
        self,
        interval_hours: int,
        trigger: TriggerCondition = TriggerCondition.SCHEDULED,
    ) -> ScheduledTask:
        """Schedule a recurring learning task.

        Args:
            interval_hours: Hours between runs
            trigger: Trigger condition for the task

        Returns:
            Created ScheduledTask
        """
        next_run = datetime.now() + timedelta(hours=interval_hours)
        return self.schedule_task(
            trigger=trigger,
            scheduled_time=next_run,
            metadata={"recurring": True, "interval_hours": interval_hours},
        )

    def check_performance_degradation(self) -> float | None:
        """Check if performance has degraded.

        Returns:
            Degradation amount if degraded, None otherwise
        """
        if (
            len(self._performance_history)
            < self.learning_config.min_samples_for_adaptation
        ):
            return None

        if self._baseline_metrics is None:
            return None

        recent = self._performance_history[-self.learning_config.performance_window :]
        recent_avg_accuracy = np.mean([m.accuracy for m in recent])

        degradation = self._baseline_metrics.accuracy - recent_avg_accuracy

        if degradation > self.learning_config.degradation_threshold:
            return degradation

        return None

    def should_update(self) -> tuple[bool, TriggerCondition | None, str]:
        """Determine if an update should be performed.

        Returns:
            Tuple of (should_update, trigger_condition, reason)
        """
        # Check performance degradation
        degradation = self.check_performance_degradation()
        if (
            degradation is not None
            and degradation > self.learning_config.degradation_threshold
        ):
            return (
                True,
                TriggerCondition.PERFORMANCE_DEGRADATION,
                f"Performance degraded by {degradation:.2%}",
            )

        # Check if scheduled
        if self._task_queue:
            next_task = self._task_queue[0]
            if next_task.scheduled_time <= datetime.now():
                return True, next_task.trigger, f"Scheduled task {next_task.task_id}"

        return False, None, "No update needed"

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Args:
            task_id: ID of task to cancel

        Returns:
            True if task was cancelled
        """
        for i, task in enumerate(self._task_queue):
            if task.task_id == task_id:
                task.status = ScheduleStatus.CANCELLED
                self._completed_tasks.append(self._task_queue.pop(i))
                self._stats.cancelled_tasks += 1
                return True
        return False

    def get_pending_tasks(self) -> list[ScheduledTask]:
        """Get all pending tasks."""
        return self._task_queue.copy()

    def get_completed_tasks(self, limit: int = 100) -> list[ScheduledTask]:
        """Get recent completed tasks.

        Args:
            limit: Maximum number to return

        Returns:
            List of completed tasks
        """
        return self._completed_tasks[-limit:]

    def set_baseline(self, metrics: PerformanceMetrics) -> None:
        """Set baseline performance metrics.

        Args:
            metrics: Baseline metrics to set
        """
        self._baseline_metrics = metrics

    def get_baseline(self) -> PerformanceMetrics | None:
        """Get current baseline metrics."""
        return self._baseline_metrics

    def get_performance_trend(self, window: int = 50) -> dict[str, Any]:
        """Analyze performance trend.

        Args:
            window: Number of recent metrics to analyze

        Returns:
            Trend analysis dictionary
        """
        if len(self._performance_history) < 2:
            return {"trend": "insufficient_data"}

        recent = self._performance_history[-window:]
        accuracies = [float(m.accuracy) for m in recent]

        # Compute trend
        x = np.arange(len(accuracies), dtype=float)
        try:
            slope, _ = np.polyfit(x, np.array(accuracies, dtype=float), 1)
            slope = float(slope)
        except (ValueError, TypeError):
            return {"trend": "error", "message": "Could not compute trend"}

        if slope > 0.001:
            trend = "improving"
        elif slope < -0.001:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "slope": float(slope),
            "current_accuracy": accuracies[-1],
            "avg_accuracy": float(np.mean(accuracies)),
            "min_accuracy": float(np.min(accuracies)),
            "max_accuracy": float(np.max(accuracies)),
            "volatility": float(np.std(accuracies)),
        }

    def get_stats(self) -> SchedulerStats:
        """Get scheduler statistics."""
        return self._stats

    def clear_history(self) -> None:
        """Clear completed task history."""
        self._completed_tasks.clear()
        self._performance_history.clear()

    def to_dict(self) -> dict[str, Any]:
        """Convert scheduler state to dictionary."""
        return {
            "config": {
                "default_interval_hours": self.config.default_interval_hours,
                "max_concurrent_tasks": self.config.max_concurrent_tasks,
                "task_timeout_minutes": self.config.task_timeout_minutes,
                "retry_on_failure": self.config.retry_on_failure,
                "max_retries": self.config.max_retries,
                "enable_auto_scheduling": self.config.enable_auto_scheduling,
            },
            "stats": self._stats.to_dict(),
            "pending_tasks": len(self._task_queue),
            "trigger_rules": {k: v.to_dict() for k, v in self._trigger_rules.items()},
            "baseline_metrics": (
                self._baseline_metrics.to_dict() if self._baseline_metrics else None
            ),
            "performance_history_count": len(self._performance_history),
        }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"LearningScheduler("
            f"pending={len(self._task_queue)}, "
            f"completed={self._stats.completed_tasks}, "
            f"rules={len(self._trigger_rules)})"
        )
