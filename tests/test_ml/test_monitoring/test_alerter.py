"""Tests for training alerter.

This module tests the TrainingAlerter class for managing training-related
alerts, notifications, and alert rules.

Acceptance Criteria:
- Training failure alerts
- Validation gate failure alerts
- Degradation detection alerts
- SLA breach alerts
- Alert acknowledgment and resolution
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from ml.monitoring.alerter import (
    TrainingAlerter,
    Alert,
    AlertRule,
    AlertSeverity,
    AlertType,
    LoggingNotificationChannel,
    DiscordNotificationChannel,
)

logger = logging.getLogger(__name__)


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message="Training failed",
            source="train_001",
            metadata={"error": "Out of memory"},
        )

        assert alert.alert_id == "alert_001"
        assert alert.alert_type == AlertType.TRAINING_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.message == "Training failed"
        assert alert.source == "train_001"
        assert not alert.acknowledged
        assert not alert.resolved

    def test_alert_acknowledge(self):
        """Test acknowledging an alert."""
        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message="Training failed",
            source="train_001",
        )

        alert.acknowledge("admin")

        assert alert.acknowledged is True
        assert alert.acknowledged_by == "admin"
        assert alert.acknowledged_at is not None

    def test_alert_resolve(self):
        """Test resolving an alert."""
        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message="Training failed",
            source="train_001",
        )

        alert.resolve()

        assert alert.resolved is True
        assert alert.resolved_at is not None

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message="Training failed",
            source="train_001",
            metadata={"error": "OOM"},
        )

        result = alert.to_dict()

        assert result["alert_id"] == "alert_001"
        assert result["alert_type"] == "training_failure"
        assert result["severity"] == "critical"
        assert result["acknowledged"] is False


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_rule_creation(self):
        """Test creating an alert rule."""
        rule = AlertRule(
            name="high_failure_rate",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: m.get("failure_rate", 0) > 0.2,
            severity=AlertSeverity.WARNING,
            message="Failure rate is high",
            cooldown_seconds=300,
        )

        assert rule.name == "high_failure_rate"
        assert rule.alert_type == AlertType.HIGH_FAILURE_RATE
        assert rule.cooldown_seconds == 300
        assert rule.enabled is True

    def test_rule_should_fire(self):
        """Test rule firing condition."""
        rule = AlertRule(
            name="test_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: m.get("value", 0) > 10,
            severity=AlertSeverity.WARNING,
            message="Value too high",
        )

        assert rule.should_fire({"value": 15}) is True
        assert rule.should_fire({"value": 5}) is False

    def test_rule_disabled(self):
        """Test that disabled rules don't fire."""
        rule = AlertRule(
            name="disabled_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Always fires",
            enabled=False,
        )

        assert rule.should_fire({}) is False

    def test_rule_cooldown(self):
        """Test rule cooldown period."""
        rule = AlertRule(
            name="cooldown_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Test",
            cooldown_seconds=60,
        )

        # First fire should succeed
        assert rule.should_fire({}) is True

        # Create alert (updates _last_triggered)
        rule.create_alert("source")

        # Second fire should fail (in cooldown)
        assert rule.should_fire({}) is False

    def test_rule_condition_exception(self):
        """Test that condition exceptions are handled."""
        rule = AlertRule(
            name="error_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: 1 / 0,  # Will raise ZeroDivisionError
            severity=AlertSeverity.WARNING,
            message="Error",
        )

        # Should not raise, should return False
        assert rule.should_fire({}) is False

    def test_rule_create_alert(self):
        """Test creating alert from rule."""
        rule = AlertRule(
            name="test_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: True,
            severity=AlertSeverity.CRITICAL,
            message="Alert: {value}",
        )

        alert = rule.create_alert("source", metadata={"value": "test"})

        assert alert.alert_type == AlertType.HIGH_FAILURE_RATE
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.message == "Alert: test"
        assert rule._last_triggered is not None


class TestNotificationChannels:
    """Tests for notification channels."""

    def test_logging_channel(self):
        """Test logging notification channel."""
        channel = LoggingNotificationChannel()

        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.CRITICAL,
            message="Test alert",
            source="test",
        )

        result = channel.send(alert)
        assert result is True

    def test_discord_channel(self):
        """Test Discord notification channel."""
        channel = DiscordNotificationChannel(
            webhook_url="https://discord.com/api/webhooks/test",
            channel_id="123456",
        )

        alert = Alert(
            alert_id="alert_001",
            alert_type=AlertType.TRAINING_FAILURE,
            severity=AlertSeverity.WARNING,
            message="Test alert",
            source="test",
        )

        result = channel.send(alert)
        assert result is True


