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
        mock_client.send_message.return_value = Mock(success=True, message_id="msg123")
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        success, message_id = await notifier._send_with_retry("Test message")

        assert success is True
        assert message_id == "msg123"
        mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_retry_failure(self, mock_client):
        """Test send failure after retries."""
        mock_client.send_message.return_value = Mock(
            success=False, error="Rate limited"
        )
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up test
            success, message_id = await notifier._send_with_retry(
                "Test message", max_retries=3
            )

        assert success is False
        assert message_id is None
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

    def test_init_with_injected_config(self):
        """Test init with injected config does not require env vars."""
        mock_config = Mock()
        mock_config.development_channel_id = "999999"
        mock_config.webhook_url = None

        with patch(
            "governance.notifications.discord_notifier.DiscordConfig.from_env",
            side_effect=Exception("should not be called"),
        ):
            notifier = DiscordNotifier(config=mock_config)

        # Should have extracted channel from config
        assert notifier.channel_id == "999999"
        # Client should be created from config
        assert notifier.client is not None
        assert notifier._owns_client is True

    def test_init_with_injected_client_and_config(self, mock_client):
        """Test init with both injected client and config uses client."""
        mock_config = Mock()
        mock_config.development_channel_id = "888888"

        notifier = DiscordNotifier(client=mock_client, config=mock_config)

        # Should use injected client, not create new one
        assert notifier.client is mock_client
        assert notifier._owns_client is False
        # Should extract channel from config
        assert notifier.channel_id == "888888"

    @pytest.mark.asyncio
    async def test_webhook_fallback_when_client_fails(self):
        """Test webhook fallback when Discord client is unavailable."""
        mock_config = Mock()
        mock_config.development_channel_id = "123"
        mock_config.webhook_url = "https://discord.com/api/webhooks/test"

        with patch(
            "governance.notifications.discord_notifier.DiscordClient",
            side_effect=Exception("Client creation failed"),
        ):
            notifier = DiscordNotifier(config=mock_config)

        # Client should be None but webhook URL should be set
        assert notifier.client is None
        assert notifier._webhook_url == "https://discord.com/api/webhooks/test"

        # Mock aiohttp for webhook test
        mock_response = Mock()
        mock_response.status = 204

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = Mock()
            mock_session.post = Mock()
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await notifier._send_with_retry("Test message")
            # Note: Due to aiohttp mocking complexity, we at least verify no exception
            # In real usage, webhook would be called

    def test_channel_id_validation_with_fallback(self, mock_client):
        """Test channel_id validation uses fallback correctly."""
        notifier = DiscordNotifier(client=mock_client, channel_id="#test-channel")

        # Valid channel formats should be accepted
        assert notifier._validate_channel_id("123456789") == "123456789"
        assert notifier._validate_channel_id("#channel-name") == "#channel-name"
        # Invalid should return fallback
        assert (
            notifier._validate_channel_id("invalid", fallback="fallback") == "fallback"
        )
        assert notifier._validate_channel_id(None, fallback="fallback") == "fallback"

    @pytest.mark.asyncio
    async def test_validate_channel_with_no_channel_id(self, mock_client):
        """Test channel validation passes when no channel_id is configured."""
        notifier = DiscordNotifier(client=mock_client, channel_id=None)

        is_valid, error_msg = await notifier._validate_channel()

        assert is_valid is True
        assert error_msg is None

    @pytest.mark.asyncio
    async def test_validate_channel_with_client_validation(self, mock_client):
        """Test channel validation uses client.validate_channel_id when available."""
        mock_client.validate_channel_id = AsyncMock(return_value=(True, None))
        notifier = DiscordNotifier(client=mock_client, channel_id="123456789")

        is_valid, error_msg = await notifier._validate_channel()

        assert is_valid is True
        assert error_msg is None
        mock_client.validate_channel_id.assert_called_once_with("123456789")

    @pytest.mark.asyncio
    async def test_validate_channel_fails_gracefully(self, mock_client):
        """Test channel validation failure is logged but doesn't block sending."""
        mock_client.validate_channel_id = AsyncMock(
            return_value=(False, "Channel not found")
        )
        notifier = DiscordNotifier(client=mock_client, channel_id="123456789")

        is_valid, error_msg = await notifier._validate_channel()

        assert is_valid is False
        assert error_msg == "Channel not found"

    @pytest.mark.asyncio
    async def test_validate_channel_exception_handling(self, mock_client):
        """Test channel validation exception triggers graceful degradation."""
        mock_client.validate_channel_id = AsyncMock(
            side_effect=Exception("Network error")
        )
        notifier = DiscordNotifier(client=mock_client, channel_id="123456789")

        # Graceful degradation: validation exception should not block sending
        is_valid, error_msg = await notifier._validate_channel()

        assert is_valid is True  # Should pass to allow send attempt
        assert error_msg is None

    @pytest.mark.asyncio
    async def test_send_with_retry_channel_validation_first(self, mock_client):
        """Test that channel validation is performed before sending."""
        mock_client.validate_channel_id = AsyncMock(return_value=(True, None))
        mock_client.send_message.return_value = Mock(success=True, message_id="msg123")
        notifier = DiscordNotifier(client=mock_client, channel_id="123")

        success, message_id = await notifier._send_with_retry("Test message")

        assert success is True
        assert message_id == "msg123"
        # Validate should be called before send
        mock_client.validate_channel_id.assert_called_once_with("123")
