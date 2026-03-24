"""Dashboard REST API.

Provides REST API endpoints for dashboard data with aggregated metrics
from telemetry pipeline and real-time status from automation controller.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import (
    CircuitBreakerPanelData,
    DashboardState,
    HealthScore,
    HealthStatus,
    IncidentPanelData,
    RollbackPanelData,
    SelfHealingPanelData,
    SystemHealthPanelData,
    TimeRange,
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
    from autonomous_control_plane.components.self_healing_engine import (
        SelfHealingEngine,
    )

logger = logging.getLogger(__name__)


class DashboardAPI:
    """Dashboard API for serving dashboard data.

    Aggregates data from multiple ACP components and provides
    unified dashboard state with filtering and time range support.

    Example:
        >>> api = DashboardAPI(
        ...     circuit_breaker_registry=cb_registry,
        ...     incident_manager=incident_manager,
        ...     automation_controller=controller,
        ... )
        >>> state = await api.get_full_state()
        >>> incidents = await api.get_incidents_panel(severity="P0")
    """

    def __init__(
        self,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        incident_manager: IncidentManager | None = None,
        self_healing_engine: SelfHealingEngine | None = None,
        rollback_coordinator: RollbackCoordinator | None = None,
        automation_controller: AutomationController | None = None,
    ):
        """Initialize dashboard API.

        Args:
            circuit_breaker_registry: Circuit breaker registry
            incident_manager: Incident manager
            self_healing_engine: Self-healing engine
            rollback_coordinator: Rollback coordinator
            automation_controller: Automation controller
        """
        self._cb_registry = circuit_breaker_registry
        self._incident_manager = incident_manager
        self._healing_engine = self_healing_engine
        self._rollback_coordinator = rollback_coordinator
        self._automation_controller = automation_controller

        self._start_time = datetime.now(UTC)
        self._version = "1.0.0"

    async def get_health(self) -> dict[str, Any]:
        """Get API health status.

        Returns:
            Health status dictionary
        """
        return {
            "status": "healthy",
            "version": self._version,
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime_seconds": (datetime.now(UTC) - self._start_time).total_seconds(),
        }

    async def get_full_state(self) -> DashboardState:
        """Get complete dashboard state.

        Returns:
            DashboardState with all panel data
        """
        state = DashboardState()
        state.circuit_breakers = await self.get_circuit_breakers_panel()
        state.incidents = await self.get_incidents_panel()
        state.self_healing = await self.get_self_healing_panel()
        state.rollbacks = await self.get_rollbacks_panel()
        state.system_health = await self.get_system_health_panel()
        return state

    async def get_circuit_breakers_panel(
        self, group: str | None = None
    ) -> CircuitBreakerPanelData:
        """Get circuit breaker panel data.

        Args:
            group: Filter by group name (optional)

        Returns:
            CircuitBreakerPanelData
        """
        data = CircuitBreakerPanelData()

        if self._cb_registry is None:
            return data

        try:
            # Get all circuit breaker states
            states = self._cb_registry.get_all_states_dict()
            data.total_count = len(states)

            # Count by state
            for name, state in states.items():
                state_value = state.get("state", "unknown")
                if state_value == "open":
                    data.open_count += 1
                elif state_value == "closed":
                    data.closed_count += 1
                elif state_value == "half_open":
                    data.half_open_count += 1

                # Add breaker details
                breaker_data = {
                    "name": name,
                    "state": state_value,
                    "failure_count": state.get("metrics", {}).get("failure_count", 0),
                    "success_count": state.get("metrics", {}).get("success_count", 0),
                    "rejection_count": state.get("metrics", {}).get(
                        "rejection_count", 0
                    ),
                    "last_error": state.get("last_error"),
                    "updated_at": state.get("updated_at"),
                }
                data.breakers.append(breaker_data)

            # Get groups
            if hasattr(self._cb_registry, "list_groups"):
                group_names = self._cb_registry.list_groups()
                for group_name in group_names:
                    if group is None or group == group_name:
                        group_data = {"name": group_name}
                        if hasattr(self._cb_registry, "get_group_metrics"):
                            metrics = self._cb_registry.get_group_metrics(group_name)
                            if metrics:
                                group_data["metrics"] = metrics.to_dict()
                        data.groups.append(group_data)

        except Exception as e:
            logger.error(f"Error getting circuit breaker data: {e}")

        return data

    async def get_incidents_panel(
        self,
        status: str | None = None,
        severity: str | None = None,
        time_range: TimeRange | None = None,
        limit: int = 50,
    ) -> IncidentPanelData:
        """Get incident panel data.

        Args:
            status: Filter by status
            severity: Filter by severity (P0-P3)
            time_range: Time range filter
            limit: Maximum number of incidents

        Returns:
            IncidentPanelData
        """
        data = IncidentPanelData()

        if self._incident_manager is None:
            return data

        try:
            # Get incident metrics
            metrics = await self._incident_manager.get_metrics()
            if metrics:
                data.total_incidents = metrics.total_incidents
                data.by_severity = metrics.by_severity
                data.by_status = metrics.by_status
                data.avg_resolution_time = metrics.avg_resolution_time

            # Count open incidents
            open_incidents = await self._incident_manager.list_incidents(
                status="open", limit=limit
            )
            data.open_incidents = len(open_incidents)

            # Get recent incidents
            incidents = await self._incident_manager.list_incidents(
                status=status,
                severity=severity,
                limit=limit,
            )

            # Filter by time range if provided
            if time_range:
                filtered = []
                for inc in incidents:
                    created = inc.created_at
                    if time_range.start <= created <= time_range.end:
                        filtered.append(inc)
                incidents = filtered

            data.recent_incidents = [inc.to_dict() for inc in incidents[:limit]]

        except Exception as e:
            logger.error(f"Error getting incident data: {e}")

        return data

    async def get_self_healing_panel(self) -> SelfHealingPanelData:
        """Get self-healing panel data.

        Returns:
            SelfHealingPanelData
        """
        data = SelfHealingPanelData()

        try:
            # Get data from automation controller
            if self._automation_controller is not None:
                status = self._automation_controller.get_status()
                stats = status.get("stats", {})

                data.total_attempts = stats.get("total_healing_attempts", 0)
                data.successful = stats.get("successful_healings", 0)
                data.failed = stats.get("workflows_failed", 0) + stats.get(
                    "workflows_escalated", 0
                )
                data.active_workflows = status.get("active_workflows", 0)

                # Calculate success rate
                if data.total_attempts > 0:
                    data.success_rate = (data.successful / data.total_attempts) * 100

            # Get data from healing engine
            if self._healing_engine is not None:
                engine_status = self._healing_engine.get_status()
                data.pending_approval = engine_status.get("pending_approvals", 0)

                # Get recent actions
                recent = engine_status.get("recent_actions", [])
                data.recent_actions = recent[:10]  # Last 10

        except Exception as e:
            logger.error(f"Error getting self-healing data: {e}")

        return data

    async def get_rollbacks_panel(self) -> RollbackPanelData:
        """Get rollback panel data.

        Returns:
            RollbackPanelData
        """
        data = RollbackPanelData()

        if self._rollback_coordinator is None:
            return data

        try:
            # Get rollback history
            if hasattr(self._rollback_coordinator, "get_rollback_history"):
                history = self._rollback_coordinator.get_rollback_history()
                data.total_executions = len(history)

                # Count by status
                for rollback in history:
                    status = rollback.get("status", "unknown")
                    if status == "completed":
                        data.successful += 1
                    elif status == "failed":
                        data.failed += 1
                    elif status == "in_progress":
                        data.in_progress += 1

                # Calculate success rate
                completed = data.successful + data.failed
                if completed > 0:
                    data.success_rate = (data.successful / completed) * 100

                # Recent rollbacks
                data.recent_rollbacks = history[:10]  # Last 10

        except Exception as e:
            logger.error(f"Error getting rollback data: {e}")

        return data

    async def get_system_health_panel(self) -> SystemHealthPanelData:
        """Get system health panel data.

        Returns:
            SystemHealthPanelData
        """
        data = SystemHealthPanelData()
        data.version = self._version
        data.uptime_seconds = (datetime.now(UTC) - self._start_time).total_seconds()

        # Calculate health score
        data.health_score = await self._calculate_health_score()

        # Get active alerts
        data.alerts = await self._get_active_alerts()

        return data

    async def _calculate_health_score(self) -> HealthScore:
        """Calculate overall system health score.

        Returns:
            HealthScore with breakdown
        """
        score = HealthScore()

        # Circuit breaker score (25% weight)
        if self._cb_registry is not None:
            try:
                states = self._cb_registry.get_all_states_dict()
                if states:
                    open_count = sum(
                        1 for s in states.values() if s.get("state") == "open"
                    )
                    score.circuit_breaker_score = max(
                        0, 100 - (open_count * 20)
                    )  # -20 per open CB
            except Exception as e:
                logger.warning(f"Error calculating CB health score: {e}")

        # Incident score (25% weight)
        if self._incident_manager is not None:
            try:
                open_incidents = await self._incident_manager.list_incidents(
                    status="open", limit=100
                )
                p0_count = sum(1 for i in open_incidents if i.severity.value == "P0")
                p1_count = sum(1 for i in open_incidents if i.severity.value == "P1")
                score.incident_score = max(
                    0, 100 - (p0_count * 30) - (p1_count * 10)
                )  # -30 per P0, -10 per P1
            except Exception as e:
                logger.warning(f"Error calculating incident health score: {e}")

        # Self-healing score (25% weight)
        if self._automation_controller is not None:
            try:
                status = self._automation_controller.get_status()
                stats = status.get("stats", {})
                total = stats.get("total_healing_attempts", 0)
                if total > 0:
                    successful = stats.get("successful_healings", 0)
                    score.healing_score = (successful / total) * 100
            except Exception as e:
                logger.warning(f"Error calculating healing health score: {e}")

        # Rollback score (25% weight)
        if self._rollback_coordinator is not None:
            try:
                if hasattr(self._rollback_coordinator, "get_rollback_history"):
                    history = self._rollback_coordinator.get_rollback_history()
                    if history:
                        successful = sum(
                            1 for h in history if h.get("status") == "completed"
                        )
                        score.rollback_score = (successful / len(history)) * 100
            except Exception as e:
                logger.warning(f"Error calculating rollback health score: {e}")

        # Calculate overall score (weighted average)
        score.overall_score = (
            score.circuit_breaker_score * 0.25
            + score.incident_score * 0.25
            + score.healing_score * 0.25
            + score.rollback_score * 0.25
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

    async def _get_active_alerts(self) -> list[dict[str, Any]]:
        """Get list of active alerts.

        Returns:
            List of alert dictionaries
        """
        alerts = []

        # Check circuit breakers
        if self._cb_registry is not None:
            try:
                states = self._cb_registry.get_all_states_dict()
                for name, state in states.items():
                    if state.get("state") == "open":
                        alerts.append(
                            {
                                "type": "circuit_breaker",
                                "severity": "high",
                                "message": f"Circuit breaker '{name}' is OPEN",
                                "source": name,
                                "timestamp": state.get("updated_at"),
                            }
                        )
            except Exception:
                pass

        # Check incidents
        if self._incident_manager is not None:
            try:
                p0_incidents = await self._incident_manager.list_incidents(
                    status="open", limit=10
                )
                for inc in p0_incidents:
                    if inc.severity.value in ("P0", "P1"):
                        alerts.append(
                            {
                                "type": "incident",
                                "severity": "critical"
                                if inc.severity.value == "P0"
                                else "high",
                                "message": f"{inc.severity.value} incident: {inc.title}",
                                "source": inc.source,
                                "timestamp": inc.created_at.isoformat(),
                                "incident_id": inc.incident_id,
                            }
                        )
            except Exception:
                pass

        return alerts

    async def search_incidents(
        self,
        query: str,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search incidents with filtering.

        Args:
            query: Search query string
            status: Filter by status
            severity: Filter by severity
            limit: Maximum results

        Returns:
            List of matching incidents
        """
        if self._incident_manager is None:
            return []

        try:
            incidents = await self._incident_manager.list_incidents(
                status=status,
                severity=severity,
                limit=limit * 2,  # Get more for filtering
            )

            # Simple text search in title and description
            results = []
            query_lower = query.lower()
            for inc in incidents:
                if (
                    query_lower in inc.title.lower()
                    or query_lower in inc.description.lower()
                ):
                    results.append(inc.to_dict())
                    if len(results) >= limit:
                        break

            return results

        except Exception as e:
            logger.error(f"Error searching incidents: {e}")
            return []

    async def acknowledge_incident(
        self, incident_id: str, acknowledged_by: str
    ) -> dict[str, Any] | None:
        """Acknowledge an incident.

        Args:
            incident_id: Incident ID
            acknowledged_by: Person acknowledging

        Returns:
            Updated incident or None if not found
        """
        if self._incident_manager is None:
            return None

        try:
            # Transition to investigating status
            incident = await self._incident_manager.transition_status(
                incident_id, "investigating"
            )
            if incident:
                # Assign to acknowledger
                incident = await self._incident_manager.assign_incident(
                    incident_id, acknowledged_by
                )
                return incident.to_dict() if incident else None
            return None

        except Exception as e:
            logger.error(f"Error acknowledging incident: {e}")
            return None

    async def trigger_rollback(
        self,
        service: str,
        reason: str,
        triggered_by: str,
    ) -> dict[str, Any] | None:
        """Trigger a rollback.

        Args:
            service: Service to rollback
            reason: Rollback reason
            triggered_by: Person triggering rollback

        Returns:
            Rollback result or None if failed
        """
        if self._rollback_coordinator is None:
            return None

        try:
            if hasattr(self._rollback_coordinator, "initiate_rollback"):
                rollback = await self._rollback_coordinator.initiate_rollback(
                    service=service,
                    reason=reason,
                    triggered_by=triggered_by,
                )
                return rollback.to_dict() if hasattr(rollback, "to_dict") else rollback
            return None

        except Exception as e:
            logger.error(f"Error triggering rollback: {e}")
            return None
