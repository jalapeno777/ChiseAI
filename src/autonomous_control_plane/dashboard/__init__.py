"""Control Plane Dashboard - Real-time visibility into ACP.

Provides comprehensive dashboard for monitoring the autonomous control plane
with real-time updates, visualization, and operational controls.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

from autonomous_control_plane.dashboard.api import DashboardAPI
from autonomous_control_plane.dashboard.client import DashboardClient
from autonomous_control_plane.dashboard.models import (
    CircuitBreakerPanelData,
    DashboardState,
    HealthScore,
    IncidentPanelData,
    PanelType,
    RollbackPanelData,
    SelfHealingPanelData,
    SystemHealthPanelData,
)
from autonomous_control_plane.dashboard.server import DashboardServer
from autonomous_control_plane.dashboard.visualization import DashboardVisualization

__all__ = [
    # Core classes
    "DashboardAPI",
    "DashboardClient",
    "DashboardServer",
    "DashboardVisualization",
    # Models
    "DashboardState",
    "PanelType",
    "HealthScore",
    "CircuitBreakerPanelData",
    "IncidentPanelData",
    "SelfHealingPanelData",
    "RollbackPanelData",
    "SystemHealthPanelData",
]

__version__ = "1.0.0"
