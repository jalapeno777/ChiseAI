"""Tests for NotificationEventRouter."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.governance.notifications.discord_notifier import DiscordNotifier
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


class TestNotificationEventRouterFailureRollback:
    """Test cases for NotificationEventRouter failure and rollback scenarios."""

    @patch("src.governance.notifications.event_router.DiscordNotifier")
    async def test_discord_delivery_failure_logs_error_and_returns_false(
        self, mock_notifier_class
    ):
        """Test that Discord delivery failure logs error and returns False.

        When DiscordNotifier.notify_autocog_event raises an exception,
        handle_event() should log the error and return False.
        """
        # Setup mock notifier that raises exception
        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(
            side_effect=Exception("Discord API error")
        )
        mock_notifier_class.return_value = mock_notifier

        router = NotificationEventRouter(notifier=mock_notifier)
        event = {
            "event_type": "execution_quality_change",
            "severity": "high",
            "event_id": "evt-rollback-001",
            "summary": "Test event",
        }

        # Patch logger to verify error logging
        with patch("src.governance.notifications.event_router.logger") as mock_logger:
            result = await router.handle_event(event)

            # handle_event should return False on delivery failure
            assert result is False
            # Logger.error should have been called
            mock_logger.error.assert_called_once()
            assert (
                "Failed to send immediate notification"
                in mock_logger.error.call_args[0][0]
            )

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_redis_unavailable_graceful_fallback(self, mock_get_redis):
        """Test that Redis unavailability doesn't break routing.

        When _get_redis_client returns None (Redis unavailable),
        critical events should still route to immediate mode.
        """
        # Redis unavailable returns None
        mock_get_redis.return_value = None

        router = NotificationEventRouter()
        event = {
            "event_type": "execution_quality_change",
            "severity": "critical",
            "event_id": "evt-rollback-002",
        }

        decision = router.route_event(event)

        # Critical severity should route to immediate even without Redis
        assert decision.mode == "immediate"
        assert "critical" in decision.reason.lower()

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_feature_flag_false_all_events_route_to_digest(self, mock_get_redis):
        """Test that disabled feature flag routes all events to digest (safe-fail rollback).

        When the notification_routing_enabled flag is 'false',
        all events should route to digest regardless of severity or event type.
        """
        # Mock Redis client that returns "false" for the feature flag
        mock_get_redis.return_value = {"get": lambda k, d: "false"}

        router = NotificationEventRouter()

        # Test critical severity event
        event1 = {
            "event_type": "approval_request",
            "severity": "critical",
            "event_id": "evt-rollback-003a",
        }
        decision1 = router.route_event(event1)
        assert decision1.mode == "digest"
        assert "disabled by feature flag" in decision1.reason.lower()

        # Test core_identity_conflict (normally immediate)
        event2 = {
            "event_type": "core_identity_conflict",
            "severity": "critical",
            "event_id": "evt-rollback-003b",
        }
        decision2 = router.route_event(event2)
        assert decision2.mode == "digest"
        assert "disabled by feature flag" in decision2.reason.lower()

        # Test high severity event (normally immediate)
        event3 = {
            "event_type": "execution_quality_change",
            "severity": "high",
            "event_id": "evt-rollback-003c",
        }
        decision3 = router.route_event(event3)
        assert decision3.mode == "digest"
        assert "disabled by feature flag" in decision3.reason.lower()

    def test_digest_buffer_overflow_triggers_should_flush(self):
        """Test that digest buffer overflow triggers should_flush.

        When digest_max_items=3 and 3 low-severity events are added,
        should_flush_digest() should return True.
        """
        notifier = DiscordNotifier(digest_max_items=3)

        # Add 3 low-severity events
        for i in range(3):
            event = {
                "event_type": f"test_event_{i}",
                "severity": "low",
                "event_id": f"evt-overflow-{i}",
                "summary": f"Test event {i}",
            }
            result = notifier.add_to_digest(event)
            assert result is True, f"Event {i} should be buffered"

        # should_flush_digest should return True when buffer is at capacity
        assert notifier.should_flush_digest() is True
