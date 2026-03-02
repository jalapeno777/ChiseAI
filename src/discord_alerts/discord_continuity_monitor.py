"""Discord continuity monitor for P0 runtime hardening.

Monitors Discord message flow, tracks metrics, triggers alerts,
and auto-retries queued messages. Stores continuity metrics in Redis.

For P0-RUNTIME-HARDEN-003: Discord Continuity
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discord_alerts.config import DiscordConfig
    from discord_alerts.discord_client import DiscordClient

logger = logging.getLogger(__name__)


@dataclass
class ContinuityMetrics:
    """Metrics for Discord continuity monitoring.

    Attributes:
        timestamp: When metrics were recorded
        messages_sent: Total messages sent
        messages_failed: Total messages failed
        messages_queued: Total messages queued
        messages_retried: Total messages retried
        last_successful_send: Timestamp of last successful send
        consecutive_failures: Current consecutive failure count
        is_connected: Whether Discord is connected
        is_disabled: Whether Discord is temporarily disabled
        queue_size: Current message queue size
        avg_latency_ms: Average message latency
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    messages_sent: int = 0
    messages_failed: int = 0
    messages_queued: int = 0
    messages_retried: int = 0
    last_successful_send: datetime | None = None
    consecutive_failures: int = 0
    is_connected: bool = False
    is_disabled: bool = False
    queue_size: int = 0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "messages_sent": self.messages_sent,
            "messages_failed": self.messages_failed,
            "messages_queued": self.messages_queued,
            "messages_retried": self.messages_retried,
            "last_successful_send": (
                self.last_successful_send.isoformat()
                if self.last_successful_send
                else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "is_connected": self.is_connected,
            "is_disabled": self.is_disabled,
            "queue_size": self.queue_size,
            "avg_latency_ms": self.avg_latency_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContinuityMetrics:
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            messages_sent=data.get("messages_sent", 0),
            messages_failed=data.get("messages_failed", 0),
            messages_queued=data.get("messages_queued", 0),
            messages_retried=data.get("messages_retried", 0),
            last_successful_send=(
                datetime.fromisoformat(data["last_successful_send"])
                if data.get("last_successful_send")
                else None
            ),
            consecutive_failures=data.get("consecutive_failures", 0),
            is_connected=data.get("is_connected", False),
            is_disabled=data.get("is_disabled", False),
            queue_size=data.get("queue_size", 0),
            avg_latency_ms=data.get("avg_latency_ms", 0.0),
        )


@dataclass
class AlertThresholds:
    """Thresholds for triggering continuity alerts.

    Attributes:
        no_message_hours: Alert if no messages in N hours
        max_queue_size: Alert if queue exceeds N messages
        max_consecutive_failures: Alert after N consecutive failures
        max_latency_ms: Alert if latency exceeds N ms
    """

    no_message_hours: float = 2.0
    max_queue_size: int = 500
    max_consecutive_failures: int = 5
    max_latency_ms: float = 5000.0


