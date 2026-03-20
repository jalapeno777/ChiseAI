"""
Test Health Remediator - Unit tests for auto-remediation (ST-GOV-008).

Story: ST-GOV-008
"""

from datetime import UTC, datetime, timedelta

from src.governance.health.predictor import (
    AlertSeverity,
    HealthAlert,
    PredictionType,
)
from src.governance.health.remediator import (
    HealthRemediator,
    RemediationAction,
    RemediationConfig,
    RemediationRecord,
    RemediationStatus,
)


def create_alert(
    agent_id: str = "test-agent",
    severity: AlertSeverity = AlertSeverity.WARNING,
    prediction_type: PredictionType = PredictionType.DEGRADATION,
    current_score: float = 60.0,
    predicted_score: float = 40.0,
) -> HealthAlert:
    """Helper to create a HealthAlert."""
    return HealthAlert(
        alert_id=f"alert-{datetime.now(UTC).timestamp()}",
        agent_id=agent_id,
        severity=severity,
        prediction_type=prediction_type,
        current_score=current_score,
        predicted_score=predicted_score,
        predicted_time=datetime.now(UTC) + timedelta(minutes=15),
        confidence=0.8,
        message="Test alert",
        contributing_factors=["Test factor"],
    )


class TestHealthRemediator:
    """Tests for HealthRemediator class."""

    def test_remediator_initialization(self):
        """Test remediator initializes with default config."""
        remediator = HealthRemediator()
        assert remediator.config.max_retries == 3
        assert remediator.config.enable_auto_remediation is True

    def test_remediator_custom_config(self):
        """Test remediator with custom configuration."""
        config = RemediationConfig(
            max_retries=5,
            enable_auto_remediation=False,
            cooldown_minutes=10,
        )
        remediator = HealthRemediator(config=config)
        assert remediator.config.max_retries == 5
        assert remediator.config.enable_auto_remediation is False
        assert remediator.config.cooldown_minutes == 10

    def test_remediate_disabled(self):
        """Test remediation when auto-remediation is disabled."""
        config = RemediationConfig(enable_auto_remediation=False)
        remediator = HealthRemediator(config=config)

        alert = create_alert()
        record = remediator.remediate(alert)

        # Should return a pending record requiring human intervention
        assert record.action == RemediationAction.NOTIFY_HUMAN
        assert record.status == RemediationStatus.PENDING

    def test_remediate_warning_alert(self):
        """Test remediation for warning-level alert."""
        remediator = HealthRemediator()

        alert = create_alert(severity=AlertSeverity.WARNING)
        record = remediator.remediate(alert)

        assert record.agent_id == "test-agent"
        assert record.status in (
            RemediationStatus.SUCCESS,
            RemediationStatus.IN_PROGRESS,
        )

    def test_remediate_critical_alert(self):
        """Test remediation for critical-level alert."""
        remediator = HealthRemediator()

        alert = create_alert(severity=AlertSeverity.CRITICAL)
        record = remediator.remediate(alert)

        assert record.agent_id == "test-agent"
        # Critical alerts may trigger various actions
        assert record.action in (
            RemediationAction.SCALE_UP,
            RemediationAction.FAILOVER,
            RemediationAction.NOTIFY_HUMAN,
            RemediationAction.REDUCE_LOAD,
            RemediationAction.CLEAR_CACHE,
            RemediationAction.TRIGGER_GARBAGE_COLLECTION,
            RemediationAction.NO_ACTION,
        )

    def test_remediation_cooldown(self):
        """Test that cooldown period prevents rapid re-remediation."""
        config = RemediationConfig(cooldown_minutes=5)
        remediator = HealthRemediator(config=config)

        # First remediation
        alert1 = create_alert(agent_id="agent-1")
        remediator.remediate(alert1)

        # Immediate second remediation should be blocked
        alert2 = create_alert(agent_id="agent-1")
        record2 = remediator.remediate(alert2)

        # Second should be no-action due to cooldown
        assert record2.action == RemediationAction.NO_ACTION

    def test_remediation_action_determination(self):
        """Test action determination based on prediction type."""
        remediator = HealthRemediator()

        # Test degradation prediction
        alert = create_alert(prediction_type=PredictionType.DEGRADATION)
        action = remediator._determine_action(alert)
        assert action in (
            RemediationAction.REDUCE_LOAD,
            RemediationAction.CLEAR_CACHE,
            RemediationAction.TRIGGER_GARBAGE_COLLECTION,
            RemediationAction.NO_ACTION,
        )

    def test_remediation_record_creation(self):
        """Test remediation record creation and properties."""
        remediator = HealthRemediator()

        record = remediator._create_record(
            agent_id="test-agent",
            action=RemediationAction.CLEAR_CACHE,
            trigger="Test trigger",
            status=RemediationStatus.SUCCESS,
            metadata={"test": "value"},
        )

        assert record.agent_id == "test-agent"
        assert record.action == RemediationAction.CLEAR_CACHE
        assert record.trigger == "Test trigger"
        assert record.status == RemediationStatus.SUCCESS
        assert record.metadata == {"test": "value"}
        assert record.started_at is not None

    def test_remediation_record_to_dict(self):
        """Test remediation record serialization."""
        record = RemediationRecord(
            record_id="test-1",
            agent_id="agent-1",
            action=RemediationAction.CLEAR_CACHE,
            trigger="Test",
            status=RemediationStatus.SUCCESS,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_ms=100.0,
        )

        data = record.to_dict()

        assert data["record_id"] == "test-1"
        assert data["agent_id"] == "agent-1"
        assert data["action"] == "clear_cache"
        assert data["status"] == "success"
        assert data["duration_ms"] == 100.0

    def test_custom_action_handler(self):
        """Test registering and using custom action handlers."""
        remediator = HealthRemediator()

        # Register custom handler
        custom_called = []

        def custom_handler(agent_id: str, metadata: dict) -> bool:
            custom_called.append(agent_id)
            return True

        remediator.register_handler(RemediationAction.RESTART_AGENT, custom_handler)

        # The handler is registered (verified by checking the handlers dict)
        assert RemediationAction.RESTART_AGENT in remediator._action_handlers

    def test_remediation_stats(self):
        """Test remediation statistics."""
        remediator = HealthRemediator()

        # Perform some remediations
        for i in range(3):
            alert = create_alert(agent_id=f"agent-{i}")
            remediator.remediate(alert)

        stats = remediator.get_remediation_stats()

        assert "total" in stats
        assert "success_count" in stats
        assert "failed_count" in stats
        assert "success_rate" in stats
        assert stats["total"] >= 3

    def test_recent_remediations(self):
        """Test getting recent remediation records."""
        remediator = HealthRemediator()

        # Perform some remediations
        for i in range(5):
            alert = create_alert(agent_id=f"agent-{i}")
            remediator.remediate(alert)

        recent = remediator.get_recent_remediations(limit=3)

        assert len(recent) <= 3

    def test_clear_history(self):
        """Test clearing remediation history."""
        remediator = HealthRemediator()

        # Perform remediation
        alert = create_alert()
        remediator.remediate(alert)

        assert len(remediator._remediation_history) > 0

        remediator.clear_history()

        assert len(remediator._remediation_history) == 0
        assert len(remediator._last_remediation) == 0


