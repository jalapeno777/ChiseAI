"""
Throughput Measurement for Parallel Execution Optimizer (ST-GOV-010).

Measures and reports execution throughput metrics for optimization
validation and monitoring.

Story: ST-GOV-010
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from src.governance.parallel_optimizer.models import (
    ExecutionPlan,
    TaskBatch,
    ThroughputMetrics,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTiming:
    """Timing information for a single execution."""

    start_time: datetime
    end_time: datetime | None = None
    duration_seconds: float = 0.0


class ThroughputMeter:
    """
    Measures throughput metrics for parallel execution.

    Features:
    - Track execution timing
    - Calculate throughput improvement
    - Monitor conflict rates
    - Report on rollback frequency

    Usage:
        meter = ThroughputMeter()

        # Start measurement
        meter.start_execution(plan)

        # ... execute batches ...

        # End and report
        metrics = meter.end_execution(plan, completed_tasks)
        print(f"Throughput improvement: {metrics.throughput_improvement}%")
    """

    # Target improvement percentage
    TARGET_IMPROVEMENT = 30.0

    # Maximum acceptable conflict rate
    MAX_CONFLICT_RATE = 2.0

    def __init__(self):
        """Initialize the throughput meter."""
        self._execution_timing: ExecutionTiming | None = None
        self._batch_timings: dict[str, ExecutionTiming] = {}
        self._task_durations: dict[str, float] = {}

    def start_execution(self, plan: ExecutionPlan) -> None:
        """
        Start timing an execution.

        Args:
            plan: The execution plan being measured
        """
        self._execution_timing = ExecutionTiming(start_time=datetime.utcnow())
        self._batch_timings.clear()
        self._task_durations.clear()

        logger.debug(f"Started throughput measurement for plan {plan.plan_id}")

    def start_batch(self, batch: TaskBatch) -> None:
        """Start timing a batch execution."""
        self._batch_timings[batch.batch_id] = ExecutionTiming(
            start_time=datetime.utcnow()
        )

    def end_batch(self, batch: TaskBatch, success: bool = True) -> float:
        """
        End timing a batch execution.

        Args:
            batch: The batch that completed
            success: Whether the batch succeeded

        Returns:
            Duration in seconds
        """
        timing = self._batch_timings.get(batch.batch_id)
        if timing:
            timing.end_time = datetime.utcnow()
            timing.duration_seconds = (
                timing.end_time - timing.start_time
            ).total_seconds()

            # Track individual task durations
            if batch.tasks:
                avg_task_duration = timing.duration_seconds / len(batch.tasks)
                for task in batch.tasks:
                    self._task_durations[task.task_id] = avg_task_duration

            return timing.duration_seconds
        return 0.0

    def end_execution(
        self,
        plan: ExecutionPlan,
        completed_tasks: set[str],
        failed_tasks: set[str] | None = None,
        rollback_count: int = 0,
    ) -> ThroughputMetrics:
        """
        End execution timing and calculate metrics.

        Args:
            plan: The execution plan
            completed_tasks: Set of successfully completed task IDs
            failed_tasks: Set of failed task IDs
            rollback_count: Number of rollbacks performed

        Returns:
            ThroughputMetrics with all measurements
        """
        if not self._execution_timing:
            logger.warning("No execution timing started")
            return ThroughputMetrics()

        # End execution timing
        self._execution_timing.end_time = datetime.utcnow()
        parallel_duration = (
            self._execution_timing.end_time - self._execution_timing.start_time
        ).total_seconds()

        # Calculate sequential duration (sum of all task estimates)
        sequential_duration = self._calculate_sequential_duration(plan)

        # Calculate tasks per minute
        total_completed = len(completed_tasks)
        tasks_per_minute = (
            (total_completed / parallel_duration) * 60 if parallel_duration > 0 else 0
        )

        # Calculate conflict rate
        conflict_rate = self._calculate_conflict_rate(plan)

        metrics = ThroughputMetrics(
            sequential_duration=sequential_duration,
            parallel_duration=parallel_duration,
            tasks_per_minute=tasks_per_minute,
            conflict_rate=conflict_rate,
            rollback_count=rollback_count,
            total_tasks=plan.total_tasks,
            completed_tasks=total_completed,
            failed_tasks=len(failed_tasks) if failed_tasks else 0,
        )

        # Calculate improvement
        metrics.calculate_improvement()

        logger.info(
            f"Execution complete: {metrics.throughput_improvement:.1f}% "
            f"improvement ({sequential_duration:.1f}s -> {parallel_duration:.1f}s)"
        )

        return metrics

    def _calculate_sequential_duration(self, plan: ExecutionPlan) -> float:
        """Calculate how long execution would take sequentially."""
        total = 0.0
        for batch in plan.batches:
            for task in batch.tasks:
                total += task.estimated_duration_seconds
        return total

    def _calculate_conflict_rate(self, plan: ExecutionPlan) -> float:
        """Calculate the conflict rate as a percentage."""
        # Conflict count is stored in the plan
        total_tasks = plan.total_tasks
        if total_tasks < 2:
            return 0.0

        # Estimate conflict rate from plan's conflict_count
        # This is an approximation - actual conflicts may differ
        conflict_count = plan.conflict_count

        # Total possible pairs
        total_pairs = total_tasks * (total_tasks - 1) / 2

        if total_pairs == 0:
            return 0.0

        return (conflict_count / total_pairs) * 100

    def validate_metrics(self, metrics: ThroughputMetrics) -> tuple[bool, list[str]]:
        """
        Validate that metrics meet the acceptance criteria.

        Args:
            metrics: The metrics to validate

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Check throughput improvement
        if not metrics.meets_target(self.TARGET_IMPROVEMENT):
            issues.append(
                f"Throughput improvement {metrics.throughput_improvement:.1f}% "
                f"is below target {self.TARGET_IMPROVEMENT}%"
            )

        # Check conflict rate
        if metrics.conflict_rate > self.MAX_CONFLICT_RATE:
            issues.append(
                f"Conflict rate {metrics.conflict_rate:.1f}% "
                f"exceeds maximum {self.MAX_CONFLICT_RATE}%"
            )

        # Check for failures
        if metrics.failed_tasks > 0:
            issues.append(f"{metrics.failed_tasks} tasks failed during execution")

        return len(issues) == 0, issues

    def generate_report(self, metrics: ThroughputMetrics) -> str:
        """
        Generate a human-readable report of the metrics.

        Args:
            metrics: The metrics to report on

        Returns:
            Formatted report string
        """
        is_valid, issues = self.validate_metrics(metrics)

        report_lines = [
            "=== Throughput Metrics Report ===",
            "",
            f"Sequential Duration: {metrics.sequential_duration:.2f}s",
            f"Parallel Duration: {metrics.parallel_duration:.2f}s",
            f"Throughput Improvement: {metrics.throughput_improvement:.1f}%",
            f"Target Improvement: {self.TARGET_IMPROVEMENT}%",
            "",
            f"Total Tasks: {metrics.total_tasks}",
            f"Completed Tasks: {metrics.completed_tasks}",
            f"Failed Tasks: {metrics.failed_tasks}",
            f"Tasks per Minute: {metrics.tasks_per_minute:.2f}",
            "",
            f"Conflict Rate: {metrics.conflict_rate:.2f}%",
            f"Max Conflict Rate: {self.MAX_CONFLICT_RATE}%",
            f"Rollback Count: {metrics.rollback_count}",
            "",
            f"Status: {'PASS' if is_valid else 'FAIL'}",
        ]

        if issues:
            report_lines.extend(["", "Issues:"])
            report_lines.extend(f"  - {issue}" for issue in issues)

        return "\n".join(report_lines)


