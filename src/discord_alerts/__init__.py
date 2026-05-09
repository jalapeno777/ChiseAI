"""Discord alert integration module.

Provides Discord bot client, alert formatting, sending, deduplication,
rate limiting for trading signal notifications, and zero-signal alerting.

For ST-NS-009: Discord Alert Integration
For ST-MVP-006: Zero-Signal Monitoring Alerts
"""

from __future__ import annotations

__all__ = [
    "DiscordClient",
    "DiscordInitializer",
    "AlertFormatter",
    "AlertSender",
    "DuplicateSuppressor",
    "RateLimiter",
    "DiscordConfig",
    "AlertType",
    "TradeNotifier",
    "TradeNotificationResult",
    # Zero-signal notifier (ST-MVP-006)
    "ZeroSignalDiscordFormatter",
    "ZeroSignalNotifier",
    "ZeroSignalNotificationResult",
]

from discord_alerts.alert_formatter import AlertFormatter, AlertType
from discord_alerts.alert_sender import AlertSender
from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient
from discord_alerts.discord_initializer import DiscordInitializer
from discord_alerts.duplicate_suppressor import DuplicateSuppressor
from discord_alerts.rate_limiter import RateLimiter
from discord_alerts.trade_notifier import TradeNotificationResult, TradeNotifier
from discord_alerts.zero_signal_notifier import (
    ZeroSignalDiscordFormatter,
    ZeroSignalNotificationResult,
    ZeroSignalNotifier,
)
