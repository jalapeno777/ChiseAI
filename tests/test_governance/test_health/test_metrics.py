"""
Test Health Metrics - Unit tests for metrics exporter (ST-GOV-008).

Story: ST-GOV-008
"""

from datetime import datetime

from src.governance.health.metrics import (
    HealthMetricPoint,
    HealthMetrics,
    get_health_metrics,
)


class TestHealthMetrics:
    """Tests for HealthMetrics class."""

    def test_metrics_initialization(self):
        """Test metrics initializes correctly."""
        metrics = HealthMetrics()
        assert metrics.namespace == "chiseai"
        assert len(metrics._metrics_buffer) == 0

    def test_record_agent_health(self):
        """Test recording agent health metrics."""
        metrics = HealthMetrics()

        metrics.record_agent_health(
            agent_id="agent-1",
            score=85.0,
            dimensions={"performance": 90.0, "quality": 80.0},
        )

        assert len(metrics._metrics_buffer) >= 1

    def test_record_swarm_health(self):
        """Test recording swarm health metrics."""
        metrics = HealthMetrics()

        metrics.record_swarm_health(
            score=75.0,
            agent_count=5,
            healthy_count=3,
        )

        assert metrics._gauges.get(metrics.METRIC_SWARM_HEALTH) == 75.0

    def test_record_alert(self):
        """Test recording alert metrics."""
        metrics = HealthMetrics()

        metrics.record_alert(
            severity="warning",
            alert_type="degradation",
            agent_id="agent-1",
        )

        assert metrics._counters[metrics.METRIC_ALERTS_TOTAL] == 1.0

    def test_record_remediation_success(self):
        """Test recording successful remediation."""
        metrics = HealthMetrics()

        metrics.record_remediation(
            success=True,
            action_type="clear_cache",
            agent_id="agent-1",
            duration_ms=150.0,
        )

        assert metrics._counters[metrics.METRIC_REMEDIATION_TOTAL] == 1.0
        assert metrics._counters[metrics.METRIC_REMEDIATION_SUCCESS] == 1.0

    def test_record_remediation_failure(self):
        """Test recording failed remediation."""
        metrics = HealthMetrics()

        metrics.record_remediation(
            success=False,
            action_type="restart_agent",
            agent_id="agent-1",
        )

        assert metrics._counters[metrics.METRIC_REMEDIATION_TOTAL] == 1.0
        assert metrics._counters[metrics.METRIC_REMEDIATION_SUCCESS] == 0.0

    def test_record_prediction_accuracy(self):
        """Test recording prediction accuracy."""
        metrics = HealthMetrics()

        metrics.record_prediction_accuracy(
            accuracy=82.5,
            prediction_horizon_minutes=15,
        )

        assert metrics._gauges[metrics.METRIC_PREDICTION_ACCURACY] == 82.5

    def test_export_prometheus(self):
        """Test Prometheus format export."""
        metrics = HealthMetrics()

        # Add some metrics
        metrics.record_swarm_health(score=80.0, agent_count=5, healthy_count=4)
        metrics.record_alert(severity="warning", alert_type="degradation")

        export = metrics.export_prometheus()

        assert isinstance(export, str)
        assert "chiseai" in export.lower() or len(export) > 0

    def test_get_metrics_summary(self):
        """Test getting metrics summary."""
        metrics = HealthMetrics()

        metrics.record_agent_health("agent-1", 85.0)
        metrics.record_alert("warning", "test")

        summary = metrics.get_metrics_summary()

        assert "counters" in summary
        assert "gauges" in summary
        assert "buffer_size" in summary

    def test_flush_buffer(self):
        """Test flushing metrics buffer."""
        metrics = HealthMetrics()

        metrics.record_agent_health("agent-1", 85.0)
        assert len(metrics._metrics_buffer) > 0

        buffer = metrics.flush_buffer()
        assert len(buffer) > 0
        assert len(metrics._metrics_buffer) == 0

    def test_clear(self):
        """Test clearing all metrics."""
        metrics = HealthMetrics()

        metrics.record_agent_health("agent-1", 85.0)
        metrics.record_alert("warning", "test")
        metrics.record_swarm_health(80.0, 5, 4)

        metrics.clear()

        assert len(metrics._metrics_buffer) == 0
        assert len(metrics._gauges) == 0
        assert len(metrics._histograms) == 0


class TestHealthMetricPoint:
    """Tests for HealthMetricPoint dataclass."""

    def test_metric_point_creation(self):
        """Test creating a metric point."""
        point = HealthMetricPoint(
            name="test_metric",
            value=42.0,
            timestamp=datetime.utcnow(),
            labels={"agent_id": "agent-1"},
            help_text="Test metric",
        )

        assert point.name == "test_metric"
        assert point.value == 42.0
        assert point.labels == {"agent_id": "agent-1"}

    def test_metric_point_defaults(self):
        """Test metric point default values."""
        point = HealthMetricPoint(
            name="test",
            value=1.0,
            timestamp=datetime.utcnow(),
        )

        assert point.labels == {}
        assert point.help_text == ""


class TestGetHealthMetrics:
    """Tests for get_health_metrics singleton."""

    def test_singleton(self):
        """Test that get_health_metrics returns singleton."""
        metrics1 = get_health_metrics()
        metrics2 = get_health_metrics()

        assert metrics1 is metrics2

    def test_singleton_can_be_cleared(self):
        """Test that singleton can be cleared."""
        metrics = get_health_metrics()
        metrics.record_alert("test", "test")

        metrics.clear()

        assert metrics._counters[metrics.METRIC_ALERTS_TOTAL] == 0.0
