"""Tests for escalation management in autonomous improvement cycles."""

from __future__ import annotations

from unittest.mock import MagicMock

from autonomous_cognition.improvement.escalation import (
    EscalationEvent,
    EscalationManager,
    EscalationStatus,
    EscalationType,
)


class TestEscalationEvent:
    """Tests for EscalationEvent dataclass."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = EscalationEvent(
            event_id="test-123",
            escalation_type=EscalationType.BOUNDARY_VIOLATION,
            description="Test violation",
            severity="high",
        )
        assert event.event_id == "test-123"
        assert event.escalation_type == EscalationType.BOUNDARY_VIOLATION
        assert event.status == EscalationStatus.PENDING
        assert event.severity == "high"
        assert event.created_at != ""  # Auto-set

    def test_event_to_dict(self):
        """Test event serialization."""
        event = EscalationEvent(
            event_id="test-123",
            escalation_type=EscalationType.EMERGENCY_STOP,
            description="Emergency",
            severity="critical",
        )
        d = event.to_dict()
        assert d["event_id"] == "test-123"
        assert d["escalation_type"] == "emergency_stop"
        assert d["severity"] == "critical"


class TestEscalationManager:
    """Tests for EscalationManager."""

    def test_create_escalation(self):
        """Test creating an escalation event."""
        manager = EscalationManager()
        event = manager.create_escalation(
            EscalationType.BOUNDARY_VIOLATION,
            "Blocked file access",
            severity="high",
            proposal_id="prop-123",
        )
        assert event.escalation_type == EscalationType.BOUNDARY_VIOLATION
        assert event.severity == "high"
        assert event.proposal_id == "prop-123"
        assert event.event_id in manager._events

    def test_request_boundary_approval_without_gates(self):
        """Test approval request when no gates configured."""
        manager = EscalationManager()
        event = manager.create_escalation(
            EscalationType.BOUNDARY_VIOLATION,
            "Test",
        )
        result = manager.request_boundary_approval(event)
        assert result is None

    def test_request_boundary_approval_with_gates(self):
        """Test approval request with gates configured."""
        mock_gates = MagicMock()
        mock_result = MagicMock()
        mock_result.request_id = "req-456"
        mock_gates.request_approval.return_value = mock_result

        manager = EscalationManager(approval_gates=mock_gates)
        event = manager.create_escalation(
            EscalationType.BOUNDARY_VIOLATION,
            "Test",
        )
        result = manager.request_boundary_approval(event)

        assert result == "req-456"
        mock_gates.request_approval.assert_called_once()

    def test_handle_emergency_stop(self):
        """Test emergency stop handling."""
        manager = EscalationManager()
        handler = MagicMock()
        manager.register_emergency_stop_handler(handler)

        event = manager.handle_emergency_stop("Critical failure", proposal_id="prop-1")

        assert event.escalation_type == EscalationType.EMERGENCY_STOP
        assert event.severity == "critical"
        handler.assert_called_once_with(event)

    def test_resolve_escalation(self):
        """Test resolving an escalation."""
        manager = EscalationManager()
        event = manager.create_escalation(
            EscalationType.VALIDATION_FAILED,
            "Test failed",
        )

        resolved = manager.resolve_escalation(
            event.event_id,
            resolved_by="admin",
        )

        assert resolved is not None
        assert resolved.status == EscalationStatus.RESOLVED
        assert resolved.resolved_by == "admin"
        assert event.event_id not in manager._events
        assert resolved in manager._history

    def test_get_pending_escalations(self):
        """Test getting pending escalations."""
        manager = EscalationManager()
        manager.create_escalation(EscalationType.BOUNDARY_VIOLATION, "pending 1")
        manager.create_escalation(EscalationType.RISK_EXCEEDED, "pending 2")
        event3 = manager.create_escalation(EscalationType.VALIDATION_FAILED, "resolved")
        manager.resolve_escalation(event3.event_id, "admin")

        pending = manager.get_pending_escalations()
        assert len(pending) == 2

    def test_get_stats(self):
        """Test escalation statistics."""
        manager = EscalationManager()
        manager.create_escalation(EscalationType.BOUNDARY_VIOLATION, "test 1")
        manager.create_escalation(EscalationType.EMERGENCY_STOP, "test 2")

        stats = manager.get_stats()

        assert stats["total_events"] == 2
        assert stats["pending"] == 2
        assert stats["resolved"] == 0
        assert "boundary_violation" in stats["by_type"]