class DiscordContinuityMonitor:
    """Monitor Discord message continuity and trigger alerts.

    Features:
        - Track messages sent/failed/queued
        - Trigger alerts if no messages sent in 2 hours
        - Auto-retry queued messages
        - Store continuity metrics in Redis
        - Monitor connection health

    Attributes:
        discord_client: DiscordClient instance to monitor
        config: Discord configuration
        thresholds: Alert thresholds
        check_interval_seconds: How often to check continuity
        redis_key_prefix: Prefix for Redis keys
    """

    DEFAULT_CHECK_INTERVAL = 60  # seconds
    REDIS_KEY_PREFIX = "discord:continuity"
    METRICS_HISTORY_SIZE = 1440  # 24 hours at 1 sample/minute

    def __init__(
        self,
        discord_client: DiscordClient,
        config: DiscordConfig,
        thresholds: AlertThresholds | None = None,
        check_interval_seconds: int = DEFAULT_CHECK_INTERVAL,
    ):
        """Initialize continuity monitor.

        Args:
            discord_client: DiscordClient to monitor
            config: Discord configuration
            thresholds: Alert thresholds (uses defaults if None)
            check_interval_seconds: How often to check continuity
        """
        self.discord_client = discord_client
        self.config = config
        self.thresholds = thresholds or AlertThresholds()
        self.check_interval_seconds = check_interval_seconds

        self._monitor_task: asyncio.Task | None = None
        self._retry_task: asyncio.Task | None = None
        self._metrics_history: list[ContinuityMetrics] = []
        self._alert_handlers: list[callable] = []
        self._is_running = False

        # Cumulative counters
        self._total_sent = 0
        self._total_failed = 0
        self._total_queued = 0
        self._total_retried = 0

    def add_alert_handler(self, handler: callable) -> None:
        """Add a handler for continuity alerts.

        Args:
            handler: Callable that receives (alert_type, message, metrics)
        """
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: callable) -> None:
        """Remove an alert handler.

        Args:
            handler: Handler to remove
        """
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    async def start(self) -> None:
        """Start the continuity monitor."""
        if self._is_running:
            logger.warning("Continuity monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("Discord continuity monitor started")

    async def stop(self) -> None:
        """Stop the continuity monitor."""
        self._is_running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retry_task

        logger.info("Discord continuity monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._is_running:
            try:
                await asyncio.sleep(self.check_interval_seconds)

                # Collect metrics
                metrics = await self._collect_metrics()
                self._metrics_history.append(metrics)

                # Trim history
                if len(self._metrics_history) > self.METRICS_HISTORY_SIZE:
                    self._metrics_history = self._metrics_history[
                        -self.METRICS_HISTORY_SIZE :
                    ]

                # Store in Redis
                await self._store_metrics(metrics)

                # Check thresholds and trigger alerts
                await self._check_thresholds(metrics)

            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    async def _retry_loop(self) -> None:
        """Auto-retry loop for queued messages."""
        while self._is_running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not self.discord_client.is_connected:
                    continue

                if (
                    hasattr(self.discord_client, "is_disabled")
                    and self.discord_client.is_disabled
                ):
                    continue

                # Trigger retry of queued messages
                # The discord_client has its own retry logic, but we can
                # trigger it more aggressively here if needed
                if hasattr(self.discord_client, "_process_message_queue"):
                    await self.discord_client._process_message_queue()
                    self._total_retried += 1

            except asyncio.CancelledError:
                logger.info("Retry loop cancelled")
                break
            except Exception as e:
                logger.error(f"Retry loop error: {e}")

    async def _collect_metrics(self) -> ContinuityMetrics:
        """Collect current metrics from Discord client.

        Returns:
            ContinuityMetrics instance
        """
        # Get client health
        try:
            health = await self.discord_client.health_check()
        except Exception as e:
            logger.error(f"Failed to get health check: {e}")
            health = {}

        # Get continuity metrics if available
        try:
            if hasattr(self.discord_client, "get_continuity_metrics"):
                client_metrics = await self.discord_client.get_continuity_metrics()
            else:
                client_metrics = {}
        except Exception as e:
            logger.error(f"Failed to get continuity metrics: {e}")
            client_metrics = {}

        # Update cumulative counters
        self._total_sent = client_metrics.get("total_messages_sent", self._total_sent)
        self._total_failed = client_metrics.get(
            "total_messages_failed", self._total_failed
        )
        self._total_queued = client_metrics.get(
            "total_messages_queued", self._total_queued
        )

        # Build metrics
        metrics = ContinuityMetrics(
            timestamp=datetime.now(UTC),
            messages_sent=self._total_sent,
            messages_failed=self._total_failed,
            messages_queued=self._total_queued,
            messages_retried=self._total_retried,
            last_successful_send=(
                datetime.fromisoformat(client_metrics["last_successful_send"])
                if client_metrics.get("last_successful_send")
                else None
            ),
            consecutive_failures=health.get("consecutive_failures", 0),
            is_connected=self.discord_client.is_connected,
            is_disabled=health.get("is_disabled", False),
            queue_size=health.get("queue_size", 0),
            avg_latency_ms=0.0,  # Could be calculated from history
        )

        return metrics

    async def _store_metrics(self, metrics: ContinuityMetrics) -> None:
        """Store metrics in Redis.

        Args:
            metrics: Metrics to store
        """
        try:
            # Try to import redis_state
            from tools.redis_state import (
                redis_state_hset,
                redis_state_lpush,
            )

            # Store current metrics
            redis_key = f"{self.REDIS_KEY_PREFIX}:metrics:current"
            redis_state_hset(redis_key, "data", json.dumps(metrics.to_dict()))
            redis_state_hset(redis_key, "timestamp", metrics.timestamp.isoformat())

            # Add to history list
            history_key = f"{self.REDIS_KEY_PREFIX}:metrics:history"
            redis_state_lpush(history_key, json.dumps(metrics.to_dict()), expire=86400)

            logger.debug(f"Stored continuity metrics: sent={metrics.messages_sent}")

        except ImportError:
            logger.debug("redis_state not available, skipping Redis storage")
        except Exception as e:
            logger.error(f"Failed to store metrics in Redis: {e}")

    async def _check_thresholds(self, metrics: ContinuityMetrics) -> None:
        """Check metrics against thresholds and trigger alerts.

        Args:
            metrics: Current metrics
        """
        alerts_triggered = []

        # Check: No messages in N hours
        if metrics.last_successful_send:
            time_since_last = datetime.now(UTC) - metrics.last_successful_send
            if time_since_last > timedelta(hours=self.thresholds.no_message_hours):
                alert_msg = (
                    f"No Discord messages sent in {time_since_last.total_seconds() / 3600:.1f} hours "
                    f"(threshold: {self.thresholds.no_message_hours}h)"
                )
                alerts_triggered.append(("no_messages", alert_msg, metrics))

        # Check: Queue size
        if metrics.queue_size > self.thresholds.max_queue_size:
            alert_msg = (
                f"Discord message queue size ({metrics.queue_size}) exceeds threshold "
                f"({self.thresholds.max_queue_size})"
            )
            alerts_triggered.append(("queue_size", alert_msg, metrics))

        # Check: Consecutive failures
        if metrics.consecutive_failures >= self.thresholds.max_consecutive_failures:
            alert_msg = (
                f"Discord has {metrics.consecutive_failures} consecutive failures "
                f"(threshold: {self.thresholds.max_consecutive_failures})"
            )
            alerts_triggered.append(("consecutive_failures", alert_msg, metrics))

        # Trigger alerts
        for alert_type, message, alert_metrics in alerts_triggered:
            await self._trigger_alert(alert_type, message, alert_metrics)

    async def _trigger_alert(
        self, alert_type: str, message: str, metrics: ContinuityMetrics
    ) -> None:
        """Trigger an alert.

        Args:
            alert_type: Type of alert
            message: Alert message
            metrics: Current metrics
        """
        logger.error(f"CONTINUITY ALERT [{alert_type}]: {message}")

        # Call registered handlers
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert_type, message, metrics)
                else:
                    handler(alert_type, message, metrics)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

        # Store alert in Redis
        try:
            from tools.redis_state import redis_state_lpush

            alert_data = {
                "type": alert_type,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
                "metrics": metrics.to_dict(),
            }
            redis_state_lpush(
                f"{self.REDIS_KEY_PREFIX}:alerts",
                json.dumps(alert_data),
                expire=86400 * 7,  # Keep for 7 days
            )
        except Exception as e:
            logger.error(f"Failed to store alert: {e}")

    async def get_metrics_history(self, hours: int = 24) -> list[ContinuityMetrics]:
        """Get metrics history.

        Args:
            hours: How many hours of history to retrieve

        Returns:
            List of ContinuityMetrics
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return [m for m in self._metrics_history if m.timestamp > cutoff]

    async def get_current_metrics(self) -> ContinuityMetrics | None:
        """Get current metrics from Redis.

        Returns:
            Current metrics or None if not available
        """
        try:
            from tools.redis_state import redis_state_hget

            redis_key = f"{self.REDIS_KEY_PREFIX}:metrics:current"
            data = redis_state_hget(redis_key, "data")

            if data:
                return ContinuityMetrics.from_dict(json.loads(data))

        except Exception as e:
            logger.error(f"Failed to get current metrics: {e}")

        # Fallback to local history
        if self._metrics_history:
            return self._metrics_history[-1]

        return None

    async def send_test_message(self) -> dict[str, Any]:
        """Send a test message to verify Discord connectivity.

        Returns:
            Result dict with success status and latency
        """
        import time

        start_time = time.time()

        try:
            result = await self.discord_client.send_message(
                content="🧪 **Discord Continuity Test**\n"
                f"Timestamp: {datetime.now(UTC).isoformat()}\n"
                f"Monitor: Active",
                channel_id=self.config.summaries_channel_id,
            )

            latency_ms = (time.time() - start_time) * 1000

            return {
                "success": result.success,
                "latency_ms": latency_ms,
                "error": result.error,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            return {
                "success": False,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of continuity status.

        Returns:
            Status summary dict
        """
        current = self._metrics_history[-1] if self._metrics_history else None

        return {
            "monitor_running": self._is_running,
            "check_interval_seconds": self.check_interval_seconds,
            "current_metrics": current.to_dict() if current else None,
            "metrics_history_count": len(self._metrics_history),
            "alert_handlers_count": len(self._alert_handlers),
            "thresholds": {
                "no_message_hours": self.thresholds.no_message_hours,
                "max_queue_size": self.thresholds.max_queue_size,
                "max_consecutive_failures": self.thresholds.max_consecutive_failures,
                "max_latency_ms": self.thresholds.max_latency_ms,
            },
        }
