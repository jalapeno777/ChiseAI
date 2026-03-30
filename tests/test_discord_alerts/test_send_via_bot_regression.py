"""Regression tests for _send_via_bot method.

Tests that _send_via_bot correctly references self._bot_client
instead of the non-existent self.bot attribute.

For ST-NS-REMEDIATION-001: Hotfix for C-4 regression
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.discord_alerts.config import DiscordConfig
from src.discord_alerts.discord_client import DiscordClient


@pytest.fixture
def mock_discord_config() -> DiscordConfig:
    """Create a mock DiscordConfig with bot token configured."""
    config = MagicMock(spec=DiscordConfig)
    config.bot_token = "test_bot_token_12345"
    config.webhook_url = None
    config.default_channel = "test-channel"
    config.guild_id = "123456789"
    config.max_retries = 3
    config.timeout_seconds = 5
    config.rate_limit_backoff_seconds = 1
    return config


@pytest.fixture
def mock_bot_client() -> MagicMock:
    """Create a mock Discord bot client."""
    mock_client = MagicMock()
    mock_client.is_ready.return_value = True

    # Mock channel with async send method
    mock_channel = MagicMock()
    mock_channel.id = 987654321
    mock_channel.name = "test-channel"
    # channel.send() is async
    mock_channel.send = AsyncMock(return_value=MagicMock(id=123456789))
    mock_client.get_channel.return_value = mock_channel

    return mock_client


@pytest.mark.asyncio
async def test_send_via_bot_uses_bot_client_attribute(
    mock_discord_config: DiscordConfig,
    mock_bot_client: MagicMock,
) -> None:
    """Test that _send_via_bot uses self._bot_client (not self.bot).

    This is a regression test for ST-NS-REMEDIATION-001 where C-4 fix
    accidentally used self.bot instead of self._bot_client.
    """
    client = DiscordClient(config=mock_discord_config)

    # Inject the mock bot client directly (simulating what _initialize_bot does)
    client._bot_client = mock_bot_client

    # Call _send_via_bot with content and channel_id
    result = await client._send_via_bot(
        content="Test message",
        channel_id="987654321",
        channel_name="test-channel",
    )

    # Verify the bot client methods were called correctly
    assert mock_bot_client.is_ready.called
    assert mock_bot_client.get_channel.called

    # Verify the result indicates success (channel was found)
    assert result.success is True
    assert result.method == "bot"
    assert result.channel_id == "987654321"


@pytest.mark.asyncio
async def test_send_via_bot_falls_back_when_bot_not_ready(
    mock_discord_config: DiscordConfig,
) -> None:
    """Test that _send_via_bot handles bot not ready state correctly."""
    client = DiscordClient(config=mock_discord_config)

    # Create a mock bot client that is NOT ready
    mock_bot_client = MagicMock()
    mock_bot_client.is_ready.return_value = False
    client._bot_client = mock_bot_client

    result = await client._send_via_bot(
        content="Test message",
        channel_id="987654321",
        channel_name="test-channel",
    )

    # Should fail with "Bot not available" since bot is not ready
    assert result.success is False
    assert result.error == "Bot not available"
    assert result.method == "bot"


@pytest.mark.asyncio
async def test_send_via_bot_no_bot_client_attribute_error(
    mock_discord_config: DiscordConfig,
) -> None:
    """Test that _send_via_bot does NOT raise AttributeError when _bot_client is None.

    Verifies the fix for self.bot -> self._bot_client regression.
    If the code incorrectly references self.bot (instead of self._bot_client),
    this would raise AttributeError since 'bot' is not an attribute of DiscordClient.
    """
    client = DiscordClient(config=mock_discord_config)

    # Explicitly do NOT set _bot_client (it's already None from __init__)
    assert client._bot_client is None

    # This should return "Bot not configured" error, NOT raise AttributeError
    # If self.bot was used instead of self._bot_client, we'd get:
    # AttributeError: 'DiscordClient' object has no attribute 'bot'
    result = await client._send_via_bot(
        content="Test message",
        channel_id="987654321",
        channel_name="test-channel",
    )

    # Should fail gracefully because bot_token is set but _bot_client is None
    # This exercises the is_ready check path
    assert result.success is False
    assert result.error == "Bot not available"
    assert result.method == "bot"
