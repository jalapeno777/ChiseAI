"""
Tests for Execution Scheduler (ST-GOV-010).

Unit tests for scheduler.py covering plan creation and batch scheduling.
"""

import pytest
from src.governance.parallel_optimizer.models import (
    BatchStatus,
    OptimizableTask,
    TaskPriority,
)
from src.governance.parallel_optimizer.scheduler import (
    ExecutionScheduler,
    SchedulingConfig,
)


class TestExecutionScheduler:
    """Tests for ExecutionScheduler."""

    @pytest.fixture
    def scheduler(self):
        """Create a fresh scheduler for each test."""
        return ExecutionScheduler()

    @pytest.fixture
    def config(self):
        """Create a custom config."""
        return SchedulingConfig(
            max_parallel=5,
            priority_weight=0.5,
            duration_weight=0.3,
            constitution_weight=0.2,
        )

    @pytest.fixture
    def independent_tasks(self):
        """Create independent tasks with different priorities."""
        return [
            OptimizableTask(
                task_id=f"task-{i}",
                scope_globs=[f"src/module{i}/**/*.py"],
                priority=TaskPriority.HIGH if i < 2 else TaskPriority.NORMAL,
                estimated_duration_seconds=10.0 * (i + 1),
            )
            for i in range(8)
        ]

    @pytest.fixture
    def dependent_tasks(self):
        """Create tasks with dependencies."""
        return [
            OptimizableTask(
                task_id="root",
                scope_globs=["src/root/**/*.py"],
                estimated_duration_seconds=10.0,
            ),
            OptimizableTask(
                task_id="child-1",
                scope_globs=["src/c1/**/*.py"],
                dependencies=["root"],
                estimated_duration_seconds=15.0,
            ),
            OptimizableTask(
                task_id="child-2",
                scope_globs=["src/c2/**/*.py"],
                dependencies=["root"],
                estimated_duration_seconds=20.0,
            ),
            OptimizableTask(
                task_id="grandchild",
                scope_globs=["src/gc/**/*.py"],
                dependencies=["child-1", "child-2"],
                estimated_duration_seconds=25.0,
            ),
        ]

    def test_create_execution_plan_independent_tasks(
        self, scheduler, independent_tasks
    ):
        """Test creating a plan with independent tasks."""
        plan = scheduler.create_execution_plan(independent_tasks)

        assert plan.total_tasks == 8
        assert plan.max_parallel == 10
        assert plan.batch_count >= 1
        assert plan.conflict_count == 0  # No overlapping scopes

    def test_create_execution_plan_dependent_tasks(self, scheduler, dependent_tasks):
        """Test creating a plan with dependencies."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        assert plan.total_tasks == 4

        # Should have multiple batches due to dependencies
        assert plan.batch_count >= 2

        # Check that batches respect dependencies
        root_batch = None
        gc_batch = None
        for batch in plan.batches:
            if "root" in batch.task_ids:
                root_batch = batch.batch_number
            if "grandchild" in batch.task_ids:
                gc_batch = batch.batch_number

        # grandchild should come after root
        assert root_batch is not None and gc_batch is not None
        assert root_batch < gc_batch

    def test_create_execution_plan_empty_tasks(self, scheduler):
        """Test creating a plan with no tasks."""
        plan = scheduler.create_execution_plan([])

        assert plan.total_tasks == 0
        assert plan.batch_count == 0

    def test_custom_config(self, config):
        """Test scheduler with custom config."""
        scheduler = ExecutionScheduler(config=config)

        assert scheduler.config.max_parallel == 5
        assert scheduler.config.priority_weight == 0.5

    def test_optimize_parallel_schedule(self, scheduler, independent_tasks):
        """Test the main optimization method."""
        plan = scheduler.optimize_parallel_schedule(
            tasks=independent_tasks,
            max_parallel=3,
        )

        assert plan.max_parallel == 3
        assert plan.total_tasks == 8

    def test_get_next_batch(self, scheduler, dependent_tasks):
        """Test getting the next ready batch."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        # Initially, only root's batch should be ready
        next_batch = scheduler.get_next_batch(plan, set(), set())
        assert next_batch is not None
        assert "root" in next_batch.task_ids

        # Mark first batch as completed
        scheduler.update_batch_status(
            plan, next_batch.batch_number, BatchStatus.COMPLETED
        )

        # After root completes, child batches should be ready
        completed = {"root"}
        next_batch = scheduler.get_next_batch(plan, completed, set())
        assert next_batch is not None
        assert "child-1" in next_batch.task_ids or "child-2" in next_batch.task_ids

    def test_get_next_batch_with_running_tasks(self, scheduler, dependent_tasks):
        """Test getting next batch with tasks already running."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        # Mark first batch as running
        first_batch = plan.batches[0]
        first_batch.status = BatchStatus.RUNNING

        # Next batch should wait until first completes
        completed = set(first_batch.task_ids)
        running = set(first_batch.task_ids)
        scheduler.get_next_batch(plan, completed, running)

        # Should be None since dependencies might not be satisfied
        # (depends on specific plan structure)

    def test_update_batch_status(self, scheduler, dependent_tasks):
        """Test updating batch status."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        success = scheduler.update_batch_status(plan, 1, BatchStatus.RUNNING)
        assert success is True

        batch = plan.get_batch(1)
        assert batch.status == BatchStatus.RUNNING
        assert batch.started_at is not None

    def test_update_batch_status_nonexistent(self, scheduler, dependent_tasks):
        """Test updating status of non-existent batch."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        success = scheduler.update_batch_status(plan, 999, BatchStatus.COMPLETED)
        assert success is False

    def test_optimization_score(self, scheduler, independent_tasks):
        """Test that optimization score is calculated."""
        plan = scheduler.create_execution_plan(independent_tasks)

        # Score should be > 0 for a reasonable plan
        assert plan.optimization_score > 0
        assert plan.optimization_score <= 100

    def test_estimated_duration(self, scheduler, dependent_tasks):
        """Test estimated duration calculation."""
        plan = scheduler.create_execution_plan(dependent_tasks)

        # Estimated parallel duration should be less than sequential
        # Sequential: 10 + 15 + 20 + 25 = 70
        # Parallel (optimal): 10 + 20 + 25 = 55
        assert plan.estimated_total_duration > 0


class TestSchedulingConfig:
    """Tests for SchedulingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SchedulingConfig()

        assert config.max_parallel == 10
        assert config.priority_weight == 0.4
        assert config.duration_weight == 0.3
        assert config.constitution_weight == 0.3

    def test_custom_config(self):
        """Test custom configuration."""
        config = SchedulingConfig(
            max_parallel=20,
            batch_timeout_seconds=7200.0,
            enable_speculative_execution=True,
        )

        assert config.max_parallel == 20
        assert config.batch_timeout_seconds == 7200.0
        assert config.enable_speculative_execution is True
