"""Tests for centralized environment variable loader.

Tests for CH-KIMI-DISCORD-001: Fix KIMI env loading
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config.env_loader import (
    EnvLoader,
    kimi_loader,
    load_discord_config,
    load_kimi_config,
)


class TestEnvLoader:
    """Test cases for EnvLoader."""

    def test_env_loader_creation(self):
        """Test creating EnvLoader with different configurations."""
        loader = EnvLoader()
        assert loader.prefix is None
        assert loader.strict is False

        loader_with_prefix = EnvLoader(prefix="TEST_", strict=True)
        assert loader_with_prefix.prefix == "TEST_"
        assert loader_with_prefix.strict is True

    def test_get_string_variable(self):
        """Test getting string environment variable."""
        loader = EnvLoader()

        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = loader.get_str("TEST_VAR")
            assert result == "test_value"

    def test_get_string_with_default(self):
        """Test getting string with default value."""
        loader = EnvLoader()

        result = loader.get_str("NONEXISTENT_VAR", default="default_value")
        assert result == "default_value"

    def test_get_integer_variable(self):
        """Test getting integer environment variable."""
        loader = EnvLoader()

        with patch.dict(os.environ, {"TEST_INT": "42"}):
            result = loader.get_int("TEST_INT")
            assert result == 42

    def test_get_integer_invalid(self):
        """Test getting integer with invalid value."""
        loader = EnvLoader()

        with patch.dict(os.environ, {"TEST_INT": "not_a_number"}):
            result = loader.get_int("TEST_INT", default=10)
            assert result == 10

    def test_get_float_variable(self):
        """Test getting float environment variable."""
        loader = EnvLoader()

        with patch.dict(os.environ, {"TEST_FLOAT": "3.14"}):
            result = loader.get_float("TEST_FLOAT")
            assert result == 3.14

    def test_get_boolean_true_values(self):
        """Test getting boolean with true values."""
        loader = EnvLoader()

        for value in ["true", "True", "1", "yes", "on"]:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = loader.get_bool("TEST_BOOL")
                assert result is True, f"Expected True for value: {value}"

    def test_get_boolean_false_values(self):
        """Test getting boolean with false values."""
        loader = EnvLoader()

        for value in ["false", "False", "0", "no", "off", "anything_else"]:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = loader.get_bool("TEST_BOOL")
                assert result is False, f"Expected False for value: {value}"

    def test_get_with_prefix(self):
        """Test getting variable with prefix."""
        loader = EnvLoader(prefix="PREFIX_")

        with patch.dict(os.environ, {"PREFIX_KEY": "prefixed_value"}):
            result = loader.get_str("KEY")
            assert result == "prefixed_value"

    def test_get_required_missing_strict_mode(self):
        """Test getting required variable in strict mode when missing."""
        loader = EnvLoader(strict=True)

        with pytest.raises(ValueError, match="Required environment variable"):
            loader.get_str("DEFINITELY_MISSING_VAR", required=True)

    def test_get_required_missing_non_strict(self):
        """Test getting required variable in non-strict mode."""
        loader = EnvLoader(strict=False)

        result = loader.get_str("DEFINITELY_MISSING_VAR", required=True)
        assert result is None


class TestKimiEnvLoading:
    """Test cases for KIMI environment loading."""

    def test_load_kimi_config_with_api_key(self):
        """Test loading KIMI config with API key."""
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "test-api-key-12345",
                "KIMI_MODEL": "k2p5-latest",
                "KIMI_TIMEOUT": "60",
            },
            clear=True,
        ):
            config = load_kimi_config()

            assert config["api_key"] == "test-api-key-12345"
            assert config["model"] == "k2p5-latest"
            assert config["timeout"] == 60.0
            assert config["base_url"] == "https://api.moonshot.cn/v1"

    def test_load_kimi_config_defaults(self):
        """Test loading KIMI config with default values."""
        # Clear KIMI env vars
        with patch.dict(os.environ, {}, clear=True):
            config = load_kimi_config()

            assert config["api_key"] is None
            assert config["model"] == "kimi-k2.5"
            assert config["timeout"] == 30.0
            assert config["max_retries"] == 3
            assert config["retry_delay"] == 1.0

    def test_kimi_loader_instance(self):
        """Test the global kimi_loader instance."""
        with patch.dict(os.environ, {"KIMI_CUSTOM_VAR": "custom_value"}):
            result = kimi_loader.get_str("CUSTOM_VAR")
            assert result == "custom_value"


class TestDiscordEnvLoading:
    """Test cases for Discord environment loading."""

    def test_load_discord_config_with_guild_id(self):
        """Test loading Discord config with guild restriction."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "test-bot-token",
                "DISCORD_GUILD_ID": "123456789",
                "DISCORD_DEFAULT_CHANNEL": "alerts",
            },
        ):
            config = load_discord_config()

            assert config["bot_token"] == "test-bot-token"
            assert config["guild_id"] == "123456789"
            assert config["default_channel"] == "alerts"

    def test_load_discord_config_without_guild_id(self):
        """Test loading Discord config without guild restriction."""
        from config.env_loader import discord_loader

        with patch.object(discord_loader, "get_str") as mock_get_str:
            # Configure mock to return values based on key
            def side_effect(key, default=None):
                values = {
                    "BOT_TOKEN": None,
                    "WEBHOOK_URL": "https://discord.com/api/webhooks/test",
                    "DEFAULT_CHANNEL": "trading-signals",
                    "GUILD_ID": None,
                }
                return values.get(key, default)

            mock_get_str.side_effect = side_effect
            config = load_discord_config()

            assert config["webhook_url"] == "https://discord.com/api/webhooks/test"
            assert config["guild_id"] is None
            assert config["default_channel"] == "trading-signals"

    def test_load_discord_config_defaults(self):
        """Test loading Discord config with default values."""
        from config.env_loader import discord_loader

        with patch.object(discord_loader, "get_str") as mock_get_str:
            # Configure mock to return default values (all None except default_channel)
            def side_effect(key, default=None):
                if key == "DEFAULT_CHANNEL":
                    return default if default is not None else "trading-signals"
                return default

            mock_get_str.side_effect = side_effect
            config = load_discord_config()

            assert config["bot_token"] is None
            assert config["webhook_url"] is None
            assert config["guild_id"] is None
            assert config["default_channel"] == "trading-signals"
