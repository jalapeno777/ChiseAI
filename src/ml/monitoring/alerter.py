"""Training alerting system for ChiseAI.

Provides configurable alert rules and notification mechanisms for training
failures, validation gate failures, degradation detection, and SLA breaches.
Integrates with InfluxDB for alert history and Discord for notifications.

Example:
    >>> from ml.monitoring.alerter import TrainingAlerter, AlertRule, AlertSeverity
    >>>
    >>> alerter = TrainingAlerter()
    >>>
    >>> # Add a custom alert rule
    >>> alerter.add_rule(AlertRule(
    ...     name="high_failure_rate",
    ...     condition=lambda m: m.get("failure_rate", 0) > 0.2,
    ...     severity=AlertSeverity.WARNING,
    ...     message="Training failure rate exceeds 20%"
    ... ))
    >>>
    >>> # Trigger an alert
    >>> alerter.alert_training_failure(
    ...     run_id="train_001",
    ...     model_name="signal_predictor",
    ...     error="Out of memory"
    ... )
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# InfluxDB availability flag - graceful degradation if not installed
INFLUXDB_AVAILABLE = False
try:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write.point import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    INFLUXDB_AVAILABLE = True
except ImportError:
    pass


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of training alerts."""

    TRAINING_FAILURE = "training_failure"
    VALIDATION_GATE_FAILURE = "validation_gate_failure"
    DEGRADATION_DETECTED = "degradation_detected"
    SLA_BREACH = "sla_breach"
    HIGH_FAILURE_RATE = "high_failure_rate"
    DATA_QUALITY_LOW = "data_quality_low"


@dataclass
class Alert:
    """Represents a triggered alert.

    Attributes:
        alert_id: Unique alert identifier
        alert_type: Type of alert
        severity: Alert severity level
        message: Human-readable alert message
        source: Source of the alert (e.g., model name, run_id)
        timestamp: When the alert was triggered
        metadata: Additional context about the alert
        acknowledged: Whether the alert has been acknowledged
        acknowledged_at: When the alert was acknowledged
        acknowledged_by: Who acknowledged the alert
        resolved: Whether the alert has been resolved
        resolved_at: When the alert was resolved
    """

    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved: bool = False
    resolved_at: datetime | None = None

    def acknowledge(self, acknowledged_by: str) -> None:
        """Acknowledge the alert.

        Args:
            acknowledged_by: Identifier of who acknowledged
        """
        self.acknowledged = True
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = acknowledged_by
        logger.info(f"Alert {self.alert_id} acknowledged by {acknowledged_by}")

    def resolve(self) -> None:
        """Mark the alert as resolved."""
        self.resolved = True
        self.resolved_at = datetime.now(UTC)
        logger.info(f"Alert {self.alert_id} resolved")

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary format."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat()
            if self.acknowledged_at
            else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class AlertRule:
    """Defines an alert rule with condition and actions.

    Attributes:
        name: Unique rule name
        alert_type: Type of alert this rule generates
        condition: Function that evaluates metrics and returns True if alert should fire
        severity: Alert severity when triggered
        message: Alert message template
        cooldown_seconds: Minimum time between alerts for this rule
        enabled: Whether the rule is active
    """

    name: str
    alert_type: AlertType
    condition: Callable[[dict[str, Any]], bool]
    severity: AlertSeverity
    message: str
    cooldown_seconds: int = 300  # 5 minutes default
    enabled: bool = True

    # Internal tracking
    _last_triggered: datetime | None = field(default=None, repr=False)

    def should_fire(self, metrics: dict[str, Any]) -> bool:
        """Check if the alert should fire given current metrics.

        Args:
            metrics: Current metrics dictionary

        Returns:
            True if alert should fire
        """
        if not self.enabled:
            return False

        # Check cooldown
        if self._last_triggered:
            elapsed = (datetime.now(UTC) - self._last_triggered).total_seconds()
            if elapsed < self.cooldown_seconds:
                logger.debug(
                    f"Alert rule {self.name} in cooldown ({elapsed:.0f}s < {self.cooldown_seconds}s)"
                )
                return False

        # Evaluate condition
        try:
            return self.condition(metrics)
        except Exception as e:
            logger.error(f"Error evaluating alert condition for {self.name}: {e}")
            return False

    def create_alert(
        self, source: str, metadata: dict[str, Any] | None = None
    ) -> Alert:
        """Create an alert instance from this rule.

        Args:
            source: Source of the alert
            metadata: Additional metadata for the alert

        Returns:
            Alert instance
        """
        self._last_triggered = datetime.now(UTC)

        # Generate unique alert ID
        alert_id = f"{self.name}_{self._last_triggered.strftime('%Y%m%d_%H%M%S_%f')}"

        # Format message with metadata
        try:
            message = self.message.format(**(metadata or {}))
        except (KeyError, ValueError):
            message = self.message

        return Alert(
            alert_id=alert_id,
            alert_type=self.alert_type,
            severity=self.severity,
            message=message,
            source=source,
            metadata=metadata or {},
        )


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Send an alert notification.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        pass


