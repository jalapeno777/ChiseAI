"""
Statistics Command - Display community and trading stats.

Provides commands to view trading statistics, portfolio performance,
and community activity metrics.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.app_commands import Transform

logger = logging.getLogger(__name__)


@dataclass
class TradingStats:
    """Trading statistics for a user or the community."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_trade_size: float = 0.0
    most_traded_pair: str = "N/A"
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


@dataclass
class CommunityStats:
    """Community activity statistics."""

    total_members: int = 0
    active_members_24h: int = 0
    total_messages_24h: int = 0
    new_members_7d: int = 0
    active_voice_channels: int = 0


class StatsTransformer(Transform[TradingStats, str]):
    """Transformer for trading stats display."""

    @classmethod
    async def transform(
        cls, interaction: discord.Interaction, value: str
    ) -> TradingStats:
        """Transform string period to TradingStats."""
        # Default to 24h stats
        return TradingStats(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_pnl=0.0,
            win_rate=0.0,
            period_start=datetime.utcnow() - timedelta(days=1),
            period_end=datetime.utcnow(),
        )


async def fetch_user_stats(user_id: int, period: str = "24h") -> TradingStats:
    """
    Fetch trading statistics for a user.

    Args:
        user_id: Discord user ID
        period: Time period (24h, 7d, 30d, all)

    Returns:
        TradingStats for the user
    """
    # TODO: Integrate with trading database/Redis
    # Placeholder implementation
    return TradingStats(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        total_pnl=0.0,
        win_rate=0.0,
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow(),
    )


async def fetch_community_stats(guild_id: int) -> CommunityStats:
    """
    Fetch community statistics for a guild.

    Args:
        guild_id: Discord guild ID

    Returns:
        CommunityStats for the guild
    """
    # TODO: Integrate with Discord API and community tracking
    # Placeholder implementation
    return CommunityStats(
        total_members=0,
        active_members_24h=0,
        total_messages_24h=0,
        new_members_7d=0,
        active_voice_channels=0,
    )


class StatsCommand:
    """
    Commands for displaying trading and community statistics.
    """

    def __init__(self, bot):
        """
        Initialize stats commands.

        Args:
            bot: The CommunityBot instance
        """
        self.bot = bot
        self._setup_commands()

    def _setup_commands(self) -> None:
        """Register stats commands with the bot."""
        pass  # Commands are registered via decorators in setup()

    async def setup(self, tree: app_commands.CommandTree) -> None:
        """
        Set up stats commands in the command tree.

        Args:
            tree: The app commands command tree
        """
        stats_group = app_commands.Group(
            name="stats", description="Trading and community statistics"
        )

        @stats_group.command(name="me", description="View your trading statistics")
        @app_commands.describe(period="Time period to view (24h, 7d, 30d, all)")
        async def user_stats(
            interaction: discord.Interaction, period: str = "24h"
        ) -> None:
            """Display trading statistics for the user."""
            # Check rate limit
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer()

            try:
                stats = await fetch_user_stats(interaction.user.id, period)

                # Calculate win rate
                if stats.total_trades > 0:
                    stats.win_rate = (stats.winning_trades / stats.total_trades) * 100

                embed = discord.Embed(
                    title=f"📊 Your Trading Statistics ({period})",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow(),
                )

                embed.add_field(
                    name="Total Trades", value=str(stats.total_trades), inline=True
                )
                embed.add_field(
                    name="Win Rate",
                    value=f"{stats.win_rate:.1f}%" if stats.total_trades > 0 else "N/A",
                    inline=True,
                )
                embed.add_field(
                    name="Total P&L", value=f"${stats.total_pnl:,.2f}", inline=True
                )
                embed.add_field(
                    name="Winning Trades", value=str(stats.winning_trades), inline=True
                )
                embed.add_field(
                    name="Losing Trades", value=str(stats.losing_trades), inline=True
                )
                embed.add_field(
                    name="Most Traded Pair", value=stats.most_traded_pair, inline=True
                )

                embed.set_footer(
                    text=f"Remaining commands: {self.bot.get_command_remaining(interaction.user.id)}"
                )

                await interaction.followup.send(embed=embed)

            except Exception as e:
                logger.error(f"Error fetching user stats: {e}")
                await interaction.followup.send(
                    "❌ Failed to fetch your statistics. Please try again.",
                    ephemeral=True,
                )

        @stats_group.command(name="community", description="View community statistics")
        async def community_stats(interaction: discord.Interaction) -> None:
            """Display community activity statistics."""
            # Check rate limit
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer()

            try:
                guild = interaction.guild
                if not guild:
                    await interaction.followup.send(
                        "❌ This command can only be used in a server.", ephemeral=True
                    )
                    return

                stats = await fetch_community_stats(guild.id)

                embed = discord.Embed(
                    title=f"👥 {guild.name} Community Statistics",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow(),
                )

                embed.add_field(
                    name="Total Members", value=str(stats.total_members), inline=True
                )
                embed.add_field(
                    name="Active (24h)",
                    value=str(stats.active_members_24h),
                    inline=True,
                )
                embed.add_field(
                    name="Messages (24h)",
                    value=str(stats.total_messages_24h),
                    inline=True,
                )
                embed.add_field(
                    name="New Members (7d)",
                    value=str(stats.new_members_7d),
                    inline=True,
                )
                embed.add_field(
                    name="Voice Channels Active",
                    value=str(stats.active_voice_channels),
                    inline=True,
                )

                await interaction.followup.send(embed=embed)

            except Exception as e:
                logger.error(f"Error fetching community stats: {e}")
                await interaction.followup.send(
                    "❌ Failed to fetch community statistics. Please try again.",
                    ephemeral=True,
                )

        @stats_group.command(name="leaderboard", description="View top traders")
        @app_commands.describe(limit="Number of traders to show (1-10)")
        async def leaderboard(interaction: discord.Interaction, limit: int = 5) -> None:
            """Display top traders by P&L."""
            # Check rate limit
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            # Clamp limit
            limit = max(1, min(10, limit))

            await interaction.response.defer()

            try:
                # TODO: Fetch from trading database
                # Placeholder data
                placeholder_traders = [
                    ("Trader1", 1500.00, 65.0),
                    ("Trader2", 1200.00, 62.0),
                    ("Trader3", 950.00, 58.0),
                    ("Trader4", 720.00, 55.0),
                    ("Trader5", 500.00, 52.0),
                ][:limit]

                embed = discord.Embed(
                    title="🏆 Top Traders Leaderboard",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow(),
                )

                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

                description = ""
                for i, (name, pnl, win_rate) in enumerate(placeholder_traders):
                    description += (
                        f"{medals[i]} **{name}**: ${pnl:,.2f} ({win_rate:.0f}% WR)\n"
                    )

                if not description:
                    description = "No trading data available yet."

                embed.description = description
                embed.set_footer(text=f"Showing top {limit} traders • Your rank: N/A")

                await interaction.followup.send(embed=embed)

            except Exception as e:
                logger.error(f"Error fetching leaderboard: {e}")
                await interaction.followup.send(
                    "❌ Failed to fetch leaderboard. Please try again.", ephemeral=True
                )

        tree.add_command(stats_group)
        self.bot.register_command("stats", stats_group)


async def setup(bot) -> StatsCommand:
    """
    Setup function to register the stats command module.

    Args:
        bot: The CommunityBot instance

    Returns:
        Configured StatsCommand instance
    """
    stats_cmd = StatsCommand(bot)
    await stats_cmd.setup(bot.tree)
    return stats_cmd
