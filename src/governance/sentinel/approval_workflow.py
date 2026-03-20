"""
Approval Workflow - Manages approval requests for oversized tasks (ST-GOV-003).

Stores approval requests in Redis, tracks approval status, and handles
expiration of stale requests.

Story: ST-GOV-003
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Redis key patterns
APPROVAL_QUEUE_KEY = "chise:governance:sentinel:pending_approvals"
APPROVAL_PREFIX = "chise:governance:sentinel:approval:"
APPROVED_TASKS_KEY = "chise:governance:sentinel:approved_tasks"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """A request for approval of an oversized task."""

    request_id: str
    task_id: str
    story_points: float
    justification: str
    requester: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime | None = None
    expires_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "story_points": self.story_points,
            "justification": self.justification,
            "requester": self.requester,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        """Create from dictionary (Redis data)."""
        return cls(
            request_id=data.get("request_id", ""),
            task_id=data.get("task_id", ""),
            story_points=float(data.get("story_points", 0)),
            justification=data.get("justification", ""),
            requester=data.get("requester", ""),
            status=ApprovalStatus(data.get("status", "pending")),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else None
            ),
            expires_at=(
                datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
            approved_by=data.get("approved_by"),
            approved_at=(
                datetime.fromisoformat(data["approved_at"])
                if data.get("approved_at")
                else None
            ),
            rejection_reason=data.get("rejection_reason"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ApprovalResult:
    """Result of an approval operation."""

    success: bool
    request_id: str
    status: ApprovalStatus
    message: str


class ApprovalWorkflow:
    """
    Manages approval workflow for oversized tasks.

    Features:
    - Create and track approval requests
    - Store in Redis with TTL
    - Approve/reject requests
    - Handle expiration
    - Query pending approvals

    Usage:
        workflow = ApprovalWorkflow(redis_client)
        request_id = workflow.request_approval(
            task_id="ST-123",
            story_points=8,
            justification="Complex integration required",
            requester="agent-1"
        )
        # Later...
        workflow.approve(request_id, approver="human-1")
    """

    def __init__(
        self,
        redis_client=None,
        default_timeout_hours: int = 24,
    ):
        """
        Initialize the approval workflow.

        Args:
            redis_client: Redis client for persistence
            default_timeout_hours: Hours before approval requests expire
        """
        self.redis_client = redis_client
        self.default_timeout_hours = default_timeout_hours

    def _get_redis(self):
        """Get Redis client or raise error."""
        if self.redis_client is None:
            raise RuntimeError("Redis client not configured")
        return self.redis_client

    def request_approval(
        self,
        task_id: str,
        story_points: float,
        justification: str,
        requester: str,
        timeout_hours: int | None = None,
        metadata: dict | None = None,
    ) -> str:
        """
        Create a new approval request.

        Args:
            task_id: ID of the task requiring approval
            story_points: Size of the task
            justification: Reason for keeping task oversized
            requester: Who is requesting approval
            timeout_hours: Optional custom timeout (uses default if None)
            metadata: Optional additional metadata

        Returns:
            The request ID

        Raises:
            RuntimeError: If Redis is not available
            ValueError: If justification is empty
        """
        if not justification or not justification.strip():
            raise ValueError("Justification is required for approval requests")

        redis = self._get_redis()
        timeout = timeout_hours or self.default_timeout_hours

        now = datetime.now(UTC)
        expires = now + timedelta(hours=timeout)

        request_id = f"apr-{uuid.uuid4().hex[:8]}"

        request = ApprovalRequest(
            request_id=request_id,
            task_id=task_id,
            story_points=story_points,
            justification=justification.strip(),
            requester=requester,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=expires,
            metadata=metadata or {},
        )

        # Store the request
        key = f"{APPROVAL_PREFIX}{request_id}"
        redis.set(
            key,
            json.dumps(request.to_dict()),
            ex=int(timedelta(hours=timeout).total_seconds()),
        )

        # Add to pending queue
        redis.lpush(APPROVAL_QUEUE_KEY, request_id)

        logger.info(
            f"Approval request created: {request_id} for task {task_id} "
            f"({story_points} SP) by {requester}"
        )

        return request_id

    def approve(
        self,
        request_id: str,
        approver: str,
        notes: str | None = None,
    ) -> ApprovalResult:
        """
        Approve a pending request.

        Args:
            request_id: The request ID to approve
            approver: Who is approving
            notes: Optional approval notes

        Returns:
            ApprovalResult indicating success/failure
        """
        redis = self._get_redis()
        key = f"{APPROVAL_PREFIX}{request_id}"

        data = redis.get(key)
        if not data:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=ApprovalStatus.PENDING,
                message=f"Approval request not found: {request_id}",
            )

        if isinstance(data, bytes):
            data = data.decode()

        request = ApprovalRequest.from_dict(json.loads(data))

        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=request.status,
                message=f"Request already {request.status.value}",
            )

        # Check expiration
        if request.expires_at and datetime.now(UTC) > request.expires_at:
            request.status = ApprovalStatus.EXPIRED
            redis.set(key, json.dumps(request.to_dict()))
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=ApprovalStatus.EXPIRED,
                message="Request has expired",
            )

        # Approve
        request.status = ApprovalStatus.APPROVED
        request.approved_by = approver
        request.approved_at = datetime.now(UTC)
        if notes:
            request.metadata["approval_notes"] = notes

        redis.set(key, json.dumps(request.to_dict()))

        # Add to approved tasks set for quick lookup
        redis.sadd(APPROVED_TASKS_KEY, request.task_id)

        # Remove from pending queue
        redis.lrem(APPROVAL_QUEUE_KEY, 0, request_id)

        logger.info(f"Approval request {request_id} approved by {approver}")

        return ApprovalResult(
            success=True,
            request_id=request_id,
            status=ApprovalStatus.APPROVED,
            message=f"Task {request.task_id} approved by {approver}",
        )

    def reject(
        self,
        request_id: str,
        rejector: str,
        reason: str,
    ) -> ApprovalResult:
        """
        Reject a pending request.

        Args:
            request_id: The request ID to reject
            rejector: Who is rejecting
            reason: Reason for rejection

        Returns:
            ApprovalResult indicating success/failure
        """
        redis = self._get_redis()
        key = f"{APPROVAL_PREFIX}{request_id}"

        data = redis.get(key)
        if not data:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=ApprovalStatus.PENDING,
                message=f"Approval request not found: {request_id}",
            )

        if isinstance(data, bytes):
            data = data.decode()

        request = ApprovalRequest.from_dict(json.loads(data))

        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=request.status,
                message=f"Request already {request.status.value}",
            )

        # Reject
        request.status = ApprovalStatus.REJECTED
        request.approved_by = rejector
        request.approved_at = datetime.now(UTC)
        request.rejection_reason = reason

        redis.set(key, json.dumps(request.to_dict()))

        # Remove from pending queue
        redis.lrem(APPROVAL_QUEUE_KEY, 0, request_id)

        logger.info(f"Approval request {request_id} rejected by {rejector}: {reason}")

        return ApprovalResult(
            success=True,
            request_id=request_id,
            status=ApprovalStatus.REJECTED,
            message=f"Task {request.task_id} rejected: {reason}",
        )

    def cancel(self, request_id: str, reason: str | None = None) -> ApprovalResult:
        """
        Cancel a pending request.

        Args:
            request_id: The request ID to cancel
            reason: Optional cancellation reason

        Returns:
            ApprovalResult indicating success/failure
        """
        redis = self._get_redis()
        key = f"{APPROVAL_PREFIX}{request_id}"

        data = redis.get(key)
        if not data:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=ApprovalStatus.PENDING,
                message=f"Approval request not found: {request_id}",
            )

        if isinstance(data, bytes):
            data = data.decode()

        request = ApprovalRequest.from_dict(json.loads(data))

        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(
                success=False,
                request_id=request_id,
                status=request.status,
                message=f"Request already {request.status.value}",
            )

        # Cancel
        request.status = ApprovalStatus.CANCELLED
        if reason:
            request.metadata["cancellation_reason"] = reason

        redis.set(key, json.dumps(request.to_dict()))

        # Remove from pending queue
        redis.lrem(APPROVAL_QUEUE_KEY, 0, request_id)

        logger.info(f"Approval request {request_id} cancelled")

        return ApprovalResult(
            success=True,
            request_id=request_id,
            status=ApprovalStatus.CANCELLED,
            message=f"Request cancelled: {reason or 'No reason provided'}",
        )

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """
        Get an approval request by ID.

        Args:
            request_id: The request ID to look up

        Returns:
            The ApprovalRequest if found, None otherwise
        """
        redis = self._get_redis()
        key = f"{APPROVAL_PREFIX}{request_id}"

        data = redis.get(key)
        if not data:
            return None

        if isinstance(data, bytes):
            data = data.decode()

        return ApprovalRequest.from_dict(json.loads(data))

    def get_pending_approvals(self, limit: int = 50) -> list[ApprovalRequest]:
        """
        Get all pending approval requests.

        Args:
            limit: Maximum number of requests to return

        Returns:
            List of pending ApprovalRequests
        """
        redis = self._get_redis()

        # Get pending request IDs
        request_ids = redis.lrange(APPROVAL_QUEUE_KEY, 0, limit - 1)

        requests = []
        for rid in request_ids:
            if isinstance(rid, bytes):
                rid = rid.decode()

            request = self.get_request(rid)
            if request and request.status == ApprovalStatus.PENDING:
                # Check for expiration
                if request.expires_at and datetime.now(UTC) > request.expires_at:
                    request.status = ApprovalStatus.EXPIRED
                    key = f"{APPROVAL_PREFIX}{rid}"
                    redis.set(key, json.dumps(request.to_dict()))
                    redis.lrem(APPROVAL_QUEUE_KEY, 0, rid)
                else:
                    requests.append(request)

        return requests

    def is_task_approved(self, task_id: str) -> bool:
        """
        Check if a task has been approved.

        Args:
            task_id: The task ID to check

        Returns:
            True if the task has an active approval
        """
        redis = self._get_redis()
        return bool(redis.sismember(APPROVED_TASKS_KEY, task_id))

    def cleanup_expired(self) -> int:
        """
        Clean up expired approval requests.

        Returns:
            Number of expired requests cleaned up
        """
        redis = self._get_redis()

        # Get all pending request IDs
        request_ids = redis.lrange(APPROVAL_QUEUE_KEY, 0, -1)

        expired_count = 0
        for rid in request_ids:
            if isinstance(rid, bytes):
                rid = rid.decode()

            request = self.get_request(rid)
            if request and request.status == ApprovalStatus.PENDING:
                if request.expires_at and datetime.now(UTC) > request.expires_at:
                    request.status = ApprovalStatus.EXPIRED
                    key = f"{APPROVAL_PREFIX}{rid}"
                    redis.set(key, json.dumps(request.to_dict()))
                    redis.lrem(APPROVAL_QUEUE_KEY, 0, rid)
                    expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired approval requests")

        return expired_count
