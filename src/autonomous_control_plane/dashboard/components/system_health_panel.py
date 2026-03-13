"""System health overview panel component.

Provides system health overview with score calculation and alert display.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import (
    HealthScore,
    HealthStatus,
    SystemHealthPanelData,
)

if TYPE_CHECKING:
    from autonomous_control_plane.automation.controller import AutomationController
    from autonomous_control_plane.components.circuit_breaker_registry import (
        CircuitBreakerRegistry,
    )
    from autonomous_control_plane.components.incident_manager import IncidentManager
    from autonomous_control_plane.components.rollback_coordinator import (
        RollbackCoordinator,
    )

logger = logging.getLogger(__name__)


class SystemHealthPanel:
    """System health overview panel component.

    Displays overall system health with score calculation,
    component breakdown, and active alerts.

    Example:
        >>> panel = SystemHealthPanel(
        ...     circuit_breaker_registry=cb_registry,
        ...     incident_manager=incident_manager,
        ...     automation_controller=controller,
        ... )
        >>> data = await panel.get_data()
        >>> score = await panel.calculate_health_score()
    """

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        incident_manager: IncidentManager | None = None,
        rollback_coordinator: RollbackCoordinator | None = None,
        automation_controller: AutomationController | None = None,
    ):
        """Initialize system health panel.

        Args:
            circuit_breaker_registry: Circuit breaker registry
            incident_manager: Incident manager
            rollback_coordinator: Rollback coordinator
            automation_controller: Automation controller
        """
        self._cb_registry = circuit_breaker_registry
        self._incident_manager = incident_manager
        self._rollback_coordinator = rollback_coordinator
        self._automation_controller = automation_controller
        self._start_time = datetime.now(UTC)
        self._version = "1.0.0"

    async def get_data(self) -> SystemHealthPanelData:
        """Get system health panel data.

        Returns:
            SystemHealthPanelData
        """
        data = SystemHealthPanelData()
        data.version = self._version
        data.uptime_seconds = (datetime.now(UTC) - self._start_time).total_seconds()
        data.last_update = datetime.now(UTC)

        # Calculate health score
        data.health_score = await self.calculate_health_score()

        # Get active alerts
        data.alerts = await self.get_active_alerts()

        return data

    async def calculate_health_score(self) -> HealthScore:
        """Calculate overall system health score.

        Returns:
            HealthScore with component breakdown
        """
        score = HealthScore()
        score.last_updated = datetime.now(UTC)

        # Calculate component scores (each contributes 25%)
        weights = {
            "circuit_breakers": 0.25,
            "incidents": 0.25,
            "healing": 0.25,
            "rollbacks": 0.25,
        }

        # Circuit breaker score
        if self._cb_registry is not None:
            try:
                score.circuit_breaker_score = self._calculate_cb_score()
            except Exception as e:
                logger.warning(f"Error calculating CB score: {e}")

        # Incident score
        if self._incident_manager is not None:
            try:
                score.incident_score = await self._calculate_incident_score()
            except Exception as e:
                logger.warning(f"Error calculating incident score: {e}")

        # Self-healing score
        if self._automation_controller is not None:
            try:
                score.healing_score = self._calculate_healing_score()
            except Exception as e:
                logger.warning(f"Error calculating healing score: {e}")

        # Rollback score
        if self._rollback_coordinator is not None:
            try:
                score.rollback_score = self._calculate_rollback_score()
            except Exception as e:
                logger.warning(f"Error calculating rollback score: {e}")

        # Calculate weighted overall score
        score.overall_score = (
            score.circuit_breaker_score * weights["circuit_breakers"]
            + score.incident_score * weights["incidents"]
            + score.healing_score * weights["healing"]
            + score.rollback_score * weights["rollbacks"]
        )

        # Determine status
        if score.overall_score >= 90:
            score.status = HealthStatus.HEALTHY
        elif score.overall_score >= 70:
            score.status = HealthStatus.DEGRADED
        elif score.overall_score >= 50:
            score.status = HealthStatus.UNHEALTHY
        else:
            score.status = HealthStatus.CRITICAL

        return score

    def _calculate_cb_score(self) -> float:
        """Calculate circuit breaker health score.

        Returns:
            Score from 0-100
        """
        if self._cb_registry is None:
            return 100.0

        states = self._cb_registry.get_all_states_dict()
        if not states:
            return 100.0

        open_count = sum(1 for s in states.values() if s.get("state") == "open")
        half_open_count = sum(
            1 for s in states.values() if s.get("state") == "half_open"
        )

        # -20 points per open, -10 per half-open
        score = 100 - (open_count * 20) - (half_open_count * 10)
        return max(0, score)

    async def _calculate_incident_score(self) -> float:
        """Calculate incident health score.

        Returns:
            Score from 0-100
        """
        if self._incident_manager is None:
            return 100.0

        open_incidents = await self._incident_manager.list_incidents(
            status="open", limit=100
        )

        p0_count = sum(1 for i in open_incidents if i.severity.value == "P0")
        p1_count = sum(1 for i in open_incidents if i.severity.value == "P1")
        p2_count = sum(1 for i in open_incidents if i.severity.value == "P2")

        # -30 per P0, -10 per P1, -5 per P2
        score = 100 - (p0_count * 30) - (p1_count * 10) - (p2_count * 5)
        return max(0, score)

    def _calculate_healing_score(self) -> float:
        """Calculate self-healing health score.

        Returns:
            Score from 0-100
        """
        if self._automation_controller is None:
            return 100.0

        status = self._automation_controller.get_status()
        stats = status.get("stats", {})

        total = stats.get("total_healing_attempts", 0)
        if total == 0:
            return 100.0

        successful = stats.get("successful_healings", 0)
        return (successful / total) * 100

    def _calculate_rollback_score(self) -> float:
        """Calculate rollback health score.

        Returns:
            Score from 0-100
        """
        if self._rollback_coordinator is None:
            return 100.0

        if not hasattr(self._rollback_coordinator, "get_rollback_history"):
            return 100.0

        history = self._rollback_coordinator.get_rollback_history()
        if not history:
            return 100.0

        successful = sum(1 for h in history if h.get("status") == "completed")
        return (successful / len(history)) * 100

    async def get_active_alerts(self) -> list[dict[str, Any]]:
        """Get list of active alerts.

        Returns:
            List of alert dictionaries
        """
        alerts = []

        # Circuit breaker alerts
        if self._cb_registry is not None:
            try:
                states = self._cb_registry.get_all_states_dict()
                for name, state in states.items():
                    state_value = state.get("state")
                    if state_value == "open":
                        alerts.append(
                            {
                                "type": "circuit_breaker",
                                "severity": "high",
                                "message": f"Circuit breaker '{name}' is OPEN",
                                "source": name,
                                "timestamp": state.get("updated_at"),
                            }
                        )
                    elif state_value == "half_open":
                        alerts.append(
                            {
                                "type": "circuit_breaker",
                                "severity": "medium",
                                "message": f"Circuit breaker '{name}' is HALF-OPEN",
                                "source": name,
                                "timestamp": state.get("updated_at"),
                            }
                        )
            except Exception:
                pass

        # Incident alerts
        if self._incident_manager is not None:
            try:
                open_incidents = await self._incident_manager.list_incidents(
                    status="open", limit=20
                )
                for inc in open_incidents:
                    if inc.severity.value == "P0":
                        alerts.append(
                            {
                                "type": "incident",
                                "severity": "critical",
                                "message": f"P0 incident: {inc.title}",
                                "source": inc.source,
                                "timestamp": inc.created_at.isoformat(),
                                "incident_id": inc.incident_id,
                            }
                        )
                    elif inc.severity.value == "P1":
                        alerts.append(
                            {
                                "type": "incident",
                                "severity": "high",
                                "message": f"P1 incident: {inc.title}",
                                "source": inc.source,
                                "timestamp": inc.created_at.isoformat(),
                                "incident_id": inc.incident_id,
                            }
                        )
            except Exception:
                pass

        # Sort by severity (critical, high, medium, low)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 4))

        return alerts

    def get_component_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all ACP components.

        Returns:
            Dictionary mapping component names to status
        """
        components = {}

        # Circuit breaker registry
        if self._cb_registry is not None:
            try:
                states = self._cb_registry.get_all_states_dict()
                open_count = sum(1 for s in states.values() if s.get("state") == "open")
                components["circuit_breaker_registry"] = {
                    "status": "healthy" if open_count == 0 else "degraded",
                    "total_breakers": len(states),
                    "open_breakers": open_count,
                }
            except Exception as e:
                components["circuit_breaker_registry"] = {
                    "status": "unknown",
                    "error": str(e),
                }

        # Incident manager
        if self._incident_manager is not None:
            components["incident_manager"] = {
                "status": "healthy",
            }
        else:
            components["incident_manager"] = {
                "status": "not_configured",
            }

        # Automation controller
        if self._automation_controller is not None:
            try:
                status = self._automation_controller.get_status()
                active = status.get("active_workflows", 0)
                components["automation_controller"] = {
                    "status": "healthy",
                    "active_workflows": active,
                }
            except Exception as e:
                components["automation_controller"] = {
                    "status": "error",
                    "error": str(e),
                }
        else:
            components["automation_controller"] = {
                "status": "not_configured",
            }

        # Rollback coordinator
        if self._rollback_coordinator is not None:
            components["rollback_coordinator"] = {
                "status": "healthy",
            }
        else:
            components["rollback_coordinator"] = {
                "status": "not_configured",
            }

        return components
