"""Integration tests for notification routing pipeline.

Tests the full routing pipeline: NotificationEventRouter + SeverityMapper + DiscordNotifier
with mocked dependencies to avoid Redis/Discord external calls.

Note: route_event() only returns routing decisions - it does NOT call the notifier.
The notifier is called by handle_event() which executes the full routing pipeline.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
)


def _mock_redis_get(key: str, field: str):
    """Mock redis_state_hget - returns None to indicate feature enabled."""
    return None  # None means "not set" which defaults to enabled


class TestNotificationRoutingIntegration(unittest.TestCase):
    """Integration tests for the notification routing pipeline."""

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_high_severity_routes_to_immediate_and_delivers_to_discord(
        self, mock_get_redis
    ):
        """Test that high severity events route to immediate and call DiscordNotifier."""
        # Return a dict with "get" callable that returns None (feature enabled)
        mock_get_redis.return_value = {"get": _mock_redis_get}

        # Import here to avoid module-level Redis calls
        from src.governance.notifications.event_router import NotificationEventRouter

        # Create mock DiscordNotifier
        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        # Create router with mocked notifier
        router = NotificationEventRouter(notifier=mock_notifier)

        # Fire event with high severity
        event = {
            "event_type": "execution_quality_change",
            "severity": "high",
            "event_id": "evt-high-001",
            "summary": "Execution quality degraded",
            "impact": "High impact on trade execution",
        }

        # Route the event - check routing decision
        decision = router.route_event(event)

        # Assert routing decision
        self.assertEqual(decision.mode, "immediate")
        self.assertIn("severity", decision.reason.lower())
        self.assertEqual(decision.event_id, "evt-high-001")

        # Execute via handle_event to trigger the notifier
        result = asyncio.run(router.handle_event(event))
        self.assertTrue(result)

        # Assert DiscordNotifier was called for immediate delivery
        mock_notifier.notify_autocog_event.assert_called_once()
        call_kwargs = mock_notifier.notify_autocog_event.call_args.kwargs
        self.assertEqual(call_kwargs["event_type"], "execution_quality_change")
        self.assertEqual(call_kwargs["severity"], "high")
        self.assertEqual(call_kwargs["summary"], "Execution quality degraded")

        # Assert NOT buffered to digest
        mock_notifier.add_to_digest.assert_not_called()

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_low_severity_routes_to_digest_and_buffers(self, mock_get_redis):
        """Test that low severity events route to digest and buffer correctly."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter

        # Create mock DiscordNotifier
        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        # Create router with mocked notifier
        router = NotificationEventRouter(notifier=mock_notifier)

        # Fire event with low severity and event type mapped to low
        event = {
            "event_type": "minor_preference_refinement",
            "severity": "low",
            "event_id": "evt-low-001",
            "summary": "Minor preference updated",
            "impact": "Minimal impact",
        }

        # Route the event - check routing decision
        decision = router.route_event(event)

        # Assert routing decision
        self.assertEqual(decision.mode, "digest")
        self.assertIn("low", decision.reason.lower())

        # Execute via handle_event to trigger the notifier
        result = asyncio.run(router.handle_event(event))
        self.assertTrue(result)

        # Assert buffered to digest
        mock_notifier.add_to_digest.assert_called_once()
        # add_to_digest takes event as positional arg, not kwarg
        call_args = mock_notifier.add_to_digest.call_args
        self.assertEqual(call_args.args[0]["event_id"], "evt-low-001")

        # Assert NOT sent immediately
        mock_notifier.notify_autocog_event.assert_not_called()

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_approval_request_overrides_severity_to_immediate(self, mock_get_redis):
        """Test that approval_request event_type overrides severity to immediate."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter

        # Create mock DiscordNotifier
        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        # Create router with mocked notifier
        router = NotificationEventRouter(notifier=mock_notifier)

        # Fire event with approval_request (in always_send_for list) but low severity
        event = {
            "event_type": "approval_request",
            "severity": "low",  # Would normally be digest, but approval_request is always immediate
            "event_id": "evt-approval-001",
            "summary": "Approval needed for core identity change",
            "impact": "Requires human approval",
        }

        # Route the event - check routing decision
        decision = router.route_event(event)

        # Assert routing decision is immediate despite low severity
        self.assertEqual(decision.mode, "immediate")
        self.assertIn("always_send_for", decision.reason.lower())
        self.assertIn("approval_request", decision.reason)

        # Execute via handle_event to trigger the notifier
        result = asyncio.run(router.handle_event(event))
        self.assertTrue(result)

        # Assert DiscordNotifier was called for immediate delivery
        mock_notifier.notify_autocog_event.assert_called_once()

        # Assert NOT buffered to digest
        mock_notifier.add_to_digest.assert_not_called()

    @patch("src.governance.notifications.event_router._get_redis_client")
    @patch("src.governance.notifications.severity_mapper._get_redis_client")
    def test_severity_mapper_derives_severity_and_routes_correctly(
        self, mock_sev_redis, mock_router_redis
    ):
        """Test that SeverityMapper derives severity when not explicitly provided."""
        mock_router_redis.return_value = {"get": _mock_redis_get}
        mock_sev_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter
        from src.governance.notifications.severity_mapper import SeverityMapper

        # Create mock DiscordNotifier
        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        # Create SeverityMapper with explicit policy_path to ensure it loads correctly
        # Path from worktree root: tests -> worktree -> repo root
        repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
        policy_path = os.path.join(
            repo_root, "config", "aria", "notification-policy.yaml"
        )
        severity_mapper = SeverityMapper(policy_path=policy_path)

        # Verify the mapping is correct
        self.assertEqual(
            severity_mapper.get_severity("execution_quality_change"),
            "high",
            "execution_quality_change should map to high severity",
        )

        # Create router with mocked notifier and severity_mapper
        router = NotificationEventRouter(
            notifier=mock_notifier, severity_mapper=severity_mapper
        )

        # Fire event WITHOUT explicit severity - SeverityMapper should derive it
        event = {
            "event_type": "execution_quality_change",
            # No severity field - should be derived by SeverityMapper
            "event_id": "evt-derived-001",
            "summary": "Quality metrics shifted",
            "impact": "Execution quality change",
        }

        # Route the event - check routing decision
        decision = router.route_event(event)

        # Assert routing is immediate because SeverityMapper derived "high"
        self.assertEqual(decision.mode, "immediate")
        self.assertIn("high", decision.reason.lower())

        # Execute via handle_event to trigger the notifier
        result = asyncio.run(router.handle_event(event))
        self.assertTrue(result)

        # Assert DiscordNotifier was called
        mock_notifier.notify_autocog_event.assert_called_once()

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_digest_builder_generates_correct_format(self, mock_get_redis):
        """Test that DigestBuilder generates correctly formatted digest."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import DigestBuilder

        # Create mock DiscordNotifier with pre-populated buffer
        mock_notifier = MagicMock()
        mock_notifier._low_severity_buffer = [
            {
                "event_type": "minor_preference_refinement",
                "severity": "low",
                "summary": "Preference item 1",
                "run_id": "run-001",
            },
            {
                "event_type": "small_workflow_observation",
                "severity": "low",
                "summary": "Workflow observation 1",
                "run_id": "run-002",
            },
        ]

        # Create DigestBuilder with mocked notifier
        builder = DigestBuilder(notifier=mock_notifier)

        # Verify buffer count
        self.assertEqual(builder.get_buffered_count(), 2)

        # Build the digest
        digest_content = builder.build_digest()

        # Assert digest is formatted correctly
        self.assertIsNotNone(digest_content)
        self.assertIsInstance(digest_content, str)
        self.assertGreater(len(digest_content), 0)

        # Verify the formatter was used by checking content structure
        self.assertIn("Low-Severity Event Digest", digest_content)
        self.assertIn("minor_preference_refinement", digest_content)
        self.assertIn("small_workflow_observation", digest_content)
        self.assertIn("Preference item 1", digest_content)
        self.assertIn("run-001", digest_content)

        # Verify LowSeverityDigestFormatter.format_digest was called implicitly
        # (via build_digest calling the formatter)
        self.assertIn("2 items", digest_content)


