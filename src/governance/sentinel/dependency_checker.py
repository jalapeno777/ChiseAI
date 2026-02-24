"""
Dependency Checker - Validates task dependencies (ST-GOV-003).

Parses task dependencies from YAML/JSON, detects circular dependencies,
and validates dependency completeness.

Story: ST-GOV-003
"""

import fnmatch
import json
import logging
from dataclasses import dataclass, field
from enum import Enum

import yaml

logger = logging.getLogger(__name__)


class DependencyType(str, Enum):
    """Types of task dependencies."""

    BLOCKS = "blocks"  # This task blocks another
    BLOCKED_BY = "blocked_by"  # This task is blocked by another
    DEPENDS_ON = "depends_on"  # Soft dependency (should complete first)
    REQUIRES = "requires"  # Hard dependency (must complete first)


@dataclass
class Dependency:
    """A single dependency relationship."""

    task_id: str
    dependency_type: DependencyType
    scope_globs: list[str] = field(default_factory=list)
    description: str | None = None


@dataclass
class DependencyDeclaration:
    """Full dependency declaration for a task."""

    task_id: str
    dependencies: list[Dependency] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    """What this task provides to other tasks."""

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyDeclaration":
        """Parse from dictionary (YAML/JSON loaded)."""
        deps = []
        for dep_data in data.get("dependencies", []):
            dep_type_str = dep_data.get("type", "depends_on")
            try:
                dep_type = DependencyType(dep_type_str)
            except ValueError:
                dep_type = DependencyType.DEPENDS_ON

            deps.append(
                Dependency(
                    task_id=dep_data.get("task_id", ""),
                    dependency_type=dep_type,
                    scope_globs=dep_data.get("scope_globs", []),
                    description=dep_data.get("description"),
                )
            )

        return cls(
            task_id=data.get("task_id", ""),
            dependencies=deps,
            provides=data.get("provides", []),
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "DependencyDeclaration":
        """Parse from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data if data else {})

    @classmethod
    def from_json(cls, json_str: str) -> "DependencyDeclaration":
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class DependencyCheckResult:
    """Result of dependency validation."""

    is_valid: bool
    has_circular_dependencies: bool
    missing_dependencies: list[str]
    circular_paths: list[list[str]]
    undeclared_scopes: list[str]
    message: str


class DependencyChecker:
    """
    Validates task dependencies for completeness and safety.

    Features:
    - Parse dependencies from YAML/JSON
    - Detect circular dependencies using DFS
    - Validate scope declarations
    - Check for missing required dependencies

    Usage:
        checker = DependencyChecker()
        result = checker.check_dependencies(declarations)
        if not result.is_valid:
            print(f"Invalid: {result.message}")
    """

    def __init__(self, known_tasks: dict[str, DependencyDeclaration] | None = None):
        """
        Initialize the dependency checker.

        Args:
            known_tasks: Optional dict of task_id -> DependencyDeclaration for context
        """
        self.known_tasks = known_tasks or {}
        self._dependency_graph: dict[str, set[str]] = {}
        self._reverse_graph: dict[str, set[str]] = {}

    def register_task(self, declaration: DependencyDeclaration) -> None:
        """Register a task's dependency declaration."""
        self.known_tasks[declaration.task_id] = declaration
        self._build_graphs()

    def _build_graphs(self) -> None:
        """Build forward and reverse dependency graphs."""
        self._dependency_graph.clear()
        self._reverse_graph.clear()

        for task_id, decl in self.known_tasks.items():
            self._dependency_graph[task_id] = set()
            for dep in decl.dependencies:
                if dep.dependency_type in (
                    DependencyType.DEPENDS_ON,
                    DependencyType.REQUIRES,
                    DependencyType.BLOCKED_BY,
                ):
                    self._dependency_graph[task_id].add(dep.task_id)

                    if dep.task_id not in self._reverse_graph:
                        self._reverse_graph[dep.task_id] = set()
                    self._reverse_graph[dep.task_id].add(task_id)

    def detect_circular_dependencies(
        self, declarations: list[DependencyDeclaration] | None = None
    ) -> tuple[bool, list[list[str]]]:
        """
        Detect circular dependencies using DFS cycle detection.

        Args:
            declarations: Optional list to check (uses registered tasks if None)

        Returns:
            Tuple of (has_cycles, list_of_circular_paths)
        """
        if declarations:
            # Temporarily add declarations
            for decl in declarations:
                self.known_tasks[decl.task_id] = decl
            self._build_graphs()

        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._dependency_graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in list(self._dependency_graph.keys()):
            if node not in visited:
                dfs(node, [])

        return len(cycles) > 0, cycles

    def check_missing_dependencies(
        self, declaration: DependencyDeclaration
    ) -> list[str]:
        """
        Check for dependencies on unknown tasks.

        Args:
            declaration: The declaration to check

        Returns:
            List of missing dependency task IDs
        """
        missing = []
        for dep in declaration.dependencies:
            if (
                dep.dependency_type
                in (DependencyType.DEPENDS_ON, DependencyType.REQUIRES)
                and dep.task_id
                and dep.task_id not in self.known_tasks
            ):
                missing.append(dep.task_id)
        return missing

    def check_scope_completeness(
        self, declaration: DependencyDeclaration, required_scopes: list[str]
    ) -> list[str]:
        """
        Check if all required scopes are declared as dependencies.

        Args:
            declaration: The declaration to check
            required_scopes: Scopes that must be declared

        Returns:
            List of undeclared scopes
        """
        declared_scopes = set()
        for dep in declaration.dependencies:
            declared_scopes.update(dep.scope_globs)

        undeclared = []
        for scope in required_scopes:
            # Check if scope matches any declared glob pattern
            matched = False
            for pattern in declared_scopes:
                # Handle ** recursive globs
                if "**" in pattern:
                    # Convert ** pattern for matching
                    # src/api/**/*.py should match:
                    # - src/api/routes.py (if pattern is src/api/**/*.py or src/api/**)
                    # - src/api/foo/bar.py
                    base = pattern.split("**")[0]
                    suffix = pattern.split("**")[1] if "**" in pattern else ""

                    if scope.startswith(base):
                        # Check suffix match
                        remaining = scope[len(base) :]
                        if suffix:
                            # suffix might be /*.py or /.py or similar
                            suffix_clean = suffix.lstrip("/")
                            # ** with suffix: remaining should end with the suffix (minus leading /)
                            if suffix_clean and remaining.endswith(
                                suffix_clean.lstrip("*")
                            ):
                                matched = True
                                break
                            elif suffix == "/*" or suffix == "/**":
                                # Matches any path
                                matched = True
                                break
                            elif not suffix_clean:
                                matched = True
                                break
                        else:
                            # No suffix, just prefix match
                            matched = True
                            break
                if fnmatch.fnmatch(scope, pattern):
                    matched = True
                    break
            if not matched:
                undeclared.append(scope)

        return undeclared

    def check_dependencies(
        self,
        declarations: list[DependencyDeclaration],
        required_scopes: dict[str, list[str]] | None = None,
    ) -> DependencyCheckResult:
        """
        Comprehensive dependency validation.

        Args:
            declarations: List of declarations to validate
            required_scopes: Optional map of task_id -> required scopes

        Returns:
            DependencyCheckResult with all validation findings
        """
        # Register all declarations
        for decl in declarations:
            self.known_tasks[decl.task_id] = decl
        self._build_graphs()

        # Check for circular dependencies
        has_cycles, circular_paths = self.detect_circular_dependencies()

        # Check for missing dependencies
        all_missing = []
        for decl in declarations:
            missing = self.check_missing_dependencies(decl)
            all_missing.extend(missing)

        # Check scope completeness
        all_undeclared = []
        if required_scopes:
            for decl in declarations:
                scopes = required_scopes.get(decl.task_id, [])
                undeclared = self.check_scope_completeness(decl, scopes)
                all_undeclared.extend(undeclared)

        # Build result message
        messages = []
        if has_cycles:
            messages.append(f"Circular dependencies detected: {circular_paths}")
        if all_missing:
            messages.append(f"Missing dependencies: {all_missing}")
        if all_undeclared:
            messages.append(f"Undeclared scopes: {all_undeclared}")

        is_valid = not (has_cycles or all_missing or all_undeclared)
        message = "All dependencies valid" if is_valid else "; ".join(messages)

        return DependencyCheckResult(
            is_valid=is_valid,
            has_circular_dependencies=has_cycles,
            missing_dependencies=list(set(all_missing)),
            circular_paths=circular_paths,
            undeclared_scopes=list(set(all_undeclared)),
            message=message,
        )

    def get_execution_order(self) -> list[str]:
        """
        Get a valid execution order using topological sort.

        Returns:
            List of task IDs in valid execution order

        Raises:
            ValueError: If circular dependencies exist
        """
        has_cycles, _ = self.detect_circular_dependencies()
        if has_cycles:
            raise ValueError(
                "Cannot determine execution order with circular dependencies"
            )

        # Kahn's algorithm for topological sort
        in_degree = {node: 0 for node in self._dependency_graph}
        for node in self._dependency_graph:
            for neighbor in self._dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] = in_degree.get(neighbor, 0)

        for node in self._dependency_graph:
            for dep in self._dependency_graph[node]:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in self._dependency_graph.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    def clear(self) -> None:
        """Clear all registered tasks."""
        self.known_tasks.clear()
        self._dependency_graph.clear()
        self._reverse_graph.clear()
