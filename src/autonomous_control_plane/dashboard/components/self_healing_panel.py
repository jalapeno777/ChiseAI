"""Self-healing activity panel component.

Provides real-time display of self-healing activity with success/failure
rates and interactive controls.

For ST-CONTROL-003: Control Plane Dashboard
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from autonomous_control_plane.dashboard.models import SelfHealingPanelData

if TYPE_CHECKING:
    from autonomous_control_plane.automation.controller import AutomationController
    from autonomous_control_plane.components.self_healing_engine import (
        SelfHealingEngine,
    )

logger = logging.getLogger(__name__)


class SelfHealingPanel:
    """Self-healing activity panel component.

    Displays self-healing activity with success/failure rates,
    active workflows, and pending approvals.

    Example:
        >>> panel = SelfHealingPanel(
        ...     automation_controller=controller,
        ...     healing_engine=healing_engine,
        ... )
        >>> data = await panel.get_data()
        >>> workflows = panel.get_active_workflows()
    """

    def __init__(
        self,
        automation_controller: AutomationController | None = None,
        healing_engine: SelfHealingEngine | None = None,
    ):
        """Initialize self-healing panel.

        Args:
            automation_controller: Automation controller
            healing_engine: Self-healing engine
        """
        self._controller = automation_controller
        self._healing_engine = healing_engine

    async def get_data(self) -> SelfHealingPanelData:
        """Get self-healing panel data.

        Returns:
            SelfHealingPanelData
        """
        data = SelfHealingPanelData()

        try:
            # Get data from automation controller
            if self._controller is not None:
                status = self._controller.get_status()
                stats = status.get("stats", {})

                data.total_attempts = stats.get("total_healing_attempts", 0)
                data.successful = stats.get("successful_healings", 0)
                data.failed = stats.get("workflows_failed", 0) + stats.get(
                    "workflows_escalated", 0
                )
                data.active_workflows = len(self._controller.get_active_workflows())

                # Calculate success rate
                if data.total_attempts > 0:
                    data.success_rate = (data.successful / data.total_attempts) * 100

                # Get recent workflows
                workflows = self._controller.get_all_workflows(limit=10)
                for wf in workflows:
                    data.recent_actions.append(
                        {
                            "workflow_id": wf.get("workflow_id"),
                            "service": wf.get("service"),
                            "pattern_type": wf.get("pattern_type"),
                            "status": wf.get("status"),
                            "created_at": wf.get("created_at"),
                            "escalation_level": wf.get("escalation_level"),
                        }
                    )

            # Get data from healing engine
            if self._healing_engine is not None:
                engine_status = self._healing_engine.get_status()
                data.pending_approval = engine_status.get("pending_approvals", 0)

                # Get recent actions from engine if not already populated
                if not data.recent_actions:
                    recent = engine_status.get("recent_actions", [])
                    data.recent_actions = recent[:10]

        except Exception as e:
            logger.error(f"Error getting self-healing panel data: {e}")

        return data

    def get_active_workflows(self) -> list[dict[str, Any]]:
        """Get list of active workflows.

        Returns:
            List of active workflow dictionaries
        """
        if self._controller is None:
            return []

        try:
            return self._controller.get_active_workflows()
        except Exception as e:
            logger.error(f"Error getting active workflows: {e}")
            return []

    def get_workflow_details(self, workflow_id: str) -> dict[str, Any] | None:
        """Get details for a specific workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow details or None if not found
        """
        if self._controller is None:
            return None

        try:
            return self._controller.get_workflow_status(workflow_id)
        except Exception as e:
            logger.error(f"Error getting workflow details: {e}")
            return None

    def get_success_rate_by_pattern(self) -> dict[str, dict[str, Any]]:
        """Get success rate breakdown by failure pattern.

        Returns:
            Dictionary mapping pattern types to success metrics
        """
        if self._controller is None:
            return {}

        try:
            workflows = self._controller.get_all_workflows(limit=1000)
            patterns: dict[str, dict[str, Any]] = {}

            for wf in workflows:
                pattern = wf.get("pattern_type", "unknown")
                if pattern not in patterns:
                    patterns[pattern] = {"total": 0, "success": 0, "failed": 0}

                patterns[pattern]["total"] += 1
                status = wf.get("status")
                if status == "completed":
                    patterns[pattern]["success"] += 1
                elif status in ("failed", "timeout", "escalated"):
                    patterns[pattern]["failed"] += 1

            # Calculate success rates
            for pattern, stats in patterns.items():
                if stats["total"] > 0:
                    stats["success_rate"] = (stats["success"] / stats["total"]) * 100
                else:
                    stats["success_rate"] = 0.0

            return patterns

        except Exception as e:
            logger.error(f"Error getting success rate by pattern: {e}")
            return {}
