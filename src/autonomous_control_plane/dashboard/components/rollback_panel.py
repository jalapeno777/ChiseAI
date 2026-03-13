"""Rollback history panel component.

Provides rollback history display with status tracking and
interactive controls.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import RollbackPanelData

if TYPE_CHECKING:
    from autonomous_control_plane.components.rollback_coordinator import (
        RollbackCoordinator,
    )

logger = logging.getLogger(__name__)


class RollbackPanel:
    """Rollback history panel component.

    Displays rollback history with status tracking and
    interactive controls for triggering rollbacks.

    Example:
        >>> panel = RollbackPanel(rollback_coordinator=coordinator)
        >>> data = await panel.get_data()
        >>> result = await panel.trigger_rollback("api_service", "hotfix")
    """

    def __init__(
        self,
        rollback_coordinator: RollbackCoordinator | None = None,
    ):
        """Initialize rollback panel.

        Args:
            rollback_coordinator: Rollback coordinator
        """
        self._coordinator = rollback_coordinator

    async def get_data(self, limit: int = 50) -> RollbackPanelData:
        """Get rollback panel data.

        Args:
            limit: Maximum number of rollbacks to return

        Returns:
            RollbackPanelData
        """
        data = RollbackPanelData()

        if self._coordinator is None:
            return data

        try:
            # Get rollback history
            if hasattr(self._coordinator, "get_rollback_history"):
                history = self._coordinator.get_rollback_history()
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
                data.recent_rollbacks = history[:limit]

        except Exception as e:
            logger.error(f"Error getting rollback panel data: {e}")

        return data

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
        if self._coordinator is None:
            return None

        try:
            if hasattr(self._coordinator, "initiate_rollback"):
                rollback = await self._coordinator.initiate_rollback(
                    service=service,
                    reason=reason,
                    triggered_by=triggered_by,
                )
                return rollback.to_dict() if hasattr(rollback, "to_dict") else rollback
            return None

        except Exception as e:
            logger.error(f"Error triggering rollback: {e}")
            return None

    def get_rollback_details(self, rollback_id: str) -> dict[str, Any] | None:
        """Get details for a specific rollback.

        Args:
            rollback_id: Rollback ID

        Returns:
            Rollback details or None if not found
        """
        if self._coordinator is None:
            return None

        try:
            if hasattr(self._coordinator, "get_rollback"):
                rollback = self._coordinator.get_rollback(rollback_id)
                return rollback.to_dict() if hasattr(rollback, "to_dict") else rollback
            return None

        except Exception as e:
            logger.error(f"Error getting rollback details: {e}")
            return None

    def get_in_progress(self) -> list[dict[str, Any]]:
        """Get list of rollbacks in progress.

        Returns:
            List of in-progress rollbacks
        """
        if self._coordinator is None:
            return []

        try:
            if hasattr(self._coordinator, "get_rollback_history"):
                history = self._coordinator.get_rollback_history()
                return [rb for rb in history if rb.get("status") == "in_progress"]
            return []

        except Exception as e:
            logger.error(f"Error getting in-progress rollbacks: {e}")
            return []

    def get_stats_by_service(self) -> dict[str, dict[str, Any]]:
        """Get rollback statistics grouped by service.

        Returns:
            Dictionary mapping service names to stats
        """
        if self._coordinator is None:
            return {}

        try:
            if hasattr(self._coordinator, "get_rollback_history"):
                history = self._coordinator.get_rollback_history()

                stats: dict[str, dict[str, Any]] = {}
                for rollback in history:
                    service = rollback.get("service", "unknown")
                    if service not in stats:
                        stats[service] = {
                            "total": 0,
                            "successful": 0,
                            "failed": 0,
                        }

                    stats[service]["total"] += 1
                    status = rollback.get("status")
                    if status == "completed":
                        stats[service]["successful"] += 1
                    elif status == "failed":
                        stats[service]["failed"] += 1

                # Calculate success rates
                for service, service_stats in stats.items():
                    total = service_stats["total"]
                    successful = service_stats["successful"]
                    service_stats["success_rate"] = (
                        (successful / total * 100) if total > 0 else 0.0
                    )

                return stats

            return {}

        except Exception as e:
            logger.error(f"Error getting stats by service: {e}")
            return {}

    def get_recent_rollbacks(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get rollbacks from the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of recent rollbacks
        """
        if self._coordinator is None:
            return []

        try:
            cutoff = datetime.now(UTC) - timedelta(hours=hours)

            if hasattr(self._coordinator, "get_rollback_history"):
                history = self._coordinator.get_rollback_history()

                recent = []
                for rollback in history:
                    # Parse timestamp if available
                    timestamp_str = rollback.get("created_at") or rollback.get(
                        "timestamp"
                    )
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )
                            if timestamp >= cutoff:
                                recent.append(rollback)
                        except ValueError:
                            # If can't parse, include it anyway
                            recent.append(rollback)
                    else:
                        recent.append(rollback)

                return recent

            return []

        except Exception as e:
            logger.error(f"Error getting recent rollbacks: {e}")
            return []
