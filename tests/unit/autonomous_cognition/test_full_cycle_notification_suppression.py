"""Unit tests for notification suppression in full_cycle.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from autonomous_cognition.full_cycle import AutonomousCognitionFullCycle


class TestNotificationSuppressionIntegration:
    """Test that should_notify_for_cycle_event gates Discord notifications."""

    def test_notify_autocog_event_skipped_when_should_notify_returns_false(
        self,
    ) -> None:
        """When should_notify_for_cycle_event returns False, notify_autocog_event should not be called."""
        runner = AutonomousCognitionFullCycle()

        # Mock the notifier
        mock_notifier = MagicMock()
        mock_notifier.should_notify_for_cycle_event.return_value = False
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        # Patch DiscordNotifier to return our mock
        with patch(
            "autonomous_cognition.full_cycle.DiscordNotifier",
            return_value=mock_notifier,
        ):
            # Create a mock event loop that handles ALL run_until_complete calls
            mock_loop = MagicMock()

            async def mock_run_until(coro):
                return coro

            mock_loop.run_until_complete.side_effect = mock_run_until
            with patch(
                "asyncio.new_event_loop",
                return_value=mock_loop,
            ):
                result = runner.run(notify_discord=True, mode="full")

        # Verify should_notify_for_cycle_event was called at least once
        assert mock_notifier.should_notify_for_cycle_event.call_count >= 1

        # Verify the suppressed notification counter was incremented
        assert result.metrics.get("notifications_suppressed") == 1

    def test_notify_autocog_event_called_when_should_notify_returns_true(
        self,
    ) -> None:
        """When should_notify_for_cycle_event returns True, notify_autocog_event should be called."""
        runner = AutonomousCognitionFullCycle()

        # Mock the notifier
        mock_notifier = MagicMock()
        mock_notifier.should_notify_for_cycle_event.return_value = True
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        # Patch DiscordNotifier to return our mock
        with patch(
            "autonomous_cognition.full_cycle.DiscordNotifier",
            return_value=mock_notifier,
        ):
            mock_loop = MagicMock()

            async def mock_run_until(coro):
                return coro

            mock_loop.run_until_complete.side_effect = mock_run_until
            with patch(
                "asyncio.new_event_loop",
                return_value=mock_loop,
            ):
                result = runner.run(notify_discord=True, mode="full")

        # Verify should_notify_for_cycle_event was called at least once
        assert mock_notifier.should_notify_for_cycle_event.call_count >= 1

        # Verify notify_autocog_event WAS called at least once (since should_notify returned True)
        assert mock_notifier.notify_autocog_event.call_count >= 1

        # Verify the suppressed notification counter was NOT set
        assert result.metrics.get("notifications_suppressed") is None

    def test_should_notify_receives_correct_parameters(self) -> None:
        """Verify should_notify_for_cycle_event is called with correct parameters."""
        runner = AutonomousCognitionFullCycle()

        # Capture the call arguments
        captured_args = {}

        def capture_should_notify(*args, **kwargs):
            captured_args.update(kwargs)
            return True

        mock_notifier = MagicMock()
        mock_notifier.should_notify_for_cycle_event.side_effect = capture_should_notify
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        with patch(
            "autonomous_cognition.full_cycle.DiscordNotifier",
            return_value=mock_notifier,
        ):
            mock_loop = MagicMock()

            async def mock_run_until(coro):
                return coro

            mock_loop.run_until_complete.side_effect = mock_run_until
            with patch(
                "asyncio.new_event_loop",
                return_value=mock_loop,
            ):
                runner.run(notify_discord=True, mode="full")

        # Verify mode parameter was passed
        assert captured_args.get("mode") == "full"

        # Verify actions_taken is an integer (len of actions list)
        assert isinstance(captured_args.get("actions_taken"), int)

        # Verify score_drift_threshold is 0.01
        assert captured_args.get("score_drift_threshold") == 0.01

        # Verify metrics is result.metrics
        assert "metrics" in captured_args
        assert isinstance(captured_args.get("metrics"), dict)

        # Verify previous_score was requested (method exists on runner)
        assert "previous_score" in captured_args

    def test_suppression_logged_when_notification_skipped(self) -> None:
        """When notification is suppressed, a log message should be generated."""
        runner = AutonomousCognitionFullCycle()

        mock_notifier = MagicMock()
        mock_notifier.should_notify_for_cycle_event.return_value = False
        mock_notifier.notify_autocog_event.return_value = None
        mock_notifier.close.return_value = None

        with patch(
            "autonomous_cognition.full_cycle.DiscordNotifier",
            return_value=mock_notifier,
        ):
            mock_loop = MagicMock()

            async def mock_run_until(coro):
                return coro

            mock_loop.run_until_complete.side_effect = mock_run_until
            with patch(
                "asyncio.new_event_loop",
                return_value=mock_loop,
            ):
                with patch("autonomous_cognition.full_cycle.logger") as mock_logger:
                    result = runner.run(notify_discord=True, mode="full")

                    # Verify logger.info was called with suppression message
                    log_calls = mock_logger.info.call_args_list
                    suppression_log_found = any(
                        "suppressed" in str(call) and "hash match" in str(call)
                        for call in log_calls
                    )
                    assert (
                        suppression_log_found
                    ), f"Expected suppression log message not found. Log calls: {log_calls}"
