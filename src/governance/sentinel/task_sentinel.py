"""
Task Decomposition Sentinel - Core Implementation (ST-GOV-003).

Enforces task size limits and requires decomposition approval for
oversized tasks. Integrated with feature flags for safe rollout.

Story: ST-GOV-003
Phase: Week 1 Batch 1B
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Redis key for feature flag
FEATURE_FLAG_KEY = "chise:feature_flags:governance:task_sentinel_active"


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


@dataclass
class TaskInfo:
    """Information about a task being validated."""

    task_id: str
    story_points: float
    title: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    labels: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of task size validation."""

    is_valid: bool
    requires_approval: bool
    story_points: float
    max_allowed: int
    message: str
    task_id: Optional[str] = None


class TaskSentinel:
    """
    Task Decomposition Sentinel.

    Validates task sizes and enforces decomposition requirements for
    oversized tasks. Integrates with Redis for feature flag control
    and approval tracking.

    Usage:
        sentinel = TaskSentinel(redis_client)
        result = sentinel.validate_task_size(task_info)
        if result.requires_approval:
            # Request approval workflow
            pass
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
            self._enabled = flag_value == "true" or flag_value == b"true"
            logger.debug(f"Sentinel feature flag: {self._enabled}")
            return self._enabled
        except Exception as e:
            logger.warning(f"Failed to read feature flag: {e}")
            return False

    def validate_task_size(self, task: TaskInfo) -> ValidationResult:
        """
        Validate if a task's size is within acceptable limits.

        Tasks exceeding max_story_points require approval before
        proceeding. This is the primary gate for decomposition enforcement.

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

    def requires_decomposition(self, task: TaskInfo) -> bool:
        """
        Check if a task requires decomposition into smaller tasks.

        TODO: Implement full decomposition logic with:
        - Historical pattern analysis
        - Task complexity scoring
        - Decomposition suggestions

        Args:
            task: Task information to analyze

        Returns:
            True if decomposition is recommended
        """
        # ST-GOV-003: Stub implementation
        # Full implementation will include:
        # - ML-based size prediction
        # - Pattern matching for known decomposition targets
        # - Integration with story patterns

        if not self.is_enabled():
            return False

        # Simple threshold check for now
        return task.story_points > self.config.max_story_points

    def get_pending_approvals(self, limit: int = 50) -> list[dict]:
        """
        Get list of tasks pending decomposition approval.

        TODO: Implement approval queue retrieval from Redis.

        Args:
            limit: Maximum number of pending approvals to return

        Returns:
            List of pending approval records
        """
        # ST-GOV-003: Stub implementation
        # Full implementation will query Redis for:
        # - chise:governance:sentinel:pending_approvals
        # - Include approval metadata, timestamps, requestors

        if not self.is_enabled():
            return []

        # Placeholder for Redis query
        # key = f"{self.config.redis_prefix}:pending_approvals"
        # return self.redis_client.lrange(key, 0, limit)

        return []

    def request_approval(self, task: TaskInfo, justification: str) -> str:
        """
        Request approval for an oversized task.

        TODO: Implement approval request workflow.

        Args:
            task: Task requiring approval
            justification: Reason for keeping task oversized

        Returns:
            Approval request ID
        """
        # ST-GOV-003: Stub implementation
        # Full implementation will:
        # - Create approval record in Redis
        # - Notify approvers via configured channels
        # - Set expiration based on approval_timeout_hours

        if self.config.require_justification and not justification:
            raise ValueError("Justification required for oversized tasks")

        import uuid

        request_id = str(uuid.uuid4())[:8]
        logger.info(f"Approval requested for task {task.task_id}: {request_id}")
        return request_id

    def approve_task(self, task_id: str, approver: str) -> bool:
        """
        Approve an oversized task.

        TODO: Implement approval recording.

        Args:
            task_id: ID of task to approve
            approver: Username or ID of approver

        Returns:
            True if approval was recorded successfully
        """
        # ST-GOV-003: Stub implementation
        logger.info(f"Task {task_id} approved by {approver}")
        return True

    def clear_cache(self) -> None:
        """Clear cached feature flag state."""
        self._enabled = None
        logger.debug("Sentinel cache cleared")
