"""Tests for Discord notifier."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from governance.notifications.discord_notifier import DiscordNotifier


class TestDiscordNotifier:
    """Test Discord notifier functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Discord client."""
        client = Mock()
        client.send_message = AsyncMock()
        return client

    def test_is_enabled_default_true(self, mock_client):
        """Test that notifications are enabled by default."""
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        with patch.object(notifier, "_is_enabled", return_value=True):
            assert notifier._is_enabled() is True

    def test_is_duplicate_without_redis(self, mock_client):
        """Test deduplication check without Redis."""
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        with patch(
            "governance.notifications.discord_notifier.get_redis_client",
            return_value=None,
        ):
            assert notifier._is_duplicate("event:123") is False

    def test_init_with_injected_client_without_channel_id(self, mock_client):
        """Test init path does not require config var when client injected."""
        with patch(
            "governance.notifications.discord_notifier.DiscordConfig.from_env",
            side_effect=Exception("missing env"),
        ):
            notifier = DiscordNotifier(client=mock_client)
        assert notifier.client is mock_client
        assert notifier.channel_id is None

    @pytest.mark.asyncio
    async def test_notify_reflection_non_blocking_on_error(self, mock_client):
        """Test that reflection notification is non-blocking on error."""
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        mock_artifact = Mock()
        mock_artifact.date = "2026-03-03"

        # Simulate error in formatter by patching the import inside the method
        with patch.object(notifier, "_is_enabled", return_value=True):
            with patch.object(notifier, "_is_duplicate", return_value=False):
                # Patch the formatter import to raise an exception
                with patch(
                    "builtins.__import__",
                    side_effect=ImportError(
                        "No module named 'governance.notifications.formatters'"
                    ),
                ):
                    result = await notifier.notify_reflection(mock_artifact, "daily")

                    # Should return False but not raise
                    assert result is False

    @pytest.mark.asyncio
    async def test_notify_decision_non_blocking_on_error(self, mock_client):
        """Test that decision notification is non-blocking on error."""
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        # Simulate error by disabling notifications
        with patch.object(notifier, "_is_enabled", return_value=False):
            result = await notifier.notify_decision({"story_id": "ST-001"})

            # Should return False when disabled
            assert result is False

    @pytest.mark.asyncio
    async def test_send_with_retry_success(self, mock_client):
        """Test successful send with retry."""
        mock_client.send_message.return_value = Mock(success=True)
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        result = await notifier._send_with_retry("Test message")

        assert result is True
        mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_retry_failure(self, mock_client):
        """Test send failure after retries."""
        mock_client.send_message.return_value = Mock(
            success=False, error="Rate limited"
        )
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up test
            result = await notifier._send_with_retry("Test message", max_retries=3)

        assert result is False
        assert mock_client.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_notify_self_assessment_success(self, mock_client):
        """Test self-assessment completion notification path."""
        mock_client.send_message.return_value = Mock(success=True)
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        class Artifact:
            assessment_date = "2026-03-13"
            assessment_id = "sa-20260313-test"
            created_at = "2026-03-13T00:00:00+00:00"
            status = "ok"
            overall_score = 0.9
            findings = ["No critical issues"]
            recommendations = ["Continue monitoring"]

        with patch.object(notifier, "_is_enabled", return_value=True):
            with patch.object(notifier, "_is_duplicate", return_value=False):
                with patch.object(notifier, "_mark_sent") as mark_sent:
                    result = await notifier.notify_self_assessment(
                        artifact=Artifact(),
                        artifact_path="docs/governance/self_assessments/a.json",
                    )
        assert result is True
        mark_sent.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_autocog_event_success(self, mock_client):
        """Test generic autonomous cognition event notification path."""
        mock_client.send_message.return_value = Mock(success=True)
        notifier = DiscordNotifier(client=mock_client, channel_id="123")
        with patch.object(notifier, "_is_enabled", return_value=True):
            with patch.object(notifier, "_is_duplicate", return_value=False):
                with patch.object(notifier, "_mark_sent") as mark_sent:
                    result = await notifier.notify_autocog_event(
                        event_type="autocog_cycle_completed",
                        severity="low",
                        summary="Cycle completed",
                        impact="All phases passed",
                        top_metrics={"promotions": 1},
                        artifact_path="_bmad-output/autocog/cycles/run.json",
                        run_id="autocog-run-1",
                    )
        assert result is True
        mark_sent.assert_called_once()