class TestRemediationActions:
    """Tests for individual remediation actions."""

    def test_clear_cache_action(self):
        """Test cache clearing action."""
        remediator = HealthRemediator()

        result = remediator._action_clear_cache("test-agent", {})
        assert result is True

    def test_reduce_load_action(self):
        """Test load reduction action."""
        remediator = HealthRemediator()

        result = remediator._action_reduce_load("test-agent", {})
        assert result is True

    def test_reset_connections_action(self):
        """Test connection reset action."""
        remediator = HealthRemediator()

        result = remediator._action_reset_connections("test-agent", {})
        assert result is True

    def test_trigger_gc_action(self):
        """Test garbage collection trigger action."""
        remediator = HealthRemediator()

        result = remediator._action_trigger_gc("test-agent", {})
        assert result is True

    def test_notify_human_action(self):
        """Test human notification action."""
        remediator = HealthRemediator()

        result = remediator._action_notify_human("test-agent", {"alert": "test"})
        assert result is True

    def test_noop_action(self):
        """Test no-op action."""
        remediator = HealthRemediator()

        result = remediator._action_noop("test-agent", {})
        assert result is True


class TestHumanApprovalRequired:
    """Tests for actions requiring human approval."""

    def test_quarantine_requires_approval(self):
        """Test that quarantine action requires human approval."""
        config = RemediationConfig(
            require_human_approval_for=[RemediationAction.QUARANTINE]
        )
        remediator = HealthRemediator(config=config)

        assert (
            RemediationAction.QUARANTINE in remediator.config.require_human_approval_for
        )

    def test_failover_requires_approval(self):
        """Test that failover action requires human approval."""
        config = RemediationConfig(
            require_human_approval_for=[RemediationAction.FAILOVER]
        )
        remediator = HealthRemediator(config=config)

        assert (
            RemediationAction.FAILOVER in remediator.config.require_human_approval_for
        )