class ThroughputComparator:
    """
    Compares throughput between sequential and parallel execution.

    Used for validation and optimization testing.
    """

    @staticmethod
    def simulate_sequential(
        tasks_durations: list[float],
    ) -> float:
        """
        Simulate sequential execution time.

        Args:
            tasks_durations: List of task durations

        Returns:
            Total sequential execution time
        """
        return sum(tasks_durations)

    @staticmethod
    def simulate_parallel(
        batches: list[list[float]],
        max_parallel: int = 10,
    ) -> float:
        """
        Simulate parallel execution time.

        Args:
            batches: List of batches, each containing task durations
            max_parallel: Maximum parallelism

        Returns:
            Total parallel execution time
        """
        total = 0.0
        for batch in batches:
            if not batch:
                continue
            # Batch duration is the max task duration
            batch_duration = max(batch) if batch else 0
            total += batch_duration
        return total

    @staticmethod
    def calculate_improvement(
        sequential_time: float,
        parallel_time: float,
    ) -> float:
        """
        Calculate improvement percentage.

        Args:
            sequential_time: Sequential execution time
            parallel_time: Parallel execution time

        Returns:
            Improvement percentage (positive is better)
        """
        if sequential_time <= 0:
            return 0.0
        return ((sequential_time - parallel_time) / sequential_time) * 100

    @staticmethod
    def estimate_theoretical_max(
        tasks_durations: list[float],
        max_parallel: int = 10,
    ) -> float:
        """
        Estimate theoretical maximum parallelization.

        This assumes perfect scheduling with no conflicts.

        Args:
            tasks_durations: List of task durations
            max_parallel: Maximum parallelism

        Returns:
            Best possible parallel execution time
        """
        if not tasks_durations:
            return 0.0

        # Sort by duration descending
        sorted_durations = sorted(tasks_durations, reverse=True)

        # Assign to parallel slots
        slots = [0.0] * max_parallel
        for duration in sorted_durations:
            # Find the slot with minimum current time
            min_slot = min(range(len(slots)), key=lambda i: slots[i])
            slots[min_slot] += duration

        # Return the max slot time (makespan)
        return max(slots)
