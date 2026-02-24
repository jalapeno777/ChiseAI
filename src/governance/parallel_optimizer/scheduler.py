"""
Execution Scheduler for Parallel Execution Optimizer (ST-GOV-010).

Schedules tasks for optimal parallel execution, balancing throughput
with conflict avoidance and dependency satisfaction.

Story: ST-GOV-010
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from src.governance.parallel_optimizer.conflict_analyzer import (
    ConflictMatrix,
    ScopeConflictAnalyzer,
)
from src.governance.parallel_optimizer.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
)
from src.governance.parallel_optimizer.models import (
    BatchStatus,
    ExecutionPlan,
    OptimizableTask,
    TaskBatch,
)

logger = logging.getLogger(__name__)


@dataclass
class SchedulingConfig:
    """Configuration for the execution scheduler."""

    max_parallel: int = 10
    """Maximum number of tasks to run in parallel."""

    priority_weight: float = 0.4
    """Weight for task priority in scheduling decisions."""

    duration_weight: float = 0.3
    """Weight for estimated duration in scheduling decisions."""

    constitution_weight: float = 0.3
    """Weight for constitution alignment in scheduling decisions."""

    batch_timeout_seconds: float = 3600.0
    """Maximum time allowed for a batch to complete."""

    enable_speculative_execution: bool = False
    """Whether to enable speculative execution of dependent tasks."""


class ExecutionScheduler:
    """
    Schedules tasks for optimal parallel execution.

    Features:
    - Respects task dependencies
    - Avoids scope conflicts
    - Prioritizes high-value tasks
    - Balances batch sizes for optimal throughput

    Usage:
        scheduler = ExecutionScheduler()
        plan = scheduler.create_execution_plan(tasks)
        for batch in plan.batches:
            # Execute batch in parallel
            for task in batch.tasks:
                execute(task)
    """

    def __init__(self, config: SchedulingConfig | None = None):
        """
        Initialize the execution scheduler.

        Args:
            config: Optional scheduling configuration
        """
        self.config = config or SchedulingConfig()
        self._graph_builder = DependencyGraphBuilder()
        self._conflict_analyzer = ScopeConflictAnalyzer()

    def create_execution_plan(
        self,
        tasks: list[OptimizableTask],
        plan_id: str | None = None,
    ) -> ExecutionPlan:
        """
        Create an optimized execution plan for the given tasks.

        Args:
            tasks: List of tasks to schedule
            plan_id: Optional plan ID (auto-generated if not provided)

        Returns:
            ExecutionPlan with optimized batch scheduling
        """
        if not tasks:
            return ExecutionPlan(
                plan_id=plan_id or str(uuid.uuid4()),
                total_tasks=0,
            )

        # Build dependency graph
        graph = self._graph_builder.build_graph(tasks)

        if graph.has_cycles:
            logger.error(
                "Cannot create execution plan - circular dependencies detected"
            )
            return ExecutionPlan(
                plan_id=plan_id or str(uuid.uuid4()),
                total_tasks=len(tasks),
                conflict_count=-1,  # Indicates cycle error
            )

        # Build conflict matrix
        conflict_matrix = self._conflict_analyzer.build_conflict_matrix(tasks)

        # Create execution layers based on dependencies
        layers = self._graph_builder.get_execution_layers(graph)

        # Optimize each layer considering conflicts
        batches = self._create_batches(
            tasks=tasks,
            layers=layers,
            conflict_matrix=conflict_matrix,
            graph=graph,
        )

        # Calculate plan metrics
        sequential_duration = self._graph_builder.estimate_sequential_duration(graph)
        parallel_duration = self._estimate_parallel_duration(batches)

        optimization_score = self._calculate_optimization_score(
            batches=batches,
            conflict_matrix=conflict_matrix,
            sequential_duration=sequential_duration,
            parallel_duration=parallel_duration,
        )

        return ExecutionPlan(
            plan_id=plan_id or str(uuid.uuid4()),
            batches=batches,
            total_tasks=len(tasks),
            max_parallel=self.config.max_parallel,
            estimated_total_duration=parallel_duration,
            conflict_count=self._conflict_analyzer.get_conflict_count(tasks),
            optimization_score=optimization_score,
        )

    def _create_batches(
        self,
        tasks: list[OptimizableTask],
        layers: list[list[str]],
        conflict_matrix: ConflictMatrix,
        graph: DependencyGraph,
    ) -> list[TaskBatch]:
        """
        Create execution batches from dependency layers.

        Each layer may be split into multiple batches if there are
        conflicts or if it exceeds max_parallel.
        """
        batches: list[TaskBatch] = []
        task_map = {t.task_id: t for t in tasks}
        batch_number = 0

        for layer in layers:
            if not layer:
                continue

            # Group tasks in this layer by conflict-free sets
            conflict_free_groups = self._group_by_conflicts(layer, conflict_matrix)

            for group in conflict_free_groups:
                # Split group if it exceeds max_parallel
                sub_groups = self._split_by_size(group)

                for sub_group in sub_groups:
                    batch_number += 1
                    batch_tasks = [
                        task_map[tid] for tid in sub_group if tid in task_map
                    ]

                    batch = TaskBatch(
                        batch_id=f"batch-{batch_number:03d}",
                        batch_number=batch_number,
                        tasks=batch_tasks,
                        parallel_safe=len(batch_tasks) <= self.config.max_parallel,
                    )
                    batches.append(batch)

        return batches

    def _group_by_conflicts(
        self,
        task_ids: list[str],
        conflict_matrix: ConflictMatrix,
    ) -> list[list[str]]:
        """
        Group tasks into conflict-free sets.

        Uses greedy graph coloring approach.
        """
        if not task_ids:
            return []

        groups: list[list[str]] = []

        # Sort by priority (priority not available in task_ids, so use order)
        sorted_ids = list(task_ids)

        for task_id in sorted_ids:
            # Try to find an existing group
            placed = False
            for group in groups:
                # Check if this task conflicts with any in the group
                has_conflict = any(
                    conflict_matrix.has_conflict(task_id, g) for g in group
                )
                if not has_conflict:
                    group.append(task_id)
                    placed = True
                    break

            if not placed:
                groups.append([task_id])

        return groups

    def _split_by_size(self, task_ids: list[str]) -> list[list[str]]:
        """Split a group into sub-groups of max_parallel size."""
        if len(task_ids) <= self.config.max_parallel:
            return [task_ids]

        result = []
        for i in range(0, len(task_ids), self.config.max_parallel):
            result.append(task_ids[i : i + self.config.max_parallel])
        return result

    def _estimate_parallel_duration(self, batches: list[TaskBatch]) -> float:
        """
        Estimate total duration with parallel execution.

        Each batch runs in parallel, so batch duration is the max task duration.
        Total duration is the sum of batch durations.
        """
        return sum(batch.total_estimated_duration for batch in batches)

    def _calculate_optimization_score(
        self,
        batches: list[TaskBatch],
        conflict_matrix: ConflictMatrix,
        sequential_duration: float,
        parallel_duration: float,
    ) -> float:
        """
        Calculate an optimization score for the plan.

        Score is based on:
        - Throughput improvement (higher is better)
        - Batch utilization (higher is better)
        - Conflict avoidance (lower conflicts is better)
        """
        if sequential_duration <= 0:
            return 0.0

        # Throughput component (0-40 points)
        throughput_improvement = (
            (sequential_duration - parallel_duration) / sequential_duration
        ) * 100
        throughput_score = min(40, throughput_improvement * 0.8)

        # Batch utilization component (0-30 points)
        if batches:
            avg_batch_size = sum(b.task_count for b in batches) / len(batches)
            utilization_ratio = avg_batch_size / self.config.max_parallel
            utilization_score = min(30, utilization_ratio * 30)
        else:
            utilization_score = 0

        # Conflict avoidance component (0-30 points)
        n = len(conflict_matrix.task_ids)
        if n > 1:
            total_pairs = n * (n - 1) / 2
            conflict_count = sum(
                1
                for i in range(n)
                for j in range(i + 1, n)
                if conflict_matrix.matrix[i][j]
            )
            conflict_rate = conflict_count / total_pairs
            conflict_score = max(0, 30 * (1 - conflict_rate * 10))
        else:
            conflict_score = 30

        return min(100, throughput_score + utilization_score + conflict_score)

    def optimize_parallel_schedule(
        self,
        tasks: list[OptimizableTask],
        conflict_matrix: ConflictMatrix | None = None,
        max_parallel: int | None = None,
        priority_weights: dict[str, float] | None = None,
    ) -> ExecutionPlan:
        """
        Optimize parallel execution schedule.

        This is the main optimization method that considers all factors.

        Args:
            tasks: List of tasks to schedule
            conflict_matrix: Pre-computed conflict matrix (optional)
            max_parallel: Override max parallelism (optional)
            priority_weights: Weights for task priorities (optional)

        Returns:
            Optimized ExecutionPlan
        """
        # Override config if provided
        original_max = self.config.max_parallel
        if max_parallel is not None:
            self.config.max_parallel = max_parallel

        try:
            plan = self.create_execution_plan(tasks)

            # Apply priority weights if provided
            if priority_weights and plan.optimization_score > 0:
                # Adjust optimization score based on constitution alignment
                total_alignment = (
                    sum(t.constitution_alignment for t in tasks) / len(tasks)
                    if tasks
                    else 1.0
                )
                plan.optimization_score *= total_alignment

            return plan
        finally:
            self.config.max_parallel = original_max

    def get_next_batch(
        self,
        plan: ExecutionPlan,
        completed_tasks: set[str],
        running_tasks: set[str],
    ) -> TaskBatch | None:
        """
        Get the next batch that is ready to execute.

        A batch is ready when all tasks in previous batches are completed
        and all dependency tasks are satisfied.

        Args:
            plan: The execution plan
            completed_tasks: Set of completed task IDs
            running_tasks: Set of currently running task IDs

        Returns:
            Next TaskBatch to execute, or None if no batch is ready
        """
        for batch in plan.batches:
            if batch.status != BatchStatus.PENDING:
                continue

            # Check if all tasks in this batch have dependencies satisfied
            all_deps_satisfied = True
            for task in batch.tasks:
                for dep_id in task.dependencies:
                    if dep_id not in completed_tasks:
                        all_deps_satisfied = False
                        break
                if not all_deps_satisfied:
                    break

            if all_deps_satisfied:
                return batch

        return None

    def update_batch_status(
        self,
        plan: ExecutionPlan,
        batch_number: int,
        status: BatchStatus,
    ) -> bool:
        """
        Update the status of a batch in the plan.

        Args:
            plan: The execution plan
            batch_number: The batch number to update
            status: The new status

        Returns:
            True if update was successful
        """
        batch = plan.get_batch(batch_number)
        if batch:
            batch.status = status
            if status == BatchStatus.RUNNING:
                batch.started_at = datetime.utcnow()
            elif status in (BatchStatus.COMPLETED, BatchStatus.FAILED):
                batch.completed_at = datetime.utcnow()
            return True
        return False
