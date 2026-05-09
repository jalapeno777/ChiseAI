"""Alerting system for Model Registry.

Provides configurable alert rules and notification mechanisms for
monitoring registry health and performance.

Example:
    # Set up alert manager with custom rules
    alert_manager = AlertManager()
    alert_manager.add_rule(AlertRule(
        name="high_latency",
        condition=lambda m: m.model_retrieval_latency_seconds and
                           m.model_retrieval_latency_seconds[-1] > 1.0,
        severity=AlertSeverity.WARNING,
        message="Model retrieval latency exceeds 1 second"
    ))
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from ml.monitoring.registry_metrics import RegistryMetrics

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents a triggered alert.

    Attributes:
        name: Alert name/identifier
        severity: Alert severity level
        message: Human-readable alert message
        timestamp: When the alert was triggered
        metadata: Additional context about the alert
        acknowledged: Whether the alert has been acknowledged
        acknowledged_at: When the alert was acknowledged
        acknowledged_by: Who acknowledged the alert
    """

    name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None

    def acknowledge(self, acknowledged_by: str) -> None:
        """Acknowledge the alert.

        Args:
            acknowledged_by: Identifier of who acknowledged
        """
        self.acknowledged = True
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = acknowledged_by
        logger.info(f"Alert {self.name} acknowledged by {acknowledged_by}")

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary format.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            "acknowledged_by": self.acknowledged_by,
        }

    def to_alertmanager_format(self) -> dict[str, Any]:
        """Convert to Prometheus Alertmanager format.

        Returns:
            Alertmanager-compatible alert dictionary
        """
        labels = {
            "alertname": self.name,
            "severity": self.severity.value,
        }
        labels.update(self.metadata.get("labels", {}))

        annotations = {
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }
        annotations.update(self.metadata.get("annotations", {}))

        return {
            "labels": labels,
            "annotations": annotations,
            "startsAt": self.timestamp.isoformat(),
            "endsAt": (
                self.timestamp + timedelta(hours=1)
            ).isoformat(),  # Default 1h TTL
        }

    def to_influxdb_format(self) -> dict[str, Any]:
        """Convert to InfluxDB-compatible alert format.

        InfluxDB uses tags for indexed/dimension fields and fields for
        data values. Timestamps use nanosecond precision Unix epoch.

        Returns:
            InfluxDB-compatible alert dictionary with measurement, tags,
            fields, and timestamp keys
        """
        from ml.monitoring.registry_metrics import sanitize_metric_name

        tags = {
            "alertname": sanitize_metric_name(self.name, "influxdb"),
            "severity": self.severity.value,
        }
        # Merge any metadata tags (e.g. environment, service)
        for k, v in self.metadata.get("labels", {}).items():
            tags[sanitize_metric_name(k, "influxdb")] = str(v)

        fields = {
            "message": self.message,
            "acknowledged": str(self.acknowledged).lower(),
        }
        # Merge any metadata fields
        for k, v in self.metadata.get("annotations", {}).items():
            fields[k] = str(v)

        # InfluxDB uses nanosecond-precision Unix timestamps
        ts_ns = int(self.timestamp.timestamp() * 1e9)

        return {
            "measurement": "alerts",
            "tags": tags,
            "fields": fields,
            "timestamp": ts_ns,
        }


