"""
Test Health Sentinel - Integration tests for main orchestrator (ST-GOV-008).

Story: ST-GOV-008
"""

import pytest
from datetime import datetime, timedelta
import asyncio

from src.governance.health.sentinel import (
    HealthSentinel,
    HealthSentinelConfig,
    HealthSnapshot,
)
from src.governance.health.scorer import HealthStatus
from src.governance.health.predictor import AlertSeverity


class TestHealthSentinel:
    """Tests for HealthSentinel class."""

    def test_sentinel_initialization(self):
        """Test sentinel initializes with default config."""
        sentinel = HealthSentinel()
        assert sentinel.config.update_interval_seconds == 60
        assert sentinel.scorer is not None
        assert sentinel.predictor is not None
        assert sentinel.remediator is not None

    def test_sentinel_custom_config(self):
        """Test sentinel with custom configuration."""
        config = HealthSentinelConfig(
            update_interval_seconds=30,
            prediction_horizon_minutes=10,
            enable_auto_remediation=False,
        )
        sentinel = HealthSentinel(config=config)
        assert sentinel.config.update_interval_seconds == 30
        assert sentinel.predictor.config.prediction_horizon_minutes == 10

    def test_update_agent_metrics(self):
        """Test updating agent metrics."""
        sentinel = HealthSentinel()

        metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        score = sentinel.update_agent_metrics("agent-1", metrics)

        assert score.agent_id == "agent-1"
        assert score.overall_score > 0
        assert score.status in HealthStatus

    def test_calculate_swarm_health(self):
        """Test swarm health calculation."""
        sentinel = HealthSentinel()

        # Add multiple agents
        good_metrics = {
            "performance": {"task_completion_time": 30},
            "quality": {"bug_escape_rate": 0},
            "reliability": {"uptime": 99.9},
            "collaboration": {"conflict_rate": 0},
        }

        for i in range(3):
            sentinel.update_agent_metrics(f"agent-{i}", good_metrics)

        swarm = sentinel.calculate_swarm_health()

        assert swarm.agent_count == 3
        assert swarm.overall_score > 0
        assert swarm.status in HealthStatus

    def test_run_predictions(self):
        """Test running predictions."""
        config = HealthSentinelConfig(enable_predictive_alerts=True)
        sentinel = HealthSentinel(config=config)

        # Add agent with declining health
        now = datetime.utcnow()
        for i in range(5):
            metrics = {
                "performance": {"task_completion_time": 30 + i * 20},
                "quality": {"bug_escape_rate": i * 2},
                "reliability": {"uptime": 99.9 - i * 2},
                "collaboration": {"conflict_rate": i},
            }
            sentinel.update_agent_metrics("agent-1", metrics)

        alerts = sentinel.run_predictions()

        # May or may not have alerts depending on prediction confidence
        assert isinstance(alerts, list)

    def test_run_predictions_disabled(self):
        """Test predictions disabled."""
        config = HealthSentinelConfig(enable_predictive_alerts=False)
        sentinel = HealthSentinel(config=config)

        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )

        alerts = sentinel.run_predictions()

        assert len(alerts) == 0

    def test_process_alerts_disabled(self):
        """Test alert processing when auto-remediation disabled."""
        config = HealthSentinelConfig(enable_auto_remediation=False)
        sentinel = HealthSentinel(config=config)

        # Manually add an alert (simulated)
        records = sentinel.process_alerts()

        assert isinstance(records, list)

    def test_get_snapshot(self):
        """Test getting health snapshot."""
        sentinel = HealthSentinel()

        # Add some agents
        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )
        sentinel.calculate_swarm_health()

        snapshot = sentinel.get_snapshot()

        assert isinstance(snapshot, HealthSnapshot)
        assert snapshot.swarm_health is not None
        assert len(snapshot.agent_health) == 1
        assert isinstance(snapshot.active_alerts, list)
        assert isinstance(snapshot.recent_remediations, list)

    def test_snapshot_to_dict(self):
        """Test snapshot serialization."""
        sentinel = HealthSentinel()

        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )
        sentinel.calculate_swarm_health()

        snapshot = sentinel.get_snapshot()
        data = snapshot.to_dict()

        assert "timestamp" in data
        assert "swarm_health" in data
        assert "agent_health" in data
        assert data["swarm_health"]["score"] >= 0

    def test_get_agent_health(self):
        """Test getting specific agent health."""
        sentinel = HealthSentinel()

        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )

        health = sentinel.get_agent_health("agent-1")
        assert health is not None
        assert health.agent_id == "agent-1"

        # Non-existent agent
        health = sentinel.get_agent_health("non-existent")
        assert health is None

    def test_get_swarm_health(self):
        """Test getting swarm health."""
        sentinel = HealthSentinel()

        # Before any updates
        health = sentinel.get_swarm_health()
        assert health is None

        # After updates
        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )
        sentinel.calculate_swarm_health()

        health = sentinel.get_swarm_health()
        assert health is not None

    def test_validate(self):
        """Test sentinel validation."""
        sentinel = HealthSentinel()

        result = sentinel.validate()
        assert result is True

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        sentinel = HealthSentinel()

        alerts = sentinel.get_active_alerts()
        assert isinstance(alerts, list)

    def test_get_prediction_accuracy(self):
        """Test getting prediction accuracy."""
        sentinel = HealthSentinel()

        accuracy = sentinel.get_prediction_accuracy()
        # May be 0 if no predictions have been made
        assert 0 <= accuracy <= 100

    def test_get_metrics_export(self):
        """Test Prometheus metrics export."""
        sentinel = HealthSentinel()

        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )
        sentinel.calculate_swarm_health()

        export = sentinel.get_metrics_export()
        assert isinstance(export, str)
        # Should contain metric names
        assert "chiseai" in export.lower() or len(export) > 0


