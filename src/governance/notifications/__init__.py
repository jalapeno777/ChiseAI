"""Discord notification module for governance events."""

from .discord_notifier import DiscordNotifier
from .event_router import DigestBuilder, NotificationEventRouter, RoutingDecision
from .formatters import (
    AutocogEventFormatter,
    DecisionNotificationFormatter,
    LowSeverityDigestFormatter,
    ReflectionNotificationFormatter,
    SelfAssessmentNotificationFormatter,
)
from .severity_mapper import DEFAULT_SEVERITY, SeverityMapper

__all__ = [
    "DiscordNotifier",
    "ReflectionNotificationFormatter",
    "DecisionNotificationFormatter",
    "SelfAssessmentNotificationFormatter",
    "AutocogEventFormatter",
    "LowSeverityDigestFormatter",
    "NotificationEventRouter",
    "RoutingDecision",
    "DigestBuilder",
    "SeverityMapper",
    "DEFAULT_SEVERITY",
]