class TestTrainingAlerter:
    """Tests for TrainingAlerter."""

    def test_initialization(self):
        """Test alerter initialization."""
        alerter = TrainingAlerter()

        assert alerter.get_active_alerts() == []
        assert alerter.get_alert_history() == []

    def test_initialization_with_channels(self):
        """Test alerter initialization with channels."""
        channels = [LoggingNotificationChannel()]
        alerter = TrainingAlerter(notification_channels=channels)

        assert alerter._notification_channels == channels

    def test_add_and_remove_rule(self):
        """Test adding and removing alert rules."""
        alerter = TrainingAlerter()

        rule = AlertRule(
            name="custom_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: True,
            severity=AlertSeverity.WARNING,
            message="Custom",
        )

        alerter.add_rule(rule)
        assert "custom_rule" in alerter._rules

        result = alerter.remove_rule("custom_rule")
        assert result is True
        assert "custom_rule" not in alerter._rules

    def test_remove_nonexistent_rule(self):
        """Test removing a non-existent rule."""
        alerter = TrainingAlerter()

        result = alerter.remove_rule("nonexistent")
        assert result is False

    def test_alert_training_failure(self):
        """Test training failure alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_training_failure(
            run_id="train_001",
            model_name="signal_predictor",
            error="Out of memory",
            error_type="runtime_error",
        )

        assert alert.alert_type == AlertType.TRAINING_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert "train_001" in alert.message
        assert "Out of memory" in alert.message

        # Should be in active alerts
        active = alerter.get_active_alerts()
        assert len(active) == 1

    def test_alert_validation_gate_failure(self):
        """Test validation gate failure alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_validation_gate_failure(
            model_name="signal_predictor",
            version="1.0.0",
            gate_name="accuracy_gate",
            failed_metrics={"accuracy": 0.55},
        )

        assert alert.alert_type == AlertType.VALIDATION_GATE_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert "accuracy_gate" in alert.message

    def test_alert_degradation(self):
        """Test degradation alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_degradation(
            model_name="signal_predictor",
            version="1.0.0",
            metric_name="accuracy",
            degradation_percentage=15.0,
            baseline_value=0.65,
            current_value=0.55,
        )

        assert alert.alert_type == AlertType.DEGRADATION_DETECTED
        assert alert.severity == AlertSeverity.CRITICAL
        assert "15.0%" in alert.message

    def test_alert_sla_breach(self):
        """Test SLA breach alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_sla_breach(
            sla_type="duration",
            actual_value=18000,  # 5 hours
            threshold_value=14400,  # 4 hours
            source="train_001",
        )

        assert alert.alert_type == AlertType.SLA_BREACH
        assert alert.severity == AlertSeverity.WARNING
        assert "duration" in alert.message

    def test_evaluate_rules(self):
        """Test evaluating alert rules."""
        alerter = TrainingAlerter()

        # Add a custom rule
        rule = AlertRule(
            name="test_rule",
            alert_type=AlertType.HIGH_FAILURE_RATE,
            condition=lambda m: m.get("failure_rate", 0) > 0.5,
            severity=AlertSeverity.WARNING,
            message="High failure rate: {failure_rate}",
            cooldown_seconds=0,
        )
        alerter.add_rule(rule)

        # Evaluate with metrics that trigger the rule
        alerts = alerter.evaluate_rules(
            metrics={"failure_rate": 0.6},
            source="test_source",
        )

        assert len(alerts) >= 1
        assert any(a.alert_type == AlertType.HIGH_FAILURE_RATE for a in alerts)

    def test_evaluate_rules_no_trigger(self):
        """Test evaluating rules that don't trigger."""
        alerter = TrainingAlerter()

        # Evaluate with metrics that don't trigger any rules
        alerts = alerter.evaluate_rules(
            metrics={"failure_rate": 0.1},  # Below threshold
            source="test_source",
        )

        # Should not trigger high_failure_rate rule
        assert not any(a.alert_type == AlertType.HIGH_FAILURE_RATE for a in alerts)

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_training_failure(
            run_id="train_001",
            model_name="signal_predictor",
            error="Error",
        )

        result = alerter.acknowledge_alert(alert.alert_id, "admin")

        assert result is True
        assert alert.acknowledged is True

    def test_acknowledge_nonexistent_alert(self):
        """Test acknowledging non-existent alert."""
        alerter = TrainingAlerter()

        result = alerter.acknowledge_alert("nonexistent", "admin")
        assert result is False

    def test_resolve_alert(self):
        """Test resolving an alert."""
        alerter = TrainingAlerter()

        alert = alerter.alert_training_failure(
            run_id="train_001",
            model_name="signal_predictor",
            error="Error",
        )

        result = alerter.resolve_alert(alert.alert_id)

        assert result is True
        assert alert.resolved is True

        # Should no longer be in active alerts
        active = alerter.get_active_alerts()
        assert len(active) == 0

    def test_resolve_nonexistent_alert(self):
        """Test resolving non-existent alert."""
        alerter = TrainingAlerter()

        result = alerter.resolve_alert("nonexistent")
        assert result is False

    def test_get_active_alerts_filtering(self):
        """Test getting active alerts with filtering."""
        alerter = TrainingAlerter()

        # Create alerts of different types
        alerter.alert_training_failure("t1", "model", "error")
        alerter.alert_sla_breach("duration", 100, 50, "t2")
        alerter.alert_degradation("model", "1.0", "acc", 15.0)

        # Filter by type
        training_alerts = alerter.get_active_alerts(
            alert_type=AlertType.TRAINING_FAILURE
        )
        assert len(training_alerts) == 1

        # Filter by severity
        critical_alerts = alerter.get_active_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical_alerts) == 2  # training_failure and degradation

    def test_get_alert_history(self):
        """Test getting alert history."""
        alerter = TrainingAlerter()

        # Create and resolve some alerts
        alert1 = alerter.alert_training_failure("t1", "model", "error")
        alerter.resolve_alert(alert1.alert_id)

        alert2 = alerter.alert_training_failure("t2", "model", "error")
        alerter.resolve_alert(alert2.alert_id)

        history = alerter.get_alert_history()
        assert len(history) == 2

    def test_get_alert_history_with_since(self):
        """Test getting alert history with time filter."""
        alerter = TrainingAlerter()

        # Create an alert
        alert = alerter.alert_training_failure("t1", "model", "error")
        alerter.resolve_alert(alert.alert_id)

        # Get history from 1 hour ago
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        history = alerter.get_alert_history(since=since)
        assert len(history) == 1

        # Get history from 1 hour in the future
        since = datetime.now(timezone.utc) + timedelta(hours=1)
        history = alerter.get_alert_history(since=since)
        assert len(history) == 0

    def test_get_alert_summary(self):
        """Test getting alert summary."""
        alerter = TrainingAlerter()

        # Create alerts
        alerter.alert_training_failure("t1", "model", "error")
        alerter.alert_training_failure("t2", "model", "error")
        alerter.alert_sla_breach("duration", 100, 50, "t3")

        # Acknowledge one
        active = alerter.get_active_alerts()
        alerter.acknowledge_alert(active[0].alert_id, "admin")

        summary = alerter.get_alert_summary(days=7)

        assert summary["total_alerts"] == 3
        assert summary["active_alerts"] == 3
        assert summary["acknowledged"] == 1
        assert summary["unacknowledged"] == 2
        assert summary["by_type"]["training_failure"] == 2

    def test_clear_history(self):
        """Test clearing alert history."""
        alerter = TrainingAlerter()

        alert = alerter.alert_training_failure("t1", "model", "error")
        alerter.resolve_alert(alert.alert_id)

        assert len(alerter.get_alert_history()) == 1

        alerter.clear_history()

        assert len(alerter.get_alert_history()) == 0
        assert len(alerter.get_active_alerts()) == 0

    def test_default_rules_present(self):
        """Test that default rules are added on initialization."""
        alerter = TrainingAlerter()

        # Should have default rules
        assert "high_failure_rate" in alerter._rules
        assert "low_data_quality" in alerter._rules
        assert "sla_breach_duration" in alerter._rules
        assert "sla_breach_data_freshness" in alerter._rules


class TestAlertEnums:
    """Tests for alert enums."""

    def test_alert_severity_values(self):
        """Test alert severity values."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_alert_type_values(self):
        """Test alert type values."""
        assert AlertType.TRAINING_FAILURE.value == "training_failure"
        assert AlertType.VALIDATION_GATE_FAILURE.value == "validation_gate_failure"
        assert AlertType.DEGRADATION_DETECTED.value == "degradation_detected"
        assert AlertType.SLA_BREACH.value == "sla_breach"
        assert AlertType.HIGH_FAILURE_RATE.value == "high_failure_rate"
        assert AlertType.DATA_QUALITY_LOW.value == "data_quality_low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
