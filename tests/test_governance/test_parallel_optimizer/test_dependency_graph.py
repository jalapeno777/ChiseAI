"""
Tests for Dependency Graph Builder (ST-GOV-010).

Unit tests for dependency_graph.py covering graph building and analysis.
"""

import pytest
from src.governance.parallel_optimizer.dependency_graph import (
    DependencyGraph,
    DependencyGraphBuilder,
    DependencyNode,
)
from src.governance.parallel_optimizer.models import (
    OptimizableTask,
)


class TestDependencyGraphBuilder:
    """Tests for DependencyGraphBuilder."""

    @pytest.fixture
    def builder(self):
        """Create a fresh builder for each test."""
        return DependencyGraphBuilder()

    @pytest.fixture
    def independent_tasks(self):
        """Create tasks with no dependencies."""
        return [
            OptimizableTask(task_id=f"task-{i}", estimated_duration_seconds=10.0)
            for i in range(5)
        ]

    @pytest.fixture
    def dependent_tasks(self):
        """Create tasks with dependencies."""
        return [
            OptimizableTask(
                task_id="task-a",
                scope_globs=["src/a/**/*.py"],
                estimated_duration_seconds=10.0,
            ),
            OptimizableTask(
                task_id="task-b",
                scope_globs=["src/b/**/*.py"],
                dependencies=["task-a"],
                estimated_duration_seconds=15.0,
            ),
            OptimizableTask(
                task_id="task-c",
                scope_globs=["src/c/**/*.py"],
                dependencies=["task-a"],
                estimated_duration_seconds=20.0,
            ),
            OptimizableTask(
                task_id="task-d",
                scope_globs=["src/d/**/*.py"],
                dependencies=["task-b", "task-c"],
                estimated_duration_seconds=25.0,
            ),
        ]

    @pytest.fixture
    def circular_tasks(self):
        """Create tasks with circular dependencies."""
        return [
            OptimizableTask(
                task_id="task-x",
                dependencies=["task-z"],
            ),
            OptimizableTask(
                task_id="task-y",
                dependencies=["task-x"],
            ),
            OptimizableTask(
                task_id="task-z",
                dependencies=["task-y"],
            ),
        ]

    def test_build_graph_independent_tasks(self, builder, independent_tasks):
        """Test building graph with independent tasks."""
        graph = builder.build_graph(independent_tasks)

        assert graph.task_count == 5
        assert graph.edge_count == 0
        assert graph.has_cycles is False
        assert graph.max_depth == 0

    def test_build_graph_dependent_tasks(self, builder, dependent_tasks):
        """Test building graph with dependencies."""
        graph = builder.build_graph(dependent_tasks)

        assert graph.task_count == 4
        assert graph.edge_count == 4  # a->b, a->c, b->d, c->d
        assert graph.has_cycles is False

        # Check depths
        assert graph.nodes["task-a"].depth == 0
        assert graph.nodes["task-b"].depth == 1
        assert graph.nodes["task-c"].depth == 1
        assert graph.nodes["task-d"].depth == 2

    def test_build_graph_circular_dependencies(self, builder, circular_tasks):
        """Test detecting circular dependencies."""
        graph = builder.build_graph(circular_tasks)

        assert graph.has_cycles is True

    def test_get_ready_tasks(self, builder, dependent_tasks):
        """Test getting tasks ready for execution."""
        graph = builder.build_graph(dependent_tasks)

        # Initially, only task-a is ready
        ready = graph.get_ready_tasks(set())
        assert ready == ["task-a"]

        # After task-a completes, task-b and task-c are ready
        ready = graph.get_ready_tasks({"task-a"})
        assert set(ready) == {"task-b", "task-c"}

        # After task-b completes, task-d still needs task-c
        ready = graph.get_ready_tasks({"task-a", "task-b"})
        assert ready == ["task-c"]

        # After all dependencies, task-d is ready
        ready = graph.get_ready_tasks({"task-a", "task-b", "task-c"})
        assert ready == ["task-d"]

    def test_get_dependents(self, builder, dependent_tasks):
        """Test getting tasks that depend on a task."""
        graph = builder.build_graph(dependent_tasks)

        dependents_a = graph.get_dependents("task-a")
        assert dependents_a == {"task-b", "task-c"}

        dependents_b = graph.get_dependents("task-b")
        assert dependents_b == {"task-d"}

        dependents_d = graph.get_dependents("task-d")
        assert dependents_d == set()

    def test_get_dependencies(self, builder, dependent_tasks):
        """Test getting a task's dependencies."""
        graph = builder.build_graph(dependent_tasks)

        deps_a = graph.get_dependencies("task-a")
        assert deps_a == set()

        deps_b = graph.get_dependencies("task-b")
        assert deps_b == {"task-a"}

        deps_d = graph.get_dependencies("task-d")
        assert deps_d == {"task-b", "task-c"}

    def test_critical_path(self, builder, dependent_tasks):
        """Test finding the critical path."""
        graph = builder.build_graph(dependent_tasks)

        # Critical path should be the longest chain
        # In this case: task-a -> task-c -> task-d (or b->d)
        assert len(graph.critical_path) >= 2
        assert "task-d" in graph.critical_path
        assert "task-a" in graph.critical_path

    def test_get_execution_layers(self, builder, dependent_tasks):
        """Test getting execution layers."""
        graph = builder.build_graph(dependent_tasks)
        layers = builder.get_execution_layers(graph)

        assert len(layers) == 3  # Depth 0, 1, 2
        assert "task-a" in layers[0]
        assert "task-b" in layers[1]
        assert "task-c" in layers[1]
        assert "task-d" in layers[2]

    def test_estimate_sequential_duration(self, builder, dependent_tasks):
        """Test estimating sequential duration."""
        graph = builder.build_graph(dependent_tasks)
        duration = builder.estimate_sequential_duration(graph)

        # 10 + 15 + 20 + 25 = 70
        assert duration == 70.0

    def test_estimate_optimal_duration(self, builder, dependent_tasks):
        """Test estimating optimal (critical path) duration."""
        graph = builder.build_graph(dependent_tasks)
        duration = builder.estimate_optimal_duration(graph)

        # Critical path: a -> c -> d = 10 + 20 + 25 = 55
        # or a -> b -> d = 10 + 15 + 25 = 50
        # Should pick the longer one
        assert duration >= 50.0

    def test_unknown_dependency(self, builder):
        """Test handling unknown dependencies."""
        tasks = [
            OptimizableTask(
                task_id="task-1",
                dependencies=["non-existent"],
            ),
        ]
        graph = builder.build_graph(tasks)

        # Should still build, just log warning
        assert graph.task_count == 1

    def test_empty_task_list(self, builder):
        """Test building graph with no tasks."""
        graph = builder.build_graph([])

        assert graph.task_count == 0
        assert graph.edge_count == 0


class TestDependencyGraph:
    """Tests for DependencyGraph dataclass."""

    def test_empty_graph(self):
        """Test empty graph properties."""
        graph = DependencyGraph()

        assert graph.task_count == 0
        assert graph.edge_count == 0
        assert graph.has_cycles is False

    def test_get_ready_tasks_empty_completed(self):
        """Test get_ready_tasks with empty completed set."""
        graph = DependencyGraph()
        node1 = DependencyNode(
            task_id="task-1",
            dependencies=set(),
        )
        node2 = DependencyNode(
            task_id="task-2",
            dependencies={"task-1"},
        )
        graph.nodes = {"task-1": node1, "task-2": node2}

        ready = graph.get_ready_tasks(set())
        assert ready == ["task-1"]


class TestDependencyNode:
    """Tests for DependencyNode dataclass."""

    def test_create_node(self):
        """Test creating a dependency node."""
        node = DependencyNode(
            task_id="test-node",
            task=OptimizableTask(task_id="test-node"),
            dependencies={"dep-1", "dep-2"},
            dependents={"dependent-1"},
            depth=2,
        )

        assert node.task_id == "test-node"
        assert len(node.dependencies) == 2
        assert len(node.dependents) == 1
        assert node.depth == 2
