"""Tests for Discord client.

Tests for ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import pytest

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient


class TestDiscordClient:
    """Test cases for DiscordClient."""

    @pytest.fixture
    def config(self) -> DiscordConfig:
        """Create Discord config fixture."""
        return DiscordConfig(
            bot_token="test_token",
            webhook_url="https://discord.com/api/webhooks/123456/test",
            default_channel="trading-signals",
        )

    @pytest.fixture
    def webhook_config(self) -> DiscordConfig:
        """Create webhook-only config fixture."""
        return DiscordConfig(
            webhook_url="https://discord.com/api/webhooks/123456/test",
            default_channel="trading-signals",
        )

    @pytest.fixture
    def bot_config(self) -> DiscordConfig:
        """Create bot-only config fixture."""
        return DiscordConfig(
            bot_token="test_token",
            default_channel="trading-signals",
        )

    def test_client_creation(self, config) -> None:
        """Test creating Discord client."""
        client = DiscordClient(config)

        assert client.config == config
        assert client.is_connected is False
        assert client._session is None

    def test_client_creation_webhook_only(self, webhook_config) -> None:
        """Test creating client with webhook only."""
        client = DiscordClient(webhook_config)

        assert client.config.webhook_url is not None
        assert client.config.bot_token is None

    def test_client_creation_bot_only(self, bot_config) -> None:
        """Test creating client with bot token only."""
        client = DiscordClient(bot_config)

        assert client.config.bot_token is not None
        assert client.config.webhook_url is None

    @pytest.mark.asyncio
    async def test_connect_no_auth(self) -> None:
        """Test connection fails with no authentication."""
        config = DiscordConfig()
        client = DiscordClient(config)

        result = await client.connect()

        assert result is False
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self) -> None:
        """Test health check when not connected."""
        config = DiscordConfig(webhook_url="https://test.webhook")
        client = DiscordClient(config)

        health = await client.health_check()

        assert health["healthy"] is False
        assert health["connected"] is False

    @pytest.mark.asyncio
    async def test_send_message_not_connected_no_auth(self) -> None:
        """Test send fails without authentication."""
        config = DiscordConfig()
        client = DiscordClient(config)

        result = await client.send_message("Test message")

        assert result["success"] is False
        assert "Failed to connect" in result["error"]

    @pytest.mark.asyncio
    async def test_send_message_no_webhook_or_bot(self) -> None:
        """Test send fails with no webhook or bot token."""
        config = DiscordConfig(default_channel="test")
        client = DiscordClient(config)
        client.is_connected = True  # Fake connection

        result = await client.send_message("Test message")

        assert result["success"] is False
        assert "No valid Discord sending method" in result["error"]

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, config) -> None:
        """Test disconnect when not connected."""
        client = DiscordClient(config)

        # Should not raise
        await client.disconnect()

        assert client.is_connected is False

    def test_make_key_private_method(self, config) -> None:
        """Test that client stores config properly."""
        client = DiscordClient(config)

        # Just verify the client was created with the config
        assert client.config.bot_token == "test_token"
        assert (
            client.config.webhook_url == "https://discord.com/api/webhooks/123456/test"
        )

    @pytest.mark.asyncio
    async def test_validate_webhook_no_url(self, config) -> None:
        """Test webhook validation with no URL."""
        config_no_webhook = DiscordConfig(bot_token="test")
        client = DiscordClient(config_no_webhook)

        result = await client._validate_webhook()

        assert result is False

    @pytest.mark.asyncio
    async def test_send_via_webhook_no_url(self, config) -> None:
        """Test webhook send with no URL."""
        config_no_webhook = DiscordConfig(bot_token="test")
        client = DiscordClient(config_no_webhook)

        result = await client._send_via_webhook("Test message")

        assert result["success"] is False
        assert "No webhook URL configured" in result["error"]

    @pytest.mark.asyncio
    async def test_send_via_bot_not_implemented(self, config) -> None:
        """Test bot send returns not implemented."""
        client = DiscordClient(config)

        result = await client._send_via_bot("Test message", "test-channel")

        assert result["success"] is False
        assert "not implemented" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connect_bot_no_token(self) -> None:
        """Test bot connection with no token."""
        config = DiscordConfig()
        client = DiscordClient(config)

        result = await client._connect_bot()

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_with_embeds(self, webhook_config) -> None:
        """Test sending message with embeds."""
        client = DiscordClient(webhook_config)

        embeds = [
            {
                "title": "Test Embed",
                "description": "Test description",
                "color": 0x00FF00,
            }
        ]

        # Will fail to connect but tests the code path
        result = await client.send_message("Test", embeds=embeds)

        # Should attempt connection first
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_health_check_webhook_mode(self, webhook_config) -> None:
        """Test health check in webhook mode."""
        client = DiscordClient(webhook_config)

        # Manually set connected for testing
        client.is_connected = True

        health = await client.health_check()

        # Should check webhook validation
        assert "mode" in health
        assert health["mode"] == "webhook"

    @pytest.mark.asyncio
    async def test_health_check_bot_mode(self, bot_config) -> None:
        """Test health check in bot mode."""
        client = DiscordClient(bot_config)

        # Manually set connected for testing
        client.is_connected = True

        health = await client.health_check()

        assert "mode" in health
        assert health["mode"] == "bot"
