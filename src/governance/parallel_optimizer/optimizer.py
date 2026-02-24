"""
Parallel Execution Optimizer - Main Orchestrator (ST-GOV-010).

Coordinates all parallel optimization components to provide a unified
interface for task scheduling, conflict resolution, and throughput optimization.

Story: ST-GOV-010
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
    ConflictAnalysis,
    ExecutionPlan,
    OptimizableTask,
    OptimizationResult,
    ThroughputMetrics,
)
from src.governance.parallel_optimizer.rollback import (
    BatchRollbackExecutor,
    RollbackManager,
    RollbackResult,
)
from src.governance.parallel_optimizer.scheduler import (
    ExecutionScheduler,
    SchedulingConfig,
)
from src.governance.parallel_optimizer.throughput import (
    ThroughputMeter,
)

logger = logging.getLogger(__name__)


@dataclass
class OptimizerConfig:
    """Configuration for the Parallel Optimizer."""

    max_parallel: int = 10
    """Maximum parallelism."""

    target_throughput_improvement: float = 30.0
    """Target throughput improvement percentage."""

    max_conflict_rate: float = 2.0
    """Maximum acceptable conflict rate."""

    enable_rollback: bool = True
    """Whether to enable rollback capabilities."""

    stop_on_first_failure: bool = True
    """Whether to stop batch execution on first failure."""

    constitution_weight: float = 0.3
    """Weight for constitution alignment in optimization."""


class ParallelOptimizer:
    """
    Main orchestrator for parallel execution optimization.

    This class coordinates all optimization components to:
    1. Analyze task dependencies
    2. Detect scope conflicts
    3. Generate optimized execution plans
    4. Execute with rollback safety
    5. Measure and validate throughput

    Usage:
        optimizer = ParallelOptimizer()

        # Create tasks
        tasks = [
            OptimizableTask(task_id="A", scope_globs=["src/api/**/*.py"]),
            OptimizableTask(task_id="B", scope_globs=["src/db/**/*.py"]),
        ]

        # Create execution plan
        plan = optimizer.create_execution_plan(tasks)

        # Execute with rollback safety
        def execute(task):
            # Do the work
            return True

        result = optimizer.execute_plan(plan, execute)

        # Check results
        print(f"Throughput improvement: {result.throughput_metrics.improvement}%")
    """

    def __init__(
        self,
        config: OptimizerConfig | None = None,
        redis_client=None,
    ):
        """
        Initialize the Parallel Optimizer.

        Args:
            config: Optional optimizer configuration
            redis_client: Optional Redis client for persistence
        """
        self.config = config or OptimizerConfig()
        self.redis_client = redis_client

        # Initialize components
        self._graph_builder = DependencyGraphBuilder()
        self._conflict_analyzer = ScopeConflictAnalyzer(redis_client=redis_client)
        self._scheduler = ExecutionScheduler(
            config=SchedulingConfig(
                max_parallel=self.config.max_parallel,
                constitution_weight=self.config.constitution_weight,
            )
        )
        self._rollback_manager = RollbackManager(redis_client=redis_client)
        self._throughput_meter = ThroughputMeter()

        # Execution state
        self._current_plan: ExecutionPlan | None = None
        self._completed_tasks: set[str] = set()
        self._failed_tasks: set[str] = set()

    def build_dependency_graph(self, tasks: list[OptimizableTask]) -> DependencyGraph:
        """
        Build a dependency graph from tasks.

        Args:
            tasks: List of tasks to analyze

        Returns:
            DependencyGraph with relationships
        """
        return self._graph_builder.build_graph(tasks)

    def analyze_scope_overlaps(self, tasks: list[OptimizableTask]) -> ConflictMatrix:
        """
        Analyze scope overlaps between tasks.

        Args:
            tasks: List of tasks to analyze

        Returns:
            ConflictMatrix with conflict information
        """
        return self._conflict_analyzer.build_conflict_matrix(tasks)

    def optimize_parallel_schedule(
        self,
        tasks: list[OptimizableTask],
        max_parallel: int | None = None,
        priority_weights: dict[str, float] | None = None,
    ) -> ExecutionPlan:
        """
        Create an optimized parallel execution schedule.

        This method analyzes dependencies, detects conflicts, and
        generates an execution plan that maximizes throughput while
        avoiding conflicts.

        Args:
            tasks: List of tasks to schedule
            max_parallel: Override max parallelism
            priority_weights: Optional priority weights

        Returns:
            Optimized ExecutionPlan
        """
        return self._scheduler.optimize_parallel_schedule(
            tasks=tasks,
            max_parallel=max_parallel or self.config.max_parallel,
            priority_weights=priority_weights,
        )

    def create_execution_plan(
        self,
        tasks: list[OptimizableTask],
        plan_id: str | None = None,
    ) -> ExecutionPlan:
        """
        Create a complete execution plan for the given tasks.

        This is the primary method for creating optimized plans.

        Args:
            tasks: List of tasks to schedule
            plan_id: Optional plan identifier

        Returns:
            ExecutionPlan with optimized batches
        """
        return self._scheduler.create_execution_plan(tasks, plan_id)

    def execute_plan(
        self,
        plan: ExecutionPlan,
        task_executor: Callable[[OptimizableTask], bool],
    ) -> OptimizationResult:
        """
        Execute an execution plan with rollback safety.

        Args:
            plan: The execution plan to execute
            task_executor: Function to execute each task

        Returns:
            OptimizationResult with execution outcome
        """
        self._current_plan = plan
        self._completed_tasks.clear()
        self._failed_tasks.clear()

        # Start throughput measurement
        self._throughput_meter.start_execution(plan)

        # Create rollback executor if enabled
        if self.config.enable_rollback:
            batch_executor = BatchRollbackExecutor(self._rollback_manager)
        else:
            batch_executor = None

        all_success = True
        last_rollback: RollbackResult | None = None

        # Execute batches sequentially (parallel within batch is external)
        for batch in plan.batches:
            # Update batch status
            self._scheduler.update_batch_status(
                plan, batch.batch_number, BatchStatus.RUNNING
            )
            self._throughput_meter.start_batch(batch)

            # Execute batch
            if batch_executor:
                success, rollback_result = batch_executor.execute_batch_with_rollback(
                    batch=batch,
                    task_executor=task_executor,
                    stop_on_failure=self.config.stop_on_first_failure,
                )
                if rollback_result:
                    last_rollback = rollback_result
                # Track completed/failed tasks
                if success:
                    for task in batch.tasks:
                        self._completed_tasks.add(task.task_id)
                elif rollback_result:
                    for task_id in rollback_result.rolled_back_tasks:
                        self._failed_tasks.add(task_id)
            else:
                # Execute without rollback support
                success = True
                for task in batch.tasks:
                    try:
                        task_success = task_executor(task)
                        if task_success:
                            self._completed_tasks.add(task.task_id)
                        else:
                            self._failed_tasks.add(task.task_id)
                            success = False
                            if self.config.stop_on_first_failure:
                                break
                    except Exception as e:
                        logger.error(f"Task {task.task_id} failed: {e}")
                        self._failed_tasks.add(task.task_id)
                        success = False
                        if self.config.stop_on_first_failure:
                            break

            self._throughput_meter.end_batch(batch, success)

            if success:
                self._scheduler.update_batch_status(
                    plan, batch.batch_number, BatchStatus.COMPLETED
                )
            else:
                all_success = False
                self._scheduler.update_batch_status(
                    plan, batch.batch_number, BatchStatus.PARTIALLY_FAILED
                )
                if self.config.stop_on_first_failure:
                    break

        # End throughput measurement
        metrics = self._throughput_meter.end_execution(
            plan=plan,
            completed_tasks=self._completed_tasks,
            failed_tasks=self._failed_tasks,
            rollback_count=self._rollback_manager.get_rollback_count(),
        )

        # Build conflict analysis
        conflict_analysis = ConflictAnalysis(
            has_conflicts=plan.conflict_count > 0,
            conflict_pairs=[],  # Would be populated from conflict matrix
            conflict_types=["scope_overlap"] if plan.conflict_count > 0 else [],
            severity="critical" if plan.conflict_count > 0 else "none",
        )

        return OptimizationResult(
            execution_plan=plan,
            throughput_metrics=metrics,
            conflict_analysis=conflict_analysis,
            success=all_success
            and metrics.meets_target(self.config.target_throughput_improvement),
            message=self._build_result_message(all_success, metrics, last_rollback),
        )

    def _build_result_message(
        self,
        success: bool,
        metrics: ThroughputMetrics,
        rollback_result: RollbackResult | None,
    ) -> str:
        """Build a human-readable result message."""
        parts = []

        if success:
            parts.append("Execution completed successfully")
        else:
            parts.append("Execution completed with issues")

        parts.append(
            f"Throughput improvement: {metrics.throughput_improvement:.1f}% "
            f"(target: {self.config.target_throughput_improvement}%)"
        )

        parts.append(
            f"Tasks: {metrics.completed_tasks}/{metrics.total_tasks} completed"
        )

        if metrics.failed_tasks > 0:
            parts.append(f"Failed tasks: {metrics.failed_tasks}")

        if metrics.rollback_count > 0:
            parts.append(f"Rollbacks performed: {metrics.rollback_count}")

        if rollback_result:
            parts.append(f"Last rollback: {rollback_result.message}")

        return ". ".join(parts)

    def validate_execution(self, result: OptimizationResult) -> tuple[bool, list[str]]:
        """
        Validate that execution meets acceptance criteria.

        Args:
            result: The optimization result to validate

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        if not result.throughput_metrics:
            issues.append("No throughput metrics available")
            return False, issues

        # Check throughput improvement
        if not result.throughput_metrics.meets_target(
            self.config.target_throughput_improvement
        ):
            issues.append(
                f"Throughput improvement {result.throughput_metrics.throughput_improvement:.1f}% "
                f"is below target {self.config.target_throughput_improvement}%"
            )

        # Check conflict rate
        if result.throughput_metrics.conflict_rate > self.config.max_conflict_rate:
            issues.append(
                f"Conflict rate {result.throughput_metrics.conflict_rate:.1f}% "
                f"exceeds maximum {self.config.max_conflict_rate}%"
            )

        # Check rollback success rate
        if self.config.enable_rollback:
            rollback_success_rate = self._rollback_manager.get_rollback_success_rate()
            if rollback_success_rate < 100:
                issues.append(
                    f"Rollback success rate {rollback_success_rate:.1f}% is below 100%"
                )

        return len(issues) == 0, issues

    def get_throughput_report(self) -> str:
        """
        Get a detailed throughput report.

        Returns:
            Formatted report string
        """
        if not self._throughput_meter._execution_timing:
            return "No execution data available"

        metrics = ThroughputMetrics(
            completed_tasks=len(self._completed_tasks),
            failed_tasks=len(self._failed_tasks),
            total_tasks=(self._current_plan.total_tasks if self._current_plan else 0),
        )
        return self._throughput_meter.generate_report(metrics)

    def get_optimization_summary(self, plan: ExecutionPlan) -> dict:
        """
        Get a summary of optimization for a plan.

        Args:
            plan: The execution plan

        Returns:
            Dictionary with optimization summary
        """
        graph = self._graph_builder.build_graph(
            [t for b in plan.batches for t in b.tasks]
        )
        sequential = self._graph_builder.estimate_sequential_duration(graph)
        optimal = self._graph_builder.estimate_optimal_duration(graph)

        return {
            "plan_id": plan.plan_id,
            "total_tasks": plan.total_tasks,
            "batch_count": plan.batch_count,
            "max_parallel": plan.max_parallel,
            "optimization_score": plan.optimization_score,
            "conflict_count": plan.conflict_count,
            "sequential_duration_estimate": sequential,
            "optimal_duration_estimate": optimal,
            "theoretical_improvement": (
                ((sequential - optimal) / sequential * 100) if sequential > 0 else 0
            ),
        }
