"""
Subscription Commands - Manage trading signal subscriptions.

Provides commands for users to subscribe/unsubscribe to trading signals,
manage notification preferences, and view subscription status.
"""

import logging
from dataclasses import dataclass
from enum import Enum

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


class SubscriptionTier(Enum):
    """Subscription tier levels."""

    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    VIP = "vip"

    @property
    def max_signals_per_day(self) -> int:
        """Maximum signals per day for this tier."""
        limits = {
            SubscriptionTier.FREE: 5,
            SubscriptionTier.BASIC: 20,
            SubscriptionTier.PREMIUM: 100,
            SubscriptionTier.VIP: -1,  # Unlimited
        }
        return limits[self]

    @property
    def features(self) -> list[str]:
        """Features available for this tier."""
        feature_map = {
            SubscriptionTier.FREE: ["Basic signals", "Daily summary"],
            SubscriptionTier.BASIC: [
                "All Free features",
                "Entry/exit alerts",
                "Multi-pair coverage",
            ],
            SubscriptionTier.PREMIUM: [
                "All Basic features",
                "Priority signals",
                "Backtest results",
                "Custom strategies",
            ],
            SubscriptionTier.VIP: [
                "All Premium features",
                "1-on-1 coaching",
                "API access",
                "White-label",
            ],
        }
        return feature_map[self]


@dataclass
class Subscription:
    """User subscription information."""

    user_id: int
    tier: SubscriptionTier
    subscribed_at: str | None = None
    signals_received_today: int = 0
    last_signal_reset: str | None = None
    enabled_pairs: list[str] = None
    enabled_strategies: list[str] = None

    def __post_init__(self):
        if self.enabled_pairs is None:
            self.enabled_pairs = []
        if self.enabled_strategies is None:
            self.enabled_strategies = []


class SubscriptionManager:
    """
    Manages user subscriptions and preferences.
    """

    def __init__(self):
        """Initialize the subscription manager."""
        # TODO: Replace with Redis/database storage
        self._subscriptions: dict[int, Subscription] = {}
        self._default_pairs = ["BTC/USDT", "ETH/USDT"]
        self._default_strategies = ["momentum", "grid"]

    async def get_subscription(self, user_id: int) -> Subscription:
        """
        Get subscription for a user.

        Args:
            user_id: Discord user ID

        Returns:
            Subscription object (creates default if not exists)
        """
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = Subscription(
                user_id=user_id, tier=SubscriptionTier.FREE
            )
        return self._subscriptions[user_id]

    async def update_tier(self, user_id: int, tier: SubscriptionTier) -> None:
        """
        Update a user's subscription tier.

        Args:
            user_id: Discord user ID
            tier: New subscription tier
        """
        sub = await self.get_subscription(user_id)
        sub.tier = tier
        logger.info(f"User {user_id} tier updated to {tier.value}")

    async def update_pairs(self, user_id: int, pairs: list[str]) -> None:
        """
        Update enabled pairs for a user.

        Args:
            user_id: Discord user ID
            pairs: List of trading pairs to enable
        """
        sub = await self.get_subscription(user_id)
        sub.enabled_pairs = pairs

    async def update_strategies(self, user_id: int, strategies: list[str]) -> None:
        """
        Update enabled strategies for a user.

        Args:
            user_id: Discord user ID
            strategies: List of strategies to enable
        """
        sub = await self.get_subscription(user_id)
        sub.enabled_strategies = strategies

    def check_signal_limit(self, user_id: int) -> bool:
        """
        Check if user can receive more signals today.

        Args:
            user_id: Discord user ID

        Returns:
            True if user can receive signals
        """
        if user_id not in self._subscriptions:
            return True

        sub = self._subscriptions[user_id]
        if sub.tier == SubscriptionTier.VIP:
            return True

        return sub.signals_received_today < sub.tier.max_signals_per_day


# Global subscription manager instance
subscription_manager = SubscriptionManager()


