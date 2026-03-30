"""
Discord Community Commands Package.

Provides slash commands for trading signals, statistics, subscriptions, and help.
"""

from .stats import StatsCommand, setup as setup_stats
from .subscription import (
    SubscriptionCommands,
    SubscriptionTier,
    setup as setup_subscription,
)
from .help import HelpCommand, setup as setup_help
from .signals import SignalsCommands, setup as setup_signals

__all__ = [
    "StatsCommand",
    "SubscriptionCommands",
    "SubscriptionTier",
    "HelpCommand",
    "SignalsCommands",
    "setup_stats",
    "setup_subscription",
    "setup_help",
    "setup_signals",
]
