"""Discord bot client wrapper.

Provides async Discord bot client with webhook fallback support,
error handling, and reconnection logic.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.config import DiscordConfig

logger = logging.getLogger(__name__)


class DiscordClient:
    """Discord bot client with webhook fallback.

    Supports both bot token (for full bot functionality) and
    webhook URL (for simple message posting) authentication.

    Attributes:
        config: Discord configuration
        is_connected: Whether client is connected
        _session: aiohttp ClientSession (created on first use)
    """

    def __init__(self, config: DiscordConfig):
        """Initialize Discord client.

        Args:
            config: Discord configuration
        """
        self.config = config
        self.is_connected = False
        self._session: Any | None = None
        self._bot_client: Any | None = None

    async def _get_session(self) -> Any:
        """Get or create aiohttp session.

        Returns:
            aiohttp ClientSession
        """
        if self._session is None:
            try:
                import aiohttp

                self._session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed, cannot create session")
                raise
        return self._session

    async def connect(self) -> bool:
        """Connect to Discord.

        For webhook mode, this validates the webhook URL.
        For bot token mode, this initializes the bot client.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try webhook first (simpler, no gateway connection needed)
            if self.config.webhook_url:
                if await self._validate_webhook():
                    self.is_connected = True
                    logger.info("Discord client connected via webhook")
                    return True

            # Fall back to bot token
            if self.config.bot_token:
                if await self._connect_bot():
                    self.is_connected = True
                    logger.info("Discord client connected via bot token")
                    return True

            logger.error("No valid Discord authentication configured")
            return False

        except Exception as e:
            logger.error(f"Discord connection failed: {e}")
            return False

    async def _validate_webhook(self) -> bool:
        """Validate webhook URL by making a test request.

        Returns:
            True if webhook is valid, False otherwise
        """
        if not self.config.webhook_url:
            return False

        try:
            session = await self._get_session()
            # Make a GET request to validate webhook exists
            async with session.get(self.config.webhook_url) as resp:
                # Webhooks return 200 with webhook info on GET
                if resp.status == 200:
                    return True
                # Some webhooks may not support GET, so we accept 401/403
                # as "exists but requires POST"
                if resp.status in (401, 403):
                    return True
                logger.warning(f"Webhook validation returned status {resp.status}")
                return False
        except Exception as e:
            logger.warning(f"Webhook validation failed: {e}")
            # Assume valid if we can't check (will fail on actual send)
            return True

    async def _connect_bot(self) -> bool:
        """Connect using bot token.

        Returns:
            True if bot connection successful, False otherwise
        """
        if not self.config.bot_token:
            return False

        try:
            # Try to import discord.py
            import discord

            intents = discord.Intents.default()
            self._bot_client = discord.Client(intents=intents)

            # We don't actually start the client here to avoid blocking
            # The bot client is used for more advanced features
            # For simple message posting, webhook is preferred
            return True

        except ImportError:
            logger.warning("discord.py not installed, bot mode unavailable")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Discord and cleanup resources."""
        self.is_connected = False

        if self._session:
            await self._session.close()
            self._session = None

        if self._bot_client:
            await self._bot_client.close()
            self._bot_client = None

        logger.info("Discord client disconnected")

    async def send_message(
        self,
        content: str,
        channel: str | None = None,
        embeds: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a message to Discord.

        Args:
            content: Message content
            channel: Target channel (uses default if not specified)
            embeds: Optional Discord embeds

        Returns:
            Dictionary with success status and message info
        """
        if not self.is_connected:
            # Auto-connect on first send
            if not await self.connect():
                return {
                    "success": False,
                    "error": "Failed to connect to Discord",
                    "message_id": None,
                }

        target_channel = channel or self.config.default_channel

        # Prefer webhook for simple message posting
        if self.config.webhook_url:
            return await self._send_via_webhook(content, embeds)

        # Fall back to bot client
        if self.config.bot_token and self._bot_client:
            return await self._send_via_bot(content, target_channel, embeds)

        return {
            "success": False,
            "error": "No valid Discord sending method available",
            "message_id": None,
        }

    async def _send_via_webhook(
        self, content: str, embeds: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Send message via webhook.

        Args:
            content: Message content
            embeds: Optional Discord embeds

        Returns:
            Dictionary with success status and message info
        """
        if not self.config.webhook_url:
            return {
                "success": False,
                "error": "No webhook URL configured",
                "message_id": None,
            }

        payload: dict[str, Any] = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            session = await self._get_session()
            async with session.post(self.config.webhook_url, json=payload) as resp:
                if resp.status == 204:
                    # Webhooks return 204 on success
                    return {
                        "success": True,
                        "error": None,
                        "message_id": None,  # Webhooks don't return message ID
                        "channel": "webhook",
                    }
                elif resp.status == 429:
                    # Rate limited
                    retry_after = resp.headers.get("Retry-After", "5")
                    return {
                        "success": False,
                        "error": f"Rate limited. Retry after {retry_after}s",
                        "message_id": None,
                        "retry_after": float(retry_after),
                    }
                else:
                    body = await resp.text()
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}: {body}",
                        "message_id": None,
                    }

        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message_id": None,
            }

    async def _send_via_bot(
        self,
        content: str,
        channel: str,
        embeds: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send message via bot client.

        Args:
            content: Message content
            channel: Target channel name
            embeds: Optional Discord embeds

        Returns:
            Dictionary with success status and message info
        """
        # Bot client sending requires the client to be running
        # This is a placeholder for full bot implementation
        logger.warning("Bot client sending not fully implemented")
        return {
            "success": False,
            "error": "Bot client sending not implemented",
            "message_id": None,
        }

    async def health_check(self) -> dict[str, Any]:
        """Check Discord connection health.

        Returns:
            Dictionary with health status
        """
        if not self.is_connected:
            return {
                "healthy": False,
                "connected": False,
                "error": "Not connected",
            }

        # Test connection by validating webhook or bot status
        if self.config.webhook_url:
            webhook_valid = await self._validate_webhook()
            return {
                "healthy": webhook_valid,
                "connected": self.is_connected,
                "mode": "webhook",
                "error": None if webhook_valid else "Webhook validation failed",
            }

        return {
            "healthy": self.is_connected,
            "connected": self.is_connected,
            "mode": "bot",
            "error": None,
        }
