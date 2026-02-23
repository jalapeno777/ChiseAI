"""
Tests for Scope Conflict Analyzer (ST-GOV-010).

Unit tests for conflict_analyzer.py covering conflict detection and analysis.
"""

import pytest

from src.governance.parallel_optimizer.models import OptimizableTask
from src.governance.parallel_optimizer.conflict_analyzer import (
    ScopeConflictAnalyzer,
    ConflictMatrix,
    ConflictAnalysis,
)


class TestScopeConflictAnalyzer:
    """Tests for ScopeConflictAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create a fresh analyzer for each test."""
        return ScopeConflictAnalyzer()

    @pytest.fixture
    def non_conflicting_tasks(self):
        """Create tasks with non-overlapping scopes."""
        return [
            OptimizableTask(
                task_id="api-task",
                scope_globs=["src/api/**/*.py"],
            ),
            OptimizableTask(
                task_id="db-task",
                scope_globs=["src/db/**/*.py"],
            ),
            OptimizableTask(
                task_id="ui-task",
                scope_globs=["src/ui/**/*.tsx"],
            ),
        ]

    @pytest.fixture
    def conflicting_tasks(self):
        """Create tasks with overlapping scopes."""
        return [
            OptimizableTask(
                task_id="task-a",
                scope_globs=["src/api/**/*.py"],
            ),
            OptimizableTask(
                task_id="task-b",
                scope_globs=["src/api/routes.py"],  # Overlaps with task-a
            ),
            OptimizableTask(
                task_id="task-c",
                scope_globs=["src/db/**/*.py"],  # No conflict
            ),
        ]

    def test_analyze_task_pair_no_conflict(self, analyzer, non_conflicting_tasks):
        """Test analyzing a pair with no conflict."""
        analysis = analyzer.analyze_task_pair(
            non_conflicting_tasks[0],
            non_conflicting_tasks[1],
        )

        assert analysis.has_conflicts is False
        assert len(analysis.conflict_pairs) == 0
        assert analysis.severity == "none"

    def test_analyze_task_pair_with_conflict(self, analyzer, conflicting_tasks):
        """Test analyzing a pair with conflict."""
        analysis = analyzer.analyze_task_pair(
            conflicting_tasks[0],
            conflicting_tasks[1],
        )

        assert analysis.has_conflicts is True
        assert len(analysis.conflict_pairs) == 1
        assert analysis.severity == "critical"

    def test_build_conflict_matrix(self, analyzer, conflicting_tasks):
        """Test building a conflict matrix."""
        matrix = analyzer.build_conflict_matrix(conflicting_tasks)

        assert len(matrix.task_ids) == 3

        # task-a and task-b should conflict
        assert matrix.has_conflict("task-a", "task-b") is True
        assert matrix.has_conflict("task-b", "task-a") is True

        # task-c should not conflict with anyone
        assert matrix.has_conflict("task-a", "task-c") is False
        assert matrix.has_conflict("task-b", "task-c") is False

    def test_build_conflict_matrix_no_conflicts(self, analyzer, non_conflicting_tasks):
        """Test building matrix with no conflicts."""
        matrix = analyzer.build_conflict_matrix(non_conflicting_tasks)

        # No conflicts
        for i, tid1 in enumerate(matrix.task_ids):
            for j, tid2 in enumerate(matrix.task_ids):
                if i != j:
                    assert matrix.has_conflict(tid1, tid2) is False

    def test_get_conflicting_tasks(self, analyzer, conflicting_tasks):
        """Test getting tasks that conflict with a specific task."""
        matrix = analyzer.build_conflict_matrix(conflicting_tasks)

        conflicting_with_a = matrix.get_conflicting_tasks("task-a")
        assert "task-b" in conflicting_with_a
        assert "task-c" not in conflicting_with_a

    def test_get_non_conflicting_groups(self, analyzer, conflicting_tasks):
        """Test grouping non-conflicting tasks."""
        matrix = analyzer.build_conflict_matrix(conflicting_tasks)
        groups = matrix.get_non_conflicting_groups()

        # task-a and task-b should be in different groups
        task_a_group = None
        task_b_group = None
        for i, group in enumerate(groups):
            if "task-a" in group:
                task_a_group = i
            if "task-b" in group:
                task_b_group = i

        assert task_a_group is not None
        assert task_b_group is not None
        assert task_a_group != task_b_group

    def test_find_max_parallel_group(self, analyzer, conflicting_tasks):
        """Test finding max parallel group."""
        group = analyzer.find_max_parallel_group(conflicting_tasks, max_size=10)

        # Should include task-c and one of task-a or task-b
        assert "task-c" in group
        # Either task-a or task-b, but not both
        assert not ("task-a" in group and "task-b" in group)

    def test_suggest_execution_order(self, analyzer, conflicting_tasks):
        """Test suggesting execution order."""
        batches = analyzer.suggest_execution_order(conflicting_tasks)

        # Should have multiple batches to avoid conflicts
        assert len(batches) >= 2

        # task-a and task-b should be in different batches
        task_a_batch = None
        task_b_batch = None
        for i, batch in enumerate(batches):
            if "task-a" in batch:
                task_a_batch = i
            if "task-b" in batch:
                task_b_batch = i

        assert task_a_batch != task_b_batch

    def test_get_conflict_count(self, analyzer, conflicting_tasks):
        """Test counting conflicts."""
        count = analyzer.get_conflict_count(conflicting_tasks)
        assert count == 1  # Only task-a and task-b conflict

    def test_get_conflict_rate(self, analyzer, conflicting_tasks):
        """Test calculating conflict rate."""
        rate = analyzer.get_conflict_rate(conflicting_tasks)

        # 3 tasks = 3 pairs, 1 conflict = 33.3%
        assert 30.0 <= rate <= 35.0

    def test_get_conflict_rate_no_conflicts(self, analyzer, non_conflicting_tasks):
        """Test conflict rate with no conflicts."""
        rate = analyzer.get_conflict_rate(non_conflicting_tasks)
        assert rate == 0.0

    def test_single_task(self, analyzer):
        """Test with a single task."""
        tasks = [OptimizableTask(task_id="only-task", scope_globs=["src/**/*.py"])]

        matrix = analyzer.build_conflict_matrix(tasks)
        assert len(matrix.task_ids) == 1
        assert analyzer.get_conflict_count(tasks) == 0
        assert analyzer.get_conflict_rate(tasks) == 0.0

    def test_empty_task_list(self, analyzer):
        """Test with no tasks."""
        matrix = analyzer.build_conflict_matrix([])

        assert len(matrix.task_ids) == 0
        assert len(matrix.matrix) == 0