class TestDigestBuilderIntegration(unittest.TestCase):
    """Additional tests for DigestBuilder behavior."""

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_digest_builder_empty_buffer_returns_none(self, mock_get_redis):
        """Test that DigestBuilder returns None when buffer is empty."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import DigestBuilder

        # Create mock DiscordNotifier with empty buffer
        mock_notifier = MagicMock()
        mock_notifier._low_severity_buffer = []

        builder = DigestBuilder(notifier=mock_notifier)

        # Build the digest
        digest_content = builder.build_digest()

        # Assert None is returned for empty buffer
        self.assertIsNone(digest_content)

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_digest_builder_should_flush(self, mock_get_redis):
        """Test should_flush logic in DigestBuilder."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import DigestBuilder

        # Create mock DiscordNotifier with buffer at max
        mock_notifier = MagicMock()
        mock_notifier._low_severity_buffer = [{}] * 10  # Default max is 10
        mock_notifier.should_flush_digest = MagicMock(return_value=True)

        builder = DigestBuilder(notifier=mock_notifier)

        # should_flush should delegate to notifier
        self.assertTrue(builder.should_flush())


class TestRoutingEdgeCases(unittest.TestCase):
    """Tests for edge cases and exception handling in routing pipeline."""

    def _mock_redis_get_disabled(self, key: str, field: str):
        """Mock redis_state_hget - returns 'false' to disable feature."""
        return "false"

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_disabled_feature_flag_routes_to_digest(self, mock_get_redis):
        """Test that disabled feature flag routes all events to digest."""
        mock_get_redis.return_value = {"get": self._mock_redis_get_disabled}

        from src.governance.notifications.event_router import NotificationEventRouter

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        router = NotificationEventRouter(notifier=mock_notifier)

        event = {
            "event_type": "core_identity_conflict",
            "severity": "critical",
            "event_id": "evt-disabled-001",
        }

        decision = router.route_event(event)

        # When disabled, safe default is digest
        self.assertEqual(decision.mode, "digest")
        self.assertIn("disabled", decision.reason.lower())

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_send_immediate_exception_returns_false(self, mock_get_redis):
        """Test that exception in _send_immediate returns False gracefully."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(
            side_effect=Exception("Discord connection failed")
        )
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        router = NotificationEventRouter(notifier=mock_notifier)

        event = {
            "event_type": "approval_request",
            "severity": "high",
            "event_id": "evt-exc-001",
        }

        # handle_event should return False when _send_immediate raises
        result = asyncio.run(router.handle_event(event))
        self.assertFalse(result)

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_add_to_digest_exception_returns_false(self, mock_get_redis):
        """Test that exception in _add_to_digest returns False gracefully."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(side_effect=Exception("Buffer full"))

        router = NotificationEventRouter(notifier=mock_notifier)

        event = {
            "event_type": "minor_preference_refinement",
            "severity": "low",
            "event_id": "evt-digest-exc-001",
        }

        # handle_event should return False when _add_to_digest raises
        result = asyncio.run(router.handle_event(event))
        self.assertFalse(result)

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_get_next_digest_time_returns_toronto_timezone(self, mock_get_redis):
        """Test that get_next_digest_time returns datetime in America/Toronto."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import DigestBuilder

        builder = DigestBuilder()
        next_time = builder.get_next_digest_time()

        # Should have Toronto timezone
        self.assertIsNotNone(next_time.tzinfo)

    @patch("src.governance.notifications.event_router._get_redis_client")
    def test_routing_with_minor_event_type_default_severity(self, mock_get_redis):
        """Test routing for event type that maps to medium severity."""
        mock_get_redis.return_value = {"get": _mock_redis_get}

        from src.governance.notifications.event_router import NotificationEventRouter

        mock_notifier = MagicMock()
        mock_notifier.notify_autocog_event = AsyncMock(return_value=True)
        mock_notifier.add_to_digest = MagicMock(return_value=True)

        router = NotificationEventRouter(notifier=mock_notifier)

        event = {
            "event_type": "useful_new_belief",  # Maps to medium severity
            "severity": "medium",
            "event_id": "evt-medium-001",
        }

        decision = router.route_event(event)

        # Medium severity is NOT in immediate list, should go to digest
        self.assertEqual(decision.mode, "digest")


if __name__ == "__main__":
    unittest.main(verbosity=2)
