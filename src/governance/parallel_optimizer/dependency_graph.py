"""
Dependency Graph Builder for Parallel Execution Optimizer (ST-GOV-010).

Builds and analyzes task dependency graphs for parallel execution optimization.
Leverages existing DependencyChecker from sentinel module.

Story: ST-GOV-010
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

from src.governance.parallel_optimizer.models import (
    OptimizableTask,
    TaskPriority,
)
from src.governance.sentinel.dependency_checker import (
    DependencyChecker,
    DependencyDeclaration,
    Dependency,
    DependencyType,
)

logger = logging.getLogger(__name__)


@dataclass
class DependencyNode:
    """
    A node in the dependency graph.

    Attributes:
        task_id: The task ID
        task: The optimizable task
        dependencies: Set of task IDs this task depends on
        dependents: Set of task IDs that depend on this task
        depth: Depth in the dependency tree (0 = no dependencies)
    """

    task_id: str
    task: Optional[OptimizableTask] = None
    dependencies: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)
    depth: int = 0


@dataclass
class DependencyGraph:
    """
    Complete dependency graph for a set of tasks.

    Attributes:
        nodes: Map of task_id to DependencyNode
        edges: List of (from_task, to_task) edges
        has_cycles: Whether the graph has circular dependencies
        critical_path: Longest path through the graph
        max_depth: Maximum depth in the graph
    """

    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    has_cycles: bool = False
    critical_path: list[str] = field(default_factory=list)
    max_depth: int = 0

    @property
    def task_count(self) -> int:
        """Number of tasks in the graph."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Number of dependency edges."""
        return len(self.edges)

    def get_ready_tasks(self, completed: set[str]) -> list[str]:
        """
        Get tasks that are ready to execute (all dependencies satisfied).

        Args:
            completed: Set of completed task IDs

        Returns:
            List of task IDs ready for execution
        """
        ready = []
        for task_id, node in self.nodes.items():
            if task_id in completed:
                continue
            if node.dependencies.issubset(completed):
                ready.append(task_id)
        return ready

    def get_dependents(self, task_id: str) -> set[str]:
        """Get all tasks that depend on the given task."""
        node = self.nodes.get(task_id)
        if not node:
            return set()
        return node.dependents.copy()

    def get_dependencies(self, task_id: str) -> set[str]:
        """Get all tasks the given task depends on."""
        node = self.nodes.get(task_id)
        if not node:
            return set()
        return node.dependencies.copy()