class TestConflictMatrix:
    """Tests for ConflictMatrix dataclass."""

    def test_empty_matrix(self):
        """Test empty matrix."""
        matrix = ConflictMatrix()

        assert matrix.has_conflict("a", "b") is False
        assert matrix.get_conflicting_tasks("a") == []

    def test_has_conflict_unknown_task(self):
        """Test has_conflict with unknown task."""
        matrix = ConflictMatrix(
            task_ids=["a", "b"], matrix=[[False, False], [False, False]]
        )

        assert matrix.has_conflict("unknown", "a") is False


class TestConflictAnalysis:
    """Tests for ConflictAnalysis dataclass."""

    def test_no_conflicts(self):
        """Test analysis with no conflicts."""
        analysis = ConflictAnalysis(
            has_conflicts=False,
            conflict_pairs=[],
            conflict_types=[],
            severity="none",
        )

        assert analysis.has_conflicts is False
        assert len(analysis.resolution_suggestions) == 0

    def test_with_conflicts(self):
        """Test analysis with conflicts."""
        analysis = ConflictAnalysis(
            has_conflicts=True,
            conflict_pairs=[("task-a", "task-b")],
            conflict_types=["scope_overlap"],
            severity="critical",
            resolution_suggestions=["Run sequentially"],
        )

        assert analysis.has_conflicts is True
        assert len(analysis.conflict_pairs) == 1
        assert len(analysis.resolution_suggestions) == 1
