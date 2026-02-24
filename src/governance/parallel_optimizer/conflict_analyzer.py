"""
Scope Conflict Analyzer for Parallel Execution Optimizer (ST-GOV-010).

Analyzes scope conflicts between tasks for safe parallel execution.
Leverages existing ConflictDetector from sentinel module.

Story: ST-GOV-010
"""

import logging
from dataclasses import dataclass, field

from src.governance.parallel_optimizer.models import (
    ConflictAnalysis,
    OptimizableTask,
)
from src.governance.sentinel.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
    ScopeDeclaration,
)

logger = logging.getLogger(__name__)


@dataclass
class ConflictMatrix:
    """
    Matrix representing conflicts between all task pairs.

    Attributes:
        task_ids: Ordered list of task IDs
        matrix: 2D matrix where matrix[i][j] = True if tasks conflict
        conflict_details: Map of (task_id1, task_id2) -> ConflictInfo
    """

    task_ids: list[str] = field(default_factory=list)
    matrix: list[list[bool]] = field(default_factory=list)
    conflict_details: dict[tuple[str, str], ConflictAnalysis] = field(
        default_factory=dict
    )

    def has_conflict(self, task_id1: str, task_id2: str) -> bool:
        """Check if two tasks have a conflict."""
        try:
            i = self.task_ids.index(task_id1)
            j = self.task_ids.index(task_id2)
            return self.matrix[i][j]
        except ValueError:
            return False

    def get_conflicting_tasks(self, task_id: str) -> list[str]:
        """Get all tasks that conflict with the given task."""
        try:
            i = self.task_ids.index(task_id)
            return [
                self.task_ids[j] for j in range(len(self.task_ids)) if self.matrix[i][j]
            ]
        except ValueError:
            return []

    def get_non_conflicting_groups(self) -> list[list[str]]:
        """
        Get groups of tasks that don't conflict with each other.

        Uses a greedy graph coloring approach to find independent sets.
        """
        if not self.task_ids:
            return []

        groups: list[list[str]] = []
        assigned: set[str] = set()

        for task_id in self.task_ids:
            if task_id in assigned:
                continue

            # Try to add to existing group
            added = False
            for group in groups:
                if not any(self.has_conflict(task_id, t) for t in group):
                    group.append(task_id)
                    assigned.add(task_id)
                    added = True
                    break

            if not added:
                groups.append([task_id])
                assigned.add(task_id)

        return groups


