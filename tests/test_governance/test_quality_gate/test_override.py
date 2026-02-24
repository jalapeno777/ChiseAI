"""Tests for quality gate override module.

For ST-GOV-006: Self-Review Quality Gate
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from src.governance.quality_gate.override import (
    HumanOverride,
    OverrideManager,
    OverrideStatus,
    RiskLevel,
)


class TestHumanOverride:
    """Tests for HumanOverride."""

    def test_override_creation(self) -> None:
        """Test human override creation."""
        override = HumanOverride(
            id="override-test123",
            pr_number=123,
            requester="test-user",
            justification="This is a valid justification for testing purposes with enough characters",
            risk_assessment=RiskLevel.LOW,
            rollback_plan="git revert",
        )

        assert override.id == "override-test123"
        assert override.pr_number == 123
        assert override.status == OverrideStatus.PENDING

    def test_override_to_dict(self) -> None:
        """Test override to dict conversion."""
        override = HumanOverride(
            id="override-abc",
            pr_number=456,
            requester="user",
            justification="Test justification that is long enough for validation requirements",
            risk_assessment=RiskLevel.MEDIUM,
            rollback_plan="rollback plan",
            affected_systems=["api", "db"],
        )

        data = override.to_dict()

        assert data["id"] == "override-abc"
        assert data["pr_number"] == 456
        assert data["status"] == "pending"
        assert data["risk_assessment"] == "medium"
        assert data["affected_systems"] == ["api", "db"]

    def test_add_audit_entry(self) -> None:
        """Test adding audit entries."""
        override = HumanOverride(
            id="override-test",
            pr_number=1,
            requester="user",
            justification="Valid justification text here for testing override creation",
            risk_assessment=RiskLevel.LOW,
            rollback_plan="plan",
        )

        override.add_audit_entry(
            event="test_event",
            actor="test_actor",
            details={"key": "value"},
        )

        assert len(override.audit_trail) == 1
        assert override.audit_trail[0]["event"] == "test_event"
        assert override.audit_trail[0]["actor"] == "test_actor"


class TestOverrideStatus:
    """Tests for OverrideStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test all expected statuses exist."""
        expected = [
            "pending",
            "approved",
            "active",
            "expired",
            "revoked",
            "rolled_back",
        ]
        for status in expected:
            assert OverrideStatus(status) is not None


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_all_risk_levels_exist(self) -> None:
        """Test all expected risk levels exist."""
        expected = ["low", "medium", "high", "critical"]
        for level in expected:
            assert RiskLevel(level) is not None


class TestOverrideManager:
    """Tests for OverrideManager."""

    @pytest.fixture
    def manager(self) -> OverrideManager:
        """Create an override manager instance."""
        return OverrideManager()

    def test_manager_initialization(self) -> None:
        """Test manager initialization."""
        manager = OverrideManager(default_expiration_hours=12)
        assert manager.default_expiration_hours == 12

    def test_manager_max_expiration(self) -> None:
        """Test max expiration is enforced."""
        manager = OverrideManager(default_expiration_hours=48)
        # Should be capped at 24
        assert manager.default_expiration_hours == 24

    def test_create_request(self, manager: OverrideManager) -> None:
        """Test creating an override request."""
        override = manager.create_request(
            pr_number=100,
            requester="test-user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="git revert",
        )

        assert override.pr_number == 100
        assert override.requester == "test-user"
        assert override.status == OverrideStatus.PENDING
        assert override.expires_at is not None

    def test_create_request_short_justification(self, manager: OverrideManager) -> None:
        """Test that short justification is rejected."""
        with pytest.raises(ValueError) as exc_info:
            manager.create_request(
                pr_number=101,
                requester="user",
                justification="too short",
                risk_assessment="low",
                rollback_plan="plan",
            )

        assert "50 characters" in str(exc_info.value)

    def test_create_request_invalid_risk(self, manager: OverrideManager) -> None:
        """Test that invalid risk level is rejected."""
        with pytest.raises(ValueError) as exc_info:
            manager.create_request(
                pr_number=102,
                requester="user",
                justification="This is a valid justification for the override request with enough characters",
                risk_assessment="extreme",
                rollback_plan="plan",
            )

        assert "Invalid risk assessment" in str(exc_info.value)

    def test_approve_request(self, manager: OverrideManager) -> None:
        """Test approving a request."""
        override = manager.create_request(
            pr_number=103,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="medium",
            rollback_plan="plan",
        )

        approved = manager.approve_request(override.id, "approver-user")

        assert approved.status == OverrideStatus.APPROVED
        assert approved.approver == "approver-user"
        assert approved.approved_at is not None

    def test_approve_nonexistent_request(self, manager: OverrideManager) -> None:
        """Test approving a nonexistent request."""
        with pytest.raises(ValueError) as exc_info:
            manager.approve_request("nonexistent", "approver")

        assert "not found" in str(exc_info.value)

    def test_approve_non_pending_request(self, manager: OverrideManager) -> None:
        """Test approving a non-pending request."""
        override = manager.create_request(
            pr_number=104,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")

        with pytest.raises(ValueError) as exc_info:
            manager.approve_request(override.id, "approver2")

        assert "not pending" in str(exc_info.value)

    def test_activate_override(self, manager: OverrideManager) -> None:
        """Test activating an override."""
        override = manager.create_request(
            pr_number=105,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        activated = manager.activate_override(override.id)

        assert activated.status == OverrideStatus.ACTIVE
        assert activated.activated_at is not None

    def test_activate_non_approved_override(self, manager: OverrideManager) -> None:
        """Test activating a non-approved override."""
        override = manager.create_request(
            pr_number=106,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        with pytest.raises(ValueError) as exc_info:
            manager.activate_override(override.id)

        assert "must be approved" in str(exc_info.value)

    def test_revoke_override(self, manager: OverrideManager) -> None:
        """Test revoking an override."""
        override = manager.create_request(
            pr_number=107,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        revoked = manager.revoke_override(override.id, "revoker", "Security concern")

        assert revoked.status == OverrideStatus.REVOKED
        assert revoked.revoked_by == "revoker"
        assert revoked.revoke_reason == "Security concern"

    def test_rollback_override(self, manager: OverrideManager) -> None:
        """Test rolling back an override."""
        override = manager.create_request(
            pr_number=108,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        rolled_back = manager.rollback_override(override.id, "rollback-user")

        assert rolled_back.status == OverrideStatus.ROLLED_BACK
        assert rolled_back.rolled_back_by == "rollback-user"

    def test_rollback_expired_window(self, manager: OverrideManager) -> None:
        """Test rollback fails outside 24-hour window."""
        override = manager.create_request(
            pr_number=109,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        # Simulate expired window
        override.activated_at = datetime.utcnow() - timedelta(hours=25)

        with pytest.raises(ValueError) as exc_info:
            manager.rollback_override(override.id, "user")

        assert "24 hours" in str(exc_info.value)

    def test_get_active_override_for_pr(self, manager: OverrideManager) -> None:
        """Test getting active override for PR."""
        override = manager.create_request(
            pr_number=110,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        active = manager.get_active_override_for_pr(110)

        assert active is not None
        assert active.id == override.id

    def test_get_active_override_for_pr_none(self, manager: OverrideManager) -> None:
        """Test getting active override for PR with no override."""
        active = manager.get_active_override_for_pr(999)
        assert active is None

    def test_get_pending_requests(self, manager: OverrideManager) -> None:
        """Test getting pending requests."""
        # Create multiple requests
        for i in range(3):
            manager.create_request(
                pr_number=200 + i,
                requester="user",
                justification="This is a valid justification for the override request with enough characters",
                risk_assessment="low",
                rollback_plan="plan",
            )

        # Approve one
        pending = manager.get_pending_requests()
        assert len(pending) == 3

        manager.approve_request(pending[0].id, "approver")
        pending = manager.get_pending_requests()
        assert len(pending) == 2

    def test_get_active_overrides(self, manager: OverrideManager) -> None:
        """Test getting active overrides."""
        # Create and activate overrides
        for i in range(2):
            override = manager.create_request(
                pr_number=300 + i,
                requester="user",
                justification="This is a valid justification for the override request with enough characters",
                risk_assessment="low",
                rollback_plan="plan",
            )
            manager.approve_request(override.id, "approver")
            manager.activate_override(override.id)

        active = manager.get_active_overrides()
        assert len(active) == 2

    def test_get_audit_trail(self, manager: OverrideManager) -> None:
        """Test getting audit trail."""
        override = manager.create_request(
            pr_number=400,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        trail = manager.get_audit_trail(override_id=override.id)

        assert len(trail) >= 3  # created, approved, activated
        for entry in trail:
            assert "timestamp" in entry
            assert "event" in entry

    def test_cleanup_expired(self, manager: OverrideManager) -> None:
        """Test cleanup of expired overrides."""
        override = manager.create_request(
            pr_number=500,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
        )

        manager.approve_request(override.id, "approver")
        manager.activate_override(override.id)

        # Simulate expiration
        override.expires_at = datetime.utcnow() - timedelta(hours=1)

        count = manager.cleanup_expired()

        assert count == 1
        assert override.status == OverrideStatus.EXPIRED

    def test_expiration_hours_parameter(self, manager: OverrideManager) -> None:
        """Test custom expiration hours."""
        override = manager.create_request(
            pr_number=600,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
            expiration_hours=6,
        )

        # Check expiration is about 6 hours from now
        expected_expiry = datetime.utcnow() + timedelta(hours=6)
        diff = abs((override.expires_at - expected_expiry).total_seconds())
        assert diff < 60  # Within 1 minute

    def test_expiration_hours_max(self, manager: OverrideManager) -> None:
        """Test expiration hours are capped at max."""
        override = manager.create_request(
            pr_number=601,
            requester="user",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="low",
            rollback_plan="plan",
            expiration_hours=48,  # Over max
        )

        # Should be capped at 24 hours
        expected_expiry = datetime.utcnow() + timedelta(hours=24)
        diff = abs((override.expires_at - expected_expiry).total_seconds())
        assert diff < 60


class TestOverrideAuditTrail:
    """Tests for override audit trail functionality."""

    def test_full_lifecycle_audit(self) -> None:
        """Test audit trail captures full override lifecycle."""
        manager = OverrideManager()

        # Create
        override = manager.create_request(
            pr_number=700,
            requester="creator",
            justification="This is a valid justification for the override request with enough characters",
            risk_assessment="medium",
            rollback_plan="plan",
        )

        # Approve
        manager.approve_request(override.id, "approver")

        # Activate
        manager.activate_override(override.id)

        # Rollback
        manager.rollback_override(override.id, "rollbacker")

        # Get audit trail
        trail = manager.get_audit_trail(pr_number=700)

        events = [e["event"] for e in trail]
        assert "created" in events
        assert "approved" in events
        assert "activated" in events
        assert "rolled_back" in events

        # Check actors
        for entry in trail:
            if entry["event"] == "created":
                assert entry["actor"] == "creator"
            elif entry["event"] == "approved":
                assert entry["actor"] == "approver"
            elif entry["event"] == "rolled_back":
                assert entry["actor"] == "rollbacker"
