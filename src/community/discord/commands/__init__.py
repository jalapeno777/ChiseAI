"""
Discord Community Commands Package.

Provides slash commands for trading signals, statistics, subscriptions, and help.
"""

from .help import HelpCommand
from .help import setup as setup_help
from .signals import SignalsCommand

# TODO: signals.py has no setup function - pre-existing bug (ST-NS-REMEDIATION-001)
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
    "SignalsCommand",
    "setup_stats",
    "setup_subscription",
    "setup_help",
    # "setup_signals",  # TEMPORARILY REMOVED: signals.py has no setup function
]
