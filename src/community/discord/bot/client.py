"""
Discord Community Bot - Main Client

Implements the community bot with rate limiting, error handling,
command registration, and event processing.
"""

import logging
import os
from dataclasses import dataclass, field

import discord
from discord import app_commands

from ..error_handler import ErrorHandler
from ..ratelimit import RateLimitConfig, RateLimiter

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for the community bot."""

    command_prefix: str = "!"
    mention_enabled: bool = True
    devs: list[int] = field(default_factory=list)
    error_webhook_url: str | None = None
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)
    error_max_retries: int = 3
    error_initial_backoff: float = 1.0
    error_max_backoff: float = 60.0


class CommunityBot(discord.Client):
    """
    Main Discord bot for ChiseAI community integration.

    Features:
    - Rate limiting (commands, messages, identify)
    - Error handling with exponential backoff
    - Command registration and routing
    - User authentication and authorization
    """

    def __init__(self, config: BotConfig | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.members = True

        super().__init__(intents=intents)

        self.config = config or BotConfig()

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(config=self.config.rate_limit_config)

        # Initialize error handler
        self.error_handler = ErrorHandler(
            max_retries=self.config.error_max_retries,
            initial_backoff=self.config.error_initial_backoff,
            max_backoff=self.config.error_max_backoff,
            ops_webhook_url=self.config.error_webhook_url,
        )

        # Command tree for slash commands
        self.tree = app_commands.CommandTree(self)

        # Registered commands storage
        self._registered_commands: dict = {}

        # Bot ready state
        self._ready = False

        # Setup logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging for the bot."""
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("chiseai.discord").setLevel(logging.DEBUG)

    async def setup_hook(self) -> None:
        """
        Called when the bot is ready. Registers commands and performs startup.
        """
        logger.info("Setting up bot...")

        # Sync commands with Discord
        await self.tree.sync()

        self._ready = True
        logger.info("Bot setup complete")

    async def on_ready(self) -> None:
        """Called when the bot receives the READY event."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        if not self._ready:
            await self.setup_hook()

        logger.info("Bot is ready to process events")

    async def on_message(self, message: discord.Message) -> None:
        """
        Process incoming messages with rate limiting.

        Args:
            message: The Discord message to process
        """
        # Ignore bot messages
        if message.author.bot:
            return

        # Check message rate limit
        is_allowed, limit_status = await self.rate_limiter.check_channel_message(
            str(message.channel.id)
        )
        if not is_allowed:
            remaining = limit_status.remaining if limit_status else 0
            await message.channel.send(
                f"⚠️ Message rate limit reached. Please wait before sending more messages. ({remaining} remaining)"
            )
            return

        # Check if bot was mentioned (if mention_enabled)
        if self.config.mention_enabled and self.user:
            if self.user.mentioned_in(message):
                await self._handle_mention(message)

    async def _handle_mention(self, message: discord.Message) -> None:
        """
        Handle when the bot is mentioned in a message.

        Args:
            message: The message where the bot was mentioned
        """
        # Acknowledge the mention
        await message.channel.send(
            f"Hello {message.author.mention}! Use `/` for slash commands or type `!help` for prefix commands."
        )

    async def on_command_error(
        self, context: discord.AppCommandContext, error: Exception
    ) -> None:
        """
        Handle errors from application commands.

        Args:
            context: The command context
            error: The exception that occurred
        """
        logger.error(f"Command error in {context.command}: {error}")

        # Check if it's a rate limit error
        user_status = self.rate_limiter.get_user_status(str(context.user.id))
        if user_status.is_limited:
            await context.response.send_message(
                "⚠️ You are rate limited. Please wait before using more commands.",
                ephemeral=True,
            )
            return

        # Check if it's a permission error
        if isinstance(error, discord.Forbidden):
            await context.response.send_message(
                "❌ I don't have permission to do that.", ephemeral=True
            )
            return

        # Handle other errors
        import uuid

        error_id = f"err-{uuid.uuid4().hex[:8]}"
        await self.error_handler.handle_event_error(
            event="on_command_error",
            error=error,
            context={
                "command": context.command.name if context.command else "unknown",
                "user_id": context.user.id,
                "guild_id": context.guild.id if context.guild else None,
            },
        )

        await context.response.send_message(
            f"❌ An error occurred. Error ID: {error_id}", ephemeral=True
        )

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """
        Handle unexpected errors in event handlers.

        Args:
            event_method: The name of the event that errored
            args: Positional arguments from the event
            kwargs: Keyword arguments from the event
        """
        logger.error(f"Error in {event_method}: {args}, {kwargs}")

        error_info = {
            "event": event_method,
            "args": str(args)[:500],
            "kwargs": str(kwargs)[:500],
        }

        await self.error_handler.handle_event_error(
            event=event_method,
            error=Exception(f"Event error in {event_method}"),
            context=error_info,
        )

    async def check_command_rate_limit(self, user_id: int) -> bool:
        """
        Check if a user is rate limited for commands.

        Args:
            user_id: The Discord user ID

        Returns:
            True if allowed, False if rate limited
        """
        is_allowed, _ = await self.rate_limiter.check_user_command(str(user_id))
        return is_allowed

    def get_command_remaining(self, user_id: int) -> int:
        """
        Get remaining commands for a user.

        Args:
            user_id: The Discord user ID

        Returns:
            Number of remaining commands
        """
        status = self.rate_limiter.get_user_status(str(user_id))
        return status.remaining if status else 0

    def register_command(self, name: str, command) -> None:
        """
        Register a command with the bot.

        Args:
            name: The command name
            command: The command object
        """
        self._registered_commands[name] = command
        logger.debug(f"Registered command: {name}")

    def is_dev(self, user_id: int) -> bool:
        """
        Check if a user is a developer.

        Args:
            user_id: The Discord user ID

        Returns:
            True if user is a developer
        """
        return user_id in self.config.devs

    async def close(self) -> None:
        """Cleanly close the bot connection."""
        logger.info("Shutting down bot...")
        await super().close()


def create_bot(
    token: str | None = None, config: BotConfig | None = None
) -> CommunityBot:
    """
    Factory function to create and configure the bot.

    Args:
        token: Discord bot token (defaults to DISCORD_COMMUNITY_BOT_TOKEN env var)
        config: Optional bot configuration

    Returns:
        Configured CommunityBot instance
    """
    if config is None:
        config = BotConfig()

    # Override token from env if not provided
    if token is None:
        token = os.environ.get("DISCORD_COMMUNITY_BOT_TOKEN")

    bot = CommunityBot(config=config)

    return bot