class DependencyGraphBuilder:
    """
    Builds and analyzes dependency graphs for parallel execution.

    This class wraps the existing DependencyChecker and adds graph-based
    analysis capabilities for parallel execution optimization.

    Usage:
        builder = DependencyGraphBuilder()
        graph = builder.build_graph(tasks)
        if graph.has_cycles:
            print("Cannot execute - circular dependencies!")
        else:
            ready = graph.get_ready_tasks(set())
    """

    def __init__(self):
        """Initialize the dependency graph builder."""
        self._checker = DependencyChecker()

    def build_graph(self, tasks: list[OptimizableTask]) -> DependencyGraph:
        """
        Build a dependency graph from a list of tasks.

        Args:
            tasks: List of optimizable tasks

        Returns:
            DependencyGraph with all relationships analyzed
        """
        graph = DependencyGraph()

        # Create nodes for all tasks
        for task in tasks:
            node = DependencyNode(
                task_id=task.task_id,
                task=task,
                dependencies=set(task.dependencies),
            )
            graph.nodes[task.task_id] = node

        # Build edges and reverse dependencies
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in graph.nodes:
                    graph.edges.append((dep_id, task.task_id))
                    graph.nodes[dep_id].dependents.add(task.task_id)
                else:
                    logger.warning(
                        f"Task {task.task_id} depends on unknown task {dep_id}"
                    )

        # Check for cycles using the existing DependencyChecker
        declarations = []
        for task in tasks:
            deps = [
                Dependency(
                    task_id=dep_id,
                    dependency_type=DependencyType.REQUIRES,
                )
                for dep_id in task.dependencies
            ]
            declarations.append(
                DependencyDeclaration(
                    task_id=task.task_id,
                    dependencies=deps,
                )
            )

        self._checker.clear()
        has_cycles, cycle_paths = self._checker.detect_circular_dependencies(
            declarations
        )
        graph.has_cycles = has_cycles

        if has_cycles:
            logger.warning(f"Circular dependencies detected: {cycle_paths}")
        else:
            # Calculate depths and critical path
            self._calculate_depths(graph)
            self._find_critical_path(graph)

        return graph

    def _calculate_depths(self, graph: DependencyGraph) -> None:
        """
        Calculate the depth of each node in the dependency tree.

        Depth is the longest path from a root (no dependencies) to this node.
        """
        visited = set()

        def get_depth(task_id: str) -> int:
            if task_id in visited:
                return graph.nodes[task_id].depth

            node = graph.nodes.get(task_id)
            if not node:
                return 0

            visited.add(task_id)

            if not node.dependencies:
                node.depth = 0
                return 0

            max_dep_depth = 0
            for dep_id in node.dependencies:
                if dep_id in graph.nodes:
                    dep_depth = get_depth(dep_id)
                    max_dep_depth = max(max_dep_depth, dep_depth + 1)

            node.depth = max_dep_depth
            return max_dep_depth

        for task_id in graph.nodes:
            depth = get_depth(task_id)
            graph.max_depth = max(graph.max_depth, depth)

    def _find_critical_path(self, graph: DependencyGraph) -> None:
        """
        Find the critical path through the dependency graph.

        The critical path is the longest path from any root to any leaf.
        This determines the minimum possible execution time.
        """
        if not graph.nodes:
            return

        # Find all leaf nodes (no dependents)
        leaves = [
            task_id for task_id, node in graph.nodes.items() if not node.dependents
        ]

        if not leaves:
            # All nodes have dependents (cycle?), pick any
            leaves = list(graph.nodes.keys())[:1]

        # For each leaf, trace back to find the longest path
        best_path: list[str] = []

        def trace_path(task_id: str, path: list[str]) -> list[str]:
            node = graph.nodes.get(task_id)
            if not node:
                return path

            path = [task_id] + path

            if not node.dependencies:
                return path

            best_subpath = path
            for dep_id in node.dependencies:
                if dep_id in graph.nodes:
                    subpath = trace_path(dep_id, path)
                    if len(subpath) > len(best_subpath):
                        best_subpath = subpath

            return best_subpath

        for leaf in leaves:
            path = trace_path(leaf, [])
            if len(path) > len(best_path):
                best_path = path

        graph.critical_path = best_path

    def get_execution_layers(self, graph: DependencyGraph) -> list[list[str]]:
        """
        Get tasks organized by execution layer (depth).

        Tasks in the same layer have no dependencies on each other
        and can potentially run in parallel.

        Args:
            graph: The dependency graph

        Returns:
            List of layers, where each layer is a list of task IDs
        """
        if graph.has_cycles:
            logger.warning("Cannot get execution layers for graph with cycles")
            return []

        layers: dict[int, list[str]] = {}
        for task_id, node in graph.nodes.items():
            depth = node.depth
            if depth not in layers:
                layers[depth] = []
            layers[depth].append(task_id)

        # Sort by depth and return as list of lists
        max_depth = max(layers.keys()) if layers else 0
        return [layers.get(d, []) for d in range(max_depth + 1)]

    def estimate_sequential_duration(self, graph: DependencyGraph) -> float:
        """
        Estimate total duration if tasks run sequentially.

        Args:
            graph: The dependency graph

        Returns:
            Estimated duration in seconds
        """
        total = 0.0
        for node in graph.nodes.values():
            if node.task:
                total += node.task.estimated_duration_seconds
        return total

    def estimate_optimal_duration(self, graph: DependencyGraph) -> float:
        """
        Estimate minimum possible duration with optimal parallelization.

        This is based on the critical path - the longest dependency chain.

        Args:
            graph: The dependency graph

        Returns:
            Estimated minimum duration in seconds
        """
        if not graph.critical_path:
            return 0.0

        total = 0.0
        for task_id in graph.critical_path:
            node = graph.nodes.get(task_id)
            if node and node.task:
                total += node.task.estimated_duration_seconds

        return total
