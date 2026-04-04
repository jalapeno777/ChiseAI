"""Tests for NotificationEventRouter."""

from unittest.mock import MagicMock, patch

from src.governance.notifications.event_router import (
    DigestBuilder,
    NotificationEventRouter,
)


class TestNotificationEventRouter:
    """Test cases for NotificationEventRouter routing decisions."""

    def test_high_severity_routes_to_immediate(self):
        """Test that high severity events route to immediate."""
        router = NotificationEventRouter()
        event = {
            "event_type": "some_event",
            "severity": "high",
            "event_id": "evt-001",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"
        assert "severity" in decision.reason.lower()

    def test_critical_severity_routes_to_immediate(self):
        """Test that critical severity events route to immediate."""
        router = NotificationEventRouter()
        event = {
            "event_type": "some_event",
            "severity": "critical",
            "event_id": "evt-002",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"

    def test_medium_severity_routes_to_digest(self):
        """Test that medium severity events route to digest."""
        router = NotificationEventRouter()
        event = {
            "event_type": "some_event",
            "severity": "medium",
            "event_id": "evt-003",
        }
        decision = router.route_event(event)
        assert decision.mode == "digest"

    def test_low_severity_routes_to_digest(self):
        """Test that low severity events route to digest."""
        router = NotificationEventRouter()
        event = {
            "event_type": "some_event",
            "severity": "low",
            "event_id": "evt-004",
        }
        decision = router.route_event(event)
        assert decision.mode == "digest"

    def test_approval_request_routes_to_immediate(self):
        """Test that approval_request routes to immediate regardless of severity."""
        router = NotificationEventRouter()
        event = {
            "event_type": "approval_request",
            "severity": "low",  # Would be digest, but approval_request is always immediate
            "event_id": "evt-005",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"
        assert "always_send_for" in decision.reason.lower()

    def test_core_identity_conflict_routes_to_immediate(self):
        """Test that core_identity_conflict routes to immediate."""
        router = NotificationEventRouter()
        event = {
            "event_type": "core_identity_conflict",
            "severity": "low",
            "event_id": "evt-006",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"

    def test_governance_conflict_routes_to_immediate(self):
        """Test that governance_conflict routes to immediate."""
        router = NotificationEventRouter()
        event = {
            "event_type": "governance_conflict",
            "severity": "medium",
            "event_id": "evt-007",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"

    def test_safety_conflict_routes_to_immediate(self):
        """Test that safety_conflict routes to immediate."""
        router = NotificationEventRouter()
        event = {
            "event_type": "safety_conflict",
            "severity": "medium",
            "event_id": "evt-008",
        }
        decision = router.route_event(event)
        assert decision.mode == "immediate"

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_disabled_feature_flag_routes_to_digest(self, mock_get_redis):
        """Test that disabled feature flag routes everything to digest."""
        mock_get_redis.return_value = {"get": lambda k, d: "false"}

        router = NotificationEventRouter()
        event = {
            "event_type": "core_identity_conflict",
            "severity": "critical",
            "event_id": "evt-009",
        }
        decision = router.route_event(event)
        # When disabled, safe default is digest
        assert decision.mode == "digest"

    def test_unknown_event_type_defaults_to_digest(self):
        """Test that unknown event types default to digest."""
        router = NotificationEventRouter()
        event = {
            "event_type": "totally_unknown_event_xyz",
            "severity": "low",
            "event_id": "evt-010",
        }
        decision = router.route_event(event)
        assert decision.mode == "digest"

    def test_severity_mapper_derives_severity_when_no_explicit_severity(self):
        """Test that SeverityMapper is used to derive severity when no explicit severity provided.

        AC #1 Fix verification: When event has no explicit severity but SeverityMapper
        maps event_type to a high-severity level, the event should route to immediate.
        """
        # Create mock SeverityMapper that maps "policy_drift" -> "high"
        mock_mapper = MagicMock()
        mock_mapper.get_severity.return_value = "high"

        router = NotificationEventRouter(severity_mapper=mock_mapper)
        event = {
            "event_type": "policy_drift",  # No explicit "severity" key
            "event_id": "evt-011",
        }

        decision = router.route_event(event)

        # Should route to immediate because SeverityMapper derived "high"
        assert decision.mode == "immediate"
        assert "severity 'high'" in decision.reason
        # Verify SeverityMapper was called
        mock_mapper.get_severity.assert_called_once_with("policy_drift")

    def test_explicit_severity_bypasses_severity_mapper(self):
        """Test that explicit severity in event is used, not SeverityMapper."""
        mock_mapper = MagicMock()
        mock_mapper.get_severity.return_value = "high"

        router = NotificationEventRouter(severity_mapper=mock_mapper)
        event = {
            "event_type": "policy_drift",
            "severity": "low",  # Explicit severity
            "event_id": "evt-012",
        }

        decision = router.route_event(event)

        # Should route to digest because explicit severity is "low"
        assert decision.mode == "digest"
        # SeverityMapper should NOT be called when explicit severity present
        mock_mapper.get_severity.assert_not_called()


class TestDigestBuilder:
    """Test cases for DigestBuilder skeleton."""

    def test_get_next_digest_time_returns_toronto_time(self):
        """Test that next digest time is in America/Toronto timezone."""
        builder = DigestBuilder()
        next_time = builder.get_next_digest_time()

        assert next_time.tzinfo is not None
        assert str(next_time.tzinfo) == "America/Toronto"

    def test_get_buffered_count_returns_zero_initially(self):
        """Test that buffered count is 0 initially."""
        builder = DigestBuilder()
        assert builder.get_buffered_count() == 0

    def test_build_digest_returns_none_when_empty(self):
        """Test that build_digest returns None when buffer is empty."""
        builder = DigestBuilder()
        result = builder.build_digest()
        assert result is None
