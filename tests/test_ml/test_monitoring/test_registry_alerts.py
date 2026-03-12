"""Tests for Model Registry alerting system.

This module tests the alert management system for the Model Registry,
including alert rules, alert evaluation, and notification mechanisms.

Acceptance Criteria:
- Alerts for: high storage (>80%), high latency (>1s), failed operations (>5 in 5min), integrity failures
- Configurable alert rules with cooldown periods
- Alert acknowledgment and history tracking
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from ml.monitoring.registry_metrics import RegistryMetrics
from ml.monitoring.registry_alerts import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    DefaultAlertManager,
    NullAlertManager,
    create_default_alert_rules,
)

logger = logging.getLogger(__name__)


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            name="test_alert",
            severity=AlertSeverity.WARNING,
            message="Test alert message",
            metadata={"key": "value"},
        )

        assert alert.name == "test_alert"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.message == "Test alert message"
        assert alert.metadata == {"key": "value"}
        assert not alert.acknowledged
        assert alert.acknowledged_at is None
        assert alert.acknowledged_by is None
        assert isinstance(alert.timestamp, datetime)

    def test_alert_acknowledge(self):
        """Test acknowledging an alert."""
        alert = Alert(
            name="test_alert",
            severity=AlertSeverity.WARNING,
            message="Test message",
        )

        alert.acknowledge("test_user")

        assert alert.acknowledged
        assert alert.acknowledged_by == "test_user"
        assert alert.acknowledged_at is not None

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            name="test_alert",
            severity=AlertSeverity.CRITICAL,
            message="Critical issue",
            metadata={"model": "test_model"},
        )

        result = alert.to_dict()

        assert result["name"] == "test_alert"
        assert result["severity"] == "critical"
        assert result["message"] == "Critical issue"
        assert result["metadata"] == {"model": "test_model"}
        assert result["acknowledged"] is False
        assert "timestamp" in result

    def test_alert_to_alertmanager_format(self):
        """Test converting alert to Alertmanager format."""
        alert = Alert(
            name="high_latency",
            severity=AlertSeverity.WARNING,
            message="P95 latency exceeds threshold",
            metadata={"labels": {"model": "test"}, "annotations": {"runbook": "url"}},
        )

        result = alert.to_alertmanager_format()

        assert result["labels"]["alertname"] == "high_latency"
        assert result["labels"]["severity"] == "warning"
        assert result["labels"]["model"] == "test"
        assert result["annotations"]["message"] == "P95 latency exceeds threshold"
        assert result["annotations"]["runbook"] == "url"
        assert "startsAt" in result
        assert "endsAt" in result


class TestAlertRule:
    """Tests for AlertRule."""

    def test_alert_rule_creation(self):
        """Test creating an alert rule."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test rule triggered",
            cooldown_seconds=300,
        )

        assert rule.name == "test_rule"
        assert rule.severity == AlertSeverity.WARNING
        assert rule.message == "Test rule triggered"
        assert rule.cooldown_seconds == 300
        assert rule.enabled

    def test_alert_rule_should_fire(self):
        """Test alert rule firing logic."""
        rule = AlertRule(
            name="always_fire",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Always fires",
        )

        metrics = RegistryMetrics()
        assert rule.should_fire(metrics)

    def test_alert_rule_disabled(self):
        """Test that disabled rules don't fire."""
        rule = AlertRule(
            name="disabled_rule",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Disabled",
            enabled=False,
        )

        metrics = RegistryMetrics()
        assert not rule.should_fire(metrics)

    def test_alert_rule_cooldown(self):
        """Test alert rule cooldown period."""
        rule = AlertRule(
            name="cooldown_rule",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Cooldown test",
            cooldown_seconds=60,
        )

        metrics = RegistryMetrics()

        # First fire should succeed
        assert rule.should_fire(metrics)

        # Create alert (updates _last_triggered)
        rule.create_alert()

        # Second fire should fail (in cooldown)
        assert not rule.should_fire(metrics)

    def test_alert_rule_condition_exception(self):
        """Test that condition exceptions are handled."""
        rule = AlertRule(
            name="error_rule",
            condition=lambda m: 1 / 0,  # Will raise ZeroDivisionError
            severity=AlertSeverity.WARNING,
            message="Error in condition",
        )

        metrics = RegistryMetrics()
        # Should not raise, should return False
        assert not rule.should_fire(metrics)

    def test_alert_rule_create_alert(self):
        """Test creating alert from rule."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: True,
            severity=AlertSeverity.CRITICAL,
            message="Alert: {value}",
        )

        alert = rule.create_alert(metadata={"value": "test_value"})

        assert alert.name == "test_rule"
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.message == "Alert: test_value"
        assert rule._last_triggered is not None


class TestNullAlertManager:
    """Tests for NullAlertManager."""

    def test_null_alert_manager(self):
        """Test that null alert manager does nothing."""
        manager = NullAlertManager()

        rule = AlertRule(
            name="test",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
        )

        manager.add_rule(rule)
        assert manager.remove_rule("test")
        assert manager.evaluate(RegistryMetrics()) == []
        assert manager.acknowledge_alert("test", "user")
        assert manager.get_active_alerts() == []
        assert manager.get_alert_history() == []


class TestDefaultAlertManager:
    """Tests for DefaultAlertManager."""

    def test_add_and_remove_rules(self):
        """Test adding and removing alert rules."""
        manager = DefaultAlertManager()

        rule = AlertRule(
            name="test_rule",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
        )

        manager.add_rule(rule)
        assert "test_rule" in manager._rules

        assert manager.remove_rule("test_rule")
        assert "test_rule" not in manager._rules

        # Remove non-existent rule
        assert not manager.remove_rule("non_existent")

    def test_evaluate_triggers_alerts(self):
        """Test that evaluate triggers matching alerts."""
        manager = DefaultAlertManager()

        # Add a rule that always fires
        rule = AlertRule(
            name="always_fire",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Always fires",
        )
        manager.add_rule(rule)

        alerts = manager.evaluate(RegistryMetrics())

        assert len(alerts) == 1
        assert alerts[0].name == "always_fire"

    def test_evaluate_no_triggers(self):
        """Test that evaluate doesn't trigger non-matching alerts."""
        manager = DefaultAlertManager()

        # Add a rule that never fires
        rule = AlertRule(
            name="never_fire",
            condition=lambda m: False,
            severity=AlertSeverity.WARNING,
            message="Never fires",
        )
        manager.add_rule(rule)

        alerts = manager.evaluate(RegistryMetrics())

        assert len(alerts) == 0

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        manager = DefaultAlertManager()

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
        )
        manager.add_rule(rule)

        # Trigger alert
        manager.evaluate(RegistryMetrics())

        # Acknowledge
        assert manager.acknowledge_alert("test_alert", "test_user")

        # Check it's removed from active
        active = manager.get_active_alerts()
        assert len(active) == 0

    def test_get_alert_history(self):
        """Test getting alert history."""
        manager = DefaultAlertManager()

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
            cooldown_seconds=0,  # No cooldown for testing
        )
        manager.add_rule(rule)

        # Trigger multiple alerts
        manager.evaluate(RegistryMetrics())
        manager.evaluate(RegistryMetrics())

        history = manager.get_alert_history()
        assert len(history) >= 2

    def test_get_alert_history_with_since(self):
        """Test getting alert history with time filter."""
        manager = DefaultAlertManager()

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
            cooldown_seconds=0,
        )
        manager.add_rule(rule)

        # Trigger alert
        manager.evaluate(RegistryMetrics())

        # Get history from 1 hour ago
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        history = manager.get_alert_history(since=since)
        assert len(history) >= 1

        # Get history from 1 hour in the future (should be empty)
        since = datetime.now(timezone.utc) + timedelta(hours=1)
        history = manager.get_alert_history(since=since)
        assert len(history) == 0

    def test_notification_callback(self):
        """Test notification callback is called."""
        notifications = []

        def callback(alert):
            notifications.append(alert)

        manager = DefaultAlertManager(notification_callback=callback)

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
        )
        manager.add_rule(rule)

        manager.evaluate(RegistryMetrics())

        assert len(notifications) == 1
        assert notifications[0].name == "test_alert"

    def test_max_history_limit(self):
        """Test that history is limited to max_history."""
        manager = DefaultAlertManager(max_history=5)

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
            cooldown_seconds=0,
        )
        manager.add_rule(rule)

        # Trigger 10 alerts
        for _ in range(10):
            manager.evaluate(RegistryMetrics())

        # History should be limited to 5
        assert len(manager._alert_history) <= 5

    def test_export_alertmanager_alerts(self):
        """Test exporting alerts in Alertmanager format."""
        manager = DefaultAlertManager()

        rule = AlertRule(
            name="test_alert",
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
        )
        manager.add_rule(rule)

        manager.evaluate(RegistryMetrics())

        exported = manager.export_alertmanager_alerts()
        assert len(exported) >= 1
        assert "labels" in exported[0]
        assert "annotations" in exported[0]