@dataclass
class AlertRule:
    """Defines an alert rule with condition and actions.

    Attributes:
        name: Unique rule name
        condition: Function that evaluates metrics and returns True if alert should fire
        severity: Alert severity when triggered
        message: Alert message template (can use {metadata} placeholders)
        cooldown_seconds: Minimum time between alerts for this rule
        enabled: Whether the rule is active
    """

    name: str
    condition: Callable[[RegistryMetrics], bool]
    severity: AlertSeverity
    message: str
    cooldown_seconds: int = 300  # 5 minutes default
    enabled: bool = True

    # Internal tracking
    _last_triggered: datetime | None = field(default=None, repr=False)

    def should_fire(self, metrics: RegistryMetrics) -> bool:
        """Check if the alert should fire given current metrics.

        Args:
            metrics: Current registry metrics

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
                    f"Alert {self.name} in cooldown ({elapsed:.0f}s < {self.cooldown_seconds}s)"
                )
                return False

        # Evaluate condition
        try:
            return self.condition(metrics)
        except Exception as e:
            logger.error(f"Error evaluating alert condition for {self.name}: {e}")
            return False

    def create_alert(self, metadata: dict[str, Any] | None = None) -> Alert:
        """Create an alert instance from this rule.

        Args:
            metadata: Additional metadata for the alert

        Returns:
            Alert instance
        """
        self._last_triggered = datetime.now(UTC)
        return Alert(
            name=self.name,
            severity=self.severity,
            message=self.message.format(**(metadata or {})),
            metadata=metadata or {},
        )


class AlertManager(ABC):
    """Abstract base class for alert management.

    Implementations should handle alert storage, notification, and lifecycle.
    """

    @abstractmethod
    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.

        Args:
            rule: Alert rule to add
        """
        pass

    @abstractmethod
    def remove_rule(self, rule_name: str) -> bool:
        """Remove an alert rule.

        Args:
            rule_name: Name of rule to remove

        Returns:
            True if rule was removed
        """
        pass

    @abstractmethod
    def evaluate(self, metrics: RegistryMetrics) -> list[Alert]:
        """Evaluate all rules against current metrics.

        Args:
            metrics: Current registry metrics

        Returns:
            List of triggered alerts
        """
        pass

    @abstractmethod
    def acknowledge_alert(self, alert_name: str, acknowledged_by: str) -> bool:
        """Acknowledge an active alert.

        Args:
            alert_name: Name of alert to acknowledge
            acknowledged_by: Who is acknowledging

        Returns:
            True if alert was acknowledged
        """
        pass

    @abstractmethod
    def get_active_alerts(self) -> list[Alert]:
        """Get all active (unacknowledged) alerts.

        Returns:
            List of active alerts
        """
        pass

    @abstractmethod
    def get_alert_history(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[Alert]:
        """Get alert history.

        Args:
            since: Only return alerts after this time
            limit: Maximum number of alerts to return

        Returns:
            List of historical alerts
        """
        pass


class NullAlertManager(AlertManager):
    """No-op alert manager that discards all alerts."""

    def add_rule(self, rule: AlertRule) -> None:
        """No-op implementation."""
        logger.debug(f"NullAlertManager: Ignoring rule addition: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """No-op implementation."""
        return True

    def evaluate(self, metrics: RegistryMetrics) -> list[Alert]:
        """No-op implementation."""
        return []

    def acknowledge_alert(self, alert_name: str, acknowledged_by: str) -> bool:
        """No-op implementation."""
        return True

    def get_active_alerts(self) -> list[Alert]:
        """No-op implementation."""
        return []

    def get_alert_history(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[Alert]:
        """No-op implementation."""
        return []


class DefaultAlertManager(AlertManager):
    """Default alert manager with in-memory storage.

    Stores alerts in memory and provides basic notification hooks.
    """

    def __init__(
        self,
        max_history: int = 1000,
        notification_callback: Callable[[Alert], None] | None = None,
    ) -> None:
        """Initialize alert manager.

        Args:
            max_history: Maximum number of alerts to keep in history
            notification_callback: Optional callback for alert notifications
        """
        self.max_history = max_history
        self.notification_callback = notification_callback
        self._rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._alert_history: list[Alert] = []

        logger.info("Initialized DefaultAlertManager")

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name} (severity={rule.severity.value})")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove an alert rule."""
        if rule_name in self._rules:
            del self._rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
            return True
        return False

    def evaluate(self, metrics: RegistryMetrics) -> list[Alert]:
        """Evaluate all rules and return triggered alerts."""
        triggered = []

        for rule_name, rule in self._rules.items():
            if rule.should_fire(metrics):
                # Build metadata with rule-specific values for message templates
                metadata: dict[str, Any] = {"rule_name": rule_name}

                # Add rule-specific metadata based on rule name
                if rule_name == "high_storage_usage":
                    capacity = 10 * 1024**3  # 10GB default capacity
                    metadata["usage_percent"] = (
                        metrics.storage_usage_bytes / capacity * 100
                    )
                elif rule_name == "multiple_failed_operations":
                    metadata["failed_count"] = sum(
                        metrics.failed_operations_total.values()
                    )
                elif rule_name == "low_cache_hit_rate":
                    total_cache_ops = (
                        metrics.cache_hits_total + metrics.cache_misses_total
                    )
                    metadata["hit_rate"] = (
                        metrics.cache_hits_total / total_cache_ops * 100
                        if total_cache_ops > 0
                        else 0.0
                    )

                alert = rule.create_alert(metadata=metadata)
                triggered.append(alert)

                # Store in active alerts
                self._active_alerts[alert.name] = alert

                # Add to history
                self._alert_history.append(alert)
                if len(self._alert_history) > self.max_history:
                    self._alert_history = self._alert_history[-self.max_history :]

                # Notify
                if self.notification_callback:
                    try:
                        self.notification_callback(alert)
                    except Exception as e:
                        logger.error(f"Error in notification callback: {e}")

                logger.warning(
                    f"Alert triggered: {alert.name} (severity={alert.severity.value}) - {alert.message}"
                )

        return triggered

    def acknowledge_alert(self, alert_name: str, acknowledged_by: str) -> bool:
        """Acknowledge an active alert."""
        if alert_name in self._active_alerts:
            alert = self._active_alerts[alert_name]
            alert.acknowledge(acknowledged_by)

            # Remove from active alerts
            del self._active_alerts[alert_name]

            logger.info(f"Alert acknowledged: {alert_name} by {acknowledged_by}")
            return True
        return False

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts."""
        return list(self._active_alerts.values())

    def get_alert_history(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[Alert]:
        """Get alert history."""
        history = self._alert_history

        if since:
            history = [a for a in history if a.timestamp >= since]

        return history[-limit:]

    def silence_alert(self, alert_name: str, duration_seconds: int) -> None:
        """Temporarily silence an alert rule.

        Args:
            alert_name: Name of alert to silence
            duration_seconds: Duration to silence for
        """
        if alert_name in self._rules:
            rule = self._rules[alert_name]
            rule.enabled = False

            # Schedule re-enable (simplified - in production use proper scheduler)
            logger.info(
                f"Silenced alert {alert_name} for {duration_seconds}s "
                "(Note: auto-unsilence requires external scheduler in production)"
            )

    def export_alertmanager_alerts(self) -> list[dict[str, Any]]:
        """Export active alerts in Alertmanager format.

        Returns:
            List of alerts in Alertmanager format
        """
        return [
            alert.to_alertmanager_format() for alert in self._active_alerts.values()
        ]


def create_default_alert_rules() -> list[AlertRule]:
    """Create default alert rules for registry monitoring.

    Returns:
        List of standard alert rules
    """
    rules = [
        AlertRule(
            name="high_storage_usage",
            condition=lambda m: m.storage_usage_bytes
            > 0.8 * (10 * 1024**3),  # >80% of 10GB
            severity=AlertSeverity.WARNING,
            message="Storage usage is high: {usage_percent:.1f}% of capacity",
            cooldown_seconds=3600,  # 1 hour
        ),
        AlertRule(
            name="high_retrieval_latency",
            condition=lambda m: (
                m.model_retrieval_latency_seconds
                and len(m.model_retrieval_latency_seconds) > 0
                and sorted(m.model_retrieval_latency_seconds)[
                    int(len(m.model_retrieval_latency_seconds) * 0.95)
                ]
                > 1.0
            ),
            severity=AlertSeverity.WARNING,
            message="P95 retrieval latency exceeds 1 second",
            cooldown_seconds=1800,  # 30 minutes
        ),
        AlertRule(
            name="multiple_failed_operations",
            condition=lambda m: (sum(m.failed_operations_total.values()) > 5),
            severity=AlertSeverity.CRITICAL,
            message="Multiple failed operations detected: {failed_count} failures",
            cooldown_seconds=300,  # 5 minutes
        ),
        AlertRule(
            name="low_cache_hit_rate",
            condition=lambda m: (
                (m.cache_hits_total + m.cache_misses_total) > 10
                and m.cache_hits_total / (m.cache_hits_total + m.cache_misses_total)
                < 0.5
            ),
            severity=AlertSeverity.WARNING,
            message="Cache hit rate is low: {hit_rate:.1f}%",
            cooldown_seconds=1800,  # 30 minutes
        ),
    ]

    return rules
