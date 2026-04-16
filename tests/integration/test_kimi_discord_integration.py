"""Integration tests for KIMI and Discord environment loading.

Integration tests for CH-KIMI-DISCORD-001:
Fix KIMI env loading + Discord guild restriction
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from src.config import load_discord_config, load_kimi_config

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient
from llm.kimi_client import KimiClient, KimiConfig


class TestKimiDiscordIntegration:
    """Integration tests for KIMI and Discord with environment loading."""

    def test_kimi_client_uses_env_loader(self):
        """Test that KimiClient properly loads configuration from environment."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "sk-kimi-test-12345",
                "KIMI_MODEL": "k2p5",
                "KIMI_TIMEOUT": "45",
                "KIMI_MAX_RETRIES": "5",
            },
        ):
            config = KimiConfig()

            # The config should load api_key from environment
            # Other fields use defaults (KimiConfig only loads api_key from env)
            assert config.api_key == "sk-kimi-test-12345"
            assert config.model == "k2p5"  # default value
            assert config.timeout == 30.0  # default value
            assert config.max_retries == 3  # default value

            # Use load_kimi_config() for full env loading
            from config import load_kimi_config

            full_config = load_kimi_config()
            assert full_config["timeout"] == 45.0  # loaded from env

    def test_discord_client_uses_env_loader(self):
        """Test that DiscordClient properly loads configuration from environment."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-bot-token",
                "DISCORD_GUILD_ID": "123456789",
                "DISCORD_DEFAULT_CHANNEL": "test-channel",
            },
        ):
            config = DiscordConfig.from_env()

            assert config.bot_token == "test-bot-token"
            assert config.guild_id == "123456789"
            assert config.default_channel == "test-channel"

    def test_end_to_end_env_loading(self):
        """Test end-to-end environment loading for both services."""
        env_vars = {
            "KIMI_API_KEY": "sk-kimi-integration-test",
            "KIMI_TIMEOUT": "60",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test",
            "DISCORD_GUILD_ID": "guild-123",
        }

        with patch.dict(os.environ, env_vars):
            # Load KIMI config
            kimi_config = load_kimi_config()
            assert kimi_config["api_key"] == "sk-kimi-integration-test"
            assert kimi_config["timeout"] == 60.0

            # Load Discord config
            discord_config = load_discord_config()
            assert (
                discord_config["webhook_url"] == "https://discord.com/api/webhooks/test"
            )
            assert discord_config["guild_id"] == "guild-123"

    def test_kimi_discord_clients_together(self):
        """Test that both clients can be instantiated together."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "sk-kimi-test",
                "DISCORD_BOT_TOKEN": "discord-test-token",
                "DISCORD_GUILD_ID": "restricted-guild",
            },
        ):
            # Create KIMI client
            kimi_config = KimiConfig()
            kimi_client = KimiClient(kimi_config)

            # Create Discord client
            discord_config = DiscordConfig.from_env()
            discord_client = DiscordClient(discord_config)

            # Verify configurations
            assert kimi_client.config.api_key == "sk-kimi-test"
            assert discord_client.config.guild_id == "restricted-guild"

            # Verify guild validation works
            assert discord_client.validate_guild("restricted-guild") is True
            assert discord_client.validate_guild("wrong-guild") is False

    @pytest.mark.asyncio
    async def test_discord_health_check_integration(self):
        """Test Discord health check includes guild restriction info."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test",
                "DISCORD_GUILD_ID": "12345",
            },
        ):
            config = DiscordConfig.from_env()
            client = DiscordClient(config)

            # Simulate connection
            client.is_connected = True

            health = await client.health_check()

            assert health["guild_restricted"] is True
            assert health["mode"] == "webhook"

    def test_env_loader_with_missing_optional_vars(self):
        """Test that missing optional environment variables don't break loading."""
        with patch.dict(os.environ, {}, clear=True):
            # Should work with defaults
            kimi_config = load_kimi_config()
            assert kimi_config["api_key"] is None
            assert kimi_config["model"] == "k2p5"

            discord_config = load_discord_config()
            assert discord_config["bot_token"] is None
            assert discord_config["guild_id"] is None

    def test_guild_restriction_flow(self):
        """Test complete guild restriction flow."""
        # Setup environment with guild restriction
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "bot-token",
                "DISCORD_GUILD_ID": "secure-guild-999",
            },
        ):
            # Load config
            config = DiscordConfig.from_env()
            assert config.guild_id == "secure-guild-999"

            # Create client
            client = DiscordClient(config)

            # Test validation
            assert client.validate_guild("secure-guild-999") is True
            assert client.validate_guild("malicious-guild") is False

            # Test that health check reflects restriction
            client.is_connected = True
            # Can't easily test async health check here without more setup


class TestConfigurationConsistency:
    """Tests for configuration consistency between components."""

    def test_kimi_config_types(self):
        """Test that KIMI config values have correct types."""
        with patch.dict(
            os.environ,
            {
                "KIMI_TIMEOUT": "30.5",
                "KIMI_MAX_RETRIES": "3",
                "KIMI_RETRY_DELAY": "1.5",
            },
        ):
            config = load_kimi_config()

            assert isinstance(config["timeout"], float)
            assert isinstance(config["max_retries"], int)
            assert isinstance(config["retry_delay"], float)

    def test_discord_config_types(self):
        """Test that Discord config values have correct types."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "token",
                "DISCORD_GUILD_ID": "12345",
            },
        ):
            config = load_discord_config()

            assert isinstance(config["bot_token"], str)
            assert isinstance(config["guild_id"], str)

    def test_empty_env_vars_handled(self):
        """Test that empty environment variables are handled correctly."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "",  # Empty string
                "DISCORD_GUILD_ID": "",  # Empty string
            },
        ):
            kimi_config = load_kimi_config()
            assert kimi_config["api_key"] is None  # Should treat empty as None

            discord_config = load_discord_config()
            assert discord_config["guild_id"] is None  # Should treat empty as None
