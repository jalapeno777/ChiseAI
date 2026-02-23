"""
Task Decomposition Sentinel - Core Implementation (ST-GOV-003).

Enforces task size limits, validates dependencies, detects conflicts,
and requires decomposition approval for oversized tasks.

Integrated with:
- Feature flags for safe rollout
- Redis for ownership tracking and approval workflow
- Dependency checker for completeness validation
- Conflict detector for parallel safety

Story: ST-GOV-003
Phase: Week 1 Batch 1B
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging
import time

from .dependency_checker import (
    DependencyChecker,
    DependencyDeclaration,
    DependencyCheckResult,
)
from .conflict_detector import (
    ConflictDetector,
    ScopeDeclaration,
    ConflictCheckResult,
)

logger = logging.getLogger(__name__)

# Redis key for feature flag
FEATURE_FLAG_KEY = "chise:feature_flags:governance:task_sentinel_active"
OWNERSHIP_KEY = "bmad:chiseai:ownership"


@dataclass
class SentinelConfig:
    """Configuration for Task Sentinel behavior."""

    max_story_points: int = 5
    """Maximum allowed story points without approval."""

    approval_timeout_hours: int = 24
    """Hours before approval request expires."""

    require_justification: bool = True
    """Whether justification is required for oversized tasks."""

    blocked_task_ttl_days: int = 7
    """Days to keep blocked task records."""

    redis_prefix: str = "chise:governance:sentinel"
    """Redis key prefix for sentinel data."""

    enable_dependency_check: bool = True
    """Enable dependency validation."""

    enable_conflict_detection: bool = True
    """Enable conflict detection for parallel tasks."""

    latency_target_ms: int = 200
    """Target latency for validation operations."""


@dataclass
class TaskInfo:
    """Information about a task being validated."""

    task_id: str
    story_points: float
    title: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    scope_globs: list[str] = field(default_factory=list)
    """Files/directories this task will modify."""

    dependencies: list[str] = field(default_factory=list)
    """Task IDs this task depends on."""


@dataclass
class ValidationResult:
    """Result of task size validation."""

    is_valid: bool
    requires_approval: bool
    story_points: float
    max_allowed: int
    message: str
    task_id: Optional[str] = None
    dependency_result: Optional[DependencyCheckResult] = None
    conflict_result: Optional[ConflictCheckResult] = None
    ownership_conflicts: list[dict] = field(default_factory=list)
    validation_latency_ms: float = 0.0


class TaskSentinel:
    """
    Task Decomposition Sentinel.

    Validates task sizes, dependencies, and scope conflicts to enforce
    decomposition requirements and ensure safe parallel execution.

    Features:
    - Task size validation against max story points
    - Dependency validation and circular dependency detection
    - Scope conflict detection for parallel execution
    - Redis ownership integration
    - Approval workflow for oversized tasks

    Usage:
        sentinel = TaskSentinel(redis_client)
        result = sentinel.validate_task(task_info)
        if result.requires_approval:
            # Request approval workflow
            sentinel.request_approval(task_info, "Complex feature")
    """

    def __init__(
        self,
        redis_client=None,
        config: Optional[SentinelConfig] = None,
    ):
        """
        Initialize the Task Sentinel.

        Args:
            redis_client: Redis client for feature flags and state
            config: Optional custom configuration
        """
        self.redis_client = redis_client
        self.config = config or SentinelConfig()
        self._enabled: Optional[bool] = None
        self._dependency_checker = DependencyChecker()
        self._conflict_detector = ConflictDetector(redis_client=redis_client)

    def is_enabled(self) -> bool:
        """
        Check if the sentinel is enabled via feature flag.

        Returns:
            True if sentinel is active, False otherwise (default: False)
        """
        if self._enabled is not None:
            return self._enabled

        if self.redis_client is None:
            logger.debug("No Redis client, sentinel disabled")
            return False

        try:
            # Read feature flag from Redis
            flag_value = self.redis_client.get(FEATURE_FLAG_KEY)
            enabled = flag_value == "true" or flag_value == b"true"
            self._enabled = enabled
            logger.debug(f"Sentinel feature flag: {self._enabled}")
            return bool(self._enabled)
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return False

    def _check_ownership(self, scope_globs: list[str]) -> list[dict]:
        """
        Check if any scopes are already owned.

        Args:
            scope_globs: List of scope glob patterns to check

        Returns:
            List of ownership conflicts
        """
        if not self.redis_client:
            return []

        conflicts = []
        for scope in scope_globs:
            # Convert scope to slug format
            slug = scope.strip().lstrip("./").replace("/", ":").lower()
            try:
                owner = self.redis_client.hget(OWNERSHIP_KEY, slug)
                if owner:
                    if isinstance(owner, bytes):
                        owner = owner.decode()
                    conflicts.append(
                        {
                            "scope": scope,
                            "slug": slug,
                            "owner": owner,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to check ownership for {slug}: {e}")

        return conflicts

    def validate_task(self, task: TaskInfo) -> ValidationResult:
        """
        Comprehensive task validation.

        Validates:
        1. Task size against max story points
        2. Dependencies (if enabled)
        3. Scope conflicts (if enabled)
        4. Redis ownership

        Args:
            task: Task information to validate

        Returns:
            ValidationResult with all validation findings
        """
        start_time = time.time()

        # Size validation
        max_sp = self.config.max_story_points
        requires_approval = task.story_points > max_sp

        messages = []
        is_valid = not requires_approval

        # Dependency validation
        dep_result = None
        if self.config.enable_dependency_check and task.dependencies:
            # Create a minimal dependency declaration
            from .dependency_checker import Dependency, DependencyType

            decl = DependencyDeclaration(
                task_id=task.task_id,
                dependencies=[
                    Dependency(
                        task_id=dep_id,
                        dependency_type=DependencyType.DEPENDS_ON,
                    )
                    for dep_id in task.dependencies
                ],
            )
            dep_result = self._dependency_checker.check_dependencies([decl])
            if not dep_result.is_valid:
                is_valid = False
                messages.append(dep_result.message)

        # Conflict detection
        conflict_result = None
        if self.config.enable_conflict_detection and task.scope_globs:
            scope = ScopeDeclaration(
                task_id=task.task_id,
                scope_globs=task.scope_globs,
            )
            conflict_result = self._conflict_detector.detect_conflicts([scope])
            # Note: Single task conflict check mainly validates scope patterns

        # Ownership check
        ownership_conflicts = self._check_ownership(task.scope_globs)
        if ownership_conflicts:
            is_valid = False
            for conflict in ownership_conflicts:
                messages.append(
                    f"Scope {conflict['scope']} is owned by {conflict['owner']}"
                )

        # Build message
        if requires_approval:
            messages.insert(
                0,
                f"Task '{task.task_id}' exceeds max story points "
                f"({task.story_points} > {max_sp}). Approval required.",
            )

        latency_ms = (time.time() - start_time) * 1000

        # Check latency target
        if latency_ms > self.config.latency_target_ms:
            logger.warning(
                f"Validation latency {latency_ms:.1f}ms exceeds target "
                f"{self.config.latency_target_ms}ms"
            )

        return ValidationResult(
            is_valid=is_valid,
            requires_approval=requires_approval,
            story_points=task.story_points,
            max_allowed=max_sp,
            message="; ".join(messages)
            if messages
            else f"Task '{task.task_id}' is valid",
            task_id=task.task_id,
            dependency_result=dep_result,
            conflict_result=conflict_result,
            ownership_conflicts=ownership_conflicts,
            validation_latency_ms=latency_ms,
        )

    def validate_task_size(self, task: TaskInfo) -> ValidationResult:
        """
        Validate if a task's size is within acceptable limits.

        This is the simple validation that only checks size.
        Use validate_task() for comprehensive validation.

        Args:
            task: Task information to validate

        Returns:
            ValidationResult with validation status and details
        """
        max_sp = self.config.max_story_points
        requires_approval = task.story_points > max_sp

        if requires_approval:
            message = (
                f"Task '{task.task_id}' exceeds max story points "
                f"({task.story_points} > {max_sp}). "
                f"Decomposition or approval required."
            )
            logger.info(f"Task requires approval: {task.task_id}")
        else:
            message = (
                f"Task '{task.task_id}' size is acceptable ({task.story_points} SP)"
            )

        return ValidationResult(
            is_valid=not requires_approval,
            requires_approval=requires_approval,
            story_points=task.story_points,
            max_allowed=max_sp,
            message=message,
            task_id=task.task_id,
        )

    def check_parallel_safety(
        self, tasks: list[TaskInfo]
    ) -> tuple[bool, ConflictCheckResult]:
        """
        Check if multiple tasks can safely run in parallel.

        Args:
            tasks: List of tasks to check

        Returns:
            Tuple of (is_safe, conflict_result)
        """
        scopes = [
            ScopeDeclaration(
                task_id=task.task_id,
                scope_globs=task.scope_globs,
            )
            for task in tasks
        ]

        result = self._conflict_detector.detect_conflicts(scopes)
        return result.safe_for_parallel, result

    def requires_decomposition(self, task: TaskInfo) -> bool:
        """
        Check if a task requires decomposition into smaller tasks.

        Args:
            task: Task information to analyze

        Returns:
            True if decomposition is recommended
        """
        if not self.is_enabled():
            return False

        return task.story_points > self.config.max_story_points

    def get_pending_approvals(self, limit: int = 50) -> list[dict]:
        """
        Get list of tasks pending decomposition approval.

        Args:
            limit: Maximum number of pending approvals to return

        Returns:
            List of pending approval records
        """
        if not self.is_enabled() or not self.redis_client:
            return []

        key = f"{self.config.redis_prefix}:pending_approvals"
        try:
            import json

            results = self.redis_client.lrange(key, 0, limit - 1)
            approvals = []
            for r in results:
                if isinstance(r, bytes):
                    r = r.decode()
                try:
                    approvals.append(json.loads(r))
                except (json.JSONDecodeError, TypeError):
                    approvals.append({"request_id": r})
            return approvals
        except Exception as e:
            logger.warning(f"Failed to get pending approvals: {e}")
            return []

    def request_approval(self, task: TaskInfo, justification: str) -> str:
        """
        Request approval for an oversized task.

        Args:
            task: Task requiring approval
            justification: Reason for keeping task oversized

        Returns:
            Approval request ID

        Raises:
            ValueError: If justification is empty
        """
        if self.config.require_justification and not justification:
            raise ValueError("Justification required for oversized tasks")

        import uuid
        import json

        request_id = f"apr-{uuid.uuid4().hex[:8]}"

        if self.redis_client:
            try:
                key = f"{self.config.redis_prefix}:approval:{request_id}"
                approval_data = {
                    "request_id": request_id,
                    "task_id": task.task_id,
                    "story_points": task.story_points,
                    "justification": justification,
                    "status": "pending",
                    "created_at": datetime.utcnow().isoformat(),
                }

                # Store with TTL
                self.redis_client.setex(
                    key,
                    self.config.approval_timeout_hours * 3600,
                    json.dumps(approval_data),
                )

                # Add to pending queue
                self.redis_client.lpush(
                    f"{self.config.redis_prefix}:pending_approvals",
                    request_id,
                )
            except Exception as e:
                logger.warning(f"Failed to store approval request: {e}")

        logger.info(f"Approval requested for task {task.task_id}: {request_id}")
        return request_id

    def approve_task(self, task_id: str, approver: str) -> bool:
        """
        Approve an oversized task.

        Args:
            task_id: ID of task to approve
            approver: Username or ID of approver

        Returns:
            True if approval was recorded successfully
        """
        import json

        if self.redis_client:
            try:
                # Add to approved set
                key = f"{self.config.redis_prefix}:approved_tasks"
                self.redis_client.sadd(key, task_id)

                # Log approval
                log_key = f"{self.config.redis_prefix}:approval_log:{task_id}"
                self.redis_client.setex(
                    log_key,
                    self.config.blocked_task_ttl_days * 86400,
                    json.dumps(
                        {
                            "task_id": task_id,
                            "approver": approver,
                            "approved_at": datetime.utcnow().isoformat(),
                        }
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to record approval: {e}")

        logger.info(f"Task {task_id} approved by {approver}")
        return True

    def is_task_approved(self, task_id: str) -> bool:
        """
        Check if a task has been approved.

        Args:
            task_id: Task ID to check

        Returns:
            True if task has active approval
        """
        if not self.redis_client:
            return False

        try:
            key = f"{self.config.redis_prefix}:approved_tasks"
            result = self.redis_client.sismember(key, task_id)
            return bool(result)
        except Exception as e:
            logger.warning(f"Failed to check approval status: {e}")
            return False

    def get_execution_order(self, tasks: list[TaskInfo]) -> list[str]:
        """
        Get a suggested execution order for tasks.

        Considers dependencies and conflicts.

        Args:
            tasks: List of tasks to order

        Returns:
            List of task IDs in suggested execution order
        """
        # Build scope declarations
        scopes = [
            ScopeDeclaration(
                task_id=task.task_id,
                scope_globs=task.scope_globs,
            )
            for task in tasks
        ]

        # Get conflict-aware order
        return self._conflict_detector.get_suggested_order(scopes)

    def clear_cache(self) -> None:
        """Clear cached feature flag state."""
        self._enabled = None
        self._dependency_checker.clear()
        self._conflict_detector.clear()
        logger.debug("Sentinel cache cleared")
