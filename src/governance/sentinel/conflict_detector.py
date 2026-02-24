"""
Conflict Detector - Detects scope overlaps and unsafe parallelism (ST-GOV-003).

Checks for scope overlaps using glob patterns, detects shared resource
conflicts, and blocks unsafe parallel execution.

Story: ST-GOV-003
"""

import fnmatch
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ConflictSeverity(str, Enum):
    """Severity of a detected conflict."""

    CRITICAL = "critical"  # Must block execution
    WARNING = "warning"  # Should warn but allow
    INFO = "info"  # Informational only


class ConflictType(str, Enum):
    """Types of conflicts that can be detected."""

    SCOPE_OVERLAP = "scope_overlap"  # Two tasks touch same files
    SHARED_RESOURCE = "shared_resource"  # Shared infra/service dependency
    DATA_RACE = "data_race"  # Concurrent data access
    DEPENDENCY_CONFLICT = "dependency_conflict"  # Conflicting requirements
    GLOBAL_LOCK = "global_lock"  # Competing for global lock


@dataclass
class ScopeDeclaration:
    """Declares what scope a task will modify."""

    task_id: str
    scope_globs: list[str] = field(default_factory=list)
    """Glob patterns for files/dirs this task will modify."""

    read_only_globs: list[str] = field(default_factory=list)
    """Glob patterns for files this task will only read."""

    forbidden_globs: list[str] = field(default_factory=list)
    """Glob patterns this task must NOT touch."""

    shared_resources: list[str] = field(default_factory=list)
    """Shared resources (e.g., 'redis', 'postgres', 'docker') this task uses."""

    global_locks: list[str] = field(default_factory=list)
    """Global locks this task requires (e.g., 'main-merge', 'ci-infra')."""


@dataclass
class Conflict:
    """A detected conflict between tasks."""

    conflict_type: ConflictType
    severity: ConflictSeverity
    task_ids: list[str]
    description: str
    affected_paths: list[str] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    resolution_hint: str | None = None


@dataclass
class ConflictCheckResult:
    """Result of conflict detection."""

    has_conflicts: bool
    has_critical_conflicts: bool
    conflicts: list[Conflict]
    safe_for_parallel: bool
    message: str


