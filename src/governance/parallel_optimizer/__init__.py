"""
Parallel Execution Optimizer Module (ST-GOV-010).

Optimizes parallel execution of agent swarm tasks by analyzing
dependencies, detecting conflicts, and generating optimized schedules.

Key Components:
- ParallelOptimizer: Main orchestrator for parallel optimization
- DependencyGraphBuilder: Builds and analyzes task dependency graphs
- ScopeConflictAnalyzer: Detects scope conflicts between tasks
- ExecutionScheduler: Creates optimized execution schedules
- RollbackManager: Provides rollback capabilities
- ThroughputMeter: Measures and validates throughput

Usage:
    from src.governance.parallel_optimizer import (
        ParallelOptimizer,
        OptimizableTask,
        TaskPriority,
    )

    # Create tasks
    tasks = [
        OptimizableTask(
            task_id="ST-001-api",
            scope_globs=["src/api/**/*.py"],
            priority=TaskPriority.HIGH,
        ),
        OptimizableTask(
            task_id="ST-002-db",
            scope_globs=["src/db/**/*.py"],
            dependencies=["ST-001-api"],
        ),
    ]

    # Create optimizer and plan
    optimizer = ParallelOptimizer()
    plan = optimizer.create_execution_plan(tasks)

    # Execute with rollback safety
    def execute(task):
        # Do the work
        return True

    result = optimizer.execute_plan(plan, execute)

    # Validate results
    is_valid, issues = optimizer.validate_execution(result)
    if is_valid:
        print(f"Success! Improvement: {result.throughput_metrics.throughput_improvement}%")

Story: ST-GOV-010
"""

from src.governance.parallel_optimizer.conflict_analyzer import (
    ConflictMatrix,
    ScopeConflictAnalyzer,
)
from src.governance.parallel_optimizer.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
)
from src.governance.parallel_optimizer.models import (
    BatchStatus,
    ConflictAnalysis,
    ExecutionPlan,
    # Data classes
    OptimizableTask,
    OptimizationResult,
    RollbackResult,
    TaskBatch,
    # Enums
    TaskPriority,
    TaskStatus,
    ThroughputMetrics,
)
from src.governance.parallel_optimizer.optimizer import (
    OptimizerConfig,
    ParallelOptimizer,
)
from src.governance.parallel_optimizer.rollback import (
    BatchRollbackExecutor,
    RollbackCheckpoint,
    RollbackHandler,
    RollbackManager,
)
from src.governance.parallel_optimizer.scheduler import (
    ExecutionScheduler,
    SchedulingConfig,
)
from src.governance.parallel_optimizer.throughput import (
    ThroughputComparator,
    ThroughputMeter,
)

__all__ = [
    # Models
    "TaskPriority",
    "TaskStatus",
    "BatchStatus",
    "OptimizableTask",
    "TaskBatch",
    "ExecutionPlan",
    "ConflictAnalysis",
    "ThroughputMetrics",
    "RollbackResult",
    "OptimizationResult",
    # Dependency Graph
    "DependencyGraphBuilder",
    "DependencyGraph",
    "DependencyNode",
    # Conflict Analysis
    "ScopeConflictAnalyzer",
    "ConflictMatrix",
    # Scheduler
    "ExecutionScheduler",
    "SchedulingConfig",
    # Rollback
    "RollbackManager",
    "RollbackCheckpoint",
    "RollbackHandler",
    "BatchRollbackExecutor",
    # Throughput
    "ThroughputMeter",
    "ThroughputComparator",
    # Main Optimizer
    "ParallelOptimizer",
    "OptimizerConfig",
]
