"""Tests for dashboard models.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import pytest
from datetime import datetime

from autonomous_control_plane.dashboard.models import (
    ChartData,
    CircuitBreakerPanelData,
    DashboardState,
    HealthScore,
    HealthStatus,
    IncidentPanelData,
    RollbackPanelData,
    SelfHealingPanelData,
    SystemHealthPanelData,
)


class TestHealthScore:
    """Test HealthScore model."""

    def test_default_values(self):
        """Test default health score values."""
        score = HealthScore()
        assert score.overall_score == 100.0
        assert score.status == HealthStatus.HEALTHY
        assert score.circuit_breaker_score == 100.0
        assert score.incident_score == 100.0
        assert score.healing_score == 100.0
        assert score.rollback_score == 100.0

    def test_to_dict(self):
        """Test health score serialization."""
        score = HealthScore(
            overall_score=85.5,
            status=HealthStatus.DEGRADED,
            circuit_breaker_score=90.0,
            incident_score=80.0,
            healing_score=85.0,
            rollback_score=87.0,
        )
        data = score.to_dict()

        assert data["overall_score"] == 85.5
        assert data["status"] == "degraded"
        assert data["circuit_breaker_score"] == 90.0
        assert data["incident_score"] == 80.0
        assert data["healing_score"] == 85.0
        assert data["rollback_score"] == 87.0
        assert "last_updated" in data


class TestCircuitBreakerPanelData:
    """Test CircuitBreakerPanelData model."""

    def test_default_values(self):
        """Test default panel data values."""
        data = CircuitBreakerPanelData()
        assert data.total_count == 0
        assert data.open_count == 0
        assert data.closed_count == 0
        assert data.half_open_count == 0
        assert data.breakers == []
        assert data.groups == []

    def test_with_breakers(self):
        """Test panel data with circuit breakers."""
        data = CircuitBreakerPanelData(
            total_count=5,
            open_count=1,
            closed_count=3,
            half_open_count=1,
            breakers=[
                {"name": "cb1", "state": "closed"},
                {"name": "cb2", "state": "open"},
            ],
        )
        result = data.to_dict()

        assert result["total_count"] == 5
        assert result["open_count"] == 1
        assert len(result["breakers"]) == 2


class TestIncidentPanelData:
    """Test IncidentPanelData model."""

    def test_default_values(self):
        """Test default panel data values."""
        data = IncidentPanelData()
        assert data.total_incidents == 0
        assert data.open_incidents == 0
        assert data.by_severity == {}
        assert data.by_status == {}
        assert data.recent_incidents == []
        assert data.avg_resolution_time == 0.0

    def test_with_incidents(self):
        """Test panel data with incidents."""
        data = IncidentPanelData(
            total_incidents=10,
            open_incidents=3,
            by_severity={"P0": 1, "P1": 2, "P2": 3, "P3": 4},
            by_status={"open": 3, "resolved": 7},
            avg_resolution_time=3600.0,
        )
        result = data.to_dict()

        assert result["total_incidents"] == 10
        assert result["open_incidents"] == 3
        assert result["by_severity"]["P0"] == 1
        assert result["avg_resolution_time"] == 3600.0


class TestSelfHealingPanelData:
    """Test SelfHealingPanelData model."""

    def test_default_values(self):
        """Test default panel data values."""
        data = SelfHealingPanelData()
        assert data.total_attempts == 0
        assert data.successful == 0
        assert data.failed == 0
        assert data.pending_approval == 0
        assert data.success_rate == 0.0
        assert data.recent_actions == []
        assert data.active_workflows == 0

    def test_success_rate_calculation(self):
        """Test success rate display."""
        data = SelfHealingPanelData(
            total_attempts=100,
            successful=80,
            failed=20,
        )
        data.success_rate = 80.0
        result = data.to_dict()

        assert result["success_rate"] == 80.0
        assert result["total_attempts"] == 100


class TestRollbackPanelData:
    """Test RollbackPanelData model."""

    def test_default_values(self):
        """Test default panel data values."""
        data = RollbackPanelData()
        assert data.total_executions == 0
        assert data.successful == 0
        assert data.failed == 0
        assert data.in_progress == 0
        assert data.success_rate == 0.0
        assert data.recent_rollbacks == []

    def test_with_rollbacks(self):
        """Test panel data with rollbacks."""
        data = RollbackPanelData(
            total_executions=10,
            successful=8,
            failed=2,
            success_rate=80.0,
        )
        result = data.to_dict()

        assert result["total_executions"] == 10
        assert result["success_rate"] == 80.0


class TestSystemHealthPanelData:
    """Test SystemHealthPanelData model."""

    def test_default_values(self):
        """Test default panel data values."""
        data = SystemHealthPanelData()
        assert data.uptime_seconds == 0.0
        assert data.version == "1.0.0"
        assert data.active_connections == 0
        assert data.alerts == []

    def test_with_health_score(self):
        """Test panel data with health score."""
        health = HealthScore(overall_score=90.0, status=HealthStatus.HEALTHY)
        data = SystemHealthPanelData(
            health_score=health,
            uptime_seconds=3600.0,
            active_connections=5,
        )
        result = data.to_dict()

        assert result["health_score"]["overall_score"] == 90.0
        assert result["uptime_seconds"] == 3600.0
        assert result["active_connections"] == 5


class TestDashboardState:
    """Test DashboardState model."""

    def test_default_values(self):
        """Test default state values."""
        state = DashboardState()
        assert isinstance(state.circuit_breakers, CircuitBreakerPanelData)
        assert isinstance(state.incidents, IncidentPanelData)
        assert isinstance(state.self_healing, SelfHealingPanelData)
        assert isinstance(state.rollbacks, RollbackPanelData)
        assert isinstance(state.system_health, SystemHealthPanelData)

    def test_full_state(self):
        """Test complete dashboard state."""
        state = DashboardState()
        state.circuit_breakers.total_count = 5
        state.incidents.total_incidents = 10
        state.self_healing.total_attempts = 50
        state.rollbacks.total_executions = 5
        state.system_health.uptime_seconds = 7200.0

        result = state.to_dict()

        assert result["circuit_breakers"]["total_count"] == 5
        assert result["incidents"]["total_incidents"] == 10
        assert result["self_healing"]["total_attempts"] == 50
        assert result["rollbacks"]["total_executions"] == 5
        assert result["system_health"]["uptime_seconds"] == 7200.0
        assert "timestamp" in result


class TestChartData:
    """Test ChartData model."""

    def test_default_values(self):
        """Test default chart data values."""
        chart = ChartData()
        assert chart.chart_type == "line"
        assert chart.labels == []
        assert chart.datasets == []
        assert chart.options == {}

    def test_line_chart(self):
        """Test line chart data."""
        chart = ChartData(
            chart_type="line",
            labels=["00:00", "01:00", "02:00"],
            datasets=[
                {"label": "Incidents", "data": [5, 3, 2]},
            ],
            options={"responsive": True},
        )
        result = chart.to_dict()

        assert result["chart_type"] == "line"
        assert len(result["labels"]) == 3
        assert len(result["datasets"]) == 1
