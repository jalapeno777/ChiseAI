"""Discord alert sender for data quality monitoring.

Sends data quality alerts (freshness, gaps) to Discord #alerts channel.
Integrates with existing Discord client from ST-NS-009.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from monitoring.data_quality import (
        DataQualityAlert,
        DataSource,
        GapAlert,
    )

logger = logging.getLogger(__name__)


class DataQualityDiscordFormatter:
    """Format data quality alerts for Discord.

    Creates embeds with consistent styling for different alert types.
    """

    # Color mapping for severity levels
    SEVERITY_COLORS = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
    }

    # Source emoji mapping
    SOURCE_EMOJI = {
        "binance": "🟡",  # Yellow
        "bybit": "🔵",  # Blue
        "bitget": "🟢",  # Green
    }

    @classmethod
    def format_freshness_alert(
        cls,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data_age_seconds: float | None,
        threshold_seconds: float,
    ) -> dict[str, Any]:
        """Format a freshness alert as Discord embed.

        Args:
            source: Data source
            symbol: Trading pair
            timeframe: Timeframe
            data_age_seconds: Age of data
            threshold_seconds: Threshold for alert

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source.value, "📊")

        if data_age_seconds is None:
            title = f"{emoji} {source.value.upper()} - No Data"
            description = f"No data received for **{symbol}** ({timeframe})"
            staleness_text = "N/A"
        else:
            age_minutes = data_age_seconds / 60
            threshold_minutes = threshold_seconds / 60
            staleness_minutes = max(0, age_minutes - threshold_minutes)

            title = f"{emoji} {source.value.upper()} - Stale Data Alert"
            description = (
                f"Data for **{symbol}** ({timeframe}) is stale\n\n"
                f"• Age: **{age_minutes:.1f}** minutes\n"
                f"• Threshold: **{threshold_minutes:.1f}** minutes\n"
                f"• Staleness: **{staleness_minutes:.1f}** minutes over threshold"
            )
            staleness_text = f"{staleness_minutes:.1f} min"

        return {
            "title": title,
            "description": description,
            "color": cls.SEVERITY_COLORS["critical"],
            "fields": [
                {
                    "name": "Source",
                    "value": source.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Symbol",
                    "value": symbol,
                    "inline": True,
                },
                {
                    "name": "Timeframe",
                    "value": timeframe,
                    "inline": True,
                },
                {
                    "name": "Staleness",
                    "value": staleness_text,
                    "inline": True,
                },
                {
                    "name": "Timestamp",
                    "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Data Quality Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def format_gap_alert(cls, gap_alert: GapAlert) -> dict[str, Any]:
        """Format a gap alert as Discord embed.

        Args:
            gap_alert: Gap alert to format

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(gap_alert.source.value, "📊")
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
        }.get(gap_alert.severity.value, "⚠️")

        from datetime import datetime

        gap_start_dt = datetime.fromtimestamp(gap_alert.gap_start / 1000, tz=UTC)
        gap_end_dt = datetime.fromtimestamp(gap_alert.gap_end / 1000, tz=UTC)

        source_name = gap_alert.source.value.upper()
        title = f"{severity_emoji} {emoji} {source_name} - Data Gap Detected"
        description = (
            "Missing data detected for "
            f"**{gap_alert.symbol}** ({gap_alert.timeframe})\n\n"
            f"• Missing candles: **{gap_alert.expected_candles}**\n"
            f"• Gap duration: **{gap_alert.duration_seconds:.0f}** seconds\n"
            f"• Gap start: {gap_start_dt.strftime('%H:%M:%S')}\n"
            f"• Gap end: {gap_end_dt.strftime('%H:%M:%S')}"
        )

        return {
            "title": title,
            "description": description,
            "color": cls.SEVERITY_COLORS.get(
                gap_alert.severity.value, cls.SEVERITY_COLORS["warning"]
            ),
            "fields": [
                {
                    "name": "Source",
                    "value": gap_alert.source.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Symbol",
                    "value": gap_alert.symbol,
                    "inline": True,
                },
                {
                    "name": "Timeframe",
                    "value": gap_alert.timeframe,
                    "inline": True,
                },
                {
                    "name": "Missing Candles",
                    "value": str(gap_alert.expected_candles),
                    "inline": True,
                },
                {
                    "name": "Severity",
                    "value": gap_alert.severity.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Detected At",
                    "value": gap_alert.detected_at.strftime("%H:%M:%S UTC"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Data Quality Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def format_recovery_notice(
        cls,
        source: DataSource,
        symbol: str,
        timeframe: str,
        alert_type: str,
    ) -> dict[str, Any]:
        """Format a recovery notice as Discord embed.

        Args:
            source: Data source
            symbol: Trading pair
            timeframe: Timeframe
            alert_type: Type of alert that recovered

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source.value, "📊")

        return {
            "title": (
                f"✅ {emoji} {source.value.upper()} - " f"{alert_type.title()} Resolved"
            ),
            "description": (
                f"Data quality issue resolved for **{symbol}** ({timeframe})\n\n"
                f"The {alert_type} alert has been cleared. "
                f"Data is now flowing normally."
            ),
            "color": 0x2ECC71,  # Green
            "fields": [
                {
                    "name": "Source",
                    "value": source.value.upper(),
                    "inline": True,
                },
                {
                    "name": "Symbol",
                    "value": symbol,
                    "inline": True,
                },
                {
                    "name": "Timeframe",
                    "value": timeframe,
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Data Quality Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }


class DataQualityDiscordSender:
    """Send data quality alerts to Discord.

    Integrates with the existing Discord client infrastructure.
    """

    def __init__(
        self,
        discord_client: Any | None = None,
        webhook_url: str | None = None,
        alerts_channel: str = "alerts",
        enable_recovery_notices: bool = True,
    ):
        """Initialize Discord sender.

        Args:
            discord_client: Existing Discord client instance
            webhook_url: Discord webhook URL (if no client provided)
            alerts_channel: Channel for data quality alerts
            enable_recovery_notices: Whether to send recovery notifications
        """
        self.discord_client = discord_client
        self.webhook_url = webhook_url
        self.alerts_channel = alerts_channel
        self.enable_recovery_notices = enable_recovery_notices

        # Track active alerts for recovery detection
        self._active_alerts: set[tuple[str, str, str, str]] = set()

    async def _get_client(self) -> Any:
        """Get or create Discord client."""
        if self.discord_client is not None:
            return self.discord_client

        # Import here to avoid circular imports
        try:
            from discord_alerts.config import DiscordConfig
            from discord_alerts.discord_client import DiscordClient

            config = DiscordConfig(
                webhook_url=self.webhook_url,
                default_channel=self.alerts_channel,
            )
            self.discord_client = DiscordClient(config)
            return self.discord_client
        except ImportError as e:
            logger.error(f"Failed to import Discord client: {e}")
            raise

    async def send_freshness_alert(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        data_age_seconds: float | None,
        threshold_seconds: float,
    ) -> dict[str, Any]:
        """Send a freshness alert to Discord.

        Args:
            source: Data source
            symbol: Trading pair
            timeframe: Timeframe
            data_age_seconds: Age of data
            threshold_seconds: Threshold for alert

        Returns:
            Send result dictionary
        """
        client = await self._get_client()

        embed = DataQualityDiscordFormatter.format_freshness_alert(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            data_age_seconds=data_age_seconds,
            threshold_seconds=threshold_seconds,
        )

        # Track this alert
        alert_key = ("freshness", source.value, symbol, timeframe)
        self._active_alerts.add(alert_key)

        try:
            result = await client.send_message(
                content=(
                    "🚨 Data Quality Alert: " f"Stale data from {source.value.upper()}"
                ),
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent freshness alert to Discord: {source.value}/{symbol}")
            return result
        except Exception as e:
            logger.error(f"Failed to send freshness alert: {e}")
            return {"success": False, "error": str(e)}

    async def send_gap_alert(self, gap_alert: GapAlert) -> dict[str, Any]:
        """Send a gap alert to Discord.

        Args:
            gap_alert: Gap alert to send

        Returns:
            Send result dictionary
        """
        client = await self._get_client()

        embed = DataQualityDiscordFormatter.format_gap_alert(gap_alert)

        # Track this alert
        alert_key = (
            "gap",
            gap_alert.source.value,
            gap_alert.symbol,
            gap_alert.timeframe,
        )
        self._active_alerts.add(alert_key)

        try:
            result = await client.send_message(
                content=(
                    "⚠️ Data Quality Alert: "
                    f"Gap detected in {gap_alert.source.value.upper()}"
                ),
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(
                "Sent gap alert to Discord: "
                f"{gap_alert.source.value}/{gap_alert.symbol}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to send gap alert: {e}")
            return {"success": False, "error": str(e)}

    async def send_recovery_notice(
        self,
        source: DataSource,
        symbol: str,
        timeframe: str,
        alert_type: str,
    ) -> dict[str, Any]:
        """Send a recovery notice to Discord.

        Args:
            source: Data source
            symbol: Trading pair
            timeframe: Timeframe
            alert_type: Type of alert that recovered

        Returns:
            Send result dictionary
        """
        if not self.enable_recovery_notices:
            return {"success": True, "skipped": True}

        # Check if we had an active alert
        alert_key = (alert_type, source.value, symbol, timeframe)
        if alert_key not in self._active_alerts:
            return {"success": True, "skipped": True, "reason": "no_active_alert"}

        self._active_alerts.discard(alert_key)

        client = await self._get_client()

        embed = DataQualityDiscordFormatter.format_recovery_notice(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            alert_type=alert_type,
        )

        try:
            result = await client.send_message(
                content=f"✅ Data Quality: Issue resolved for {source.value.upper()}",
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent recovery notice to Discord: {source.value}/{symbol}")
            return result
        except Exception as e:
            logger.error(f"Failed to send recovery notice: {e}")
            return {"success": False, "error": str(e)}

    async def send_generic_alert(self, alert: DataQualityAlert) -> dict[str, Any]:
        """Send a generic data quality alert.

        Args:
            alert: Data quality alert to send

        Returns:
            Send result dictionary
        """
        if alert.alert_type == "freshness":
            metrics = alert.metrics
            return await self.send_freshness_alert(
                source=alert.source,
                symbol=metrics.get("symbol", "unknown"),
                timeframe=metrics.get("timeframe", "unknown"),
                data_age_seconds=metrics.get("data_age_seconds"),
                threshold_seconds=metrics.get("threshold_seconds", 300.0),
            )
        elif alert.alert_type == "gap":
            # For gap alerts, we need to reconstruct the GapAlert object
            metrics = alert.metrics
            from monitoring.data_quality import AlertSeverity, GapAlert

            gap_alert = GapAlert(
                source=alert.source,
                symbol=metrics.get("symbol", "unknown"),
                timeframe=metrics.get("timeframe", "unknown"),
                gap_start=metrics.get("gap_start", 0),
                gap_end=metrics.get("gap_end", 0),
                expected_candles=metrics.get("expected_candles", 0),
                severity=AlertSeverity(metrics.get("severity", "warning")),
            )
            return await self.send_gap_alert(gap_alert)
        else:
            logger.warning(f"Unknown alert type: {alert.alert_type}")
            return {
                "success": False,
                "error": f"Unknown alert type: {alert.alert_type}",
            }

    def get_active_alert_count(self) -> int:
        """Get number of active alerts."""
        return len(self._active_alerts)

    def clear_active_alerts(self) -> None:
        """Clear all active alert tracking."""
        self._active_alerts.clear()
        logger.info("Cleared active alert tracking")


# Convenience function for creating alert handler
def create_discord_alert_handler(
    webhook_url: str | None = None,
    discord_client: Any | None = None,
    alerts_channel: str = "alerts",
) -> callable:
    """Create an alert handler function for use with DataQualityMonitor.

    Args:
        webhook_url: Discord webhook URL
        discord_client: Existing Discord client
        alerts_channel: Channel for alerts

    Returns:
        Async handler function
    """
    sender = DataQualityDiscordSender(
        discord_client=discord_client,
        webhook_url=webhook_url,
        alerts_channel=alerts_channel,
    )

    async def handler(alert: DataQualityAlert) -> None:
        await sender.send_generic_alert(alert)

    return handler
