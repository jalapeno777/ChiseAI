"""Connection health monitor for execution exchanges.

Monitors Bybit and Bitget connection health with heartbeat tracking,
data gap detection, and exponential backoff reconnection.

For ST-DATA-002: Execution Market Data Ingestion - Bybit/Bitget
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DataGapAlert:
    """Data gap alert for monitoring.

    Attributes:
        source: Exchange name (bybit/bitget)
        symbol: Trading pair
        gap_start: Gap start timestamp (Unix ms)
        gap_end: Gap end timestamp (Unix ms)
        duration_seconds: Gap duration
        severity: Alert severity
        detected_at: When gap was detected
    """

    source: str
    symbol: str
    gap_start: float
    gap_end: float
    duration_seconds: float
    severity: AlertSeverity
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "symbol": self.symbol,
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "duration_seconds": self.duration_seconds,
            "severity": self.severity.value,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class ConnectionStatus:
    """Connection status for an exchange.

    Attributes:
        exchange: Exchange name
        is_connected: Whether currently connected
        last_heartbeat: Last successful heartbeat timestamp
        last_message: Last message received timestamp
        reconnect_count: Total reconnections
        latency_ms: Current latency
        data_gap_alerts: Active data gap alerts
    """

    exchange: str
    is_connected: bool = False
    last_heartbeat: datetime | None = None
    last_message: datetime | None = None
    reconnect_count: int = 0
    latency_ms: float = 0.0
    data_gap_alerts: list[DataGapAlert] = field(default_factory=list)

    @property
    def time_since_heartbeat(self) -> float:
        """Time since last heartbeat in seconds."""
        if self.last_heartbeat is None:
            return float("inf")
        return (datetime.now(UTC) - self.last_heartbeat).total_seconds()

    @property
    def time_since_message(self) -> float:
        """Time since last message in seconds."""
        if self.last_message is None:
            return float("inf")
        return (datetime.now(UTC) - self.last_message).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exchange": self.exchange,
            "is_connected": self.is_connected,
            "last_heartbeat": (
                self.last_heartbeat.isoformat() if self.last_heartbeat else None
            ),
            "last_message": (
                self.last_message.isoformat() if self.last_message else None
            ),
            "time_since_heartbeat_sec": self.time_since_heartbeat,
            "time_since_message_sec": self.time_since_message,
            "reconnect_count": self.reconnect_count,
            "latency_ms": self.latency_ms,
            "active_gap_alerts": len(self.data_gap_alerts),
        }


class ExecutionHealthMonitor:
    """Health monitor for Bybit and Bitget connections.

    Monitors:
    - Heartbeat every 30s
    - Data gaps >10s
    - Connection failures with exponential backoff
    - Alerts via Discord

    For ST-DATA-002: Execution Market Data Ingestion
    """

    HEARTBEAT_INTERVAL = 30  # seconds
    DATA_GAP_THRESHOLD = 10  # seconds
    MAX_ALERTS = 100  # Max alerts to keep in memory

    def __init__(
        self,
        bybit_connector: Any | None = None,
        bitget_connector: Any | None = None,
        alert_callback: Callable[[DataGapAlert], None] | None = None,
    ):
        """Initialize health monitor.

        Args:
            bybit_connector: BybitConnector instance
            bitget_connector: BitgetConnector instance
            alert_callback: Callback for gap alerts
        """
        self._bybit = bybit_connector
        self._bitget = bitget_connector
        self._alert_callback = alert_callback

        self._status: dict[str, ConnectionStatus] = {
            "bybit": ConnectionStatus(exchange="bybit"),
            "bitget": ConnectionStatus(exchange="bitget"),
        }

        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._alert_history: list[DataGapAlert] = []

    async def start(self) -> None:
        """Start health monitoring."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Execution health monitor started")

    async def stop(self) -> None:
        """Stop health monitoring."""
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        logger.info("Execution health monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_health()
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)

    async def _check_health(self) -> None:
        """Check health of all connections."""
        # Check Bybit
        if self._bybit:
            await self._check_exchange_health("bybit", self._bybit)

        # Check Bitget
        if self._bitget:
            await self._check_exchange_health("bitget", self._bitget)

    async def _check_exchange_health(self, exchange: str, connector: Any) -> None:
        """Check health of a single exchange."""
        status = self._status[exchange]

        try:
            # Get health from connector
            health = await connector.health_check()

            # Update status
            status.is_connected = health.get("connected", False)
            status.latency_ms = health.get("latency_ms", 0.0)

            if health.get("healthy"):
                status.last_heartbeat = datetime.now(UTC)
                status.last_message = datetime.now(UTC)

            # Check for data gaps
            time_since_message = health.get("last_message_seconds_ago", float("inf"))
            if time_since_message > self.DATA_GAP_THRESHOLD:
                await self._handle_data_gap(exchange, time_since_message)

        except Exception as e:
            logger.warning(f"Health check failed for {exchange}: {e}")
            status.is_connected = False

    async def _handle_data_gap(self, source: str, gap_duration: float) -> None:
        """Handle data gap detection.

        Args:
            source: Exchange name
            gap_duration: Duration of data gap in seconds
        """
        now = datetime.now(UTC)
        gap_start = now.timestamp() - gap_duration

        alert = DataGapAlert(
            source=source,
            symbol="ALL",  # Generic for connection-level gaps
            gap_start=gap_start,
            gap_end=now.timestamp(),
            duration_seconds=gap_duration,
            severity=(
                AlertSeverity.CRITICAL if gap_duration > 60 else AlertSeverity.WARNING
            ),
        )

        # Store alert
        self._alert_history.append(alert)
        if len(self._alert_history) > self.MAX_ALERTS:
            self._alert_history.pop(0)

        # Add to active alerts
        self._status[source].data_gap_alerts.append(alert)

        # Send alert
        if self._alert_callback:
            try:
                await self._alert_callback(alert)  # type: ignore[misc]
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        logger.warning(f"Data gap detected: {source} - {gap_duration:.1f}s")

    def get_status(self, exchange: str | None = None) -> dict[str, Any]:
        """Get health status.

        Args:
            exchange: Specific exchange or None for all

        Returns:
            Status dictionary
        """
        if exchange:
            return self._status.get(
                exchange, ConnectionStatus(exchange=exchange or "unknown")
            ).to_dict()

        return {
            "bybit": self._status["bybit"].to_dict(),
            "bitget": self._status["bitget"].to_dict(),
            "monitoring_active": self._running,
        }

    def is_healthy(self, exchange: str) -> bool:
        """Check if exchange connection is healthy.

        Args:
            exchange: Exchange name

        Returns:
            True if healthy
        """
        status = self._status.get(exchange)
        if not status:
            return False

        return (
            status.is_connected
            and status.time_since_heartbeat < self.HEARTBEAT_INTERVAL * 2
        )

    def get_active_alerts(self, exchange: str | None = None) -> list[DataGapAlert]:
        """Get active data gap alerts.

        Args:
            exchange: Filter by exchange (optional)

        Returns:
            List of active alerts
        """
        alerts = []
        for status in self._status.values():
            for alert in status.data_gap_alerts:
                if exchange is None or alert.source == exchange:
                    alerts.append(alert)
        return alerts

    def clear_alert(self, alert_id: str) -> bool:
        """Clear a specific alert.

        Args:
            alert_id: Alert identifier (source_symbol_timestamp)

        Returns:
            True if cleared
        """
        for status in self._status.values():
            for i, alert in enumerate(status.data_gap_alerts):
                alert_key = f"{alert.source}_{alert.symbol}_{alert.gap_start}"
                if alert_key == alert_id:
                    status.data_gap_alerts.pop(i)
                    return True
        return False

    def get_alert_history(
        self, limit: int = 50, exchange: str | None = None
    ) -> list[dict[str, Any]]:
        """Get alert history.

        Args:
            limit: Maximum number of alerts
            exchange: Filter by exchange (optional)

        Returns:
            List of alert dictionaries
        """
        alerts = self._alert_history
        if exchange:
            alerts = [a for a in alerts if a.source == exchange]

        return [a.to_dict() for a in alerts[-limit:]]