class SubscriptionCommands:
    """
    Commands for managing trading signal subscriptions.
    """

    def __init__(self, bot):
        """
        Initialize subscription commands.

        Args:
            bot: The CommunityBot instance
        """
        self.bot = bot
        self.manager = subscription_manager
        self._setup_commands()

    def _setup_commands(self) -> None:
        """Register subscription commands."""
        pass

    async def setup(self, tree: app_commands.CommandTree) -> None:
        """
        Set up subscription commands in the command tree.

        Args:
            tree: The app commands command tree
        """
        sub_group = app_commands.Group(
            name="subscribe", description="Manage trading signal subscriptions"
        )

        @sub_group.command(name="status", description="View your subscription status")
        async def sub_status(interaction: discord.Interaction) -> None:
            """Display current subscription status."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                sub = await self.manager.get_subscription(interaction.user.id)

                embed = discord.Embed(
                    title="📋 Your Subscription Status", color=discord.Color.purple()
                )

                tier_emoji = {
                    SubscriptionTier.FREE: "🆓",
                    SubscriptionTier.BASIC: "⭐",
                    SubscriptionTier.PREMIUM: "💫",
                    SubscriptionTier.VIP: "👑",
                }

                embed.add_field(
                    name="Current Tier",
                    value=f"{tier_emoji[sub.tier]} {sub.tier.value.upper()}",
                    inline=False,
                )

                # Features
                features_text = "\n".join([f"• {f}" for f in sub.tier.features])
                embed.add_field(name="Features", value=features_text, inline=False)

                # Signals today
                if sub.tier == SubscriptionTier.VIP:
                    signals_text = "∞ (Unlimited)"
                else:
                    signals_text = (
                        f"{sub.signals_received_today}/{sub.tier.max_signals_per_day}"
                    )
                embed.add_field(name="Signals Today", value=signals_text, inline=True)

                # Enabled pairs
                pairs_text = (
                    ", ".join(sub.enabled_pairs) if sub.enabled_pairs else "All pairs"
                )
                embed.add_field(name="Enabled Pairs", value=pairs_text, inline=True)

                # Enabled strategies
                strategies_text = (
                    ", ".join(sub.enabled_strategies)
                    if sub.enabled_strategies
                    else "All strategies"
                )
                embed.add_field(
                    name="Enabled Strategies", value=strategies_text, inline=True
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                logger.error(f"Error fetching subscription status: {e}")
                await interaction.followup.send(
                    "❌ Failed to fetch subscription status.", ephemeral=True
                )

        @sub_group.command(name="upgrade", description="Upgrade your subscription tier")
        @app_commands.describe(tier="Tier to upgrade to (basic, premium, vip)")
        async def sub_upgrade(interaction: discord.Interaction, tier: str) -> None:
            """Upgrade to a higher subscription tier."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            # Validate tier
            tier_map = {
                "free": SubscriptionTier.FREE,
                "basic": SubscriptionTier.BASIC,
                "premium": SubscriptionTier.PREMIUM,
                "vip": SubscriptionTier.VIP,
            }

            new_tier = tier_map.get(tier.lower())
            if not new_tier:
                await interaction.response.send_message(
                    "❌ Invalid tier. Choose: free, basic, premium, or vip",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                await self.manager.update_tier(interaction.user.id, new_tier)

                embed = discord.Embed(
                    title="✅ Subscription Upgraded",
                    description=f"You are now on the **{new_tier.value.upper()}** tier!",
                    color=discord.Color.green(),
                )

                features_text = "\n".join([f"• {f}" for f in new_tier.features])
                embed.add_field(
                    name="Your New Features", value=features_text, inline=False
                )

                # Note about upgrade flow
                embed.add_field(
                    name="💡 Note",
                    value="This is a placeholder. In production, this would integrate with a payment system.",
                    inline=False,
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                logger.error(f"Error upgrading subscription: {e}")
                await interaction.followup.send(
                    "❌ Failed to upgrade subscription.", ephemeral=True
                )

        @sub_group.command(
            name="pairs", description="Manage your enabled trading pairs"
        )
        @app_commands.describe(action="Action to perform (add, remove, list)")
        @app_commands.describe(pair="Trading pair (e.g., BTC/USDT)")
        async def sub_pairs(
            interaction: discord.Interaction, action: str, pair: str | None = None
        ) -> None:
            """Manage which trading pairs to receive signals for."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                sub = await self.manager.get_subscription(interaction.user.id)

                action = action.lower()

                if action == "list":
                    pairs = sub.enabled_pairs or ["All pairs enabled"]
                    pairs_text = (
                        "\n".join([f"• {p}" for p in pairs])
                        if isinstance(pairs, list)
                        else pairs
                    )

                    embed = discord.Embed(
                        title="📊 Your Enabled Pairs",
                        description=pairs_text,
                        color=discord.Color.blue(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif action == "add":
                    if not pair:
                        await interaction.followup.send(
                            "❌ Please specify a pair to add (e.g., `/subscribe pairs add BTC/USDT`)",
                            ephemeral=True,
                        )
                        return

                    pair = pair.upper()
                    if sub.enabled_pairs is None:
                        sub.enabled_pairs = []

                    if pair not in sub.enabled_pairs:
                        sub.enabled_pairs.append(pair)

                    embed = discord.Embed(
                        title="✅ Pair Added",
                        description=f"**{pair}** has been added to your enabled pairs.",
                        color=discord.Color.green(),
                    )
                    embed.add_field(
                        name="Current Pairs",
                        value=", ".join(sub.enabled_pairs),
                        inline=False,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif action == "remove":
                    if not pair:
                        await interaction.followup.send(
                            "❌ Please specify a pair to remove", ephemeral=True
                        )
                        return

                    pair = pair.upper()
                    if sub.enabled_pairs and pair in sub.enabled_pairs:
                        sub.enabled_pairs.remove(pair)

                    pairs_text = (
                        ", ".join(sub.enabled_pairs)
                        if sub.enabled_pairs
                        else "All pairs"
                    )

                    embed = discord.Embed(
                        title="✅ Pair Removed",
                        description=f"**{pair}** has been removed from your enabled pairs.",
                        color=discord.Color.orange(),
                    )
                    embed.add_field(
                        name="Current Pairs", value=pairs_text, inline=False
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ Invalid action. Use: add, remove, or list", ephemeral=True
                    )

            except Exception as e:
                logger.error(f"Error managing pairs: {e}")
                await interaction.followup.send(
                    "❌ Failed to manage pairs.", ephemeral=True
                )

        @sub_group.command(
            name="strategies", description="Manage your enabled strategies"
        )
        @app_commands.describe(action="Action to perform (add, remove, list)")
        @app_commands.describe(strategy="Strategy name")
        async def sub_strategies(
            interaction: discord.Interaction,
            action: str,
            strategy: str | None = None,
        ) -> None:
            """Manage which trading strategies to receive signals for."""
            if not self.bot.check_command_rate_limit(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ Command rate limit reached. Please wait.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                sub = await self.manager.get_subscription(interaction.user.id)

                action = action.lower()
                available_strategies = [
                    "momentum",
                    "grid",
                    "mean_reversion",
                    "scalping",
                    "swing",
                ]

                if action == "list":
                    strategies = sub.enabled_strategies or ["All strategies enabled"]
                    strategies_text = (
                        "\n".join([f"• {s}" for s in strategies])
                        if isinstance(strategies, list)
                        else strategies
                    )

                    embed = discord.Embed(
                        title="📊 Your Enabled Strategies",
                        description=strategies_text,
                        color=discord.Color.blue(),
                    )
                    embed.add_field(
                        name="Available Strategies",
                        value=", ".join(available_strategies),
                        inline=False,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif action == "add":
                    if not strategy:
                        await interaction.followup.send(
                            f"❌ Please specify a strategy to add. Available: {', '.join(available_strategies)}",
                            ephemeral=True,
                        )
                        return

                    strategy = strategy.lower()
                    if strategy not in available_strategies:
                        await interaction.followup.send(
                            f"❌ Invalid strategy. Available: {', '.join(available_strategies)}",
                            ephemeral=True,
                        )
                        return

                    if sub.enabled_strategies is None:
                        sub.enabled_strategies = []

                    if strategy not in sub.enabled_strategies:
                        sub.enabled_strategies.append(strategy)

                    embed = discord.Embed(
                        title="✅ Strategy Added",
                        description=f"**{strategy}** has been added to your enabled strategies.",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif action == "remove":
                    if not strategy:
                        await interaction.followup.send(
                            "❌ Please specify a strategy to remove", ephemeral=True
                        )
                        return

                    strategy = strategy.lower()
                    if sub.enabled_strategies and strategy in sub.enabled_strategies:
                        sub.enabled_strategies.remove(strategy)

                    strategies_text = (
                        ", ".join(sub.enabled_strategies)
                        if sub.enabled_strategies
                        else "All strategies"
                    )

                    embed = discord.Embed(
                        title="✅ Strategy Removed",
                        description=f"**{strategy}** has been removed.",
                        color=discord.Color.orange(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ Invalid action. Use: add, remove, or list", ephemeral=True
                    )

            except Exception as e:
                logger.error(f"Error managing strategies: {e}")
                await interaction.followup.send(
                    "❌ Failed to manage strategies.", ephemeral=True
                )

        tree.add_command(sub_group)
        self.bot.register_command("subscribe", sub_group)


async def setup(bot) -> SubscriptionCommands:
    """
    Setup function to register the subscription command module.

    Args:
        bot: The CommunityBot instance

    Returns:
        Configured SubscriptionCommands instance
    """
    sub_cmd = SubscriptionCommands(bot)
    await sub_cmd.setup(bot.tree)
    return sub_cmd
