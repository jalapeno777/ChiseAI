"""
Tests for Parallel Optimizer Data Models (ST-GOV-010).

Unit tests for models.py covering all data classes and enums.
"""

import pytest
from datetime import datetime

from src.governance.parallel_optimizer.models import (
    TaskPriority,
    TaskStatus,
    BatchStatus,
    OptimizableTask,
    TaskBatch,
    ExecutionPlan,
    ConflictAnalysis,
    ThroughputMetrics,
    RollbackResult,
    OptimizationResult,
)


class TestOptimizableTask:
    """Tests for OptimizableTask."""

    def test_create_basic_task(self):
        """Test creating a basic task."""
        task = OptimizableTask(task_id="test-task")
        assert task.task_id == "test-task"
        assert task.scope_globs == []
        assert task.dependencies == []
        assert task.priority == TaskPriority.NORMAL
        assert task.estimated_duration_seconds == 60.0

    def test_create_task_with_all_fields(self):
        """Test creating a task with all fields."""
        task = OptimizableTask(
            task_id="full-task",
            scope_globs=["src/**/*.py"],
            dependencies=["dep-1", "dep-2"],
            priority=TaskPriority.HIGH,
            estimated_duration_seconds=120.0,
            constitution_alignment=0.8,
            agent_id="agent-1",
            metadata={"custom": "value"},
        )
        assert task.task_id == "full-task"
        assert len(task.scope_globs) == 1
        assert len(task.dependencies) == 2
        assert task.priority == TaskPriority.HIGH
        assert task.estimated_duration_seconds == 120.0

    def test_task_hash_and_equality(self):
        """Test task hashing and equality."""
        task1 = OptimizableTask(task_id="task-1")
        task2 = OptimizableTask(task_id="task-1")
        task3 = OptimizableTask(task_id="task-2")

        assert hash(task1) == hash(task2)
        assert task1 == task2
        assert task1 != task3
        assert task1 != "not-a-task"


class TestTaskBatch:
    """Tests for TaskBatch."""

    @pytest.fixture
    def sample_tasks(self):
        """Create sample tasks for testing."""
        return [
            OptimizableTask(
                task_id=f"task-{i}",
                estimated_duration_seconds=10.0 * (i + 1),
            )
            for i in range(3)
        ]

    def test_create_basic_batch(self, sample_tasks):
        """Test creating a basic batch."""
        batch = TaskBatch(
            batch_id="batch-1",
            batch_number=1,
            tasks=sample_tasks,
        )
        assert batch.batch_id == "batch-1"
        assert batch.batch_number == 1
        assert len(batch.tasks) == 3
        assert batch.status == BatchStatus.PENDING
        assert batch.parallel_safe is True

    def test_batch_task_ids(self, sample_tasks):
        """Test getting task IDs from batch."""
        batch = TaskBatch(
            batch_id="batch-1",
            batch_number=1,
            tasks=sample_tasks,
        )
        assert batch.task_ids == ["task-0", "task-1", "task-2"]

    def test_batch_total_estimated_duration(self, sample_tasks):
        """Test total estimated duration (max of tasks)."""
        batch = TaskBatch(
            batch_id="batch-1",
            batch_number=1,
            tasks=sample_tasks,
        )
        # Max duration is task-2 with 30 seconds
        assert batch.total_estimated_duration == 30.0

    def test_empty_batch_duration(self):
        """Test empty batch duration."""
        batch = TaskBatch(batch_id="empty", batch_number=1)
        assert batch.total_estimated_duration == 0.0
        assert batch.task_count == 0


class TestExecutionPlan:
    """Tests for ExecutionPlan."""

    @pytest.fixture
    def sample_plan(self):
        """Create a sample execution plan."""
        batch1 = TaskBatch(
            batch_id="batch-1",
            batch_number=1,
            tasks=[
                OptimizableTask(task_id="t1", estimated_duration_seconds=10.0),
                OptimizableTask(task_id="t2", estimated_duration_seconds=15.0),
            ],
        )
        batch2 = TaskBatch(
            batch_id="batch-2",
            batch_number=2,
            tasks=[
                OptimizableTask(task_id="t3", estimated_duration_seconds=20.0),
            ],
        )
        return ExecutionPlan(
            plan_id="test-plan",
            batches=[batch1, batch2],
            total_tasks=3,
            max_parallel=10,
            estimated_total_duration=35.0,
            conflict_count=0,
            optimization_score=85.0,
        )

    def test_create_plan(self, sample_plan):
        """Test creating an execution plan."""
        assert sample_plan.plan_id == "test-plan"
        assert sample_plan.batch_count == 2
        assert sample_plan.total_tasks == 3
        assert sample_plan.max_parallel == 10

    def test_get_batch(self, sample_plan):
        """Test getting a batch by number."""
        batch = sample_plan.get_batch(1)
        assert batch is not None
        assert batch.batch_id == "batch-1"

        # Non-existent batch
        assert sample_plan.get_batch(99) is None


class TestThroughputMetrics:
    """Tests for ThroughputMetrics."""

    def test_calculate_improvement(self):
        """Test throughput improvement calculation."""
        metrics = ThroughputMetrics(
            sequential_duration=100.0,
            parallel_duration=60.0,
        )
        improvement = metrics.calculate_improvement()
        assert improvement == 40.0
        assert metrics.throughput_improvement == 40.0

    def test_zero_sequential_duration(self):
        """Test improvement with zero sequential duration."""
        metrics = ThroughputMetrics(
            sequential_duration=0.0,
            parallel_duration=10.0,
        )
        improvement = metrics.calculate_improvement()
        assert improvement == 0.0

    def test_meets_target(self):
        """Test target improvement check."""
        metrics = ThroughputMetrics(throughput_improvement=35.0)
        assert metrics.meets_target(30.0) is True
        assert metrics.meets_target(40.0) is False


class TestRollbackResult:
    """Tests for RollbackResult."""

    def test_successful_rollback(self):
        """Test successful rollback result."""
        result = RollbackResult(
            success=True,
            rolled_back_tasks=["task-1", "task-2"],
            failed_rollbacks=[],
            message="Rollback successful",
        )
        assert result.success is True
        assert len(result.rolled_back_tasks) == 2
        assert len(result.failed_rollbacks) == 0

    def test_partial_rollback(self):
        """Test partial rollback result."""
        result = RollbackResult(
            success=False,
            rolled_back_tasks=["task-1"],
            failed_rollbacks=["task-2"],
            message="Partial rollback",
        )
        assert result.success is False
        assert len(result.rolled_back_tasks) == 1
        assert len(result.failed_rollbacks) == 1


class TestEnums:
    """Tests for enum values."""

    def test_task_priority_values(self):
        """Test TaskPriority enum values."""
        assert TaskPriority.CRITICAL.value == "critical"
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.LOW.value == "low"

    def test_task_status_values(self):
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ROLLED_BACK.value == "rolled_back"

    def test_batch_status_values(self):
        """Test BatchStatus enum values."""
        assert BatchStatus.PENDING.value == "pending"
        assert BatchStatus.RUNNING.value == "running"
        assert BatchStatus.COMPLETED.value == "completed"
        assert BatchStatus.FAILED.value == "failed"
        assert BatchStatus.ROLLED_BACK.value == "rolled_back"
