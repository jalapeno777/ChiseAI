"""Tests for dashboard components.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_control_plane.dashboard.components.circuit_breaker_panel import (
    CircuitBreakerPanel,
)
from autonomous_control_plane.dashboard.components.incident_panel import IncidentPanel
from autonomous_control_plane.dashboard.components.self_healing_panel import (
    SelfHealingPanel,
)
from autonomous_control_plane.dashboard.components.system_health_panel import (
    SystemHealthPanel,
)


class TestCircuitBreakerPanel:
    """Test CircuitBreakerPanel component."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock circuit breaker registry."""
        registry = MagicMock()
        registry.get_all_states_dict.return_value = {
            "cb1": {
                "state": "closed",
                "metrics": {
                    "failure_count": 0,
                    "success_count": 100,
                    "consecutive_failures": 0,
                    "consecutive_successes": 10,
                },
                "last_error": None,
                "updated_at": datetime.now().isoformat(),
            },
            "cb2": {
                "state": "open",
                "metrics": {
                    "failure_count": 5,
                    "success_count": 10,
                    "consecutive_failures": 5,
                    "consecutive_successes": 0,
                },
                "last_error": "Connection refused",
                "updated_at": datetime.now().isoformat(),
            },
        }
        registry.list_groups.return_value = ["group1", "group2"]
        registry.get_health.return_value = MagicMock(
            is_healthy=True,
            failure_rate=0.0,
        )
        return registry

    @pytest.mark.asyncio
    async def test_get_data(self, mock_registry):
        """Test getting panel data."""
        panel = CircuitBreakerPanel(circuit_breaker_registry=mock_registry)
        data = await panel.get_data()

        assert data.total_count == 2
        assert data.open_count == 1
        assert data.closed_count == 1
        assert len(data.breakers) == 2
        assert len(data.groups) == 2

    @pytest.mark.asyncio
    async def test_force_open(self, mock_registry):
        """Test forcing circuit breaker open."""
        mock_registry.force_open.return_value = True
        panel = CircuitBreakerPanel(circuit_breaker_registry=mock_registry)

        result = await panel.force_open("cb1", "test")
        assert result is True
        mock_registry.force_open.assert_called_once_with("cb1", "test")

    @pytest.mark.asyncio
    async def test_force_close(self, mock_registry):
        """Test forcing circuit breaker closed."""
        mock_registry.force_close.return_value = True
        panel = CircuitBreakerPanel(circuit_breaker_registry=mock_registry)

        result = await panel.force_close("cb1", "test")
        assert result is True

    @pytest.mark.asyncio
    async def test_reset(self, mock_registry):
        """Test resetting circuit breaker."""
        mock_registry.reset.return_value = True
        panel = CircuitBreakerPanel(circuit_breaker_registry=mock_registry)

        result = await panel.reset("cb1")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_health_summary(self, mock_registry):
        """Test getting health summary."""
        panel = CircuitBreakerPanel(circuit_breaker_registry=mock_registry)
        summary = panel.get_health_summary()

        assert summary["total"] == 2
        assert "healthy" in summary
        assert "unhealthy" in summary


class TestIncidentPanel:
    """Test IncidentPanel component."""

    @pytest.fixture
    def mock_manager(self):
        """Create mock incident manager."""
        manager = AsyncMock()

        incident = MagicMock()
        incident.incident_id = "inc-001"
        incident.title = "Test Incident"
        incident.severity.value = "P1"
        incident.status.value = "open"
        incident.source = "test-service"
        incident.created_at = datetime.now()
        incident.resolved_at = None
        incident.to_dict.return_value = {
            "incident_id": "inc-001",
            "title": "Test Incident",
        }

        manager.list_incidents.return_value = [incident]

        metrics = MagicMock()
        metrics.total_incidents = 10
        metrics.by_severity = {"P0": 1, "P1": 2}
        metrics.by_status = {"open": 3, "resolved": 7}
        metrics.avg_resolution_time = 3600.0
        manager.get_metrics.return_value = metrics

        return manager

    @pytest.mark.asyncio
    async def test_get_data(self, mock_manager):
        """Test getting panel data."""
        panel = IncidentPanel(incident_manager=mock_manager)
        data = await panel.get_data()

        assert data.total_incidents == 10
        assert data.open_incidents >= 0
        assert len(data.recent_incidents) >= 0

    @pytest.mark.asyncio
    async def test_search(self, mock_manager):
        """Test incident search."""
        panel = IncidentPanel(incident_manager=mock_manager)
        results = await panel.search("test")

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_acknowledge(self, mock_manager):
        """Test acknowledging incident."""
        incident = MagicMock()
        incident.to_dict.return_value = {"incident_id": "inc-001"}
        mock_manager.transition_status.return_value = incident
        mock_manager.assign_incident.return_value = incident

        panel = IncidentPanel(incident_manager=mock_manager)
        result = await panel.acknowledge("inc-001", "user@example.com")

        assert result is not None


