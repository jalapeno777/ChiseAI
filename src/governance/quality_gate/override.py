"""Human Override Mechanism for Quality Gate.

Allows humans to override blocked PRs with proper justification
and audit trail.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OverrideStatus(str, Enum):
    """Status of an override request."""

    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ROLLED_BACK = "rolled_back"


class RiskLevel(str, Enum):
    """Risk assessment levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HumanOverride:
    """Represents a human override request."""

    id: str
    pr_number: int
    requester: str
    justification: str
    risk_assessment: RiskLevel
    rollback_plan: str
    affected_systems: list[str] = field(default_factory=list)
    status: OverrideStatus = OverrideStatus.PENDING
    approver: str | None = None
    approved_at: datetime | None = None
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "pr_number": self.pr_number,
            "requester": self.requester,
            "justification": self.justification,
            "risk_assessment": self.risk_assessment.value,
            "rollback_plan": self.rollback_plan,
            "affected_systems": self.affected_systems,
            "status": self.status.value,
            "approver": self.approver,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "activated_at": (
                self.activated_at.isoformat() if self.activated_at else None
            ),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_by": self.revoked_by,
            "revoke_reason": self.revoke_reason,
            "rolled_back_at": (
                self.rolled_back_at.isoformat() if self.rolled_back_at else None
            ),
            "rolled_back_by": self.rolled_back_by,
            "created_at": self.created_at.isoformat(),
            "audit_trail": self.audit_trail,
        }

    def add_audit_entry(
        self, event: str, actor: str, details: dict[str, Any] | None = None
    ) -> None:
        """Add an entry to the audit trail."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "actor": actor,
            "details": details or {},
        }
        self.audit_trail.append(entry)


class OverrideManager:
    """Manages human override requests for the quality gate."""

    MAX_EXPIRATION_HOURS = 24
    MIN_JUSTIFICATION_LENGTH = 50

    def __init__(self, default_expiration_hours: int = 24):
        """Initialize the override manager.

        Args:
            default_expiration_hours: Default hours until override expires
        """
        self.default_expiration_hours = min(
            default_expiration_hours, self.MAX_EXPIRATION_HOURS
        )
        self._overrides: dict[str, HumanOverride] = {}
        self._pr_overrides: dict[int, str] = {}  # pr_number -> override_id

    def create_request(
        self,
        pr_number: int,
        requester: str,
        justification: str,
        risk_assessment: str,
        rollback_plan: str,
        affected_systems: list[str] | None = None,
        expiration_hours: int | None = None,
    ) -> HumanOverride:
        """Create a new override request.

        Args:
            pr_number: PR number to override
            requester: ID of person requesting override
            justification: Reason for override (min 50 characters)
            risk_assessment: Risk level (low/medium/high/critical)
            rollback_plan: Plan for rolling back changes
            affected_systems: List of affected systems
            expiration_hours: Hours until override expires (max 24)

        Returns:
            Created HumanOverride request

        Raises:
            ValueError: If validation fails
        """
        # Validate justification length
        if len(justification) < self.MIN_JUSTIFICATION_LENGTH:
            raise ValueError(
                f"Justification must be at least {self.MIN_JUSTIFICATION_LENGTH} characters. "
                f"Got {len(justification)}."
            )

        # Validate risk assessment
        try:
            risk = RiskLevel(risk_assessment.lower())
        except ValueError:
            raise ValueError(
                f"Invalid risk assessment: {risk_assessment}. "
                f"Must be one of: low, medium, high, critical"
            )

        # Validate expiration
        expiration_hours = expiration_hours or self.default_expiration_hours
        expiration_hours = min(expiration_hours, self.MAX_EXPIRATION_HOURS)

        # Create override
        override_id = f"override-{uuid.uuid4().hex[:12]}"
        override = HumanOverride(
            id=override_id,
            pr_number=pr_number,
            requester=requester,
            justification=justification,
            risk_assessment=risk,
            rollback_plan=rollback_plan,
            affected_systems=affected_systems or [],
            expires_at=datetime.now(UTC) + timedelta(hours=expiration_hours),
        )

        override.add_audit_entry(
            event="created",
            actor=requester,
            details={
                "pr_number": pr_number,
                "risk_assessment": risk.value,
            },
        )

        self._overrides[override_id] = override
        self._pr_overrides[pr_number] = override_id

        logger.info(f"Created override request {override_id} for PR #{pr_number}")
        return override

    def approve_request(self, override_id: str, approver: str) -> HumanOverride:
        """Approve an override request.

        Args:
            override_id: Override request ID
            approver: ID of approver

        Returns:
            Approved HumanOverride

        Raises:
            ValueError: If override not found or wrong status
        """
        override = self._overrides.get(override_id)
        if not override:
            raise ValueError(f"Override not found: {override_id}")

        if override.status != OverrideStatus.PENDING:
            raise ValueError(
                f"Override is not pending. Current status: {override.status.value}"
            )

        override.status = OverrideStatus.APPROVED
        override.approver = approver
        override.approved_at = datetime.now(UTC)

        override.add_audit_entry(
            event="approved",
            actor=approver,
        )

        logger.info(f"Override {override_id} approved by {approver}")
        return override

    def activate_override(self, override_id: str) -> HumanOverride:
        """Activate an approved override.

        Args:
            override_id: Override request ID

        Returns:
            Activated HumanOverride

        Raises:
            ValueError: If override not approved or already active
        """
        override = self._overrides.get(override_id)
        if not override:
            raise ValueError(f"Override not found: {override_id}")

        if override.status != OverrideStatus.APPROVED:
            raise ValueError(
                f"Override must be approved first. Current status: {override.status.value}"
            )

        override.status = OverrideStatus.ACTIVE
        override.activated_at = datetime.now(UTC)

        override.add_audit_entry(
            event="activated",
            actor="system",
        )

        logger.info(f"Override {override_id} activated")
        return override

    def revoke_override(
        self, override_id: str, revoked_by: str, reason: str
    ) -> HumanOverride:
        """Revoke an active override.

        Args:
            override_id: Override request ID
            revoked_by: ID of revoker
            reason: Reason for revocation

        Returns:
            Revoked HumanOverride

        Raises:
            ValueError: If override not found or not active
        """
        override = self._overrides.get(override_id)
        if not override:
            raise ValueError(f"Override not found: {override_id}")

        if override.status not in (
            OverrideStatus.ACTIVE,
            OverrideStatus.APPROVED,
            OverrideStatus.PENDING,
        ):
            raise ValueError(
                f"Cannot revoke override with status: {override.status.value}"
            )

        override.status = OverrideStatus.REVOKED
        override.revoked_at = datetime.now(UTC)
        override.revoked_by = revoked_by
        override.revoke_reason = reason

        override.add_audit_entry(
            event="revoked",
            actor=revoked_by,
            details={"reason": reason},
        )

        # Remove from PR mapping
        if override.pr_number in self._pr_overrides:
            if self._pr_overrides[override.pr_number] == override_id:
                del self._pr_overrides[override.pr_number]

        logger.warning(f"Override {override_id} revoked by {revoked_by}: {reason}")
        return override

    def rollback_override(self, override_id: str, rolled_back_by: str) -> HumanOverride:
        """Roll back an override (within 24-hour window).

        Args:
            override_id: Override request ID
            rolled_back_by: ID of person performing rollback

        Returns:
            Rolled back HumanOverride

        Raises:
            ValueError: If override not found or outside window
        """
        override = self._overrides.get(override_id)
        if not override:
            raise ValueError(f"Override not found: {override_id}")

        if override.status != OverrideStatus.ACTIVE:
            raise ValueError(
                f"Can only rollback active overrides. Current status: {override.status.value}"
            )

        # Check 24-hour window
        if override.activated_at:
            window = datetime.now(UTC) - override.activated_at
            if window > timedelta(hours=24):
                raise ValueError("Rollback window (24 hours) has expired")

        override.status = OverrideStatus.ROLLED_BACK
        override.rolled_back_at = datetime.now(UTC)
        override.rolled_back_by = rolled_back_by

        override.add_audit_entry(
            event="rolled_back",
            actor=rolled_back_by,
        )

        # Remove from PR mapping
        if override.pr_number in self._pr_overrides:
            if self._pr_overrides[override.pr_number] == override_id:
                del self._pr_overrides[override.pr_number]

        logger.info(f"Override {override_id} rolled back by {rolled_back_by}")
        return override

    def get_active_override_for_pr(self, pr_number: int) -> HumanOverride | None:
        """Get the active override for a PR.

        Args:
            pr_number: PR number

        Returns:
            Active HumanOverride if exists, None otherwise
        """
        override_id = self._pr_overrides.get(pr_number)
        if not override_id:
            return None

        override = self._overrides.get(override_id)
        if not override:
            return None

        # Check if expired
        if override.expires_at and datetime.now(UTC) > override.expires_at:
            override.status = OverrideStatus.EXPIRED
            return None

        # Only return active overrides
        if override.status == OverrideStatus.ACTIVE:
            return override

        # Auto-activate approved overrides
        if override.status == OverrideStatus.APPROVED:
            self.activate_override(override_id)
            return override

        return None

    def get_request(self, override_id: str) -> HumanOverride | None:
        """Get an override request by ID.

        Args:
            override_id: Override request ID

        Returns:
            HumanOverride if found, None otherwise
        """
        return self._overrides.get(override_id)

    def get_pending_requests(self) -> list[HumanOverride]:
        """Get all pending override requests.

        Returns:
            List of pending HumanOverride requests
        """
        return [
            o for o in self._overrides.values() if o.status == OverrideStatus.PENDING
        ]

    def get_active_overrides(self) -> list[HumanOverride]:
        """Get all active overrides.

        Returns:
            List of active HumanOverride objects
        """
        return [
            o for o in self._overrides.values() if o.status == OverrideStatus.ACTIVE
        ]

    def get_audit_trail(
        self,
        override_id: str | None = None,
        pr_number: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get audit trail entries.

        Args:
            override_id: Filter by override ID
            pr_number: Filter by PR number
            limit: Maximum entries to return

        Returns:
            List of audit trail entries
        """
        entries: list[dict[str, Any]] = []

        overrides = list(self._overrides.values())
        if override_id:
            overrides = [o for o in overrides if o.id == override_id]
        if pr_number:
            overrides = [o for o in overrides if o.pr_number == pr_number]

        for override in overrides:
            for entry in override.audit_trail:
                entry_copy = {**entry, "override_id": override.id}
                entries.append(entry_copy)

        # Sort by timestamp descending
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        return entries[:limit]

    def cleanup_expired(self) -> int:
        """Clean up expired overrides.

        Returns:
            Number of overrides cleaned up
        """
        count = 0
        now = datetime.now(UTC)

        for override in list(self._overrides.values()):
            if override.expires_at and now > override.expires_at:
                if override.status == OverrideStatus.ACTIVE:
                    override.status = OverrideStatus.EXPIRED
                    override.add_audit_entry(
                        event="expired",
                        actor="system",
                    )
                    count += 1

                    # Remove from PR mapping
                    if override.pr_number in self._pr_overrides:
                        if self._pr_overrides[override.pr_number] == override.id:
                            del self._pr_overrides[override.pr_number]

        return count
