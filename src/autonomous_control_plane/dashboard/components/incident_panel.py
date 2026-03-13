"""Incident timeline panel component.

Provides incident timeline display with filtering, search, and
interactive controls for incident management.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import IncidentPanelData

if TYPE_CHECKING:
    from autonomous_control_plane.components.incident_manager import IncidentManager

logger = logging.getLogger(__name__)


class IncidentPanel:
    """Incident timeline panel component.

    Displays incidents with filtering, search, timeline view,
    and interactive controls for incident management.

    Example:
        >>> panel = IncidentPanel(incident_manager=incident_manager)
        >>> data = await panel.get_data(severity="P0", limit=50)
        >>> results = await panel.search("database timeout")
    """

    def __init__(
        self,
        incident_manager: IncidentManager | None = None,
    ):
        """Initialize incident panel.

        Args:
            incident_manager: Incident manager
        """
        self._manager = incident_manager

    async def get_data(
        self,
        status: str | None = None,
        severity: str | None = None,
        source: str | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        limit: int = 50,
    ) -> IncidentPanelData:
        """Get incident panel data.

        Args:
            status: Filter by status
            severity: Filter by severity (P0-P3)
            source: Filter by source component
            time_range: Tuple of (start, end) datetime
            limit: Maximum number of incidents

        Returns:
            IncidentPanelData
        """
        data = IncidentPanelData()

        if self._manager is None:
            return data

        try:
            # Get metrics
            metrics = await self._manager.get_metrics()
            if metrics:
                data.total_incidents = metrics.total_incidents
                data.by_severity = metrics.by_severity
                data.by_status = metrics.by_status
                data.avg_resolution_time = metrics.avg_resolution_time

            # Get open incidents count
            open_incidents = await self._manager.list_incidents(
                status="open", limit=1000
            )
            data.open_incidents = len(open_incidents)

            # Get filtered incidents
            incidents = await self._manager.list_incidents(
                status=status,
                severity=severity,
                source=source,
                limit=limit * 2,  # Get more for time filtering
            )

            # Apply time range filter if provided
            if time_range:
                start, end = time_range
                incidents = [i for i in incidents if start <= i.created_at <= end]

            # Sort by created_at descending and limit
            incidents.sort(key=lambda x: x.created_at, reverse=True)
            incidents = incidents[:limit]

            # Convert to dict
            data.recent_incidents = [inc.to_dict() for inc in incidents]

        except Exception as e:
            logger.error(f"Error getting incident panel data: {e}")

        return data

    async def search(
        self,
        query: str,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search incidents.

        Args:
            query: Search query string
            status: Filter by status
            severity: Filter by severity
            limit: Maximum results

        Returns:
            List of matching incidents as dictionaries
        """
        if self._manager is None:
            return []

        try:
            incidents = await self._manager.list_incidents(
                status=status,
                severity=severity,
                limit=limit * 2,
            )

            # Simple text search
            results = []
            query_lower = query.lower()
            for inc in incidents:
                if (
                    query_lower in inc.title.lower()
                    or query_lower in inc.description.lower()
                    or query_lower in inc.source.lower()
                ):
                    results.append(inc.to_dict())
                    if len(results) >= limit:
                        break

            return results

        except Exception as e:
            logger.error(f"Error searching incidents: {e}")
            return []

    async def acknowledge(
        self, incident_id: str, acknowledged_by: str
    ) -> dict[str, Any] | None:
        """Acknowledge an incident.

        Args:
            incident_id: Incident ID
            acknowledged_by: Person acknowledging

        Returns:
            Updated incident or None if not found
        """
        if self._manager is None:
            return None

        try:
            # Transition to investigating
            incident = await self._manager.transition_status(
                incident_id, "investigating"
            )
            if incident:
                # Assign to acknowledger
                incident = await self._manager.assign_incident(
                    incident_id, acknowledged_by
                )
                return incident.to_dict() if incident else None
            return None

        except Exception as e:
            logger.error(f"Error acknowledging incident: {e}")
            return None

    async def resolve(
        self, incident_id: str, resolution_notes: str, resolved_by: str
    ) -> dict[str, Any] | None:
        """Resolve an incident.

        Args:
            incident_id: Incident ID
            resolution_notes: Resolution notes
            resolved_by: Person resolving

        Returns:
            Updated incident or None if not found
        """
        if self._manager is None:
            return None

        try:
            # First assign if not assigned
            incident = await self._manager.get_incident(incident_id)
            if incident and not incident.assigned_to:
                await self._manager.assign_incident(incident_id, resolved_by)

            # Resolve
            incident = await self._manager.resolve_incident(
                incident_id, resolution_notes
            )
            return incident.to_dict() if incident else None

        except Exception as e:
            logger.error(f"Error resolving incident: {e}")
            return None

    async def get_timeline(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get incident timeline for the specified period.

        Args:
            hours: Number of hours to look back

        Returns:
            List of timeline events
        """
        if self._manager is None:
            return []

        try:
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=hours)

            incidents = await self._manager.list_incidents(limit=1000)

            events = []
            for inc in incidents:
                # Creation event
                if start_time <= inc.created_at <= end_time:
                    events.append(
                        {
                            "timestamp": inc.created_at.isoformat(),
                            "type": "created",
                            "incident_id": inc.incident_id,
                            "title": inc.title,
                            "severity": inc.severity.value,
                            "source": inc.source,
                        }
                    )

                # Resolution event
                if inc.resolved_at and start_time <= inc.resolved_at <= end_time:
                    events.append(
                        {
                            "timestamp": inc.resolved_at.isoformat(),
                            "type": "resolved",
                            "incident_id": inc.incident_id,
                            "title": inc.title,
                            "severity": inc.severity.value,
                            "resolution_notes": inc.resolution_notes,
                        }
                    )

            # Sort by timestamp
            events.sort(key=lambda x: x["timestamp"])
            return events

        except Exception as e:
            logger.error(f"Error getting incident timeline: {e}")
            return []

    def get_severity_counts(self) -> dict[str, int]:
        """Get incident counts by severity.

        Returns:
            Dictionary mapping severity to count
        """
        if self._manager is None:
            return {}

        try:
            import asyncio

            # Run async in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def get_counts():
                metrics = await self._manager.get_metrics()
                return metrics.by_severity if metrics else {}

            return loop.run_until_complete(get_counts())

        except Exception as e:
            logger.error(f"Error getting severity counts: {e}")
            return {}
