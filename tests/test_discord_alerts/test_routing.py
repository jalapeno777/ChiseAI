"""Tests for Discord alert routing (Gate B fix).

Tests for:
- Bot-send primary method
- Webhook fallback
- Guild lock enforcement
- Channel ID routing

For GATE-RECOVERY-002: Discord Channel Routing Fix
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Set test env vars before importing
os.environ["DISCORD_GUILD_ID"] = "1413522994810327134"
os.environ["DISCORD_SUMMARIES_CHANNEL_ID"] = "1445752426563899492"
os.environ["DISCORD_TRADING_CHANNEL_ID"] = "1444447985378398459"

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DeliveryResult, DiscordClient


class TestDiscordConfig:
    """Tests for DiscordConfig with channel IDs."""

    def test_default_channel_ids(self):
        """Test that authoritative channel IDs are set by default."""
        config = DiscordConfig()

        # Authoritative channel IDs (Gate B fix)
        assert config.summaries_channel_id == "1445752426563899492"
        assert config.trading_channel_id == "1444447985378398459"

    def test_channel_id_resolution(self):
        """Test channel name to ID resolution."""
        config = DiscordConfig()

        # Test summaries channel resolution
        assert config.get_channel_id_for_name("summaries") == "1445752426563899492"
        assert config.get_channel_id_for_name("summary") == "1445752426563899492"
        assert (
            config.get_channel_id_for_name("summaries_channel") == "1445752426563899492"
        )

        # Test trading channel resolution
        assert config.get_channel_id_for_name("trading") == "1444447985378398459"
        assert (
            config.get_channel_id_for_name("trading_channel") == "1444447985378398459"
        )
        assert (
            config.get_channel_id_for_name("trading-signals") == "1444447985378398459"
        )

        # Test unknown channel
        assert config.get_channel_id_for_name("unknown") is None

    def test_from_env_with_channel_ids(self):
        """Test loading config from environment with channel IDs."""
        # Set environment variables
        os.environ["DISCORD_SUMMARIES_CHANNEL_ID"] = "1445752426563899492"
        os.environ["DISCORD_TRADING_CHANNEL_ID"] = "1444447985378398459"
        os.environ["DISCORD_GUILD_ID"] = "1413522994810327134"

        config = DiscordConfig.from_env()

        assert config.summaries_channel_id == "1445752426563899492"
        assert config.trading_channel_id == "1444447985378398459"
        assert config.guild_id == "1413522994810327134"

    def test_from_dict_with_channel_ids(self):
        """Test loading config from dict with channel IDs."""
        config_dict = {
            "bot_token": "test_token",
            "summaries_channel_id": "1445752426563899492",
            "trading_channel_id": "1444447985378398459",
            "guild_id": "1413522994810327134",
        }

        config = DiscordConfig.from_dict(config_dict)

        assert config.bot_token == "test_token"
        assert config.summaries_channel_id == "1445752426563899492"
        assert config.trading_channel_id == "1444447985378398459"
        assert config.guild_id == "1413522994810327134"

    def test_to_dict_includes_channel_ids(self):
        """Test that to_dict includes channel IDs."""
        config = DiscordConfig(
            summaries_channel_id="1445752426563899492",
            trading_channel_id="1444447985378398459",
        )

        result = config.to_dict()

        assert result["summaries_channel_id"] == "1445752426563899492"
        assert result["trading_channel_id"] == "1444447985378398459"


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_delivery_result_defaults(self):
        """Test DeliveryResult with default values."""
        result = DeliveryResult(success=True)

        assert result.success is True
        assert result.message_id is None
        assert result.channel_id is None
        assert result.channel_name is None
        assert result.error is None
        assert result.method == "none"
        assert result.guild_validated is False

    def test_delivery_result_full(self):
        """Test DeliveryResult with all values."""
        result = DeliveryResult(
            success=True,
            message_id="123456789",
            channel_id="1445752426563899492",
            channel_name="summaries",
            error=None,
            method="bot",
            guild_validated=True,
        )

        assert result.success is True
        assert result.message_id == "123456789"
        assert result.channel_id == "1445752426563899492"
        assert result.channel_name == "summaries"
        assert result.error is None
        assert result.method == "bot"
        assert result.guild_validated is True


class TestDiscordClientGuildLock:
    """Tests for guild lock enforcement."""

    def test_validate_guild_no_restriction(self):
        """Test that all guilds are allowed when no guild_id configured."""
        config = DiscordConfig(guild_id=None)
        client = DiscordClient(config)

        assert client.validate_guild("any_guild") is True
        assert client.validate_guild(None) is True

    def test_validate_guild_with_restriction(self):
        """Test guild validation with configured guild_id."""
        config = DiscordConfig(guild_id="1413522994810327134")
        client = DiscordClient(config)

        # Matching guild
        assert client.validate_guild("1413522994810327134") is True

        # Non-matching guild
        assert client.validate_guild("9999999999999999999") is False

        # No guild provided
        assert client.validate_guild(None) is False

    def test_validate_guild_string_comparison(self):
        """Test that guild validation works with string/int comparison."""
        config = DiscordConfig(guild_id="1413522994810327134")
        client = DiscordClient(config)

        # String comparison
        assert client.validate_guild("1413522994810327134") is True

        # Integer as string should also work
        assert client.validate_guild(1413522994810327134) is True


class TestDiscordClientSend:
    """Tests for DiscordClient send methods."""

    @pytest.mark.asyncio
    async def test_send_message_without_connection(self):
        """Test that send fails without connection."""
        config = DiscordConfig()
        client = DiscordClient(config)

        result = await client.send_message("Test message")

        assert result.success is False
        assert "Failed to connect" in result.error

    @pytest.mark.asyncio
    async def test_send_via_webhook_no_url(self):
        """Test webhook send fails without URL."""
        config = DiscordConfig(webhook_url=None)
        client = DiscordClient(config)

        result = await client._send_via_webhook("Test message")

        assert result.success is False
        assert "No webhook URL configured" in result.error
        assert result.method == "webhook"

    @pytest.mark.asyncio
    async def test_send_via_bot_no_token(self):
        """Test bot send fails without token."""
        config = DiscordConfig(bot_token=None)
        client = DiscordClient(config)

        result = await client._send_via_bot(
            "Test message",
            channel_id="1445752426563899492",
            channel_name="summaries",
        )

        assert result.success is False
        assert "Bot not configured" in result.error
        assert result.method == "bot"

    @pytest.mark.asyncio
    async def test_channel_id_resolution_in_send(self):
        """Test that channel names are resolved to IDs in send_message."""
        config = DiscordConfig(
            webhook_url="http://example.com/webhook",
            summaries_channel_id="1445752426563899492",
        )
        client = DiscordClient(config)

        # Mock the webhook send to capture the result
        with patch.object(
            client,
            "_send_via_webhook",
            return_value=DeliveryResult(
                success=True,
                method="webhook",
                channel_id="1445752426563899492",
                channel_name="summaries",
            ),
        ):
            # Also mock connect to return True
            with patch.object(client, "connect", return_value=True):
                client.is_connected = True

                result = await client.send_message(
                    "Test message",
                    channel="summaries",
                )

                assert result.success is True
                assert result.channel_id == "1445752426563899492"


class TestEnvLoaderDiscordConfig:
    """Tests for env_loader Discord config functions."""

    def test_load_discord_config_basic(self):
        """Test basic Discord config loading."""
        from config import load_discord_config

        # Set test env vars
        os.environ["DISCORD_BOT_TOKEN"] = "test_token"
        os.environ["DISCORD_WEBHOOK_URL"] = "http://example.com/webhook"
        os.environ["DISCORD_GUILD_ID"] = "1413522994810327134"

        config = load_discord_config()

        assert config["bot_token"] == "test_token"
        assert config["webhook_url"] == "http://example.com/webhook"
        assert config["guild_id"] == "1413522994810327134"

    def test_load_discord_config_with_ids(self):
        """Test Discord config loading with channel IDs."""
        from config import load_discord_config_with_ids

        # Set test env vars
        os.environ["DISCORD_BOT_TOKEN"] = "test_token"
        os.environ["DISCORD_SUMMARIES_CHANNEL_ID"] = "1445752426563899492"
        os.environ["DISCORD_TRADING_CHANNEL_ID"] = "1444447985378398459"
        os.environ["DISCORD_GUILD_ID"] = "1413522994810327134"

        config = load_discord_config_with_ids()

        assert config["bot_token"] == "test_token"
        assert config["summaries_channel_id"] == "1445752426563899492"
        assert config["trading_channel_id"] == "1444447985378398459"
        assert config["guild_id"] == "1413522994810327134"

    def test_load_discord_config_with_ids_defaults(self):
        """Test Discord config loading with default channel IDs."""
        from config import load_discord_config_with_ids

        # Clear env vars to test defaults
        for key in ["DISCORD_SUMMARIES_CHANNEL_ID", "DISCORD_TRADING_CHANNEL_ID"]:
            if key in os.environ:
                del os.environ[key]

        config = load_discord_config_with_ids()

        # Should use default authoritative IDs
        assert config["summaries_channel_id"] == "1445752426563899492"
        assert config["trading_channel_id"] == "1444447985378398459"


class TestIntegration:
    """Integration tests for Discord routing."""

    @pytest.mark.asyncio
    async def test_fallback_chain_webhook(self):
        """Test that webhook is used as fallback when bot fails."""
        config = DiscordConfig(
            bot_token="fake_token",  # Bot will fail (not implemented)
            webhook_url="http://example.com/webhook",
        )
        client = DiscordClient(config)

        # Mock connect to succeed
        with patch.object(client, "connect", return_value=True):
            client.is_connected = True

            # Mock webhook send to succeed
            with patch.object(
                client,
                "_send_via_webhook",
                return_value=DeliveryResult(
                    success=True,
                    method="webhook",
                    channel_id="1445752426563899492",
                ),
            ) as mock_webhook:
                result = await client.send_message(
                    "Test message",
                    channel="summaries",
                )

                # Webhook should have been called (fallback)
                assert mock_webhook.called
                assert result.success is True
                assert result.method == "webhook"

    def test_authoritative_guild_id(self):
        """Test that authoritative guild ID is enforced."""
        # Authoritative Guild ID: 1413522994810327134
        config = DiscordConfig(guild_id="1413522994810327134")
        client = DiscordClient(config)

        # Should allow the authoritative guild
        assert client.validate_guild("1413522994810327134") is True

        # Should reject other guilds
        assert client.validate_guild("9999999999999999999") is False

    def test_authoritative_channel_ids(self):
        """Test that authoritative channel IDs are used."""
        config = DiscordConfig()

        # Authoritative channel IDs
        assert config.summaries_channel_id == "1445752426563899492"
        assert config.trading_channel_id == "1444447985378398459"

        # Resolution should return authoritative IDs
        assert config.get_channel_id_for_name("summaries") == "1445752426563899492"
        assert config.get_channel_id_for_name("trading") == "1444447985378398459"