class ConflictDetector:
    """
    Detects conflicts between tasks for safe parallel execution.

    Features:
    - Check for scope overlaps using glob patterns
    - Detect shared resource conflicts
    - Identify global lock contention
    - Suggest execution ordering when conflicts exist

    Usage:
        detector = ConflictDetector()
        scope1 = ScopeDeclaration(task_id="A", scope_globs=["src/api/**/*.py"])
        scope2 = ScopeDeclaration(task_id="B", scope_globs=["src/api/routes.py"])
        result = detector.detect_conflicts([scope1, scope2])
        if result.has_critical_conflicts:
            print("Cannot run in parallel!")
    """

    # Global locks that must be acquired exclusively
    GLOBAL_LOCKS = {
        "main-merge",
        "ci-infra",
        "database-migration",
        "terraform-apply",
    }

    # Resources that can cause contention
    SHARED_RESOURCES = {
        "redis",
        "postgres",
        "qdrant",
        "docker",
        "kubernetes",
    }

    def __init__(self, redis_client=None):
        """
        Initialize the conflict detector.

        Args:
            redis_client: Optional Redis client for checking live ownership
        """
        self.redis_client = redis_client
        self._registered_scopes: dict[str, ScopeDeclaration] = {}

    def register_scope(self, scope: ScopeDeclaration) -> None:
        """Register a task's scope declaration."""
        self._registered_scopes[scope.task_id] = scope

    def _paths_overlap(self, path1: str, path2: str) -> bool:
        """Check if two paths/globs overlap."""
        # Normalize paths
        p1 = path1.strip().lstrip("./")
        p2 = path2.strip().lstrip("./")

        # Direct match
        if p1 == p2:
            return True

        # Check if either matches the other's pattern
        if fnmatch.fnmatch(p1, p2) or fnmatch.fnmatch(p2, p1):
            return True

        # Check parent-child relationship
        # If one path is a prefix of the other (considering directory boundaries)
        if p1.endswith("**") or p2.endswith("**"):
            prefix1 = p1.rstrip("*").rstrip("/")
            prefix2 = p2.rstrip("*").rstrip("/")
            if p1.startswith(prefix2) or p2.startswith(prefix1):
                return True

        # Check if paths share a common prefix (one is under the other)
        parts1 = p1.split("/")
        parts2 = p2.split("/")

        # Check for overlapping directories
        min_len = min(len(parts1), len(parts2))
        common_prefix = 0
        for i in range(min_len):
            if "*" in parts1[i] or "*" in parts2[i]:
                # Wildcard match
                if not (
                    fnmatch.fnmatch(parts1[i], parts2[i])
                    or fnmatch.fnmatch(parts2[i], parts1[i])
                ):
                    break
                common_prefix = i + 1
            elif parts1[i] == parts2[i]:
                common_prefix = i + 1
            else:
                break

        # If they share significant prefix and one goes deeper
        return bool(
            common_prefix > 0
            and (common_prefix == len(parts1) - 1 or common_prefix == len(parts2) - 1)
        )

    def _check_scope_overlap(
        self, scope1: ScopeDeclaration, scope2: ScopeDeclaration
    ) -> list[Conflict]:
        """Check for file/directory scope overlaps between two tasks."""
        conflicts = []

        # Check write-write conflicts (both modifying same files)
        for glob1 in scope1.scope_globs:
            for glob2 in scope2.scope_globs:
                if self._paths_overlap(glob1, glob2):
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.SCOPE_OVERLAP,
                            severity=ConflictSeverity.CRITICAL,
                            task_ids=[scope1.task_id, scope2.task_id],
                            description=f"Both tasks modify overlapping scope: {glob1} <-> {glob2}",
                            affected_paths=[glob1, glob2],
                            resolution_hint="Run sequentially or split scope more precisely",
                        )
                    )

        # Check write-read conflicts with forbidden areas
        for glob1 in scope1.scope_globs:
            for forbidden in scope2.forbidden_globs:
                if self._paths_overlap(glob1, forbidden):
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.SCOPE_OVERLAP,
                            severity=ConflictSeverity.CRITICAL,
                            task_ids=[scope1.task_id, scope2.task_id],
                            description=f"Task {scope1.task_id} touches forbidden scope of {scope2.task_id}: {glob1}",
                            affected_paths=[glob1, forbidden],
                            resolution_hint=f"Move changes outside {forbidden} or update forbidden scope",
                        )
                    )

        return conflicts

    def _check_shared_resources(
        self, scope1: ScopeDeclaration, scope2: ScopeDeclaration
    ) -> list[Conflict]:
        """Check for shared resource conflicts."""
        conflicts = []

        shared = set(scope1.shared_resources) & set(scope2.shared_resources)

        for resource in shared:
            # Some resources are safe for concurrent read but not write
            if resource in ("redis", "postgres"):
                # Check if both are writing
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.SHARED_RESOURCE,
                        severity=ConflictSeverity.WARNING,
                        task_ids=[scope1.task_id, scope2.task_id],
                        description=f"Both tasks use shared resource: {resource}",
                        affected_resources=[resource],
                        resolution_hint="Ensure operations are on different keys/tables or run sequentially",
                    )
                )
            elif resource in ("docker", "kubernetes"):
                # Infrastructure changes are more sensitive
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.SHARED_RESOURCE,
                        severity=ConflictSeverity.CRITICAL,
                        task_ids=[scope1.task_id, scope2.task_id],
                        description=f"Both tasks modify infrastructure: {resource}",
                        affected_resources=[resource],
                        resolution_hint="Run infrastructure changes sequentially",
                    )
                )

        return conflicts

    def _check_global_locks(
        self, scope1: ScopeDeclaration, scope2: ScopeDeclaration
    ) -> list[Conflict]:
        """Check for global lock contention."""
        conflicts = []

        common_locks = set(scope1.global_locks) & set(scope2.global_locks)

        for lock in common_locks:
            conflicts.append(
                Conflict(
                    conflict_type=ConflictType.GLOBAL_LOCK,
                    severity=ConflictSeverity.CRITICAL,
                    task_ids=[scope1.task_id, scope2.task_id],
                    description=f"Both tasks require global lock: {lock}",
                    affected_resources=[lock],
                    resolution_hint="Tasks requiring the same global lock must run sequentially",
                )
            )

        return conflicts

    def detect_conflicts(self, scopes: list[ScopeDeclaration]) -> ConflictCheckResult:
        """
        Detect all conflicts between the given scope declarations.

        Args:
            scopes: List of scope declarations to check

        Returns:
            ConflictCheckResult with all detected conflicts
        """
        all_conflicts: list[Conflict] = []

        # Check all pairs
        for i, scope1 in enumerate(scopes):
            for scope2 in scopes[i + 1 :]:
                # Check scope overlaps
                all_conflicts.extend(self._check_scope_overlap(scope1, scope2))

                # Check shared resources
                all_conflicts.extend(self._check_shared_resources(scope1, scope2))

                # Check global locks
                all_conflicts.extend(self._check_global_locks(scope1, scope2))

        has_critical = any(
            c.severity == ConflictSeverity.CRITICAL for c in all_conflicts
        )

        message = (
            "No conflicts detected - safe for parallel execution"
            if not all_conflicts
            else f"Found {len(all_conflicts)} conflict(s), {sum(1 for c in all_conflicts if c.severity == ConflictSeverity.CRITICAL)} critical"
        )

        return ConflictCheckResult(
            has_conflicts=len(all_conflicts) > 0,
            has_critical_conflicts=has_critical,
            conflicts=all_conflicts,
            safe_for_parallel=not has_critical,
            message=message,
        )

    def check_redis_ownership(self, scope_globs: list[str]) -> dict[str, str]:
        """
        Check if any scope is already owned in Redis.

        Args:
            scope_globs: List of scope glob patterns to check

        Returns:
            Dict mapping scope to current owner (if any)
        """
        if not self.redis_client:
            return {}

        ownership = {}
        # This would check Redis hash bmad:chiseai:ownership
        # For each scope, convert to slug and check
        for scope in scope_globs:
            slug = scope.strip().lstrip("./").replace("/", ":").lower()
            try:
                owner = self.redis_client.hget("bmad:chiseai:ownership", slug)
                if owner:
                    ownership[scope] = (
                        owner.decode() if isinstance(owner, bytes) else owner
                    )
            except Exception as e:
                logger.warning(f"Failed to check Redis ownership for {slug}: {e}")

        return ownership

    def get_suggested_order(self, scopes: list[ScopeDeclaration]) -> list[str]:
        """
        Suggest an execution order that avoids conflicts.

        Args:
            scopes: List of scope declarations

        Returns:
            List of task IDs in suggested execution order
        """
        result = self.detect_conflicts(scopes)
        if result.safe_for_parallel:
            return [s.task_id for s in scopes]

        # Build a conflict graph
        conflict_graph: dict[str, set[str]] = {s.task_id: set() for s in scopes}

        for conflict in result.conflicts:
            if conflict.severity == ConflictSeverity.CRITICAL:
                for i, tid1 in enumerate(conflict.task_ids):
                    for tid2 in conflict.task_ids[i + 1 :]:
                        conflict_graph[tid1].add(tid2)
                        conflict_graph[tid2].add(tid1)

        # Simple ordering: tasks with fewer conflicts first
        # This is a heuristic; real topological sort would be better
        ordered = sorted(
            scopes, key=lambda s: len(conflict_graph.get(s.task_id, set()))
        )

        # Group non-conflicting tasks
        groups: list[list[str]] = []
        for scope in ordered:
            placed = False
            for group in groups:
                # Check if this task conflicts with any in the group
                if not any(
                    scope.task_id in conflict_graph.get(tid, set()) for tid in group
                ):
                    group.append(scope.task_id)
                    placed = True
                    break
            if not placed:
                groups.append([scope.task_id])

        # Flatten for return (sequential groups)
        return [tid for group in groups for tid in group]

    def clear(self) -> None:
        """Clear all registered scopes."""
        self._registered_scopes.clear()
