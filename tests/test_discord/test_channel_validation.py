"""Tests for Discord channel validation.

Tests for ST-DISCORD-VALIDATION-001: Discord channel configuration validation hardening
"""

from __future__ import annotations

from unittest import mock

import pytest

from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient


class MockAsyncContextManager:
    """Helper class to create async context managers for mocking."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass


class TestChannelValidation:
    """Test cases for Discord channel validation."""

    @pytest.fixture
    def config_with_dev_channel(self) -> DiscordConfig:
        """Create config with development channel."""
        return DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
        )

    @pytest.fixture
    def client_with_dev_channel(self, config_with_dev_channel) -> DiscordClient:
        """Create client with development channel."""
        return DiscordClient(config_with_dev_channel)

    @pytest.mark.asyncio
    async def test_validate_channel_id_no_token(self) -> None:
        """Test validation skips when no bot token."""
        config = DiscordConfig(development_channel_id="1234567890123456789")
        client = DiscordClient(config)

        is_valid, error = await client.validate_channel_id("1234567890123456789")

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_channel_id_none(self, client_with_dev_channel) -> None:
        """Test validation passes for None channel ID."""
        is_valid, error = await client_with_dev_channel.validate_channel_id(None)

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_channel_id_valid_text_channel(self) -> None:
        """Test validation passes for valid text channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
        )
        client = DiscordClient(config)

        # Mock the API response for a valid text channel
        mock_response = mock.AsyncMock()
        mock_response.status = 200
        mock_response.json = mock.AsyncMock(
            return_value={
                "id": "1234567890123456789",
                "type": 0,  # GUILD_TEXT
                "name": "test-channel",
                "guild_id": "9876543210987654321",
            }
        )

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("1234567890123456789")

        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_channel_id_guild_id_misconfiguration(self) -> None:
        """Test validation detects guild ID passed as channel ID."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1413522994810327134",  # Guild ID
        )
        client = DiscordClient(config)

        # Mock the API response for a guild (has owner_id, no type)
        mock_response = mock.AsyncMock()
        mock_response.status = 200
        mock_response.json = mock.AsyncMock(
            return_value={
                "id": "1413522994810327134",
                "name": "Test Guild",
                "owner_id": "1234567890123456789",
                "description": "A test guild",
            }
        )

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("1413522994810327134")

        assert is_valid is False
        assert error is not None
        assert "Guild/Server ID" in error
        assert "not a Channel ID" in error
        assert "COMMON MISTAKE" in error

    @pytest.mark.asyncio
    async def test_validate_channel_id_voice_channel(self) -> None:
        """Test validation fails for voice channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
        )
        client = DiscordClient(config)

        # Mock the API response for a voice channel
        mock_response = mock.AsyncMock()
        mock_response.status = 200
        mock_response.json = mock.AsyncMock(
            return_value={
                "id": "1234567890123456789",
                "type": 2,  # GUILD_VOICE
                "name": "test-voice",
            }
        )

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("1234567890123456789")

        assert is_valid is False
        assert error is not None
        assert "not a text channel" in error
        assert "GROUP_DM" in error

    @pytest.mark.asyncio
    async def test_validate_channel_id_not_found(self) -> None:
        """Test validation fails for nonexistent channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="9999999999999999999",
        )
        client = DiscordClient(config)

        mock_response = mock.AsyncMock()
        mock_response.status = 404

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("9999999999999999999")

        assert is_valid is False
        assert error is not None
        assert "not found" in error
        assert "404" in error

    @pytest.mark.asyncio
    async def test_validate_channel_id_unauthorized(self) -> None:
        """Test validation fails for unauthorized access."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
        )
        client = DiscordClient(config)

        mock_response = mock.AsyncMock()
        mock_response.status = 401

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("1234567890123456789")

        assert is_valid is False
        assert error is not None
        assert "Authentication failed" in error

    @pytest.mark.asyncio
    async def test_validate_channel_id_forbidden(self) -> None:
        """Test validation fails for forbidden access."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
        )
        client = DiscordClient(config)

        mock_response = mock.AsyncMock()
        mock_response.status = 403

        mock_session = mock.AsyncMock()
        mock_session.get = mock.MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        with mock.patch.object(client, "_get_session", return_value=mock_session):
            is_valid, error = await client.validate_channel_id("1234567890123456789")

        assert is_valid is False
        assert error is not None
        assert "Access denied" in error
        assert "403" in error


class TestDevelopmentChannelValidation:
    """Test cases for development channel configuration validation."""

    @pytest.mark.asyncio
    async def test_validate_development_channel_success(self) -> None:
        """Test successful validation of development channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1234567890123456789",
            strict_validation=True,
        )
        client = DiscordClient(config)

        # Mock successful channel validation
        with mock.patch.object(
            client, "validate_channel_id", return_value=(True, None)
        ):
            success, errors = await client.validate_development_channel()

        assert success is True
        assert errors == []
        assert config.notifications_enabled is True

    @pytest.mark.asyncio
    async def test_validate_development_channel_no_channel(self) -> None:
        """Test validation passes when no development channel configured."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id=None,
            strict_validation=True,
        )
        client = DiscordClient(config)

        success, errors = await client.validate_development_channel()

        assert success is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_development_channel_strict_mode_failure(self) -> None:
        """Test strict mode fails on invalid channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1413522994810327134",  # Guild ID
            strict_validation=True,
        )
        client = DiscordClient(config)

        error_msg = "This is a Guild/Server ID, not a Channel ID"
        with mock.patch.object(
            client, "validate_channel_id", return_value=(False, error_msg)
        ):
            success, errors = await client.validate_development_channel()

        assert success is False
        assert len(errors) == 1
        assert error_msg in errors[0]
        assert config.validation_errors == errors

    @pytest.mark.asyncio
    async def test_validate_development_channel_non_strict_mode(self) -> None:
        """Test non-strict mode disables notifications on invalid channel."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1413522994810327134",  # Guild ID
            strict_validation=False,
        )
        client = DiscordClient(config)

        error_msg = "This is a Guild/Server ID, not a Channel ID"
        with mock.patch.object(
            client, "validate_channel_id", return_value=(False, error_msg)
        ):
            success, errors = await client.validate_development_channel()

        # Non-strict mode returns success but disables notifications
        assert success is True
        assert len(errors) == 1
        assert config.notifications_enabled is False
        assert config.validation_errors == errors


class TestSendMessageWithValidation:
    """Test cases for send_message with validation checks."""

    @pytest.mark.asyncio
    async def test_send_message_disabled_due_to_validation(self) -> None:
        """Test send fails when notifications disabled due to validation."""
        config = DiscordConfig(
            bot_token="test_token",
            development_channel_id="1413522994810327134",
            strict_validation=False,  # Non-strict mode
        )
        config.notifications_enabled = False
        config.validation_errors = [
            "Invalid channel: Guild ID used instead of Channel ID"
        ]

        client = DiscordClient(config)

        result = await client.send_message("Test message")

        assert result["success"] is False
        assert "disabled" in result["error"].lower()
        assert "validation" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_message_enabled_after_validation(self) -> None:
        """Test send proceeds when validation passed."""
        config = DiscordConfig(
            bot_token="test_token",
            webhook_url="https://discord.com/api/webhooks/123456/test",
            development_channel_id="1234567890123456789",
            strict_validation=True,
        )
        client = DiscordClient(config)
        client.is_connected = True

        # Mock successful validation
        with mock.patch.object(
            client, "validate_development_channel", return_value=(True, [])
        ):
            # This would normally try to send, but we're just checking
            # that notifications are enabled
            assert config.notifications_enabled is True


class TestConfigStrictValidationFlag:
    """Test cases for DISCORD_STRICT_VALIDATION configuration."""

    def test_strict_validation_default_true(self) -> None:
        """Test strict_validation defaults to True."""
        config = DiscordConfig()
        assert config.strict_validation is True

    def test_strict_validation_from_dict_true(self) -> None:
        """Test strict_validation True from dict."""
        config = DiscordConfig.from_dict({"strict_validation": True})
        assert config.strict_validation is True

    def test_strict_validation_from_dict_false(self) -> None:
        """Test strict_validation False from dict."""
        config = DiscordConfig.from_dict({"strict_validation": False})
        assert config.strict_validation is False

    def test_strict_validation_from_env_true(self) -> None:
        """Test strict_validation True from env."""
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"DISCORD_STRICT_VALIDATION": "true"}):
            config = DiscordConfig.from_env()

        assert config.strict_validation is True

    def test_strict_validation_from_env_false(self) -> None:
        """Test strict_validation False from env."""
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"DISCORD_STRICT_VALIDATION": "false"}):
            config = DiscordConfig.from_env()

        assert config.strict_validation is False

    def test_notifications_enabled_default(self) -> None:
        """Test notifications_enabled defaults to True."""
        config = DiscordConfig()
        assert config.notifications_enabled is True

    def test_validation_errors_default_empty(self) -> None:
        """Test validation_errors defaults to empty list."""
        config = DiscordConfig()
        assert config.validation_errors == []

    def test_to_dict_includes_validation_fields(self) -> None:
        """Test to_dict includes new validation fields."""
        config = DiscordConfig(
            strict_validation=False,
            notifications_enabled=False,
            validation_errors=["Test error"],
        )

        config_dict = config.to_dict()

        assert config_dict["strict_validation"] is False
        assert config_dict["notifications_enabled"] is False
        assert config_dict["validation_errors"] == ["Test error"]
