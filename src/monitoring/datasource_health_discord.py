"""Discord alert sender for data source health monitoring.

Sends datasource health alerts (disconnect, reconnect failures, extended downtime)
to Discord #alerts channel.

For ST-OPS-008: Grafana Data Source Health Monitoring
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from monitoring.datasource_health import (
        ConnectionMetrics,
        ConnectionStatus,
        DataSourceType,
        DatasourceHealthAlert,
    )

logger = logging.getLogger(__name__)


class DatasourceHealthDiscordFormatter:
    """Format data source health alerts for Discord.

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
        "influxdb": "📊",  # Chart
        "postgresql": "🐘",  # Elephant
    }

    # Status emoji mapping
    STATUS_EMOJI = {
        "connected": "✅",
        "disconnected": "❌",
        "reconnecting": "🔄",
        "failed": "🚨",
    }

    @classmethod
    def format_disconnect_alert(
        cls,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
    ) -> dict[str, Any]:
        """Format a disconnect alert as Discord embed.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source_type.value, "🔌")
        status_emoji = cls.STATUS_EMOJI.get("disconnected", "❌")

        title = f"{status_emoji} {emoji} {source_name} - Disconnected"
        description = (
            f"**{source_name}** has lost connectivity.\n\n"
            f"Auto-reconnect will be attempted with exponential backoff."
        )

        fields = [
            {
                "name": "Source Type",
                "value": source_type.value.upper(),
                "inline": True,
            },
            {
                "name": "Status",
                "value": "Disconnected",
                "inline": True,
            },
            {
                "name": "Disconnect Count",
                "value": str(metrics.disconnect_count),
                "inline": True,
            },
            {
                "name": "Availability",
                "value": f"{metrics.availability_percentage:.1f}%",
                "inline": True,
            },
        ]

        if metrics.last_connected_at:
            fields.append(
                {
                    "name": "Last Connected",
                    "value": metrics.last_connected_at.strftime("%H:%M:%S UTC"),
                    "inline": True,
                }
            )

        fields.append(
            {
                "name": "Timestamp",
                "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": True,
            }
        )

        return {
            "title": title,
            "description": description,
            "color": cls.SEVERITY_COLORS["warning"],
            "fields": fields,
            "footer": {
                "text": "ChiseAI Data Source Health Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def format_reconnect_failed_alert(
        cls,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
        max_attempts: int,
    ) -> dict[str, Any]:
        """Format a reconnect failed alert as Discord embed.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics
            max_attempts: Maximum reconnection attempts

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source_type.value, "🔌")
        status_emoji = cls.STATUS_EMOJI.get("failed", "🚨")

        title = f"{status_emoji} {emoji} {source_name} - Reconnect Failed"
        description = (
            f"**{source_name}** failed to reconnect after "
            f"**{max_attempts}** attempts.\n\n"
            f"⚠️ **Manual intervention required.**"
        )

        fields = [
            {
                "name": "Source Type",
                "value": source_type.value.upper(),
                "inline": True,
            },
            {
                "name": "Status",
                "value": "Failed",
                "inline": True,
            },
            {
                "name": "Total Attempts",
                "value": str(metrics.total_reconnect_attempts),
                "inline": True,
            },
            {
                "name": "Disconnect Count",
                "value": str(metrics.disconnect_count),
                "inline": True,
            },
            {
                "name": "Availability",
                "value": f"{metrics.availability_percentage:.1f}%",
                "inline": True,
            },
            {
                "name": "Timestamp",
                "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": True,
            },
        ]

        return {
            "title": title,
            "description": description,
            "color": cls.SEVERITY_COLORS["critical"],
            "fields": fields,
            "footer": {
                "text": "ChiseAI Data Source Health Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def format_extended_downtime_alert(
        cls,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
        downtime_minutes: float,
    ) -> dict[str, Any]:
        """Format an extended downtime alert as Discord embed.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics
            downtime_minutes: Downtime in minutes

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source_type.value, "🔌")
        status_emoji = cls.STATUS_EMOJI.get("failed", "🚨")

        title = f"{status_emoji} {emoji} {source_name} - Extended Downtime"
        description = (
            f"**{source_name}** has been down for "
            f"**{downtime_minutes:.1f} minutes**.\n\n"
            f"⚠️ **Critical: Data ingestion may be affected.**"
        )

        fields = [
            {
                "name": "Source Type",
                "value": source_type.value.upper(),
                "inline": True,
            },
            {
                "name": "Status",
                "value": "Extended Downtime",
                "inline": True,
            },
            {
                "name": "Downtime",
                "value": f"{downtime_minutes:.1f} min",
                "inline": True,
            },
            {
                "name": "Reconnect Attempts",
                "value": str(metrics.reconnect_attempts),
                "inline": True,
            },
            {
                "name": "Total Attempts",
                "value": str(metrics.total_reconnect_attempts),
                "inline": True,
            },
            {
                "name": "Availability",
                "value": f"{metrics.availability_percentage:.1f}%",
                "inline": True,
            },
        ]

        return {
            "title": title,
            "description": description,
            "color": cls.SEVERITY_COLORS["critical"],
            "fields": fields,
            "footer": {
                "text": "ChiseAI Data Source Health Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def format_recovery_notice(
        cls,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
    ) -> dict[str, Any]:
        """Format a recovery notice as Discord embed.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics

        Returns:
            Discord embed dictionary
        """
        emoji = cls.SOURCE_EMOJI.get(source_type.value, "🔌")
        status_emoji = cls.STATUS_EMOJI.get("connected", "✅")

        title = f"{status_emoji} {emoji} {source_name} - Recovered"
        description = (
            f"**{source_name}** has recovered and is now connected.\n\n"
            f"Data source is operational."
        )

        fields = [
            {
                "name": "Source Type",
                "value": source_type.value.upper(),
                "inline": True,
            },
            {
                "name": "Status",
                "value": "Connected",
                "inline": True,
            },
            {
                "name": "Response Time",
                "value": f"{metrics.response_time_ms:.1f}ms"
                if metrics.response_time_ms
                else "N/A",
                "inline": True,
            },
            {
                "name": "Availability",
                "value": f"{metrics.availability_percentage:.1f}%",
                "inline": True,
            },
            {
                "name": "Disconnect Count",
                "value": str(metrics.disconnect_count),
                "inline": True,
            },
            {
                "name": "Timestamp",
                "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": True,
            },
        ]

        return {
            "title": title,
            "description": description,
            "color": 0x2ECC71,  # Green
            "fields": fields,
            "footer": {
                "text": "ChiseAI Data Source Health Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }


class DatasourceHealthDiscordSender:
    """Send data source health alerts to Discord.

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
            alerts_channel: Channel for health alerts
            enable_recovery_notices: Whether to send recovery notifications
        """
        self.discord_client = discord_client
        self.webhook_url = webhook_url
        self.alerts_channel = alerts_channel
        self.enable_recovery_notices = enable_recovery_notices

        # Track active alerts for recovery detection
        self._active_alerts: set[tuple[str, str]] = set()

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

    async def send_disconnect_alert(
        self,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
    ) -> dict[str, Any]:
        """Send a disconnect alert to Discord.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics

        Returns:
            Send result dictionary
        """
        client = await self._get_client()

        embed = DatasourceHealthDiscordFormatter.format_disconnect_alert(
            source_type=source_type,
            source_name=source_name,
            metrics=metrics,
        )

        # Track this alert
        alert_key = ("disconnected", source_type.value)
        self._active_alerts.add(alert_key)

        try:
            result = await client.send_message(
                content=f"⚠️ Data Source Alert: {source_name} disconnected",
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent disconnect alert to Discord: {source_name}")
            return cast(dict[str, Any], result)
        except Exception as e:
            logger.error(f"Failed to send disconnect alert: {e}")
            return {"success": False, "error": str(e)}

    async def send_reconnect_failed_alert(
        self,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
        max_attempts: int,
    ) -> dict[str, Any]:
        """Send a reconnect failed alert to Discord.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics
            max_attempts: Maximum reconnection attempts

        Returns:
            Send result dictionary
        """
        client = await self._get_client()

        embed = DatasourceHealthDiscordFormatter.format_reconnect_failed_alert(
            source_type=source_type,
            source_name=source_name,
            metrics=metrics,
            max_attempts=max_attempts,
        )

        # Track this alert
        alert_key = ("reconnect_failed", source_type.value)
        self._active_alerts.add(alert_key)

        try:
            result = await client.send_message(
                content=f"🚨 Data Source Critical: {source_name} reconnect failed",
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent reconnect failed alert to Discord: {source_name}")
            return cast(dict[str, Any], result)
        except Exception as e:
            logger.error(f"Failed to send reconnect failed alert: {e}")
            return {"success": False, "error": str(e)}

    async def send_extended_downtime_alert(
        self,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
        downtime_minutes: float,
    ) -> dict[str, Any]:
        """Send an extended downtime alert to Discord.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics
            downtime_minutes: Downtime in minutes

        Returns:
            Send result dictionary
        """
        client = await self._get_client()

        embed = DatasourceHealthDiscordFormatter.format_extended_downtime_alert(
            source_type=source_type,
            source_name=source_name,
            metrics=metrics,
            downtime_minutes=downtime_minutes,
        )

        # Track this alert
        alert_key = ("extended_downtime", source_type.value)
        self._active_alerts.add(alert_key)

        try:
            result = await client.send_message(
                content=f"🚨 Data Source Critical: {source_name} extended downtime",
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent extended downtime alert to Discord: {source_name}")
            return cast(dict[str, Any], result)
        except Exception as e:
            logger.error(f"Failed to send extended downtime alert: {e}")
            return {"success": False, "error": str(e)}

    async def send_recovery_notice(
        self,
        source_type: DataSourceType,
        source_name: str,
        metrics: ConnectionMetrics,
    ) -> dict[str, Any]:
        """Send a recovery notice to Discord.

        Args:
            source_type: Type of data source
            source_name: Human-readable name
            metrics: Connection metrics

        Returns:
            Send result dictionary
        """
        if not self.enable_recovery_notices:
            return {"success": True, "skipped": True}

        # Check if we had an active alert
        had_alert = False
        for alert_type in ["disconnected", "reconnect_failed", "extended_downtime"]:
            alert_key = (alert_type, source_type.value)
            if alert_key in self._active_alerts:
                had_alert = True
                self._active_alerts.discard(alert_key)

        if not had_alert:
            return {"success": True, "skipped": True, "reason": "no_active_alert"}

        client = await self._get_client()

        embed = DatasourceHealthDiscordFormatter.format_recovery_notice(
            source_type=source_type,
            source_name=source_name,
            metrics=metrics,
        )

        try:
            result = await client.send_message(
                content=f"✅ Data Source Recovered: {source_name} is now connected",
                channel=self.alerts_channel,
                embeds=[embed],
            )
            logger.info(f"Sent recovery notice to Discord: {source_name}")
            return cast(dict[str, Any], result)
        except Exception as e:
            logger.error(f"Failed to send recovery notice: {e}")
            return {"success": False, "error": str(e)}

    async def send_generic_alert(self, alert: DatasourceHealthAlert) -> dict[str, Any]:
        """Send a generic data source health alert.

        Args:
            alert: Datasource health alert to send

        Returns:
            Send result dictionary
        """
        from monitoring.datasource_health import ConnectionMetrics, ConnectionStatus

        # Reconstruct metrics from alert
        metrics_dict = alert.metrics
        metrics = ConnectionMetrics(
            source_type=alert.source_type,
            source_name=alert.source_name,
            status=ConnectionStatus(metrics_dict.get("status", "disconnected")),
            disconnect_count=metrics_dict.get("disconnect_count", 0),
            reconnect_attempts=metrics_dict.get("reconnect_attempts", 0),
            total_reconnect_attempts=metrics_dict.get("total_reconnect_attempts", 0),
            uptime_seconds=metrics_dict.get("uptime_seconds", 0.0),
            downtime_seconds=metrics_dict.get("downtime_seconds", 0.0),
            response_time_ms=metrics_dict.get("response_time_ms"),
        )

        if alert.alert_type == "disconnected":
            return await self.send_disconnect_alert(
                source_type=alert.source_type,
                source_name=alert.source_name,
                metrics=metrics,
            )
        elif alert.alert_type == "reconnect_failed":
            # Get max attempts from config or default
            max_attempts = 3
            return await self.send_reconnect_failed_alert(
                source_type=alert.source_type,
                source_name=alert.source_name,
                metrics=metrics,
                max_attempts=max_attempts,
            )
        elif alert.alert_type == "extended_downtime":
            downtime_minutes = metrics_dict.get("downtime_seconds", 0) / 60
            return await self.send_extended_downtime_alert(
                source_type=alert.source_type,
                source_name=alert.source_name,
                metrics=metrics,
                downtime_minutes=downtime_minutes,
            )
        elif alert.alert_type == "recovered":
            return await self.send_recovery_notice(
                source_type=alert.source_type,
                source_name=alert.source_name,
                metrics=metrics,
            )
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
) -> Callable[[DatasourceHealthAlert], Awaitable[None]]:
    """Create an alert handler function for use with DataSourceHealthMonitor.

    Args:
        webhook_url: Discord webhook URL
        discord_client: Existing Discord client
        alerts_channel: Channel for alerts

    Returns:
        Async handler function
    """
    sender = DatasourceHealthDiscordSender(
        discord_client=discord_client,
        webhook_url=webhook_url,
        alerts_channel=alerts_channel,
    )

    async def handler(alert: DatasourceHealthAlert) -> None:
        await sender.send_generic_alert(alert)

    return handler
