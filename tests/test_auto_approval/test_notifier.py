"""Tests for auto-approval notifier."""

import pytest
from unittest.mock import AsyncMock, patch

from src.autonomous_git.auto_approval.notifier import DiscordNotifier


class TestDiscordNotifier:
    """Test cases for DiscordNotifier."""

    def test_init_default(self):
        """Test notifier initializes with default values."""
        notifier = DiscordNotifier()

        assert notifier.webhook_url is None
        assert notifier.channel == "#git-activity"
        assert notifier.alert_channel == "#alerts"
        assert notifier.rate_limit == "1 per 5 minutes"

    def test_init_custom(self):
        """Test notifier initializes with custom values."""
        notifier = DiscordNotifier(
            webhook_url="https://discord.com/webhook",
            channel="#custom",
            alert_channel="#custom-alerts",
            rate_limit="5 per 10 minutes",
        )

        assert notifier.webhook_url == "https://discord.com/webhook"
        assert notifier.channel == "#custom"
        assert notifier.alert_channel == "#custom-alerts"
        assert notifier.rate_limit == "5 per 10 minutes"

    def test_parse_rate_limit_default(self):
        """Test parsing default rate limit."""
        notifier = DiscordNotifier()

        assert notifier._rate_limit_count == 1
        assert notifier._rate_limit_seconds == 300  # 5 minutes

    def test_parse_rate_limit_custom(self):
        """Test parsing custom rate limit."""
        notifier = DiscordNotifier(rate_limit="5 per 10 minutes")

        assert notifier._rate_limit_count == 5
        assert notifier._rate_limit_seconds == 600  # 10 minutes

    def test_parse_rate_limit_hours(self):
        """Test parsing hourly rate limit."""
        notifier = DiscordNotifier(rate_limit="10 per 2 hours")

        assert notifier._rate_limit_count == 10
        assert notifier._rate_limit_seconds == 7200  # 2 hours

    def test_parse_rate_limit_seconds(self):
        """Test parsing seconds rate limit."""
        notifier = DiscordNotifier(rate_limit="3 per 30 seconds")

        assert notifier._rate_limit_count == 3
        assert notifier._rate_limit_seconds == 30

    @pytest.mark.asyncio
    async def test_check_rate_limit_memory_allowed(self):
        """Test rate limit check passes when under limit."""
        notifier = DiscordNotifier()

        result = await notifier._check_rate_limit()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_memory_blocked(self):
        """Test rate limit check blocks when over limit."""
        notifier = DiscordNotifier(rate_limit="1 per 3600 seconds")

        # First call should pass and update last_notification_time
        result1 = await notifier._check_rate_limit()
        assert result1 is True

        # Second call should be blocked (within rate limit window)
        result2 = await notifier._check_rate_limit()
        assert result2 is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis(self):
        """Test rate limit check with Redis."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire = AsyncMock()

        notifier = DiscordNotifier(redis_client=mock_redis)

        result = await notifier._check_rate_limit()

        assert result is True
        mock_redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_exceeded(self):
        """Test rate limit check with Redis when exceeded."""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 2  # Exceeds limit of 1

        notifier = DiscordNotifier(
            rate_limit="1 per 5 minutes",
            redis_client=mock_redis,
        )

        result = await notifier._check_rate_limit()

        assert result is False

    @pytest.mark.asyncio
    async def test_notify_auto_merge_success(self):
        """Test successful auto-merge notification."""
        notifier = DiscordNotifier(webhook_url="https://webhook.url")
        notifier._check_rate_limit = AsyncMock(return_value=True)
        notifier._send_webhook = AsyncMock()

        await notifier.notify_auto_merge(
            pr_number=123,
            pr_title="Fix bug",
            author="dev1",
            file_count=5,
            classification_confidence=0.95,
        )

        notifier._send_webhook.assert_called_once()
        call_args = notifier._send_webhook.call_args
        assert call_args[0][1] == "#git-activity"  # channel

    @pytest.mark.asyncio
    async def test_notify_auto_merge_rate_limited(self):
        """Test auto-merge notification when rate limited."""
        notifier = DiscordNotifier()
        notifier._check_rate_limit = AsyncMock(return_value=False)
        notifier._send_webhook = AsyncMock()

        await notifier.notify_auto_merge(
            pr_number=123,
            pr_title="Fix bug",
            author="dev1",
            file_count=5,
            classification_confidence=0.95,
        )

        # Should not send webhook when rate limited
        notifier._send_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_failure(self):
        """Test failure notification."""
        notifier = DiscordNotifier(webhook_url="https://webhook.url")
        notifier._send_webhook = AsyncMock()

        await notifier.notify_failure(
            pr_number=123,
            pr_title="Fix bug",
            author="dev1",
            error_message="API error",
        )

        notifier._send_webhook.assert_called_once()
        call_args = notifier._send_webhook.call_args
        assert call_args[0][1] == "#alerts"  # alert channel

    def test_format_success_message(self):
        """Test success message formatting."""
        notifier = DiscordNotifier()

        payload = notifier._format_success_message(
            pr_number=123,
            pr_title="Fix critical bug",
            author="dev1",
            file_count=5,
            classification_confidence=0.95,
        )

        assert payload["embeds"][0]["title"] == "✅ Auto-Merged PR #123"
        assert payload["embeds"][0]["description"] == "Fix critical bug"
        assert payload["embeds"][0]["color"] == 0x00FF00  # Green

        # Check fields
        fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
        assert fields["Author"] == "dev1"
        assert fields["Files Changed"] == "5"
        assert fields["Confidence"] == "95%"

    def test_format_failure_message(self):
        """Test failure message formatting."""
        notifier = DiscordNotifier()

        payload = notifier._format_failure_message(
            pr_number=123,
            pr_title="Fix bug",
            author="dev1",
            error_message="API connection failed",
        )

        assert "🚨 Auto-approval failed for PR #123" in payload["content"]
        assert payload["embeds"][0]["title"] == "Fix bug"
        assert "API connection failed" in payload["embeds"][0]["description"]
        assert payload["embeds"][0]["color"] == 0xFF0000  # Red

    @pytest.mark.asyncio
    async def test_send_webhook_no_url(self):
        """Test webhook send when no URL configured."""
        notifier = DiscordNotifier(webhook_url=None)

        payload = {"content": "Test"}
        await notifier._send_webhook(payload, "#channel")

        # Should not raise, just log

    @pytest.mark.asyncio
    async def test_send_webhook_success(self):
        """Test successful webhook send."""
        notifier = DiscordNotifier(webhook_url="https://webhook.url")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 204
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )

            payload = {"content": "Test"}
            await notifier._send_webhook(payload, "#channel")

            mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_webhook_rate_limited(self):
        """Test webhook send when Discord rate limits."""
        notifier = DiscordNotifier(webhook_url="https://webhook.url")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_session.post.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )

            payload = {"content": "Test"}
            await notifier._send_webhook(payload, "#channel")

            # Should handle rate limit gracefully
            mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_manual_notification(self):
        """Test manual notification."""
        notifier = DiscordNotifier(webhook_url="https://webhook.url")
        notifier._send_webhook = AsyncMock()

        await notifier.send_manual_notification("Custom message")

        notifier._send_webhook.assert_called_once()
        call_args = notifier._send_webhook.call_args
        assert call_args[0][0]["content"] == "Custom message"
