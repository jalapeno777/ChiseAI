"""
Discord Community Commands Package.

Provides slash commands for trading signals, statistics, subscriptions, and help.
"""

from .help import HelpCommand
from .help import setup as setup_help
from .signals import SignalsCommands
from .signals import setup as setup_signals
from .stats import StatsCommand
from .stats import setup as setup_stats
from .subscription import (
    SubscriptionCommands,
    SubscriptionTier,
)
from .subscription import (
    setup as setup_subscription,
)

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
