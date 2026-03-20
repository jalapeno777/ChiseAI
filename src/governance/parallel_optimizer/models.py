"""
Data models for Parallel Execution Optimizer (ST-GOV-010).

Defines core data structures for task representation, execution plans,
batches, and optimization results.

Story: ST-GOV-010
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class TaskPriority(str, Enum):
    """Task priority levels for scheduling."""

    CRITICAL = "critical"  # Must execute first
    HIGH = "high"  # Important but not blocking
    NORMAL = "normal"  # Standard priority
    LOW = "low"  # Can wait


class TaskStatus(str, Enum):
    """Status of a task in the execution pipeline."""

    PENDING = "pending"
    READY = "ready"  # Dependencies satisfied
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class BatchStatus(str, Enum):
    """Status of an execution batch."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class OptimizableTask:
    """
    A task that can be optimized for parallel execution.

    Attributes:
        task_id: Unique identifier for the task
        scope_globs: File/directory patterns this task modifies
        dependencies: Task IDs that must complete before this task
        priority: Task priority for scheduling
        estimated_duration_seconds: Estimated execution time
        constitution_alignment: Weight for constitution alignment (0.0-1.0)
        agent_id: ID of the agent that will execute this task
        metadata: Additional task metadata
    """

    task_id: str
    scope_globs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.NORMAL
    estimated_duration_seconds: float = 60.0
    constitution_alignment: float = 1.0
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.task_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OptimizableTask):
            return False
        return self.task_id == other.task_id


@dataclass
class TaskBatch:
    """
    A batch of tasks that can be executed in parallel.

    Attributes:
        batch_id: Unique identifier for the batch
        batch_number: Sequential batch number in execution plan
        tasks: List of tasks in this batch
        status: Current batch status
        started_at: When batch execution started
        completed_at: When batch execution completed
        parallel_safe: Whether all tasks can safely run in parallel
    """

    batch_id: str
    batch_number: int
    tasks: list[OptimizableTask] = field(default_factory=list)
    status: BatchStatus = BatchStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parallel_safe: bool = True

    @property
    def task_ids(self) -> list[str]:
        """Get list of task IDs in this batch."""
        return [t.task_id for t in self.tasks]

    @property
    def total_estimated_duration(self) -> float:
        """Get estimated duration (max of parallel tasks)."""
        if not self.tasks:
            return 0.0
        return max(t.estimated_duration_seconds for t in self.tasks)

    @property
    def task_count(self) -> int:
        """Number of tasks in this batch."""
        return len(self.tasks)


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for parallel task execution.

    Attributes:
        plan_id: Unique identifier for this plan
        batches: Ordered list of task batches
        total_tasks: Total number of tasks in plan
        max_parallel: Maximum parallelism allowed
        estimated_total_duration: Estimated total execution time
        created_at: When the plan was created
        conflict_count: Number of conflicts detected during planning
        optimization_score: Score for how well the plan is optimized (0-100)
    """

    plan_id: str
    batches: list[TaskBatch] = field(default_factory=list)
    total_tasks: int = 0
    max_parallel: int = 10
    estimated_total_duration: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    conflict_count: int = 0
    optimization_score: float = 0.0

    @property
    def batch_count(self) -> int:
        """Number of batches in the plan."""
        return len(self.batches)

    def get_batch(self, batch_number: int) -> TaskBatch | None:
        """Get a specific batch by number."""
        for batch in self.batches:
            if batch.batch_number == batch_number:
                return batch
        return None

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """Get the status of a specific task."""
        for batch in self.batches:
            for task in batch.tasks:
                if task.task_id == task_id:
                    return TaskStatus.PENDING  # Would be tracked separately
        return None


@dataclass
class ConflictAnalysis:
    """
    Result of conflict analysis between tasks.

    Attributes:
        has_conflicts: Whether any conflicts were detected
        conflict_pairs: List of (task_id1, task_id2) pairs with conflicts
        conflict_types: Types of conflicts detected
        severity: Maximum severity of conflicts
        resolution_suggestions: Suggested resolutions
    """

    has_conflicts: bool = False
    conflict_pairs: list[tuple[str, str]] = field(default_factory=list)
    conflict_types: list[str] = field(default_factory=list)
    severity: str = "none"
    resolution_suggestions: list[str] = field(default_factory=list)


@dataclass
class ThroughputMetrics:
    """
    Metrics for measuring execution throughput.

    Attributes:
        sequential_duration: How long sequential execution would take
        parallel_duration: Actual parallel execution time
        throughput_improvement: Percentage improvement (0-100)
        tasks_per_minute: Task completion rate
        conflict_rate: Percentage of tasks that had conflicts
        rollback_count: Number of rollbacks performed
    """

    sequential_duration: float = 0.0
    parallel_duration: float = 0.0
    throughput_improvement: float = 0.0
    tasks_per_minute: float = 0.0
    conflict_rate: float = 0.0
    rollback_count: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    def calculate_improvement(self) -> float:
        """Calculate throughput improvement percentage."""
        if self.sequential_duration <= 0:
            return 0.0
        improvement = (
            (self.sequential_duration - self.parallel_duration)
            / self.sequential_duration
        ) * 100
        self.throughput_improvement = max(0.0, improvement)
        return self.throughput_improvement

    def meets_target(self, target_improvement: float = 30.0) -> bool:
        """Check if throughput meets the target improvement."""
        return self.throughput_improvement >= target_improvement


@dataclass
class RollbackResult:
    """
    Result of a rollback operation.

    Attributes:
        success: Whether the rollback was successful
        rolled_back_tasks: List of task IDs that were rolled back
        failed_rollbacks: List of task IDs that failed to roll back
        message: Human-readable result message
        timestamp: When the rollback occurred
    """

    success: bool = False
    rolled_back_tasks: list[str] = field(default_factory=list)
    failed_rollbacks: list[str] = field(default_factory=list)
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OptimizationResult:
    """
    Complete result of the optimization process.

    Attributes:
        execution_plan: The generated execution plan
        throughput_metrics: Measured throughput metrics
        conflict_analysis: Conflict analysis results
        success: Whether optimization was successful
        message: Human-readable result message
    """

    execution_plan: ExecutionPlan | None = None
    throughput_metrics: ThroughputMetrics | None = None
    conflict_analysis: ConflictAnalysis | None = None
    success: bool = False
    message: str = ""
