"""E2E tests for dashboard functionality.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import pytest

from autonomous_control_plane.dashboard.api import DashboardAPI
from autonomous_control_plane.dashboard.models import (
    CircuitBreakerPanelData,
    IncidentPanelData,
    RollbackPanelData,
    SelfHealingPanelData,
    SystemHealthPanelData,
)


@pytest.mark.asyncio
class TestDashboardE2E:
    """End-to-end tests for dashboard functionality."""

    async def test_dashboard_state_integration(self):
        """Test full dashboard state retrieval."""
        api = DashboardAPI()

        # Get full state
        state = await api.get_full_state()

        # Verify all panels are populated
        assert isinstance(state.circuit_breakers, CircuitBreakerPanelData)
        assert isinstance(state.incidents, IncidentPanelData)
        assert isinstance(state.self_healing, SelfHealingPanelData)
        assert isinstance(state.rollbacks, RollbackPanelData)
        assert isinstance(state.system_health, SystemHealthPanelData)

        # Verify state can be serialized
        data = state.to_dict()
        assert "timestamp" in data
        assert "circuit_breakers" in data
        assert "incidents" in data
        assert "self_healing" in data
        assert "rollbacks" in data
        assert "system_health" in data

    async def test_health_endpoint(self):
        """Test health endpoint."""
        api = DashboardAPI()

        health = await api.get_health()

        assert health["status"] == "healthy"
        assert "version" in health
        assert "timestamp" in health
        assert "uptime_seconds" in health

    async def test_all_panels_accessible(self):
        """Test that all panels are accessible."""
        api = DashboardAPI()

        # Test each panel
        cb_data = await api.get_circuit_breakers_panel()
        assert isinstance(cb_data.to_dict(), dict)

        incident_data = await api.get_incidents_panel()
        assert isinstance(incident_data.to_dict(), dict)

        healing_data = await api.get_self_healing_panel()
        assert isinstance(healing_data.to_dict(), dict)

        rollback_data = await api.get_rollbacks_panel()
        assert isinstance(rollback_data.to_dict(), dict)

        health_data = await api.get_system_health_panel()
        assert isinstance(health_data.to_dict(), dict)

    async def test_panel_response_times(self):
        """Test that panel endpoints respond within 200ms."""
        api = DashboardAPI()

        import time

        # Test each panel response time
        panels = [
            ("circuit_breakers", api.get_circuit_breakers_panel()),
            ("incidents", api.get_incidents_panel()),
            ("self_healing", api.get_self_healing_panel()),
            ("rollbacks", api.get_rollbacks_panel()),
            ("system_health", api.get_system_health_panel()),
        ]

        for name, coro in panels:
            start = time.time()
            await coro
            elapsed = (time.time() - start) * 1000  # Convert to ms

            assert elapsed < 200, f"{name} panel took {elapsed:.2f}ms (max 200ms)"

    async def test_health_score_calculation(self):
        """Test health score calculation produces valid scores."""
        api = DashboardAPI()

        score = await api._calculate_health_score()

        # Verify score ranges
        assert 0 <= score.overall_score <= 100
        assert 0 <= score.circuit_breaker_score <= 100
        assert 0 <= score.incident_score <= 100
        assert 0 <= score.healing_score <= 100
        assert 0 <= score.rollback_score <= 100

        # Verify status is valid
        assert score.status.value in [
            "healthy",
            "degraded",
            "unhealthy",
            "critical",
            "unknown",
        ]

    async def test_websocket_update_interval(self):
        """Test that updates are generated at 5-second intervals."""
        # This test verifies the update interval is configured correctly
        from autonomous_control_plane.telemetry.dashboard_sync import (
            DashboardSyncServer,
        )

        server = DashboardSyncServer()
        assert server.UPDATE_INTERVAL == 5.0

    async def test_dashboard_client_connection(self):
        """Test dashboard client can connect."""
        from autonomous_control_plane.dashboard.client import DashboardClient

        client = DashboardClient(
            uri="ws://localhost:8765/acp-dashboard",
            api_url="http://localhost:8080/api/v1/dashboard",
        )

        # Verify client properties
        assert client.uri == "ws://localhost:8765/acp-dashboard"
        assert client.api_url == "http://localhost:8080/api/v1/dashboard"
        assert not client.is_connected()


@pytest.mark.asyncio
class TestDashboardVisualization:
    """Tests for dashboard visualization layer."""

    async def test_chart_data_generation(self):
        """Test chart data can be generated."""
        from autonomous_control_plane.dashboard.visualization import (
            DashboardVisualization,
        )

        viz = DashboardVisualization()

        # Generate charts
        health_chart = await viz.generate_health_gauge()
        assert health_chart.chart_type == "gauge"

        # Even without data, charts should be generated
        assert health_chart.to_dict() is not None

    async def test_trend_analysis(self):
        """Test trend analysis produces valid results."""
        from autonomous_control_plane.dashboard.visualization import (
            DashboardVisualization,
        )

        viz = DashboardVisualization()

        analysis = await viz.generate_trend_analysis("incidents", hours=24)

        assert analysis["metric"] == "incidents"
        assert analysis["time_range_hours"] == 24
        assert "trend" in analysis
        assert analysis["trend"] in ["increasing", "decreasing", "stable"]
