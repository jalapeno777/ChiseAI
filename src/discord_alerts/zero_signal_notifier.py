"""
Zero-signal Discord notifier module.

Sends structured zero-signal alerts to Discord when signal outages are detected,
and resolution notifications when signals resume. Uses existing discord_alerts
infrastructure for formatting, rate limiting, and sending.

Rate limiting: max 1 alert per datasource per 15 minutes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Rate limit: 15 minutes between alerts per datasource
DEFAULT_ALERT_COOLDOWN_SECONDS = 900  # 15 * 60

# Discord embed colors
COLOR_INFO = 0x3498DB  # Blue
COLOR_WARNING = 0xF39C12  # Orange
COLOR_CRITICAL = 0xE74C3C  # Red
COLOR_RECOVERY = 0x2ECC71  # Green

SEVERITY_COLORS = {
    "info": COLOR_INFO,
    "warning": COLOR_WARNING,
    "critical": COLOR_CRITICAL,
}

SEVERITY_EMOJIS = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
    "recovery": "✅",
}


@dataclass
class ZeroSignalNotificationResult:
    """Result of a zero-signal notification attempt."""

    success: bool
    datasource: str
    notification_type: str  # "alert" or "recovery"
    error: Optional[str] = None
    rate_limited: bool = False
    timestamp: float = field(default_factory=time.time)


class ZeroSignalDiscordFormatter:
    """Format zero-signal alerts as Discord embeds.

    Follows the same pattern as DatasourceHealthDiscordFormatter
    with class methods returning embed dicts.
    """

    FOOTER_TEXT = "ChiseAI Zero-Signal Monitor"

    @classmethod
    def format_zero_signal_alert(
        cls,
        datasource: str,
        duration_minutes: float,
        window_count: int,
        severity: str,
        event_count: int,
        last_signal_time: Optional[float] = None,
    ) -> dict[str, Any]:
        """Format a zero-signal alert embed.

        Args:
            datasource: Name of the datasource.
            duration_minutes: Duration of the zero-signal condition.
            window_count: Number of consecutive zero-signal windows.
            severity: Severity level (info, warning, critical).
            event_count: Total event count for this datasource.
            last_signal_time: Unix timestamp of last signal.

        Returns:
            Discord embed dict with content and embeds.
        """
        emoji = SEVERITY_EMOJIS.get(severity, "❓")
        color = SEVERITY_COLORS.get(severity, COLOR_WARNING)

        # Format last signal time
        last_signal_str = "Unknown"
        if last_signal_time and last_signal_time > 0:
            import datetime

            dt = datetime.datetime.fromtimestamp(
                last_signal_time, tz=datetime.timezone.utc
            )
            last_signal_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Build severity label
        severity_label = severity.upper()

        # Duration formatting
        if duration_minutes >= 60:
            hours = int(duration_minutes // 60)
            mins = int(duration_minutes % 60)
            duration_str = f"{hours}h {mins}m"
        else:
            duration_str = f"{int(duration_minutes)}m"

        fields = [
            {"name": "Datasource", "value": datasource, "inline": True},
            {"name": "Duration", "value": duration_str, "inline": True},
            {
                "name": "Consecutive Windows",
                "value": str(window_count),
                "inline": True,
            },
            {"name": "Severity", "value": severity_label, "inline": True},
            {"name": "Event Count", "value": str(event_count), "inline": True},
            {"name": "Last Signal", "value": last_signal_str, "inline": True},
        ]

        embed = {
            "title": f"{emoji} Zero-Signal Alert: {datasource}",
            "description": (
                f"No actionable signals from **{datasource}** for "
                f"**{duration_str}** ({window_count} consecutive windows).\n"
                f"Severity: **{severity_label}**"
            ),
            "color": color,
            "fields": fields,
            "footer": {"text": cls.FOOTER_TEXT},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        content = f"{emoji} **Zero-Signal Alert** — {datasource} ({severity_label}, {duration_str})"

        return {"content": content, "embeds": [embed]}

    @classmethod
    def format_recovery_notification(
        cls,
        datasource: str,
        outage_duration_minutes: float,
        event_count: int,
    ) -> dict[str, Any]:
        """Format a signal recovery notification embed.

        Args:
            datasource: Name of the datasource that recovered.
            outage_duration_minutes: Total duration of the outage.
            event_count: Total event count for this datasource.

        Returns:
            Discord embed dict with content and embeds.
        """
        emoji = SEVERITY_EMOJIS["recovery"]

        # Duration formatting
        if outage_duration_minutes >= 60:
            hours = int(outage_duration_minutes // 60)
            mins = int(outage_duration_minutes % 60)
            duration_str = f"{hours}h {mins}m"
        else:
            duration_str = f"{int(outage_duration_minutes)}m"

        fields = [
            {"name": "Datasource", "value": datasource, "inline": True},
            {
                "name": "Outage Duration",
                "value": duration_str,
                "inline": True,
            },
            {"name": "Total Events", "value": str(event_count), "inline": True},
        ]

        embed = {
            "title": f"{emoji} Signal Resumed: {datasource}",
            "description": (
                f"Signals from **{datasource}** have resumed after "
                f"a **{duration_str}** outage."
            ),
            "color": COLOR_RECOVERY,
            "fields": fields,
            "footer": {"text": cls.FOOTER_TEXT},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        content = f"{emoji} **Signal Resumed** — {datasource} (after {duration_str})"

        return {"content": content, "embeds": [embed]}


class ZeroSignalNotifier:
    """Sends zero-signal alerts to Discord with rate limiting.

    Uses the existing discord_alerts pipeline for sending.
    Tracks last notification time per datasource for rate limiting.
    """

    def __init__(
        self,
        discord_client: Any = None,
        channel_id: Optional[str] = None,
        cooldown_seconds: int = DEFAULT_ALERT_COOLDOWN_SECONDS,
        enable_recovery_notices: bool = True,
    ) -> None:
        """Initialize the zero-signal notifier.

        Args:
            discord_client: Optional pre-configured Discord client.
            channel_id: Discord channel ID for alerts.
            cooldown_seconds: Seconds between alerts per datasource.
            enable_recovery_notices: Whether to send recovery notifications.
        """
        self._discord_client = discord_client
        self._channel_id = channel_id
        self._cooldown_seconds = cooldown_seconds
        self._enable_recovery_notices = enable_recovery_notices

        # Track last notification time per datasource for rate limiting
        self._last_alert_time: dict[str, float] = {}
        # Track which datasources have active alerts (for recovery detection)
        self._active_alerts: set[str] = set()

    def _get_client(self) -> Any:
        """Lazy init Discord client using existing discord_alerts infrastructure."""
        if self._discord_client is None:
            try:
                from src.discord_alerts import DiscordClient, DiscordConfig

                config = DiscordConfig.from_env()
                self._discord_client = DiscordClient(config)
                if self._channel_id is None:
                    self._channel_id = config.get_channel_id_for_name("summaries")
            except Exception as e:
                logger.error("Failed to initialize Discord client: %s", e)
                raise
        return self._discord_client

    def _is_rate_limited(self, datasource: str) -> bool:
        """Check if a datasource is rate-limited for alerts.

        Returns:
            True if the datasource should be rate-limited.
        """
        last_time = self._last_alert_time.get(datasource, 0)
        elapsed = time.time() - last_time
        return elapsed < self._cooldown_seconds

    def _time_until_available(self, datasource: str) -> float:
        """Get seconds until rate limit expires for a datasource."""
        last_time = self._last_alert_time.get(datasource, 0)
        elapsed = time.time() - last_time
        return max(0.0, self._cooldown_seconds - elapsed)

    async def send_zero_signal_alert(
        self,
        datasource: str,
        duration_minutes: float,
        window_count: int,
        severity: str,
        event_count: int,
        last_signal_time: Optional[float] = None,
    ) -> ZeroSignalNotificationResult:
        """Send a zero-signal alert to Discord.

        Respects rate limiting: max 1 alert per datasource per cooldown period.

        Args:
            datasource: Name of the datasource with zero signals.
            duration_minutes: Duration of the zero-signal condition.
            window_count: Number of consecutive zero-signal windows.
            severity: Severity level (info, warning, critical).
            event_count: Total event count for this datasource.
            last_signal_time: Unix timestamp of last signal.

        Returns:
            ZeroSignalNotificationResult with outcome.
        """
        # Check rate limit
        if self._is_rate_limited(datasource):
            remaining = self._time_until_available(datasource)
            logger.info(
                "Zero-signal alert for %s rate-limited (%.0fs remaining)",
                datasource,
                remaining,
            )
            return ZeroSignalNotificationResult(
                success=False,
                datasource=datasource,
                notification_type="alert",
                rate_limited=True,
            )

        try:
            client = self._get_client()

            formatted = ZeroSignalDiscordFormatter.format_zero_signal_alert(
                datasource=datasource,
                duration_minutes=duration_minutes,
                window_count=window_count,
                severity=severity,
                event_count=event_count,
                last_signal_time=last_signal_time,
            )

            result = await client.send_message(
                content=formatted["content"],
                channel=self._channel_id,
                embeds=formatted["embeds"],
            )

            # Update rate limit tracking
            self._last_alert_time[datasource] = time.time()
            self._active_alerts.add(datasource)

            logger.info(
                "Zero-signal alert sent for %s (severity=%s, duration=%.0fm)",
                datasource,
                severity,
                duration_minutes,
            )

            return ZeroSignalNotificationResult(
                success=True,
                datasource=datasource,
                notification_type="alert",
            )

        except Exception as e:
            logger.error("Failed to send zero-signal alert for %s: %s", datasource, e)
            return ZeroSignalNotificationResult(
                success=False,
                datasource=datasource,
                notification_type="alert",
                error=str(e),
            )

    async def send_recovery_notification(
        self,
        datasource: str,
        outage_duration_minutes: float,
        event_count: int,
    ) -> ZeroSignalNotificationResult:
        """Send a signal recovery notification to Discord.

        Only sends if there was an active alert for this datasource.

        Args:
            datasource: Name of the datasource that recovered.
            outage_duration_minutes: Total duration of the outage.
            event_count: Total event count for this datasource.

        Returns:
            ZeroSignalNotificationResult with outcome.
        """
        # Only send recovery if there was an active alert
        if datasource not in self._active_alerts:
            logger.debug(
                "No active alert for %s, skipping recovery notification",
                datasource,
            )
            return ZeroSignalNotificationResult(
                success=False,
                datasource=datasource,
                notification_type="recovery",
                error="No active alert to recover from",
            )

        if not self._enable_recovery_notices:
            return ZeroSignalNotificationResult(
                success=False,
                datasource=datasource,
                notification_type="recovery",
                error="Recovery notices disabled",
            )

        try:
            client = self._get_client()

            formatted = ZeroSignalDiscordFormatter.format_recovery_notification(
                datasource=datasource,
                outage_duration_minutes=outage_duration_minutes,
                event_count=event_count,
            )

            await client.send_message(
                content=formatted["content"],
                channel=self._channel_id,
                embeds=formatted["embeds"],
            )

            # Clear active alert tracking
            self._active_alerts.discard(datasource)
            # Reset rate limit on recovery so next alert can fire immediately
            self._last_alert_time.pop(datasource, None)

            logger.info(
                "Recovery notification sent for %s (outage=%.0fm)",
                datasource,
                outage_duration_minutes,
            )

            return ZeroSignalNotificationResult(
                success=True,
                datasource=datasource,
                notification_type="recovery",
            )

        except Exception as e:
            logger.error(
                "Failed to send recovery notification for %s: %s", datasource, e
            )
            return ZeroSignalNotificationResult(
                success=False,
                datasource=datasource,
                notification_type="recovery",
                error=str(e),
            )

    def has_active_alert(self, datasource: str) -> bool:
        """Check if there's an active zero-signal alert for a datasource."""
        return datasource in self._active_alerts

    def get_active_alerts(self) -> set[str]:
        """Get set of datasources with active alerts."""
        return set(self._active_alerts)

    def clear_rate_limit(self, datasource: str) -> None:
        """Clear rate limit for a specific datasource."""
        self._last_alert_time.pop(datasource, None)

    def reset(self) -> None:
        """Reset all tracking state."""
        self._last_alert_time.clear()
        self._active_alerts.clear()
