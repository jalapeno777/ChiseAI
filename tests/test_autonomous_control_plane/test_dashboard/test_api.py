"""Tests for dashboard API.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_control_plane.dashboard.api import DashboardAPI
from autonomous_control_plane.dashboard.models import (
    DashboardState,
    HealthStatus,
)


@pytest.fixture
def mock_cb_registry():
    """Create mock circuit breaker registry."""
    registry = MagicMock()
    registry.get_all_states_dict.return_value = {
        "cb1": {
            "state": "closed",
            "metrics": {"failure_count": 0, "success_count": 100},
        },
        "cb2": {
            "state": "open",
            "metrics": {"failure_count": 5, "success_count": 10},
        },
    }
    registry.list_groups.return_value = ["group1"]
    return registry


@pytest.fixture
def mock_incident_manager():
    """Create mock incident manager."""
    manager = AsyncMock()

    # Mock incident
    incident = MagicMock()
    incident.incident_id = "inc-001"
    incident.title = "Test Incident"
    incident.severity.value = "P1"
    incident.status.value = "open"
    incident.source = "test"
    incident.created_at = datetime.now()
    incident.resolved_at = None
    incident.to_dict.return_value = {
        "incident_id": "inc-001",
        "title": "Test Incident",
        "severity": "P1",
        "status": "open",
    }

    manager.list_incidents.return_value = [incident]

    # Mock metrics
    metrics = MagicMock()
    metrics.total_incidents = 10
    metrics.by_severity = {"P0": 1, "P1": 2, "P2": 3, "P3": 4}
    metrics.by_status = {"open": 3, "resolved": 7}
    metrics.avg_resolution_time = 3600.0
    metrics.to_dict.return_value = {
        "total_incidents": 10,
        "by_severity": {"P0": 1, "P1": 2},
    }
    manager.get_metrics.return_value = metrics

    return manager


@pytest.fixture
def mock_automation_controller():
    """Create mock automation controller."""
    controller = MagicMock()
    controller.get_status.return_value = {
        "running": True,
        "active_workflows": 2,
        "stats": {
            "total_healing_attempts": 50,
            "successful_healings": 45,
            "workflows_failed": 3,
            "workflows_escalated": 2,
        },
    }
    controller.get_active_workflows.return_value = []
    return controller


class TestDashboardAPI:
    """Test DashboardAPI class."""

    @pytest.mark.asyncio
    async def test_get_health(self):
        """Test health endpoint."""
        api = DashboardAPI()
        health = await api.get_health()

        assert health["status"] == "healthy"
        assert "version" in health
        assert "timestamp" in health
        assert "uptime_seconds" in health

    @pytest.mark.asyncio
    async def test_get_circuit_breakers_panel(self, mock_cb_registry):
        """Test circuit breakers panel."""
        api = DashboardAPI(circuit_breaker_registry=mock_cb_registry)
        data = await api.get_circuit_breakers_panel()

        assert data.total_count == 2
        assert data.open_count == 1
        assert data.closed_count == 1  # cb1 is closed
        assert len(data.breakers) == 2

    @pytest.mark.asyncio
    async def test_get_incidents_panel(self, mock_incident_manager):
        """Test incidents panel."""
        api = DashboardAPI(incident_manager=mock_incident_manager)
        data = await api.get_incidents_panel()

        assert data.total_incidents == 10
        assert data.by_severity["P0"] == 1
        assert len(data.recent_incidents) > 0

    @pytest.mark.asyncio
    async def test_get_self_healing_panel(self, mock_automation_controller):
        """Test self-healing panel."""
        api = DashboardAPI(automation_controller=mock_automation_controller)
        data = await api.get_self_healing_panel()

        assert data.total_attempts == 50
        assert data.successful == 45
        assert data.success_rate == 90.0

    @pytest.mark.asyncio
    async def test_get_system_health_panel(
        self, mock_cb_registry, mock_incident_manager
    ):
        """Test system health panel."""
        api = DashboardAPI(
            circuit_breaker_registry=mock_cb_registry,
            incident_manager=mock_incident_manager,
        )
        data = await api.get_system_health_panel()

        assert data.version == "1.0.0"
        assert data.health_score is not None
        assert "alerts" in data.to_dict()

    @pytest.mark.asyncio
    async def test_health_score_calculation(
        self, mock_cb_registry, mock_incident_manager
    ):
        """Test health score calculation."""
        api = DashboardAPI(
            circuit_breaker_registry=mock_cb_registry,
            incident_manager=mock_incident_manager,
        )
        score = await api._calculate_health_score()

        assert 0 <= score.overall_score <= 100
        assert score.status in [
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
            HealthStatus.CRITICAL,
        ]

    @pytest.mark.asyncio
    async def test_search_incidents(self, mock_incident_manager):
        """Test incident search."""
        api = DashboardAPI(incident_manager=mock_incident_manager)
        results = await api.search_incidents(query="test")

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_full_state(self, mock_cb_registry, mock_incident_manager):
        """Test getting full dashboard state."""
        api = DashboardAPI(
            circuit_breaker_registry=mock_cb_registry,
            incident_manager=mock_incident_manager,
        )
        state = await api.get_full_state()

        assert isinstance(state, DashboardState)
        assert state.circuit_breakers is not None
        assert state.incidents is not None
        assert state.self_healing is not None
        assert state.rollbacks is not None
        assert state.system_health is not None
