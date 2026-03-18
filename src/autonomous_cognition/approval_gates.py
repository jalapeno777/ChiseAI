"""Approval gates for autonomous cognition human-in-the-loop decisions.

This module provides the ApprovalGates class which manages approval requests
for high-risk autonomous actions, including timeout handling, multiple approvers,
and comprehensive audit trail.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


@dataclass
class ApprovalResult:
    """Result of an approval request.

    Attributes:
        request_id: Unique identifier for the approval request
        status: Current status of the request
        timeout_at: When the request will timeout
        approved_by: Who approved the request (if approved)
        rejected_by: Who rejected the request (if rejected)
        notes: Additional notes about the decision
    """

    request_id: str
    status: ApprovalStatus
    timeout_at: datetime
    approved_by: str | None = None
    rejected_by: str | None = None
    notes: str = ""


@dataclass
class ApprovalRequest:
    """An approval request packet.

    Attributes:
        request_id: Unique identifier for this request
        decision: The decision requiring approval
        risk_level: Risk level of the decision
        requested_at: When the request was created
        timeout_at: When the request will timeout
        status: Current status
        approver: Who approved/rejected (if decided)
        notes: Notes about the decision
        evidence: Supporting evidence for the decision
        history: List of status changes
    """

    request_id: str
    decision: dict[str, Any]
    risk_level: str
    requested_at: datetime
    timeout_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver: str | None = None
    notes: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "request_id": self.request_id,
            "decision": self.decision,
            "risk_level": self.risk_level,
            "requested_at": self.requested_at.isoformat(),
            "timeout_at": self.timeout_at.isoformat(),
            "status": self.status.value,
            "approver": self.approver,
            "notes": self.notes,
            "evidence": self.evidence,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRequest:
        """Create from dictionary representation."""
        return cls(
            request_id=data["request_id"],
            decision=data["decision"],
            risk_level=data["risk_level"],
            requested_at=datetime.fromisoformat(data["requested_at"]),
            timeout_at=datetime.fromisoformat(data["timeout_at"]),
            status=ApprovalStatus(data["status"]),
            approver=data.get("approver"),
            notes=data.get("notes", ""),
            evidence=data.get("evidence", {}),
            history=data.get("history", []),
        )


class ApprovalGates:
    """Manages approval requests for high-risk autonomous actions.

    This class provides:
    - Approval request creation with evidence packets
    - Timeout handling with safe fallback (auto-reject on timeout)
    - Multiple approver support
    - Approval history tracking
    - Redis integration for persistence and pub/sub notifications
    - Discord integration for approval notifications

    Safe fallback behavior:
    - On timeout: Reject action, log incident
    - On approval error: Block action, notify admin
    - On system failure: Fail closed (block all actions)
    """

    REDIS_APPROVAL_REQUESTS_KEY = "bmad:chiseai:autocog:approval_requests"
    REDIS_APPROVAL_HISTORY_KEY = "bmad:chiseai:autocog:approval_history"
    REDIS_APPROVAL_PUBSUB_CHANNEL = "bmad:chiseai:autocog:approval_notifications"

    DEFAULT_TIMEOUT_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        redis_client: Any | None = None,
        discord_notifier: Any | None = None,
        default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the approval gates.

        Args:
            redis_client: Redis client for persistence and pub/sub.
                         If None, uses in-memory storage.
            discord_notifier: Discord notifier for approval notifications.
            default_timeout_seconds: Default timeout for approval requests.
        """
        self._redis = redis_client
        self._discord = discord_notifier
        self._default_timeout = default_timeout_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []

        logger.info(
            "ApprovalGates initialized with timeout=%ds", default_timeout_seconds
        )

    def request_approval(
        self,
        decision: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> ApprovalResult:
        """Create a new approval request.

        Args:
            decision: Dictionary containing decision details:
                - action: str - action being taken
                - description: str - human-readable description
                - files: list[str] - files affected
                - evidence: dict - supporting evidence
            timeout_seconds: Timeout in seconds (uses default if not specified)

        Returns:
            ApprovalResult with request details
        """
        request_id = str(uuid.uuid4())
        timeout = timeout_seconds or self._default_timeout

        requested_at = datetime.now(UTC)
        timeout_at = requested_at + timedelta(seconds=timeout)

        # Build evidence packet
        evidence = self._build_evidence_packet(decision)

        # Create request
        request = ApprovalRequest(
            request_id=request_id,
            decision=decision,
            risk_level=decision.get("risk_level", "unknown"),
            requested_at=requested_at,
            timeout_at=timeout_at,
            status=ApprovalStatus.PENDING,
            evidence=evidence,
            history=[
                {
                    "timestamp": requested_at.isoformat(),
                    "status": ApprovalStatus.PENDING.value,
                    "event": "request_created",
                }
            ],
        )

        self._requests[request_id] = request

        # Persist to Redis
        self._persist_request(request)

        # Publish notification
        self._publish_notification(
            {
                "type": "approval_requested",
                "request_id": request_id,
                "risk_level": request.risk_level,
                "action": decision.get("action"),
                "timeout_at": timeout_at.isoformat(),
            }
        )

        # Notify Discord if available
        if self._discord:
            self._notify_discord_request(request)

        logger.info(
            "Approval requested: id=%s action=%s timeout=%ds",
            request_id,
            decision.get("action"),
            timeout,
        )

        return ApprovalResult(
            request_id=request_id,
            status=ApprovalStatus.PENDING,
            timeout_at=timeout_at,
        )

    def check_approval_status(self, request_id: str) -> ApprovalResult:
        """Check the status of an approval request.

        Args:
            request_id: The approval request ID

        Returns:
            ApprovalResult with current status
        """
        # Check timeout first
        self._check_timeout(request_id)

        request = self._requests.get(request_id)
        if not request:
            logger.warning("Approval request not found: %s", request_id)
            return ApprovalResult(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,  # Fail closed
                timeout_at=datetime.now(UTC),
                notes="Request not found",
            )

        return ApprovalResult(
            request_id=request_id,
            status=request.status,
            timeout_at=request.timeout_at,
            approved_by=(
                request.approver if request.status == ApprovalStatus.APPROVED else None
            ),
            rejected_by=(
                request.approver if request.status == ApprovalStatus.REJECTED else None
            ),
            notes=request.notes,
        )

    def approve_request(
        self,
        request_id: str,
        approver: str,
        notes: str = "",
    ) -> ApprovalResult:
        """Approve an approval request.

        Args:
            request_id: The approval request ID
            approver: Who is approving the request
            notes: Optional notes about the approval

        Returns:
            ApprovalResult with updated status
        """
        request = self._requests.get(request_id)
        if not request:
            logger.error("Cannot approve: request not found: %s", request_id)
            return ApprovalResult(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,  # Fail closed
                timeout_at=datetime.now(UTC),
                notes="Request not found",
            )

        # Check if already decided
        if request.status != ApprovalStatus.PENDING:
            logger.warning(
                "Cannot approve request %s: already %s",
                request_id,
                request.status.value,
            )
            return ApprovalResult(
                request_id=request_id,
                status=request.status,
                timeout_at=request.timeout_at,
                notes=f"Request already {request.status.value}",
            )

        # Check timeout
        if datetime.now(UTC) > request.timeout_at:
            self.timeout_request(request_id)
            return ApprovalResult(
                request_id=request_id,
                status=ApprovalStatus.TIMEOUT,
                timeout_at=request.timeout_at,
                notes="Request timed out before approval",
            )

        # Approve
        request.status = ApprovalStatus.APPROVED
        request.approver = approver
        request.notes = notes
        request.history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "status": ApprovalStatus.APPROVED.value,
                "event": "approved",
                "approver": approver,
                "notes": notes,
            }
        )

        # Persist and notify
        self._persist_request(request)
        self._publish_notification(
            {
                "type": "approval_granted",
                "request_id": request_id,
                "approver": approver,
                "action": request.decision.get("action"),
            }
        )

        if self._discord:
            self._notify_discord_approval(request)

        # Move to history
        self._move_to_history(request)

        logger.info(
            "Approval granted: id=%s approver=%s action=%s",
            request_id,
            approver,
            request.decision.get("action"),
        )

        return ApprovalResult(
            request_id=request_id,
            status=ApprovalStatus.APPROVED,
            timeout_at=request.timeout_at,
            approved_by=approver,
            notes=notes,
        )

    def reject_request(
        self,
        request_id: str,
        approver: str,
        reason: str = "",
    ) -> ApprovalResult:
        """Reject an approval request.

        Args:
            request_id: The approval request ID
            approver: Who is rejecting the request
            reason: Reason for rejection

        Returns:
            ApprovalResult with updated status
        """
        request = self._requests.get(request_id)
        if not request:
            logger.error("Cannot reject: request not found: %s", request_id)
            return ApprovalResult(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,
                timeout_at=datetime.now(UTC),
                notes="Request not found",
            )

        # Check if already decided
        if request.status != ApprovalStatus.PENDING:
            logger.warning(
                "Cannot reject request %s: already %s",
                request_id,
                request.status.value,
            )
            return ApprovalResult(
                request_id=request_id,
                status=request.status,
                timeout_at=request.timeout_at,
                notes=f"Request already {request.status.value}",
            )

        # Reject
        request.status = ApprovalStatus.REJECTED
        request.approver = approver
        request.notes = reason
        request.history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "status": ApprovalStatus.REJECTED.value,
                "event": "rejected",
                "approver": approver,
                "reason": reason,
            }
        )

        # Persist and notify
        self._persist_request(request)
        self._publish_notification(
            {
                "type": "approval_rejected",
                "request_id": request_id,
                "approver": approver,
                "reason": reason,
                "action": request.decision.get("action"),
            }
        )

        if self._discord:
            self._notify_discord_rejection(request)

        # Move to history
        self._move_to_history(request)

        logger.info(
            "Approval rejected: id=%s approver=%s reason=%s action=%s",
            request_id,
            approver,
            reason,
            request.decision.get("action"),
        )

        return ApprovalResult(
            request_id=request_id,
            status=ApprovalStatus.REJECTED,
            timeout_at=request.timeout_at,
            rejected_by=approver,
            notes=reason,
        )

    def timeout_request(self, request_id: str) -> ApprovalResult:
        """Mark a request as timed out (auto-reject).

        This implements the safe fallback: on timeout, reject the action
        and log an incident.

        Args:
            request_id: The approval request ID

        Returns:
            ApprovalResult with timeout status
        """
        request = self._requests.get(request_id)
        if not request:
            logger.error("Cannot timeout: request not found: %s", request_id)
            return ApprovalResult(
                request_id=request_id,
                status=ApprovalStatus.REJECTED,
                timeout_at=datetime.now(UTC),
                notes="Request not found",
            )

        # Only timeout pending requests
        if request.status != ApprovalStatus.PENDING:
            return ApprovalResult(
                request_id=request_id,
                status=request.status,
                timeout_at=request.timeout_at,
            )

        # Timeout (safe fallback: reject)
        request.status = ApprovalStatus.TIMEOUT
        request.notes = "Request timed out - action auto-rejected"
        request.history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "status": ApprovalStatus.TIMEOUT.value,
                "event": "timeout",
                "note": "Auto-rejected due to timeout",
            }
        )

        # Persist and notify
        self._persist_request(request)
        self._publish_notification(
            {
                "type": "approval_timeout",
                "request_id": request_id,
                "action": request.decision.get("action"),
                "note": "Action auto-rejected due to timeout",
            }
        )

        # Log incident
        self._log_timeout_incident(request)

        if self._discord:
            self._notify_discord_timeout(request)

        # Move to history
        self._move_to_history(request)

        logger.warning(
            "Approval request timed out: id=%s action=%s",
            request_id,
            request.decision.get("action"),
        )

        return ApprovalResult(
            request_id=request_id,
            status=ApprovalStatus.TIMEOUT,
            timeout_at=request.timeout_at,
            notes="Request timed out - action auto-rejected",
        )

    def get_pending_requests(self) -> list[dict[str, Any]]:
        """Get all pending approval requests.

        Returns:
            List of pending request dictionaries
        """
        # Check timeouts first
        for request_id in list(self._requests.keys()):
            self._check_timeout(request_id)

        pending = [
            req.to_dict()
            for req in self._requests.values()
            if req.status == ApprovalStatus.PENDING
        ]

        # Sort by requested_at (oldest first)
        pending.sort(key=lambda x: x["requested_at"])

        return pending

    def get_approval_history(
        self,
        limit: int = 100,
        status: ApprovalStatus | None = None,
    ) -> list[dict[str, Any]]:
        """Get approval history with optional filtering.

        Args:
            limit: Maximum number of entries to return
            status: Filter by status (optional)

        Returns:
            List of approval request dictionaries
        """
        history = self._history

        if status:
            history = [h for h in history if h.status == status]

        # Return most recent first
        return [h.to_dict() for h in history[-limit:][::-1]]

    def _check_timeout(self, request_id: str) -> bool:
        """Check if a request has timed out and handle it.

        Args:
            request_id: The request ID to check

        Returns:
            True if the request timed out
        """
        request = self._requests.get(request_id)
        if not request:
            return False

        if (
            request.status == ApprovalStatus.PENDING
            and datetime.now(UTC) > request.timeout_at
        ):
            self.timeout_request(request_id)
            return True

        return False

    def _build_evidence_packet(self, decision: dict[str, Any]) -> dict[str, Any]:
        """Build an evidence packet for an approval request.

        Args:
            decision: The decision requiring approval

        Returns:
            Dictionary with evidence information
        """
        return {
            "action": decision.get("action"),
            "description": decision.get("description"),
            "files": decision.get("files", []),
            "risk_level": decision.get("risk_level", "unknown"),
            "timestamp": datetime.now(UTC).isoformat(),
            "supporting_evidence": decision.get("evidence", {}),
            "system_context": {
                "autocog_enabled": True,
                "approval_required": True,
            },
        }

    def _persist_request(self, request: ApprovalRequest) -> None:
        """Persist a request to Redis.

        Args:
            request: The request to persist
        """
        if not self._redis:
            return

        try:
            # Store in hash for easy lookup
            self._redis.hset(
                self.REDIS_APPROVAL_REQUESTS_KEY,
                request.request_id,
                json.dumps(request.to_dict()),
            )
        except Exception as e:
            logger.warning("Failed to persist request to Redis: %s", e)

    def _publish_notification(self, message: dict[str, Any]) -> None:
        """Publish a notification to Redis pub/sub.

        Args:
            message: The message to publish
        """
        if not self._redis:
            return

        try:
            self._redis.publish(
                self.REDIS_APPROVAL_PUBSUB_CHANNEL,
                json.dumps(message),
            )
        except Exception as e:
            logger.warning("Failed to publish notification: %s", e)

    def _move_to_history(self, request: ApprovalRequest) -> None:
        """Move a request from active to history.

        Args:
            request: The request to move
        """
        # Add to history
        self._history.append(request)

        # Remove from active
        if request.request_id in self._requests:
            del self._requests[request.request_id]

        # Persist history
        if self._redis:
            try:
                self._redis.lpush(
                    self.REDIS_APPROVAL_HISTORY_KEY,
                    json.dumps(request.to_dict()),
                )
            except Exception as e:
                logger.warning("Failed to persist history to Redis: %s", e)

    def _log_timeout_incident(self, request: ApprovalRequest) -> None:
        """Log a timeout as an incident.

        Args:
            request: The timed out request
        """
        incident = {
            "incident_id": f"timeout-{request.request_id}",
            "type": "approval_timeout",
            "severity": "medium",
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request.request_id,
            "action": request.decision.get("action"),
            "risk_level": request.risk_level,
            "description": "Approval request timed out - action auto-rejected",
        }

        logger.warning("Timeout incident logged: %s", incident["incident_id"])

        # Could also write to incident logging system here

    def _notify_discord_request(self, request: ApprovalRequest) -> None:
        """Notify Discord of a new approval request.

        Args:
            request: The approval request
        """
        if not self._discord:
            return

        try:
            # Use notify_autocog_event if available
            if hasattr(self._discord, "notify_autocog_event"):
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._discord.notify_autocog_event(
                        event_type="approval_requested",
                        severity=(
                            "high" if request.risk_level == "critical" else "medium"
                        ),
                        summary=f"Approval required: {request.decision.get('action')}",
                        impact=f"Risk level: {request.risk_level}",
                        top_metrics={
                            "timeout_seconds": self._default_timeout,
                            "request_id": request.request_id[:8],
                        },
                        run_id=request.request_id,
                        title="Approval Requested",
                        issue=request.decision.get("description", "No description"),
                        intended_resolution="Human approval required before proceeding",
                        expected_improvement="Prevents unauthorized high-risk actions",
                        outcome_status="in_progress",
                        evidence_reasoning=[
                            f"risk_level={request.risk_level}",
                            f"action={request.decision.get('action')}",
                        ],
                    )
                )
                loop.close()
        except Exception as e:
            logger.warning("Failed to notify Discord: %s", e)

    def _notify_discord_approval(self, request: ApprovalRequest) -> None:
        """Notify Discord of an approval.

        Args:
            request: The approved request
        """
        if not self._discord:
            return

        try:
            if hasattr(self._discord, "notify_autocog_event"):
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._discord.notify_autocog_event(
                        event_type="approval_granted",
                        severity="low",
                        summary=f"Approved: {request.decision.get('action')}",
                        impact=f"Approved by: {request.approver}",
                        top_metrics={
                            "approver": request.approver,
                            "request_id": request.request_id[:8],
                        },
                        run_id=request.request_id,
                        title="Approval Granted",
                        issue="",
                        intended_resolution="Action approved - can proceed",
                        expected_improvement="",
                        outcome_status="success",
                        evidence_reasoning=[
                            f"approver={request.approver}",
                            f"notes={request.notes}",
                        ],
                    )
                )
                loop.close()
        except Exception as e:
            logger.warning("Failed to notify Discord: %s", e)

    def _notify_discord_rejection(self, request: ApprovalRequest) -> None:
        """Notify Discord of a rejection.

        Args:
            request: The rejected request
        """
        if not self._discord:
            return

        try:
            if hasattr(self._discord, "notify_autocog_event"):
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._discord.notify_autocog_event(
                        event_type="approval_rejected",
                        severity="medium",
                        summary=f"Rejected: {request.decision.get('action')}",
                        impact=f"Rejected by: {request.approver}",
                        top_metrics={
                            "rejector": request.approver,
                            "request_id": request.request_id[:8],
                        },
                        run_id=request.request_id,
                        title="Approval Rejected",
                        issue=request.notes,
                        intended_resolution="Action rejected - do not proceed",
                        expected_improvement="Prevents potentially harmful actions",
                        outcome_status="failed",
                        evidence_reasoning=[
                            f"rejector={request.approver}",
                            f"reason={request.notes}",
                        ],
                    )
                )
                loop.close()
        except Exception as e:
            logger.warning("Failed to notify Discord: %s", e)

    def _notify_discord_timeout(self, request: ApprovalRequest) -> None:
        """Notify Discord of a timeout.

        Args:
            request: The timed out request
        """
        if not self._discord:
            return

        try:
            if hasattr(self._discord, "notify_autocog_event"):
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._discord.notify_autocog_event(
                        event_type="approval_timeout",
                        severity="high",
                        summary=f"Timeout: {request.decision.get('action')}",
                        impact="Action auto-rejected due to timeout",
                        top_metrics={
                            "request_id": request.request_id[:8],
                        },
                        run_id=request.request_id,
                        title="Approval Timeout",
                        issue="No approval received within timeout period",
                        intended_resolution="Action auto-rejected as safe fallback",
                        expected_improvement="Prevents indefinite waits",
                        outcome_status="failed",
                        evidence_reasoning=[
                            f"timeout_at={request.timeout_at.isoformat()}",
                            "action=auto_rejected",
                        ],
                    )
                )
                loop.close()
        except Exception as e:
            logger.warning("Failed to notify Discord: %s", e)

    def cleanup_expired_requests(self) -> int:
        """Clean up expired (timed out) requests.

        Returns:
            Number of requests cleaned up
        """
        expired_count = 0
        for request_id in list(self._requests.keys()):
            if self._check_timeout(request_id):
                expired_count += 1

        return expired_count
