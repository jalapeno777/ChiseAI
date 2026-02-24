"""Audit logging for constitution overrides.

Provides audit logging with 90-day retention and rollback capability.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Redis key patterns
OVERRIDE_LOG_KEY = "chise:governance:override_log"
OVERRIDE_ACTIVE_KEY = "chise:governance:active_overrides"
RETENTION_DAYS = 90


class OverrideStatus(str, Enum):
    """Status of an override request."""

    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ROLLED_BACK = "rolled_back"


class RiskAssessment(str, Enum):
    """Risk assessment levels for overrides."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class OverrideRequest:
    """Represents a human override request."""

    override_id: str
    requester: str
    justification: str
    risk_assessment: RiskAssessment
    affected_systems: list[str]
    rollback_plan: str
    expires_at: datetime
    status: OverrideStatus = OverrideStatus.PENDING
    approver: str | None = None
    approved_at: datetime | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    revoked_by: str | None = None
    revoked_at: datetime | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "override_id": self.override_id,
            "requester": self.requester,
            "justification": self.justification,
            "risk_assessment": self.risk_assessment.value,
            "affected_systems": self.affected_systems,
            "rollback_plan": self.rollback_plan,
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "approver": self.approver,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "actions_taken": self.actions_taken,
            "created_at": self.created_at.isoformat(),
            "revoked_by": self.revoked_by,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "rolled_back_at": (
                self.rolled_back_at.isoformat() if self.rolled_back_at else None
            ),
            "rolled_back_by": self.rolled_back_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OverrideRequest:
        """Create from dictionary."""
        return cls(
            override_id=data["override_id"],
            requester=data["requester"],
            justification=data["justification"],
            risk_assessment=RiskAssessment(data["risk_assessment"]),
            affected_systems=data["affected_systems"],
            rollback_plan=data["rollback_plan"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            status=OverrideStatus(data["status"]),
            approver=data.get("approver"),
            approved_at=(
                datetime.fromisoformat(data["approved_at"])
                if data.get("approved_at")
                else None
            ),
            actions_taken=data.get("actions_taken", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            revoked_by=data.get("revoked_by"),
            revoked_at=(
                datetime.fromisoformat(data["revoked_at"])
                if data.get("revoked_at")
                else None
            ),
            rolled_back_at=(
                datetime.fromisoformat(data["rolled_back_at"])
                if data.get("rolled_back_at")
                else None
            ),
            rolled_back_by=data.get("rolled_back_by"),
        )

    def is_expired(self) -> bool:
        """Check if the override has expired."""
        return datetime.utcnow() > self.expires_at

    def is_rollback_allowed(self) -> bool:
        """Check if rollback is still allowed (within 24-hour window)."""
        if self.approved_at is None:
            return False
        rollback_window = timedelta(hours=24)
        return datetime.utcnow() < self.approved_at + rollback_window


class AuditLogger:
    """Manages audit logging for constitution overrides."""

    def __init__(
        self,
        retention_days: int = RETENTION_DAYS,
        redis_client: Any = None,
    ):
        """Initialize the audit logger.

        Args:
            retention_days: Number of days to retain logs
            redis_client: Redis client for persistence (optional)
        """
        self.retention_days = retention_days
        self._redis = redis_client
        self._pending_requests: dict[str, OverrideRequest] = {}
        self._active_overrides: dict[str, OverrideRequest] = {}

    def create_request(
        self,
        requester: str,
        justification: str,
        risk_assessment: RiskAssessment,
        affected_systems: list[str],
        rollback_plan: str,
        expiration_hours: int = 24,
    ) -> OverrideRequest:
        """Create a new override request.

        Args:
            requester: ID of the human requesting override
            justification: Reason for the override (min 50 chars)
            risk_assessment: Risk level assessment
            affected_systems: List of affected system names
            rollback_plan: Plan for rolling back changes
            expiration_hours: Hours until override expires (max 24)

        Returns:
            Created OverrideRequest

        Raises:
            ValueError: If validation fails
        """
        # Validate justification length
        if len(justification) < 50:
            raise ValueError(
                f"Justification must be at least 50 characters (got {len(justification)})"
            )

        # Cap expiration at 24 hours
        expiration_hours = min(expiration_hours, 24)

        request = OverrideRequest(
            override_id=str(uuid.uuid4()),
            requester=requester,
            justification=justification,
            risk_assessment=risk_assessment,
            affected_systems=affected_systems,
            rollback_plan=rollback_plan,
            expires_at=datetime.utcnow() + timedelta(hours=expiration_hours),
        )

        self._pending_requests[request.override_id] = request
        self._log_request(request)

        logger.info(f"Created override request: {request.override_id} by {requester}")

        return request

    def approve_request(
        self,
        override_id: str,
        approver: str,
    ) -> OverrideRequest:
        """Approve an override request.

        Args:
            override_id: ID of the request to approve
            approver: ID of the approver

        Returns:
            Approved OverrideRequest

        Raises:
            ValueError: If request not found or already processed
        """
        request = self._pending_requests.get(override_id)
        if request is None:
            raise ValueError(f"Override request not found: {override_id}")

        if request.status != OverrideStatus.PENDING:
            raise ValueError(f"Override request already {request.status.value}")

        request.status = OverrideStatus.APPROVED
        request.approver = approver
        request.approved_at = datetime.utcnow()

        # Move to active overrides
        del self._pending_requests[override_id]
        self._active_overrides[override_id] = request

        self._log_approval(request)

        logger.info(f"Approved override request: {override_id} by {approver}")

        return request

    def activate_override(
        self,
        override_id: str,
    ) -> OverrideRequest:
        """Activate an approved override.

        Args:
            override_id: ID of the override to activate

        Returns:
            Activated OverrideRequest
        """
        request = self._active_overrides.get(override_id)
        if request is None:
            raise ValueError(f"Active override not found: {override_id}")

        if request.status != OverrideStatus.APPROVED:
            raise ValueError(
                f"Override must be approved first (current: {request.status.value})"
            )

        request.status = OverrideStatus.ACTIVE
        self._log_activation(request)

        logger.info(f"Activated override: {override_id}")

        return request

    def record_action(
        self,
        override_id: str,
        action: str,
        result: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an action taken under an override.

        Args:
            override_id: ID of the active override
            action: Description of the action
            result: Result of the action (success/failure)
            details: Additional details
        """
        request = self._active_overrides.get(override_id)
        if request is None:
            logger.warning(
                f"Attempted to record action for unknown override: {override_id}"
            )
            return

        action_record = {
            "action": action,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }
        request.actions_taken.append(action_record)

        self._log_action(request, action_record)

        logger.info(f"Recorded action for override {override_id}: {action}")

    def revoke_override(
        self,
        override_id: str,
        revoked_by: str,
        reason: str,
    ) -> OverrideRequest:
        """Revoke an active override.

        Args:
            override_id: ID of the override to revoke
            revoked_by: ID of the revoker
            reason: Reason for revocation

        Returns:
            Revoked OverrideRequest
        """
        request = self._active_overrides.get(override_id)
        if request is None:
            raise ValueError(f"Active override not found: {override_id}")

        request.status = OverrideStatus.REVOKED
        request.revoked_by = revoked_by
        request.revoked_at = datetime.utcnow()

        self._log_revocation(request, reason)

        logger.info(f"Revoked override: {override_id} by {revoked_by}")

        return request

    def rollback_override(
        self,
        override_id: str,
        rolled_back_by: str,
    ) -> OverrideRequest:
        """Roll back an override (within 24-hour window).

        Args:
            override_id: ID of the override to roll back
            rolled_back_by: ID of the person performing rollback

        Returns:
            Rolled back OverrideRequest

        Raises:
            ValueError: If rollback not allowed
        """
        request = self._active_overrides.get(override_id)
        if request is None:
            raise ValueError(f"Active override not found: {override_id}")

        if not request.is_rollback_allowed():
            raise ValueError("Rollback window has expired (24 hours from approval)")

        request.status = OverrideStatus.ROLLED_BACK
        request.rolled_back_by = rolled_back_by
        request.rolled_back_at = datetime.utcnow()

        self._log_rollback(request)

        logger.info(f"Rolled back override: {override_id} by {rolled_back_by}")

        return request

    def get_request(self, override_id: str) -> OverrideRequest | None:
        """Get an override request by ID.

        Args:
            override_id: ID of the request

        Returns:
            OverrideRequest if found, None otherwise
        """
        # Check pending first
        if override_id in self._pending_requests:
            return self._pending_requests[override_id]

        # Check active
        if override_id in self._active_overrides:
            return self._active_overrides[override_id]

        return None

    def get_active_overrides(self) -> list[OverrideRequest]:
        """Get all active overrides.

        Returns:
            List of active OverrideRequests
        """
        # Filter out expired
        active = []
        expired_ids = []

        for override_id, request in self._active_overrides.items():
            if request.is_expired() and request.status == OverrideStatus.ACTIVE:
                request.status = OverrideStatus.EXPIRED
                expired_ids.append(override_id)
            else:
                active.append(request)

        # Clean up expired
        for override_id in expired_ids:
            self._log_expiry(self._active_overrides[override_id])

        return active

    def get_pending_requests(self) -> list[OverrideRequest]:
        """Get all pending override requests.

        Returns:
            List of pending OverrideRequests
        """
        return list(self._pending_requests.values())

    def _log_request(self, request: OverrideRequest) -> None:
        """Log override request creation."""
        log_entry = {
            "event": "override_requested",
            "timestamp": datetime.utcnow().isoformat(),
            "request": request.to_dict(),
        }
        self._write_log(log_entry)

    def _log_approval(self, request: OverrideRequest) -> None:
        """Log override approval."""
        log_entry = {
            "event": "override_approved",
            "timestamp": datetime.utcnow().isoformat(),
            "request": request.to_dict(),
        }
        self._write_log(log_entry)

    def _log_activation(self, request: OverrideRequest) -> None:
        """Log override activation."""
        log_entry = {
            "event": "override_activated",
            "timestamp": datetime.utcnow().isoformat(),
            "request": request.to_dict(),
        }
        self._write_log(log_entry)

    def _log_action(self, request: OverrideRequest, action: dict[str, Any]) -> None:
        """Log action taken under override."""
        log_entry = {
            "event": "override_action",
            "timestamp": datetime.utcnow().isoformat(),
            "override_id": request.override_id,
            "action": action,
        }
        self._write_log(log_entry)

    def _log_revocation(self, request: OverrideRequest, reason: str) -> None:
        """Log override revocation."""
        log_entry = {
            "event": "override_revoked",
            "timestamp": datetime.utcnow().isoformat(),
            "override_id": request.override_id,
            "revoked_by": request.revoked_by,
            "reason": reason,
        }
        self._write_log(log_entry)

    def _log_rollback(self, request: OverrideRequest) -> None:
        """Log override rollback."""
        log_entry = {
            "event": "override_rolled_back",
            "timestamp": datetime.utcnow().isoformat(),
            "request": request.to_dict(),
        }
        self._write_log(log_entry)

    def _log_expiry(self, request: OverrideRequest) -> None:
        """Log override expiration."""
        log_entry = {
            "event": "override_expired",
            "timestamp": datetime.utcnow().isoformat(),
            "override_id": request.override_id,
        }
        self._write_log(log_entry)

    def _write_log(self, entry: dict[str, Any]) -> None:
        """Write log entry to storage.

        Args:
            entry: Log entry to write
        """
        # Try Redis first
        if self._redis is not None:
            try:
                self._redis.lpush(
                    OVERRIDE_LOG_KEY,
                    json.dumps(entry),
                )
                # Set expiration on the key for retention
                self._redis.expire(
                    OVERRIDE_LOG_KEY,
                    self.retention_days * 24 * 60 * 60,
                )
            except Exception as e:
                logger.error(f"Failed to write to Redis: {e}")
                # Fall back to file logging
                logger.info(f"Audit log entry: {json.dumps(entry)}")
        else:
            # File logging fallback
            logger.info(f"Audit log entry: {json.dumps(entry)}")

    def get_audit_trail(
        self,
        override_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get audit trail entries.

        Args:
            override_id: Filter by override ID
            event_type: Filter by event type
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        # For now, return in-memory entries
        # In production, this would query Redis or database
        trail: list[dict[str, Any]] = []

        # Collect from active overrides
        for request in self._active_overrides.values():
            if override_id and request.override_id != override_id:
                continue

            trail.append(
                {
                    "event": f"override_{request.status.value}",
                    "timestamp": request.created_at.isoformat(),
                    "request": request.to_dict(),
                }
            )

            for action in request.actions_taken:
                trail.append(
                    {
                        "event": "override_action",
                        "timestamp": action["timestamp"],
                        "override_id": request.override_id,
                        "action": action,
                    }
                )

        # Sort by timestamp descending
        trail.sort(key=lambda x: x["timestamp"], reverse=True)

        return trail[:limit]
