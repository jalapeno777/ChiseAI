"""
Help Command - Display help information for all commands.

Provides comprehensive help for bot commands, organized by category,
with detailed usage information.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


@dataclass
class CommandHelp:
    """Help information for a single command."""

    name: str
    description: str
    usage: str
    examples: List[str]
    aliases: List[str] = None
    permissions: Optional[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []
        if self.permissions is None:
            self.permissions = "Everyone"


@dataclass
class CategoryHelp:
    """Help information for a command category."""

    name: str
    emoji: str
    description: str
    commands: List[CommandHelp]


# Command help data organized by category
COMMAND_CATEGORIES = {
    "stats": CategoryHelp(
        name="Statistics",
        emoji="📊",
        description="View trading and community statistics",
        commands=[
            CommandHelp(
                name="/stats me",
                description="View your personal trading statistics",
                usage="/stats me [period: 24h|7d|30d|all]",
                examples=["/stats me", "/stats me period:7d"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/stats community",
                description="View community activity statistics",
                usage="/stats community",
                examples=["/stats community"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/stats leaderboard",
                description="View the top traders leaderboard",
                usage="/stats leaderboard [limit: 1-10]",
                examples=["/stats leaderboard", "/stats leaderboard limit:10"],
                permissions="Everyone",
            ),
        ],
    ),
    "subscribe": CategoryHelp(
        name="Subscriptions",
        emoji="📋",
        description="Manage trading signal subscriptions",
        commands=[
            CommandHelp(
                name="/subscribe status",
                description="View your current subscription tier and features",
                usage="/subscribe status",
                examples=["/subscribe status"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/subscribe upgrade",
                description="Upgrade your subscription tier",
                usage="/subscribe upgrade tier:<basic|premium|vip>",
                examples=["/subscribe upgrade tier:premium"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/subscribe pairs",
                description="Manage your enabled trading pairs",
                usage="/subscribe pairs <action> [pair]",
                examples=[
                    "/subscribe pairs list",
                    "/subscribe pairs add BTC/USDT",
                    "/subscribe pairs remove ETH/USDT",
                ],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/subscribe strategies",
                description="Manage your enabled trading strategies",
                usage="/subscribe strategies <action> [strategy]",
                examples=[
                    "/subscribe strategies list",
                    "/subscribe strategies add momentum",
                ],
                permissions="Everyone",
            ),
        ],
    ),
    "signals": CategoryHelp(
        name="Trading Signals",
        emoji="📡",
        description="Receive and manage trading signals",
        commands=[
            CommandHelp(
                name="/signals subscribe",
                description="Subscribe to trading signals",
                usage="/signals subscribe [tier: free|basic|premium]",
                examples=["/signals subscribe", "/signals subscribe tier:basic"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/signals unsubscribe",
                description="Unsubscribe from trading signals",
                usage="/signals unsubscribe",
                examples=["/signals unsubscribe"],
                permissions="Everyone",
            ),
            CommandHelp(
                name="/signals history",
                description="View your recent signal history",
                usage="/signals history [limit: 1-20]",
                examples=["/signals history", "/signals history limit:10"],
                permissions="Everyone",
            ),
        ],
    ),
    "admin": CategoryHelp(
        name="Admin",
        emoji="⚙️",
        description="Administrative commands (staff only)",
        commands=[
            CommandHelp(
                name="/admin broadcast",
                description="Broadcast a message to all subscribers",
                usage="/admin broadcast <message>",
                examples=["/admin broadcast System maintenance in 10 minutes"],
                permissions="Admin",
            ),
            CommandHelp(
                name="/admin signals push",
                description="Manually push a trading signal",
                usage="/admin signals push <pair> <direction> <entry>",
                examples=["/admin signals push BTC/USDT LONG 45000"],
                permissions="Admin",
            ),
            CommandHelp(
                name="/admin signals cancel",
                description="Cancel an active signal",
                usage="/admin signals cancel <signal_id>",
                examples=["/admin signals cancel 12345"],
                permissions="Admin",
            ),
        ],
    ),
}


def create_help_embed(
    category: Optional[str] = None, command: Optional[str] = None
) -> discord.Embed:
    """
    Create a help embed.

    Args:
        category: Optional specific category to show
        command: Optional specific command to show

    Returns:
        Formatted Discord embed
    """
    if command:
        # Find command across all categories
        for cat_help in COMMAND_CATEGORIES.values():
            for cmd_help in cat_help.commands:
                if (
                    cmd_help.name.lower() == command.lower()
                    or command.lower() in cmd_help.aliases
                ):
                    embed = discord.Embed(
                        title=f"📖 Help: {cmd_help.name}",
                        description=cmd_help.description,
                        color=discord.Color.blue(),
                    )

                    embed.add_field(
                        name="Usage", value=f"```{cmd_help.usage}```", inline=False
                    )

                    if cmd_help.examples:
                        examples_text = "\n".join([f"`{e}`" for e in cmd_help.examples])
                        embed.add_field(
                            name="Examples", value=examples_text, inline=False
                        )

                    if cmd_help.aliases:
                        embed.add_field(
                            name="Aliases",
                            value=", ".join(cmd_help.aliases),
                            inline=False,
                        )

                    embed.add_field(
                        name="Required Permissions",
                        value=cmd_help.permissions,
                        inline=False,
                    )

                    return embed

        # Command not found
        return discord.Embed(
            title="❌ Command Not Found",
            description=f"No help available for `{command}`",
            color=discord.Color.red(),
        )

    if category and category in COMMAND_CATEGORIES:
        # Show specific category
        cat_help = COMMAND_CATEGORIES[category]
        embed = discord.Embed(
            title=f"{cat_help.emoji} {cat_help.name}",
            description=cat_help.description,
            color=discord.Color.blue(),
        )

        for cmd_help in cat_help.commands:
            embed.add_field(
                name=cmd_help.name, value=cmd_help.description, inline=False
            )

        return embed

    # Show all categories
    embed = discord.Embed(
        title="🤖 ChiseAI Trading Bot Commands",
        description="Use the dropdown below or click on a category to see available commands.",
        color=discord.Color.blue(),
    )

    # Create overview of categories
    overview = ""
    for key, cat_help in COMMAND_CATEGORIES.items():
        overview += f"{cat_help.emoji} **{cat_help.name}**: {cat_help.description}\n"

    embed.add_field(name="Categories", value=overview, inline=False)

    embed.add_field(
        name="Quick Start",
        value="1. Use `/subscribe status` to check your subscription\n"
        "2. Use `/subscribe upgrade tier:basic` to upgrade\n"
        "3. Use `/stats me` to view your trading stats\n"
        "4. Use `/signals subscribe` to receive signals",
        inline=False,
    )

    embed.set_footer(
        text="💡 Tip: Use /help <command> for detailed help on a specific command"
    )

    return embed


class HelpCommand:
    """
    Help command with category-based organization.
    """

    def __init__(self, bot):
        """
        Initialize help command.

        Args:
            bot: The CommunityBot instance
        """
        self.bot = bot

    async def setup(self, tree: app_commands.CommandTree) -> None:
        """
        Set up help commands in the command tree.

        Args:
            tree: The app commands command tree
        """

        @app_commands.command(name="help", description="Get help with bot commands")
        @app_commands.describe(
            category="Category to get help for (stats, subscribe, signals, admin)",
            command="Specific command to get help for",
        )
        async def help_command(
            interaction: discord.Interaction,
            category: Optional[str] = None,
            command: Optional[str] = None,
        ) -> None:
            """Display help information."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer()

            embed = create_help_embed(category, command)
            await interaction.followup.send(embed=embed)

        # Add command selection choice for autocomplete
        @help_command.autocomplete("category")
        async def category_autocomplete(
            interaction: discord.Interaction, current: str
        ) -> List[app_commands.Choice]:
            """Autocomplete for category parameter."""
            categories = [
                app_commands.Choice(name="Statistics 📊", value="stats"),
                app_commands.Choice(name="Subscriptions 📋", value="subscribe"),
                app_commands.Choice(name="Trading Signals 📡", value="signals"),
                app_commands.Choice(name="Admin ⚙️", value="admin"),
            ]

            if current:
                return [c for c in categories if current.lower() in c.name.lower()]
            return categories

        tree.add_command(help_command)
        self.bot.register_command("help", help_command)

        # Also add a simple help command without params
        @app_commands.command(name="quickhelp", description="Get quick help overview")
        async def quick_help(interaction: discord.Interaction) -> None:
            """Display quick help overview."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer()

            embed = create_help_embed()
            await interaction.followup.send(embed=embed)

        tree.add_command(quick_help)
        self.bot.register_command("quickhelp", quick_help)


async def setup(bot) -> HelpCommand:
    """
    Setup function to register the help command module.

    Args:
        bot: The CommunityBot instance

    Returns:
        Configured HelpCommand instance
    """
    help_cmd = HelpCommand(bot)
    await help_cmd.setup(bot.tree)
    return help_cmd