class LoggingNotificationChannel(NotificationChannel):
    """Notification channel that logs alerts."""

    def send(self, alert: Alert) -> bool:
        """Send alert via logging."""
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }.get(alert.severity, logger.info)

        log_method(
            f"ALERT [{alert.severity.value.upper()}] {alert.alert_type.value}: {alert.message}"
        )
        return True


class DiscordNotificationChannel(NotificationChannel):
    """Notification channel for Discord.

    Note: This is a placeholder implementation. In production, this would
    integrate with the actual Discord notification system.
    """

    def __init__(self, webhook_url: str | None = None, channel_id: str | None = None):
        """Initialize Discord notification channel.

        Args:
            webhook_url: Discord webhook URL
            channel_id: Discord channel ID
        """
        self.webhook_url = webhook_url
        self.channel_id = channel_id

    def send(self, alert: Alert) -> bool:
        """Send alert to Discord."""
        # Placeholder - in production, this would send to Discord
        emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
        }.get(alert.severity, "ℹ️")

        logger.info(
            f"[DISCORD {emoji}] {alert.severity.value.upper()}: {alert.message}"
        )
        return True


class InfluxDBAlertLogger:
    """Logger for alerts to InfluxDB."""

    def __init__(
        self,
        url: str = "http://chiseai-influxdb:18087",
        token: str = "chiseai-token",
        org: str = "chiseai",
        bucket: str = "chiseai",
    ):
        """Initialize InfluxDB alert logger.

        Args:
            url: InfluxDB URL
            token: Authentication token
            org: Organization name
            bucket: Bucket name
        """
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._client = None
        self._write_api = None
        self._available = INFLUXDB_AVAILABLE

    def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if not self._available:
            return None

        if self._client is None:
            try:
                self._client = InfluxDBClient(
                    url=self._url, token=self._token, org=self._org
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                logger.warning(f"Failed to create InfluxDB client: {e}")
                return None

        return self._client

    def log_alert(self, alert: Alert) -> bool:
        """Log an alert to InfluxDB.

        Args:
            alert: Alert to log

        Returns:
            True if logged successfully
        """
        if not self._available or self._write_api is None:
            self._get_client()
            if self._write_api is None:
                return False

        try:
            point = (
                Point("training_alert")
                .tag("alert_id", alert.alert_id)
                .tag("alert_type", alert.alert_type.value)
                .tag("severity", alert.severity.value)
                .tag("source", alert.source)
                .tag("acknowledged", str(alert.acknowledged))
                .field("message", alert.message)
                .time(alert.timestamp)
            )

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            logger.debug(f"Logged alert to InfluxDB: {alert.alert_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to log alert to InfluxDB: {e}")
            return False


class TrainingAlerter:
    """Alerting system for training operations.

    Provides configurable alert rules and notification mechanisms for
    training failures, validation gate failures, degradation detection,
    and SLA breaches.

    Example:
        >>> alerter = TrainingAlerter()
        >>>
        >>> # Alert on training failure
        >>> alerter.alert_training_failure(
        ...     run_id="train_001",
        ...     model_name="signal_predictor",
        ...     error="Out of memory"
        ... )
        >>>
        >>> # Alert on degradation
        >>> alerter.alert_degradation(
        ...     model_name="signal_predictor",
        ...     version="1.0.0",
        ...     metric_name="accuracy",
        ...     degradation_percentage=15.0
        ... )
        >>>
        >>> # Check active alerts
        >>> active_alerts = alerter.get_active_alerts()
    """

    def __init__(
        self,
        notification_channels: list[NotificationChannel] | None = None,
        influx_logger: InfluxDBAlertLogger | None = None,
    ):
        """Initialize training alerter.

        Args:
            notification_channels: List of notification channels
            influx_logger: Optional InfluxDB logger
        """
        self._notification_channels = notification_channels or [
            LoggingNotificationChannel()
        ]
        self._influx_logger = influx_logger or InfluxDBAlertLogger()
        self._rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._alert_history: list[Alert] = []
        self._max_history = 1000

        # Add default alert rules
        self._add_default_rules()

        logger.info("TrainingAlerter initialized")

    def _add_default_rules(self) -> None:
        """Add default alert rules."""
        default_rules = [
            AlertRule(
                name="high_failure_rate",
                alert_type=AlertType.HIGH_FAILURE_RATE,
                condition=lambda m: m.get("failure_rate", 0) > 0.2,
                severity=AlertSeverity.WARNING,
                message="Training failure rate is high: {failure_rate:.1%}",
                cooldown_seconds=3600,  # 1 hour
            ),
            AlertRule(
                name="low_data_quality",
                alert_type=AlertType.DATA_QUALITY_LOW,
                condition=lambda m: m.get("data_quality_score", 100) < 50,
                severity=AlertSeverity.WARNING,
                message="Data quality score is low: {data_quality_score:.1f}",
                cooldown_seconds=1800,  # 30 minutes
            ),
            AlertRule(
                name="sla_breach_duration",
                alert_type=AlertType.SLA_BREACH,
                condition=lambda m: m.get("duration_seconds", 0) > 14400,  # 4 hours
                severity=AlertSeverity.WARNING,
                message="Training duration exceeds SLA: {duration_seconds:.0f}s",
                cooldown_seconds=3600,
            ),
            AlertRule(
                name="sla_breach_data_freshness",
                alert_type=AlertType.SLA_BREACH,
                condition=lambda m: m.get("data_freshness_hours", 0) > 48,
                severity=AlertSeverity.WARNING,
                message="Training data is stale: {data_freshness_hours:.1f}h old",
                cooldown_seconds=3600,
            ),
        ]

        for rule in default_rules:
            self.add_rule(rule)

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.

        Args:
            rule: Alert rule to add
        """
        self._rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name} (severity={rule.severity.value})")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove an alert rule.

        Args:
            rule_name: Name of rule to remove

        Returns:
            True if rule was removed
        """
        if rule_name in self._rules:
            del self._rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
            return True
        return False

    def _trigger_alert(self, alert: Alert) -> None:
        """Trigger an alert through all channels.

        Args:
            alert: Alert to trigger
        """
        # Store in active alerts
        self._active_alerts[alert.alert_id] = alert

        # Add to history
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history :]

        # Log to InfluxDB
        self._influx_logger.log_alert(alert)

        # Send through notification channels
        for channel in self._notification_channels:
            try:
                channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert through channel: {e}")

        logger.warning(
            f"Alert triggered: {alert.alert_id} ({alert.alert_type.value}, {alert.severity.value})"
        )

    def alert_training_failure(
        self,
        run_id: str,
        model_name: str,
        error: str,
        error_type: str = "runtime_error",
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Alert on training failure.

        Args:
            run_id: Training run ID
            model_name: Model name
            error: Error message
            error_type: Type of error
            metadata: Additional metadata

        Returns:
            Created alert
        """
        alert_metadata = {
            "run_id": run_id,
            "model_name": model_name,
            "error": error,
            "error_type": error_type,
            **(metadata or {}),
        }

        alert = Alert(
            alert_id=f"training_failure_{run_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message=f"Training failed for {model_name} (run {run_id}): {error}",
            source=run_id,
            metadata=alert_metadata,
        )

        self._trigger_alert(alert)
        return alert

    def alert_validation_gate_failure(
        self,
        model_name: str,
        version: str,
        gate_name: str,
        failed_metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Alert on validation gate failure.

        Args:
            model_name: Model name
            version: Model version
            gate_name: Name of the failed gate
            failed_metrics: Metrics that failed validation
            metadata: Additional metadata

        Returns:
            Created alert
        """
        alert_metadata = {
            "model_name": model_name,
            "version": version,
            "gate_name": gate_name,
            "failed_metrics": failed_metrics or {},
            **(metadata or {}),
        }

        alert = Alert(
            alert_id=f"validation_failure_{model_name}_{version}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            alert_type=AlertType.VALIDATION_GATE_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message=f"Validation gate '{gate_name}' failed for {model_name}@{version}",
            source=f"{model_name}@{version}",
            metadata=alert_metadata,
        )

        self._trigger_alert(alert)
        return alert

    def alert_degradation(
        self,
        model_name: str,
        version: str,
        metric_name: str,
        degradation_percentage: float,
        baseline_value: float | None = None,
        current_value: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Alert on model degradation.

        Args:
            model_name: Model name
            version: Model version
            metric_name: Name of degraded metric
            degradation_percentage: Percentage of degradation
            baseline_value: Baseline metric value
            current_value: Current metric value
            metadata: Additional metadata

        Returns:
            Created alert
        """
        alert_metadata = {
            "model_name": model_name,
            "version": version,
            "metric_name": metric_name,
            "degradation_percentage": degradation_percentage,
            "baseline_value": baseline_value,
            "current_value": current_value,
            **(metadata or {}),
        }

        alert = Alert(
            alert_id=f"degradation_{model_name}_{version}_{metric_name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            alert_type=AlertType.DEGRADATION_DETECTED,
            severity=AlertSeverity.CRITICAL,
            message=(
                f"Degradation detected in {model_name}@{version}: "
                f"{metric_name} degraded by {degradation_percentage:.1f}%"
            ),
            source=f"{model_name}@{version}",
            metadata=alert_metadata,
        )

        self._trigger_alert(alert)
        return alert

    def alert_sla_breach(
        self,
        sla_type: str,
        actual_value: float,
        threshold_value: float,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Alert on SLA breach.

        Args:
            sla_type: Type of SLA breached (e.g., "duration", "freshness")
            actual_value: Actual measured value
            threshold_value: SLA threshold value
            source: Source of the breach (e.g., run_id)
            metadata: Additional metadata

        Returns:
            Created alert
        """
        alert_metadata = {
            "sla_type": sla_type,
            "actual_value": actual_value,
            "threshold_value": threshold_value,
            **(metadata or {}),
        }

        alert = Alert(
            alert_id=f"sla_breach_{sla_type}_{source}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            alert_type=AlertType.SLA_BREACH,
            severity=AlertSeverity.WARNING,
            message=(
                f"SLA breach: {sla_type} = {actual_value:.1f} "
                f"(threshold: {threshold_value:.1f})"
            ),
            source=source,
            metadata=alert_metadata,
        )

        self._trigger_alert(alert)
        return alert

    def evaluate_rules(self, metrics: dict[str, Any], source: str) -> list[Alert]:
        """Evaluate all alert rules against current metrics.

        Args:
            metrics: Current metrics dictionary
            source: Source identifier for triggered alerts

        Returns:
            List of triggered alerts
        """
        triggered = []

        for rule_name, rule in self._rules.items():
            if rule.should_fire(metrics):
                alert = rule.create_alert(source=source, metadata=metrics)
                self._trigger_alert(alert)
                triggered.append(alert)

        return triggered

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an active alert.

        Args:
            alert_id: ID of alert to acknowledge
            acknowledged_by: Who is acknowledging

        Returns:
            True if alert was acknowledged
        """
        alert = self._active_alerts.get(alert_id)
        if alert:
            alert.acknowledge(acknowledged_by)
            return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert.

        Args:
            alert_id: ID of alert to resolve

        Returns:
            True if alert was resolved
        """
        alert = self._active_alerts.get(alert_id)
        if alert:
            alert.resolve()
            # Move from active to history-only
            del self._active_alerts[alert_id]
            return True
        return False

    def get_active_alerts(
        self,
        alert_type: AlertType | None = None,
        severity: AlertSeverity | None = None,
    ) -> list[Alert]:
        """Get all active (unresolved) alerts.

        Args:
            alert_type: Filter by alert type
            severity: Filter by severity

        Returns:
            List of active alerts
        """
        alerts = list(self._active_alerts.values())

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_alert_history(
        self,
        since: datetime | None = None,
        alert_type: AlertType | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Get alert history.

        Args:
            since: Only return alerts after this time
            alert_type: Filter by alert type
            limit: Maximum number of alerts

        Returns:
            List of historical alerts
        """
        history = self._alert_history

        if since:
            history = [a for a in history if a.timestamp >= since]

        if alert_type:
            history = [a for a in history if a.alert_type == alert_type]

        return sorted(history, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_alert_summary(self, days: int = 7) -> dict[str, Any]:
        """Get summary of alerts over a period.

        Args:
            days: Number of days to summarize

        Returns:
            Dictionary with alert summary
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        recent_alerts = [a for a in self._alert_history if a.timestamp >= cutoff]

        summary = {
            "period_days": days,
            "total_alerts": len(recent_alerts),
            "active_alerts": len(self._active_alerts),
            "by_type": {},
            "by_severity": {},
            "acknowledged": 0,
            "unacknowledged": 0,
        }

        for alert in recent_alerts:
            # Count by type
            alert_type = alert.alert_type.value
            summary["by_type"][alert_type] = summary["by_type"].get(alert_type, 0) + 1

            # Count by severity
            severity = alert.severity.value
            summary["by_severity"][severity] = (
                summary["by_severity"].get(severity, 0) + 1
            )

            # Count acknowledged
            if alert.acknowledged:
                summary["acknowledged"] += 1
            else:
                summary["unacknowledged"] += 1

        return summary

    def clear_history(self) -> None:
        """Clear all alert history."""
        self._active_alerts.clear()
        self._alert_history.clear()
        logger.info("Alert history cleared")