class TestSelfHealingPanel:
    """Test SelfHealingPanel component."""

    @pytest.fixture
    def mock_controller(self):
        """Create mock automation controller."""
        controller = MagicMock()
        controller.get_status.return_value = {
            "stats": {
                "total_healing_attempts": 100,
                "successful_healings": 90,
                "workflows_failed": 5,
                "workflows_escalated": 5,
            },
            "active_workflows": 3,
        }
        controller.get_active_workflows.return_value = [
            {},
            {},
            {},
        ]  # 3 active workflows
        controller.get_all_workflows.return_value = []
        return controller

    @pytest.mark.asyncio
    async def test_get_data(self, mock_controller):
        """Test getting panel data."""
        panel = SelfHealingPanel(automation_controller=mock_controller)
        data = await panel.get_data()

        assert data.total_attempts == 100
        assert data.successful == 90
        assert data.success_rate == 90.0
        assert data.active_workflows == 3

    def test_get_active_workflows(self, mock_controller):
        """Test getting active workflows."""
        panel = SelfHealingPanel(automation_controller=mock_controller)
        workflows = panel.get_active_workflows()

        assert isinstance(workflows, list)

    def test_get_success_rate_by_pattern(self, mock_controller):
        """Test getting success rate by pattern."""
        panel = SelfHealingPanel(automation_controller=mock_controller)
        rates = panel.get_success_rate_by_pattern()

        assert isinstance(rates, dict)


class TestSystemHealthPanel:
    """Test SystemHealthPanel component."""

    @pytest.fixture
    def mock_components(self):
        """Create mock ACP components."""
        cb_registry = MagicMock()
        cb_registry.get_all_states_dict.return_value = {
            "cb1": {"state": "closed"},
            "cb2": {"state": "closed"},
        }

        incident_manager = AsyncMock()
        incident_manager.list_incidents.return_value = []

        controller = MagicMock()
        controller.get_status.return_value = {
            "stats": {"total_healing_attempts": 10, "successful_healings": 9}
        }

        return cb_registry, incident_manager, controller

    @pytest.mark.asyncio
    async def test_get_data(self, mock_components):
        """Test getting panel data."""
        cb_registry, incident_manager, controller = mock_components
        panel = SystemHealthPanel(
            circuit_breaker_registry=cb_registry,
            incident_manager=incident_manager,
            automation_controller=controller,
        )
        data = await panel.get_data()

        assert data.health_score is not None
        assert data.version == "1.0.0"
        assert data.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_calculate_health_score(self, mock_components):
        """Test health score calculation."""
        cb_registry, incident_manager, controller = mock_components
        panel = SystemHealthPanel(
            circuit_breaker_registry=cb_registry,
            incident_manager=incident_manager,
            automation_controller=controller,
        )
        score = await panel.calculate_health_score()

        assert 0 <= score.overall_score <= 100
        assert score.circuit_breaker_score == 100.0

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, mock_components):
        """Test getting active alerts."""
        cb_registry, incident_manager, controller = mock_components
        panel = SystemHealthPanel(
            circuit_breaker_registry=cb_registry,
            incident_manager=incident_manager,
        )
        alerts = await panel.get_active_alerts()

        assert isinstance(alerts, list)

    def test_get_component_status(self, mock_components):
        """Test getting component status."""
        cb_registry, incident_manager, controller = mock_components
        panel = SystemHealthPanel(
            circuit_breaker_registry=cb_registry,
            incident_manager=incident_manager,
            automation_controller=controller,
        )
        status = panel.get_component_status()

        assert "circuit_breaker_registry" in status
        assert "incident_manager" in status
        assert "automation_controller" in status
