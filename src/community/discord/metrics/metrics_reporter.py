"""Metrics reporter for community Discord."""

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Severity level for alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Type of anomaly alert."""

    SPIKE = "spike"
    DROP = "drop"
    THRESHOLD_BREACH = "threshold_breach"


@dataclass
class AnomalyAlert:
    """Alert for anomalous activity."""

    alert_type: AlertType
    severity: AlertSeverity
    metric_name: str
    message: str
    current_value: float
    expected_value: float
    deviation_percent: float
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "metric_name": self.metric_name,
            "message": self.message,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "deviation_percent": self.deviation_percent,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
        }


@dataclass
class MetricsExport:
    """Exported metrics data."""

    timestamp: datetime
    period: str
    active_users: dict[str, int]
    engagement: dict[str, Any]
    command_usage: list[dict[str, Any]]
    anomaly_alerts: list[AnomalyAlert]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "period": self.period,
            "active_users": self.active_users,
            "engagement": self.engagement,
            "command_usage": self.command_usage,
            "anomaly_alerts": [a.to_dict() for a in self.anomaly_alerts],
        }


class MetricsReporter:
    """Periodic metrics aggregation and export.

    Aggregates community metrics periodically, exports them for dashboard
    consumption, and generates alerts for anomalous activity.
    """

    def __init__(
        self,
        redis_client: Any = None,
        aggregation_interval_seconds: int = 300,  # 5 minutes
        alert_threshold_percent: float = 50.0,
        history_window_hours: int = 24,
    ):
        """Initialize MetricsReporter.

        Args:
            redis_client: Redis client for storing metrics
            aggregation_interval_seconds: Interval between aggregations
            alert_threshold_percent: Percent deviation to trigger alert
            history_window_hours: Hours of history to analyze for anomalies
        """
        self._redis = redis_client
        self._aggregation_interval = aggregation_interval_seconds
        self._alert_threshold = alert_threshold_percent
        self._history_window = history_window_hours
        self._alerts: list[AnomalyAlert] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def _get_baseline_key(self, metric_name: str) -> str:
        """Get Redis key for baseline metrics."""
        return f"community:discord:metrics:baseline:{metric_name}"

    def _get_alerts_key(self) -> str:
        """Get Redis key for recent alerts."""
        return "community:discord:alerts:recent"

    async def _calculate_baseline(
        self,
        metric_name: str,
        window_hours: int | None = None,
    ) -> float | None:
        """Calculate baseline value for a metric from historical data.

        Args:
            metric_name: Name of the metric
            window_hours: Hours of history to analyze

        Returns:
            Average baseline value or None
        """
        window = window_hours or self._history_window

        try:
            from tools.redis_state import redis_state_get, redis_state_scan_keys

            pattern = f"community:discord:metrics:{metric_name}:*"
            keys = redis_state_scan_keys(pattern, count=100)

            values: list[float] = []
            cutoff = datetime.now() - timedelta(hours=window)

            for key in keys:
                data = redis_state_get(key)
                if data:
                    try:
                        parsed = json.loads(data)
                        ts = parsed.get("timestamp")
                        if ts:
                            if isinstance(ts, str):
                                ts = datetime.fromisoformat(ts)
                            if ts > cutoff:
                                values.append(float(parsed.get("value", 0)))
                    except (json.JSONDecodeError, ValueError):
                        continue

            if values:
                return sum(values) / len(values)

        except Exception as e:
            logger.warning(f"Failed to calculate baseline: {e}")

        return None

    async def _detect_anomalies(
        self,
        metric_name: str,
        current_value: float,
    ) -> AnomalyAlert | None:
        """Detect anomalies in metric values.

        Args:
            metric_name: Name of the metric
            current_value: Current metric value

        Returns:
            AnomalyAlert or None if no anomaly
        """
        baseline = await self._calculate_baseline(metric_name)

        if baseline is None or baseline == 0:
            return None

        deviation = ((current_value - baseline) / baseline) * 100

        if abs(deviation) >= self._alert_threshold:
            if deviation > 0:
                alert_type = AlertType.SPIKE
                severity = (
                    AlertSeverity.WARNING if deviation < 100 else AlertSeverity.CRITICAL
                )
            else:
                alert_type = AlertType.DROP
                severity = (
                    AlertSeverity.WARNING if deviation > -50 else AlertSeverity.CRITICAL
                )

            return AnomalyAlert(
                alert_type=alert_type,
                severity=severity,
                metric_name=metric_name,
                message=f"{metric_name.replace('_', ' ').title()} {alert_type.value}: {abs(deviation):.1f}% from baseline",
                current_value=current_value,
                expected_value=baseline,
                deviation_percent=deviation,
            )

        return None

    async def _store_alert(self, alert: AnomalyAlert) -> None:
        """Store an alert in Redis.

        Args:
            alert: AnomalyAlert to store
        """
        try:
            from tools.redis_state import redis_state_get, redis_state_set

            alerts_key = self._get_alerts_key()
            alerts_data = redis_state_get(alerts_key)

            alerts = json.loads(alerts_data) if alerts_data else []
            alerts.append(alert.to_dict())

            # Keep only recent alerts (last 100)
            alerts = alerts[-100:]

            redis_state_set(alerts_key, json.dumps(alerts))

        except Exception as e:
            logger.warning(f"Failed to store alert in Redis: {e}")

    async def aggregate_metrics(
        self,
        metrics_instance: Any,
    ) -> MetricsExport:
        """Aggregate all community metrics.

        Args:
            metrics_instance: CommunityMetrics instance

        Returns:
            MetricsExport with aggregated data
        """

        # Get active users
        active_users = await metrics_instance.get_active_users("daily")
        active_users_dict = {
            "daily": active_users.daily,
            "weekly": active_users.weekly,
            "monthly": active_users.monthly,
            "total": active_users.total,
        }

        # Get engagement metrics
        engagement = await metrics_instance.get_engagement_metrics()
        engagement_dict = {
            "messages_sent": engagement.messages_sent,
            "reactions_added": engagement.reactions_added,
            "threads_created": engagement.threads_created,
            "avg_messages_per_user": engagement.avg_messages_per_user,
            "total_engagement_score": engagement.total_engagement_score,
        }

        # Get command usage
        command_usage_raw = await metrics_instance.get_command_usage(limit=20)
        command_usage = [
            {
                "command_name": c.command_name,
                "usage_count": c.usage_count,
                "unique_users": c.unique_users,
                "avg_response_time_ms": c.avg_response_time_ms,
                "error_count": c.error_count,
            }
            for c in command_usage_raw
        ]

        # Detect anomalies
        alerts: list[AnomalyAlert] = []
        for metric_name, value in [
            ("messages", engagement.messages_sent),
            ("active_users", active_users.daily),
            ("threads", engagement.threads_created),
        ]:
            alert = await self._detect_anomalies(metric_name, value)
            if alert:
                alerts.append(alert)
                await self._store_alert(alert)

        self._alerts.extend(alerts)

        return MetricsExport(
            timestamp=datetime.now(),
            period="daily",
            active_users=active_users_dict,
            engagement=engagement_dict,
            command_usage=command_usage,
            anomaly_alerts=alerts,
        )

    async def export_for_dashboard(
        self,
        metrics_instance: Any,
        format: str = "json",
    ) -> str:
        """Export metrics for dashboard consumption.

        Args:
            metrics_instance: CommunityMetrics instance
            format: Export format ('json' or 'csv')

        Returns:
            Exported metrics as string
        """
        export = await self.aggregate_metrics(metrics_instance)

        if format == "json":
            return json.dumps(export.to_dict(), indent=2)
        elif format == "csv":
            lines = ["metric,value,timestamp"]

            # Active users
            for period, value in export.active_users.items():
                lines.append(
                    f"active_users_{period},{value},{export.timestamp.isoformat()}"
                )

            # Engagement
            for key, value in export.engagement.items():
                lines.append(f"engagement_{key},{value},{export.timestamp.isoformat()}")

            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    async def get_recent_alerts(
        self,
        limit: int = 20,
        unacknowledged_only: bool = False,
    ) -> list[AnomalyAlert]:
        """Get recent anomaly alerts.

        Args:
            limit: Maximum number of alerts to return
            unacknowledged_only: Only return unacknowledged alerts

        Returns:
            List of AnomalyAlert
        """
        alerts = list(self._alerts)

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        return alerts[-limit:]

    async def acknowledge_alert(self, alert_index: int) -> bool:
        """Acknowledge an alert.

        Args:
            alert_index: Index of alert in recent list

        Returns:
            True if acknowledged successfully
        """
        if 0 <= alert_index < len(self._alerts):
            self._alerts[alert_index].acknowledged = True
            return True
        return False

    async def start_periodic_aggregation(
        self,
        metrics_instance: Any,
    ) -> None:
        """Start periodic metrics aggregation.

        Args:
            metrics_instance: CommunityMetrics instance
        """
        self._running = True
        self._task = asyncio.create_task(self._aggregation_loop(metrics_instance))
        logger.info("Started periodic metrics aggregation")

    async def _aggregation_loop(self, metrics_instance: Any) -> None:
        """Periodic aggregation loop."""
        while self._running:
            try:
                await asyncio.sleep(self._aggregation_interval)
                await self.aggregate_metrics(metrics_instance)
                logger.debug("Aggregated community metrics")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in aggregation loop: {e}")

    async def stop_periodic_aggregation(self) -> None:
        """Stop periodic aggregation."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Stopped periodic metrics aggregation")

    async def export_time_series(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Export time-series data for a metric.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            interval_minutes: Bucket interval in minutes

        Returns:
            List of time-series data points
        """
        series: list[dict[str, Any]] = []

        try:
            from tools.redis_state import redis_state_get, redis_state_scan_keys

            pattern = f"community:discord:metrics:{metric_name}:*"
            keys = redis_state_scan_keys(pattern, count=1000)

            for key in keys:
                data = redis_state_get(key)
                if data:
                    try:
                        parsed = json.loads(data)
                        ts_str = parsed.get("timestamp")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                            if start_time <= ts <= end_time:
                                series.append(
                                    {
                                        "timestamp": ts.isoformat(),
                                        "value": parsed.get("value"),
                                        "metadata": parsed.get("metadata", {}),
                                    }
                                )
                    except (json.JSONDecodeError, ValueError):
                        continue

            # Sort by timestamp
            series.sort(key=lambda x: x["timestamp"])

        except Exception as e:
            logger.warning(f"Failed to export time series: {e}")

        return series