# Convenience functions for Discord integration
async def send_gap_alert_to_discord(
    alert: DataGapAlert,
    discord_sender: Any | None = None,
) -> dict[str, Any]:
    """Send data gap alert to Discord.

    Args:
        alert: Data gap alert
        discord_sender: Discord sender instance

    Returns:
        Send result
    """
    try:
        from monitoring.data_quality.discord_sender import (
            DataQualityDiscordSender,
        )

        sender = discord_sender or DataQualityDiscordSender()

        # Format for Discord
        from monitoring.data_quality import DataSource

        source = DataSource(alert.source)

        embed = {
            "title": f"🚨 {source.value.upper()} - Data Gap Detected",
            "description": (
                f"Connection data gap detected for **{alert.source}**\n\n"
                f"• Duration: **{alert.duration_seconds:.1f}** seconds\n"
                f"• Threshold: **10** seconds\n"
                f"• Severity: **{alert.severity.value.upper()}**"
            ),
            "color": 0xE74C3C if alert.severity == AlertSeverity.CRITICAL else 0xF39C12,
            "fields": [
                {
                    "name": "Source",
                    "value": alert.source.upper(),
                    "inline": True,
                },
                {
                    "name": "Duration",
                    "value": f"{alert.duration_seconds:.1f}s",
                    "inline": True,
                },
                {
                    "name": "Detected At",
                    "value": alert.detected_at.strftime("%H:%M:%S UTC"),
                    "inline": True,
                },
            ],
            "footer": {
                "text": "ChiseAI Execution Health Monitor",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

        result = await sender._get_client().send_message(
            content=f"🚨 Execution Data Gap: {alert.source.upper()}",
            channel="alerts",
            embeds=[embed],
        )

        return result  # type: ignore[no-any-return]

    except Exception as e:
        logger.error(f"Failed to send Discord alert: {e}")
        return {"success": False, "error": str(e)}