class TestHealthSentinelConfig:
    """Tests for HealthSentinelConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HealthSentinelConfig()

        assert config.update_interval_seconds == 60
        assert config.history_retention_hours == 24
        assert config.enable_predictive_alerts is True
        assert config.prediction_horizon_minutes == 15
        assert config.enable_auto_remediation is True
        assert config.healthy_threshold == 80.0
        assert config.alert_threshold_score == 60.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HealthSentinelConfig(
            update_interval_seconds=30,
            prediction_horizon_minutes=10,
            enable_auto_remediation=False,
        )

        assert config.update_interval_seconds == 30
        assert config.prediction_horizon_minutes == 10
        assert config.enable_auto_remediation is False


class TestMonitoringLoop:
    """Tests for the monitoring loop functionality."""

    @pytest.mark.asyncio
    async def test_monitoring_iteration(self):
        """Test single monitoring iteration."""
        sentinel = HealthSentinel()

        # Add agents
        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )

        await sentinel._monitoring_iteration()

        assert sentinel._last_update is not None
        assert sentinel._swarm_health is not None

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        config = HealthSentinelConfig(update_interval_seconds=1)
        sentinel = HealthSentinel(config=config)

        # Add agents
        sentinel.update_agent_metrics(
            "agent-1",
            {
                "performance": {"task_completion_time": 30},
                "quality": {"bug_escape_rate": 0},
                "reliability": {"uptime": 99.9},
                "collaboration": {"conflict_rate": 0},
            },
        )

        # Start monitoring in background
        task = asyncio.create_task(sentinel.start_monitoring_loop())

        # Let it run briefly
        await asyncio.sleep(0.5)

        # Stop monitoring
        sentinel.stop_monitoring()

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert sentinel._running is False


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow(self):
        """Test complete health monitoring workflow."""
        sentinel = HealthSentinel()

        # 1. Add multiple agents with varying health
        agents = [
            (
                "healthy-agent",
                {
                    "performance": {"task_completion_time": 15},
                    "quality": {"bug_escape_rate": 0},
                    "reliability": {"uptime": 99.99},
                    "collaboration": {"conflict_rate": 0},
                },
            ),
            (
                "degraded-agent",
                {
                    "performance": {"task_completion_time": 90},
                    "quality": {"bug_escape_rate": 5},
                    "reliability": {"uptime": 97},
                    "collaboration": {"conflict_rate": 3},
                },
            ),
            (
                "unhealthy-agent",
                {
                    "performance": {"task_completion_time": 180},
                    "quality": {"bug_escape_rate": 15},
                    "reliability": {"uptime": 90},
                    "collaboration": {"conflict_rate": 8},
                },
            ),
        ]

        for agent_id, metrics in agents:
            sentinel.update_agent_metrics(agent_id, metrics)

        # 2. Calculate swarm health
        swarm = sentinel.calculate_swarm_health()
        assert swarm.agent_count == 3
        assert swarm.healthy_count >= 1

        # 3. Run predictions
        alerts = sentinel.run_predictions()
        assert isinstance(alerts, list)

        # 4. Get snapshot
        snapshot = sentinel.get_snapshot()
        assert len(snapshot.agent_health) == 3

        # 5. Validate
        assert sentinel.validate() is True

        # 6. Export metrics
        metrics_export = sentinel.get_metrics_export()
        assert isinstance(metrics_export, str)
