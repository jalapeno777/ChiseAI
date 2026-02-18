"""Discord alert integration module.

Provides Discord bot client, alert formatting, sending, deduplication,
and rate limiting for trading signal notifications.

For ST-NS-009: Discord Alert Integration
"""

from __future__ import annotations

__all__ = [
    "DiscordClient",
    "AlertFormatter",
    "AlertSender",
    "DuplicateSuppressor",
    "RateLimiter",
    "DiscordConfig",
    "AlertType",
    "TradeNotifier",
    "TradeNotificationResult",
]

from discord_alerts.alert_formatter import AlertFormatter, AlertType
from discord_alerts.alert_sender import AlertSender
from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient
from discord_alerts.duplicate_suppressor import DuplicateSuppressor
from discord_alerts.rate_limiter import RateLimiter
from discord_alerts.trade_notifier import TradeNotifier, TradeNotificationResult