class ScopeConflictAnalyzer:
    """
    Analyzes scope conflicts between tasks for parallel execution.

    This class wraps the existing ConflictDetector and adds batch analysis
    and conflict matrix generation for optimization.

    Usage:
        analyzer = ScopeConflictAnalyzer()
        matrix = analyzer.build_conflict_matrix(tasks)
        if matrix.has_conflict("task-a", "task-b"):
            print("Cannot run task-a and task-b in parallel!")
    """

    def __init__(self, redis_client=None):
        """
        Initialize the conflict analyzer.

        Args:
            redis_client: Optional Redis client for checking live ownership
        """
        self._detector = ConflictDetector(redis_client=redis_client)

    def analyze_task_pair(
        self, task1: OptimizableTask, task2: OptimizableTask
    ) -> ConflictAnalysis:
        """
        Analyze conflicts between two specific tasks.

        Args:
            task1: First task
            task2: Second task

        Returns:
            ConflictAnalysis with conflict details
        """
        scope1 = ScopeDeclaration(
            task_id=task1.task_id,
            scope_globs=task1.scope_globs,
        )
        scope2 = ScopeDeclaration(
            task_id=task2.task_id,
            scope_globs=task2.scope_globs,
        )

        result = self._detector.detect_conflicts([scope1, scope2])

        analysis = ConflictAnalysis(
            has_conflicts=result.has_conflicts,
            conflict_pairs=(
                [(task1.task_id, task2.task_id)] if result.has_conflicts else []
            ),
            conflict_types=[c.conflict_type.value for c in result.conflicts],
            severity=(
                "critical"
                if result.has_critical_conflicts
                else ("warning" if result.has_conflicts else "none")
            ),
            resolution_suggestions=[
                c.resolution_hint for c in result.conflicts if c.resolution_hint
            ],
        )

        return analysis

    def build_conflict_matrix(self, tasks: list[OptimizableTask]) -> ConflictMatrix:
        """
        Build a complete conflict matrix for all tasks.

        Args:
            tasks: List of tasks to analyze

        Returns:
            ConflictMatrix with all pairwise conflict information
        """
        task_ids = [t.task_id for t in tasks]
        n = len(task_ids)

        # Initialize matrix
        matrix = [[False] * n for _ in range(n)]
        conflict_details: dict[tuple[str, str], ConflictAnalysis] = {}

        # Create scope declarations
        scopes = [
            ScopeDeclaration(task_id=t.task_id, scope_globs=t.scope_globs)
            for t in tasks
        ]

        # Batch check all conflicts using the existing detector
        full_result = self._detector.detect_conflicts(scopes)

        # Build matrix from conflict results
        for conflict in full_result.conflicts:
            if len(conflict.task_ids) >= 2:
                tid1, tid2 = conflict.task_ids[0], conflict.task_ids[1]
                try:
                    i = task_ids.index(tid1)
                    j = task_ids.index(tid2)
                    # Only mark as conflict if critical
                    if conflict.severity == ConflictSeverity.CRITICAL:
                        matrix[i][j] = True
                        matrix[j][i] = True

                        # Store details
                        key = (min(tid1, tid2), max(tid1, tid2))
                        if key not in conflict_details:
                            conflict_details[key] = ConflictAnalysis(
                                has_conflicts=True,
                                conflict_pairs=[(tid1, tid2)],
                                conflict_types=[conflict.conflict_type.value],
                                severity="critical",
                                resolution_suggestions=(
                                    [conflict.resolution_hint]
                                    if conflict.resolution_hint
                                    else []
                                ),
                            )
                        else:
                            conflict_details[key].conflict_types.append(
                                conflict.conflict_type.value
                            )
                except ValueError:
                    pass

        return ConflictMatrix(
            task_ids=task_ids,
            matrix=matrix,
            conflict_details=conflict_details,
        )

    def find_max_parallel_group(
        self, tasks: list[OptimizableTask], max_size: int = 10
    ) -> list[str]:
        """
        Find the largest group of tasks that can run in parallel.

        Uses a greedy approach to find a maximal independent set.

        Args:
            tasks: List of tasks to analyze
            max_size: Maximum size of the group

        Returns:
            List of task IDs that can run in parallel
        """
        matrix = self.build_conflict_matrix(tasks)

        # Greedy approach: add tasks that don't conflict with current group
        group: list[str] = []
        for task_id in matrix.task_ids:
            if len(group) >= max_size:
                break

            # Check if this task conflicts with any in the group
            conflicts = any(matrix.has_conflict(task_id, g) for g in group)
            if not conflicts:
                group.append(task_id)

        return group

    def suggest_execution_order(self, tasks: list[OptimizableTask]) -> list[list[str]]:
        """
        Suggest an execution order (batches) that avoids conflicts.

        Groups tasks into batches where each batch contains tasks
        that can safely run in parallel.

        Args:
            tasks: List of tasks to schedule

        Returns:
            List of batches, where each batch is a list of task IDs
        """
        matrix = self.build_conflict_matrix(tasks)
        return matrix.get_non_conflicting_groups()

    def get_conflict_count(self, tasks: list[OptimizableTask]) -> int:
        """
        Count the total number of conflicts between tasks.

        Args:
            tasks: List of tasks to analyze

        Returns:
            Number of conflicting task pairs
        """
        matrix = self.build_conflict_matrix(tasks)
        count = 0
        for i in range(len(matrix.task_ids)):
            for j in range(i + 1, len(matrix.task_ids)):
                if matrix.matrix[i][j]:
                    count += 1
        return count

    def get_conflict_rate(self, tasks: list[OptimizableTask]) -> float:
        """
        Calculate the conflict rate as a percentage.

        Args:
            tasks: List of tasks to analyze

        Returns:
            Conflict rate as percentage (0-100)
        """
        n = len(tasks)
        if n < 2:
            return 0.0

        total_pairs = n * (n - 1) / 2
        conflict_count = self.get_conflict_count(tasks)

        return (conflict_count / total_pairs) * 100 if total_pairs > 0 else 0.0
