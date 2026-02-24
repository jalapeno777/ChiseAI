"""Tests for audit logger module.

Tests for constitution override audit logging.

For ST-GOV-002: Agent Constitution Artifact
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from src.governance.constitution.audit_logger import (
    AuditLogger,
    OverrideRequest,
    OverrideStatus,
    RiskAssessment,
)


class TestOverrideRequest:
    """Tests for OverrideRequest."""

    @pytest.fixture
    def sample_request(self) -> OverrideRequest:
        """Create a sample override request."""
        return OverrideRequest(
            override_id="test-override-001",
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.MEDIUM,
            affected_systems=["system-a", "system-b"],
            rollback_plan="Step 1: Revert config. Step 2: Verify systems.",
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

    def test_request_creation(self, sample_request: OverrideRequest) -> None:
        """Test request creation."""
        assert sample_request.override_id == "test-override-001"
        assert sample_request.status == OverrideStatus.PENDING

    def test_is_expired_false(self, sample_request: OverrideRequest) -> None:
        """Test expiration check for non-expired request."""
        assert not sample_request.is_expired()

    def test_is_expired_true(self) -> None:
        """Test expiration check for expired request."""
        request = OverrideRequest(
            override_id="expired-001",
            requester="user-123",
            justification="Test justification",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Rollback plan",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert request.is_expired()

    def test_is_rollback_allowed_true(self, sample_request: OverrideRequest) -> None:
        """Test rollback allowed within window."""
        sample_request.status = OverrideStatus.APPROVED
        sample_request.approved_at = datetime.utcnow()

        assert sample_request.is_rollback_allowed()

    def test_is_rollback_allowed_false(self) -> None:
        """Test rollback not allowed outside window."""
        request = OverrideRequest(
            override_id="old-001",
            requester="user-123",
            justification="Test",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        request.status = OverrideStatus.APPROVED
        request.approved_at = datetime.utcnow() - timedelta(hours=25)

        assert not request.is_rollback_allowed()

    def test_to_dict(self, sample_request: OverrideRequest) -> None:
        """Test to dict conversion."""
        data = sample_request.to_dict()

        assert data["override_id"] == "test-override-001"
        assert data["status"] == "pending"
        assert data["risk_assessment"] == "medium"

    def test_from_dict(self, sample_request: OverrideRequest) -> None:
        """Test from dict conversion."""
        data = sample_request.to_dict()
        restored = OverrideRequest.from_dict(data)

        assert restored.override_id == sample_request.override_id
        assert restored.status == sample_request.status


class TestAuditLogger:
    """Tests for AuditLogger."""

    @pytest.fixture
    def logger(self) -> AuditLogger:
        """Create an audit logger instance."""
        return AuditLogger(retention_days=90)

    def test_logger_initialization(self, logger: AuditLogger) -> None:
        """Test logger initialization."""
        assert logger.retention_days == 90

    def test_create_request(self, logger: AuditLogger) -> None:
        """Test creating an override request."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.HIGH,
            affected_systems=["system-a"],
            rollback_plan="Rollback plan",
            expiration_hours=12,
        )

        assert request.status == OverrideStatus.PENDING
        assert request.requester == "user-123"
        assert request.risk_assessment == RiskAssessment.HIGH

    def test_create_request_short_justification(self, logger: AuditLogger) -> None:
        """Test that short justification raises ValueError."""
        with pytest.raises(ValueError, match="50 characters"):
            logger.create_request(
                requester="user-123",
                justification="Too short",
                risk_assessment=RiskAssessment.LOW,
                affected_systems=["system-a"],
                rollback_plan="Plan",
            )

    def test_create_request_expiration_cap(self, logger: AuditLogger) -> None:
        """Test that expiration is capped at 24 hours."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
            expiration_hours=48,  # Should be capped to 24
        )

        # Verify expiration is within 24 hours
        max_expiry = datetime.utcnow() + timedelta(hours=24, seconds=10)
        assert request.expires_at <= max_expiry

    def test_approve_request(self, logger: AuditLogger) -> None:
        """Test approving an override request."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.MEDIUM,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        approved = logger.approve_request(request.override_id, "approver-456")

        assert approved.status == OverrideStatus.APPROVED
        assert approved.approver == "approver-456"
        assert approved.approved_at is not None

    def test_approve_nonexistent_request(self, logger: AuditLogger) -> None:
        """Test approving nonexistent request raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            logger.approve_request("nonexistent-id", "approver")

    def test_approve_already_approved(self, logger: AuditLogger) -> None:
        """Test approving already approved request raises ValueError."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")

        # After approval, request is moved from _pending_requests to _active_overrides
        # So second approval attempt will fail with "not found"
        with pytest.raises(ValueError, match="not found"):
            logger.approve_request(request.override_id, "approver2")

    def test_activate_override(self, logger: AuditLogger) -> None:
        """Test activating an override."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")
        activated = logger.activate_override(request.override_id)

        assert activated.status == OverrideStatus.ACTIVE

    def test_revoke_override(self, logger: AuditLogger) -> None:
        """Test revoking an override."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")
        logger.activate_override(request.override_id)

        revoked = logger.revoke_override(
            request.override_id, "admin-user", "Security concern"
        )

        assert revoked.status == OverrideStatus.REVOKED
        assert revoked.revoked_by == "admin-user"

    def test_rollback_override(self, logger: AuditLogger) -> None:
        """Test rolling back an override."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")
        logger.activate_override(request.override_id)

        rolled_back = logger.rollback_override(request.override_id, "admin-user")

        assert rolled_back.status == OverrideStatus.ROLLED_BACK
        assert rolled_back.rolled_back_by == "admin-user"

    def test_rollback_outside_window(self, logger: AuditLogger) -> None:
        """Test rollback outside 24-hour window raises ValueError."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")
        request.approved_at = datetime.utcnow() - timedelta(
            hours=25
        )  # Manually set old time

        with pytest.raises(ValueError, match="Rollback window"):
            logger.rollback_override(request.override_id, "admin-user")

    def test_record_action(self, logger: AuditLogger) -> None:
        """Test recording actions under override."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        logger.approve_request(request.override_id, "approver")
        logger.activate_override(request.override_id)

        logger.record_action(
            request.override_id,
            action="Modified configuration",
            result="success",
            details={"key": "value"},
        )

        # Verify action was recorded
        updated = logger.get_request(request.override_id)
        assert len(updated.actions_taken) == 1  # type: ignore
        assert updated.actions_taken[0]["action"] == "Modified configuration"  # type: ignore

    def test_get_request(self, logger: AuditLogger) -> None:
        """Test getting a request by ID."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        retrieved = logger.get_request(request.override_id)
        assert retrieved is not None
        assert retrieved.override_id == request.override_id

    def test_get_request_nonexistent(self, logger: AuditLogger) -> None:
        """Test getting nonexistent request returns None."""
        retrieved = logger.get_request("nonexistent-id")
        assert retrieved is None

    def test_get_active_overrides(self, logger: AuditLogger) -> None:
        """Test getting active overrides."""
        # Create and activate an override
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )
        logger.approve_request(request.override_id, "approver")
        logger.activate_override(request.override_id)

        active = logger.get_active_overrides()
        assert len(active) >= 1

    def test_get_pending_requests(self, logger: AuditLogger) -> None:
        """Test getting pending requests."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )

        pending = logger.get_pending_requests()
        assert any(r.override_id == request.override_id for r in pending)

    def test_get_audit_trail(self, logger: AuditLogger) -> None:
        """Test getting audit trail."""
        request = logger.create_request(
            requester="user-123",
            justification="This is a test justification that meets the minimum length requirement of 50 characters.",
            risk_assessment=RiskAssessment.LOW,
            affected_systems=["system-a"],
            rollback_plan="Plan",
        )
        logger.approve_request(request.override_id, "approver")
        logger.activate_override(request.override_id)
        logger.record_action(request.override_id, "test action", "success")

        trail = logger.get_audit_trail()
        assert len(trail) >= 1


class TestRiskAssessment:
    """Tests for RiskAssessment."""

    def test_risk_levels(self) -> None:
        """Test risk level values."""
        assert RiskAssessment.LOW.value == "low"
        assert RiskAssessment.MEDIUM.value == "medium"
        assert RiskAssessment.HIGH.value == "high"
        assert RiskAssessment.CRITICAL.value == "critical"


class TestOverrideStatus:
    """Tests for OverrideStatus."""

    def test_status_values(self) -> None:
        """Test status values."""
        assert OverrideStatus.PENDING.value == "pending"
        assert OverrideStatus.APPROVED.value == "approved"
        assert OverrideStatus.ACTIVE.value == "active"
        assert OverrideStatus.EXPIRED.value == "expired"
        assert OverrideStatus.REVOKED.value == "revoked"
        assert OverrideStatus.ROLLED_BACK.value == "rolled_back"