class TestDefaultAlertRules:
    """Tests for default alert rules."""

    def test_create_default_alert_rules(self):
        """Test that default rules are created."""
        rules = create_default_alert_rules()

        assert len(rules) == 4

        rule_names = [r.name for r in rules]
        assert "high_storage_usage" in rule_names
        assert "high_retrieval_latency" in rule_names
        assert "multiple_failed_operations" in rule_names
        assert "low_cache_hit_rate" in rule_names

    def test_high_storage_usage_rule(self):
        """Test high storage usage alert rule."""
        rules = create_default_alert_rules()
        storage_rule = next(r for r in rules if r.name == "high_storage_usage")

        # Below threshold
        metrics = RegistryMetrics()
        metrics.storage_usage_bytes = 5 * 1024**3  # 5GB (50% of 10GB)
        assert not storage_rule.condition(metrics)

        # Above threshold
        metrics.storage_usage_bytes = 9 * 1024**3  # 9GB (90% of 10GB)
        assert storage_rule.condition(metrics)

    def test_high_retrieval_latency_rule(self):
        """Test high retrieval latency alert rule."""
        rules = create_default_alert_rules()
        latency_rule = next(r for r in rules if r.name == "high_retrieval_latency")

        # Below threshold
        metrics = RegistryMetrics()
        metrics.model_retrieval_latency_seconds = [0.1, 0.2, 0.3, 0.4, 0.5]
        assert not latency_rule.condition(metrics)

        # Above threshold (P95 > 1.0s)
        metrics.model_retrieval_latency_seconds = [0.1, 0.2, 0.5, 1.5, 2.0, 3.0]
        assert latency_rule.condition(metrics)

    def test_multiple_failed_operations_rule(self):
        """Test multiple failed operations alert rule."""
        rules = create_default_alert_rules()
        failures_rule = next(r for r in rules if r.name == "multiple_failed_operations")

        # Below threshold
        metrics = RegistryMetrics()
        metrics.failed_operations_total = {"register:ValueError": 2}
        assert not failures_rule.condition(metrics)

        # Above threshold
        metrics.failed_operations_total = {
            "register:ValueError": 2,
            "retrieve:KeyError": 2,
            "rollback:RuntimeError": 2,
        }
        assert failures_rule.condition(metrics)

    def test_low_cache_hit_rate_rule(self):
        """Test low cache hit rate alert rule."""
        rules = create_default_alert_rules()
        cache_rule = next(r for r in rules if r.name == "low_cache_hit_rate")

        # Good hit rate
        metrics = RegistryMetrics()
        metrics.cache_hits_total = 80
        metrics.cache_misses_total = 20
        assert not cache_rule.condition(metrics)

        # Low hit rate
        metrics.cache_hits_total = 30
        metrics.cache_misses_total = 70
        assert cache_rule.condition(metrics)


class TestAlertIntegration:
    """Integration tests for alerting system."""

    def test_full_alert_workflow(self):
        """Test complete alert workflow."""
        manager = DefaultAlertManager()

        # Add all default rules
        for rule in create_default_alert_rules():
            manager.add_rule(rule)

        # Create metrics that trigger alerts
        metrics = RegistryMetrics()
        metrics.storage_usage_bytes = 9 * 1024**3  # High storage
        metrics.model_retrieval_latency_seconds = [1.5, 2.0, 3.0]  # High latency
        metrics.failed_operations_total = {
            "error1": 3,
            "error2": 3,
        }  # Multiple failures
        metrics.cache_hits_total = 20
        metrics.cache_misses_total = 80  # Low hit rate

        # Evaluate
        alerts = manager.evaluate(metrics)

        # Should have multiple alerts
        assert len(alerts) >= 1

        # Check active alerts
        active = manager.get_active_alerts()
        assert len(active) >= 1

        # Acknowledge all alerts
        for alert in active:
            manager.acknowledge_alert(alert.name, "admin")

        # Should have no active alerts now
        assert len(manager.get_active_alerts()) == 0

        # Check history
        history = manager.get_alert_history()
        assert len(history) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
